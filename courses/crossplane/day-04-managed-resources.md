# Day 04 — Managed Resources

## Learning Objectives
- Write managed resource YAML for S3, RDS, VPC, and GCS
- Understand the `forProvider`, `providerConfigRef`, and `writeConnectionSecretToRef` fields
- Control deletion behaviour with `deletionPolicy`
- Import existing cloud resources into Crossplane management

---

## Managed Resource Structure

Every managed resource follows the same structure:

```yaml
apiVersion: <group>/<version>           # provider-specific API group
kind: <ResourceKind>                    # the cloud resource type
metadata:
  name: <name>                          # Kubernetes object name
  annotations:
    crossplane.io/external-name: <id>   # optional: cloud resource ID override
spec:
  forProvider:                          # cloud-specific configuration
    region: us-east-1
    # ... all provider-specific fields

  providerConfigRef:                    # which ProviderConfig to use
    name: default

  deletionPolicy: Delete                # Delete | Orphan

  writeConnectionSecretToRef:           # where to write connection details
    namespace: crossplane-system
    name: my-resource-conn
```

---

## AWS S3 Bucket

```yaml
# s3-bucket.yaml
apiVersion: s3.aws.upbound.io/v1beta1
kind: Bucket
metadata:
  name: taskapp-assets
  annotations:
    crossplane.io/external-name: taskapp-assets-prod-20240101   # actual bucket name in AWS
spec:
  forProvider:
    region: us-east-1

    # Block all public access
    publicAccessBlockConfiguration:
      blockPublicAcls: true
      blockPublicPolicy: true
      ignorePublicAcls: true
      restrictPublicBuckets: true

    # Enable versioning
    versioningConfiguration:
      status: Enabled

    # Tags
    tags:
      Environment: production
      Team: backend
      ManagedBy: crossplane

  providerConfigRef:
    name: default

  deletionPolicy: Retain               # Retain = keep bucket even if MR is deleted

  writeConnectionSecretToRef:
    namespace: crossplane-system
    name: taskapp-assets-conn
```

```bash
kubectl apply -f s3-bucket.yaml

# Watch the bucket being created in AWS
kubectl get bucket taskapp-assets -w
# NAME               READY   SYNCED   EXTERNAL-NAME                      AGE
# taskapp-assets     False   True     taskapp-assets-prod-20240101        5s
# taskapp-assets     True    True     taskapp-assets-prod-20240101        30s

# Check the connection secret
kubectl get secret taskapp-assets-conn -n crossplane-system -o yaml
```

---

## AWS RDS PostgreSQL Instance

```yaml
# rds-instance.yaml
apiVersion: rds.aws.upbound.io/v1beta1
kind: Instance
metadata:
  name: taskapp-db
spec:
  forProvider:
    region: us-east-1
    engine: postgres
    engineVersion: "15.4"
    instanceClass: db.t3.micro
    allocatedStorage: 20
    dbName: taskapp
    username: taskapp_admin
    skipFinalSnapshot: true              # set false in production
    publiclyAccessible: false
    autoMinorVersionUpgrade: true
    backupRetentionPeriod: 7             # days
    multiAz: false                       # set true for production

    # VPC settings
    dbSubnetGroupName: my-db-subnet-group
    vpcSecurityGroupIds:
      - sg-0123456789abcdef0

    tags:
      Environment: production
      ManagedBy: crossplane

    # Password from a Secret (avoid plaintext in YAML)
    passwordSecretRef:
      namespace: crossplane-system
      name: rds-password
      key: password

  providerConfigRef:
    name: default

  deletionPolicy: Orphan                 # protect database from accidental deletion

  writeConnectionSecretToRef:
    namespace: crossplane-system
    name: taskapp-db-conn               # connection string written here
```

```yaml
# rds-password-secret.yaml
apiVersion: v1
kind: Secret
metadata:
  name: rds-password
  namespace: crossplane-system
type: Opaque
stringData:
  password: "MySecurePassword123!"
```

```bash
kubectl apply -f rds-password-secret.yaml
kubectl apply -f rds-instance.yaml

# RDS takes 5-10 minutes to provision
kubectl get instance taskapp-db -w
# NAME         READY   SYNCED   EXTERNAL-NAME   AGE
# taskapp-db   False   True     taskapp-db       2m
# taskapp-db   True    True     taskapp-db       8m

# Connection secret contains: endpoint, port, username, password, dbname
kubectl get secret taskapp-db-conn -n crossplane-system \
  -o jsonpath='{.data}' | jq 'with_entries(.value |= @base64d)'
```

---

## AWS VPC + Subnet

```yaml
# vpc.yaml
apiVersion: ec2.aws.upbound.io/v1beta1
kind: VPC
metadata:
  name: platform-vpc
spec:
  forProvider:
    region: us-east-1
    cidrBlock: "10.0.0.0/16"
    enableDnsHostnames: true
    enableDnsSupport: true
    tags:
      Name: platform-vpc
      ManagedBy: crossplane
  providerConfigRef:
    name: default
---
# subnet.yaml
apiVersion: ec2.aws.upbound.io/v1beta1
kind: Subnet
metadata:
  name: platform-subnet-a
spec:
  forProvider:
    region: us-east-1
    availabilityZone: us-east-1a
    cidrBlock: "10.0.1.0/24"
    vpcIdRef:                          # reference the VPC by Crossplane resource name
      name: platform-vpc               # Crossplane resolves this to the VPC ID
    mapPublicIpOnLaunch: false
    tags:
      Name: platform-subnet-a
  providerConfigRef:
    name: default
```

---

## GCP Cloud Storage Bucket

```yaml
# gcs-bucket.yaml
apiVersion: storage.gcp.upbound.io/v1beta1
kind: Bucket
metadata:
  name: taskapp-gcs
spec:
  forProvider:
    location: US-EAST1
    storageClass: STANDARD
    uniformBucketLevelAccess: true
    versioning:
      - enabled: true
    labels:
      environment: production
      managed-by: crossplane

  providerConfigRef:
    name: default

  deletionPolicy: Retain

  writeConnectionSecretToRef:
    namespace: crossplane-system
    name: taskapp-gcs-conn
```

---

## GCP Cloud SQL (PostgreSQL)

```yaml
# cloudsql.yaml
apiVersion: sql.gcp.upbound.io/v1beta1
kind: DatabaseInstance
metadata:
  name: taskapp-cloudsql
spec:
  forProvider:
    databaseVersion: POSTGRES_15
    region: us-east1
    deletionProtection: true
    settings:
      - tier: db-f1-micro
        diskSize: 10
        diskType: PD_SSD
        backupConfiguration:
          - enabled: true
            pointInTimeRecoveryEnabled: true
            backupRetentionSettings:
              - retainedBackups: 7

  providerConfigRef:
    name: default

  deletionPolicy: Orphan

  writeConnectionSecretToRef:
    namespace: crossplane-system
    name: taskapp-cloudsql-conn
```

---

## Cross-Resource References

Crossplane MRs reference each other by name instead of IDs:

```yaml
# Instead of: vpcId: "vpc-0123456789abcdef0"
# Use:
vpcIdRef:
  name: platform-vpc          # Crossplane resolves to the actual VPC ID

# Instead of: subnetIds: ["subnet-abc", "subnet-def"]
# Use:
subnetIdRefs:
  - name: platform-subnet-a
  - name: platform-subnet-b

# Instead of: securityGroupId: "sg-xxxx"
# Use:
securityGroupIdRef:
  name: platform-sg
```

Crossplane waits for the referenced resource to be Ready before proceeding — automatic dependency ordering.

---

## deletionPolicy

```yaml
spec:
  deletionPolicy: Delete    # (default) deleting MR deletes cloud resource
  deletionPolicy: Orphan    # deleting MR leaves cloud resource intact
```

```bash
# Override deletion policy at runtime (before deleting)
kubectl patch bucket taskapp-assets \
  --type=merge \
  -p '{"spec":{"deletionPolicy":"Orphan"}}'

kubectl delete bucket taskapp-assets
# Bucket remains in AWS — safe!
```

Use `Orphan` for:
- Databases (never accidentally delete data)
- Production buckets with important objects
- Any resource that takes hours to recreate

---

## Import Existing Cloud Resources

If a resource already exists in the cloud, you can import it into Crossplane management:

```yaml
# import-existing-bucket.yaml
apiVersion: s3.aws.upbound.io/v1beta1
kind: Bucket
metadata:
  name: existing-bucket-import
  annotations:
    crossplane.io/external-name: my-existing-bucket-name   # exact cloud name
spec:
  forProvider:
    region: us-east-1
  providerConfigRef:
    name: default
```

```bash
kubectl apply -f import-existing-bucket.yaml

# Crossplane will discover the existing bucket and manage it
# It will NOT recreate it — just adopt it
kubectl get bucket existing-bucket-import
# READY   SYNCED
# True    True     ← found and adopted existing bucket
```

---

## Connection Secrets

The `writeConnectionSecretToRef` field causes Crossplane to write connection details to a Secret:

```bash
# RDS connection secret contains:
kubectl get secret taskapp-db-conn -n crossplane-system -o yaml
# data:
#   endpoint: <base64 RDS endpoint>
#   password: <base64 password>
#   port: <base64 port>
#   username: <base64 username>
#   attribute.database_name: <base64 db name>

# Reference in an app deployment
env:
  - name: DB_HOST
    valueFrom:
      secretKeyRef:
        name: taskapp-db-conn
        key: endpoint
  - name: DB_PASSWORD
    valueFrom:
      secretKeyRef:
        name: taskapp-db-conn
        key: password
```

---

## Gotchas

1. **`external-name` annotation controls the cloud resource name** — without it, Crossplane uses the Kubernetes object name. Cloud resource names have restrictions (S3: global unique, no uppercase) that Kubernetes names don't enforce.
2. **`deletionPolicy: Delete` is the default** — always set `Orphan` for databases and production storage before you forget. A `kubectl delete` is irreversible.
3. **Cross-resource references wait for Ready** — if a Subnet references a VPC that isn't Ready yet, the Subnet stays unsynced. This is automatic dependency ordering, not an error.
4. **Connection secret is in `crossplane-system` by default** — to use it in your app namespace, copy it or use External Secrets Operator to sync it across namespaces.

---

## Practice

1. Using `provider-nop`, create a `NopResource` that simulates a database. Set `deletionPolicy: Orphan` and verify deleting the MR doesn't break anything (nop has no real resource).
2. If you have AWS credentials: create an S3 bucket with versioning enabled. Verify it appears in the AWS Console.
3. Create two MRs where one references the other using `<field>Ref`. Observe that the dependent resource waits for the first to be Ready.
4. Import an existing cloud resource using `crossplane.io/external-name` annotation. Verify Crossplane shows it as Ready without recreating it.

---

## Key Takeaways

- `forProvider` contains all cloud-specific config. `providerConfigRef` selects the credentials. `writeConnectionSecretToRef` writes the connection string.
- `deletionPolicy: Orphan` protects cloud resources from accidental deletion — always use for databases.
- Cross-resource refs (`vpcIdRef: name: platform-vpc`) create automatic dependency ordering — no manual coordination needed.
- Connection secrets are written to `crossplane-system` by default. Sync to app namespaces using External Secrets Operator.
