# Day 06 — Compositions

## Learning Objectives
- Write a Composition that maps an XR to managed resources
- Use patches to copy values from XR parameters to managed resources
- Apply transforms (map, convert, string, math)
- Use readiness checks and connection detail publishing

---

## What Is a Composition?

A Composition is the "recipe" that tells Crossplane how to build a Composite Resource. It maps XR parameters to one or more Managed Resources using patches.

```
XRD defines:        "A Database has engine, size, storageGB"
Composition defines: "A Database = RDS Instance + Parameter Group + Subnet Group"
                      and how the XR fields map to each MR's fields
```

---

## Composition Structure

```yaml
apiVersion: apiextensions.crossplane.io/v1
kind: Composition
metadata:
  name: database-aws-rds
  labels:
    provider: aws
    engine: postgres
spec:
  # Which XRD this Composition implements
  compositeTypeRef:
    apiVersion: platform.mycompany.com/v1alpha1
    kind: XDatabase

  # The managed resources to create
  resources:
    - name: rds-instance          # logical name (referenced in patches)
      base:                       # the base MR template
        apiVersion: rds.aws.upbound.io/v1beta1
        kind: Instance
        spec:
          forProvider:
            region: us-east-1
            engine: postgres
            engineVersion: "15.4"
            instanceClass: db.t3.micro   # overridden by patch
            allocatedStorage: 20          # overridden by patch
            skipFinalSnapshot: true
            publiclyAccessible: false
          providerConfigRef:
            name: default

      patches: []                 # patches applied to this resource (see below)
```

---

## Patches — Copying XR Fields to MRs

### FromCompositeFieldPath — XR → MR

```yaml
patches:
  # Copy XR spec.parameters.storageGB → MR spec.forProvider.allocatedStorage
  - type: FromCompositeFieldPath
    fromFieldPath: spec.parameters.storageGB
    toFieldPath: spec.forProvider.allocatedStorage

  # Copy XR metadata labels → MR metadata labels
  - type: FromCompositeFieldPath
    fromFieldPath: metadata.labels
    toFieldPath: metadata.labels
```

### ToCompositeFieldPath — MR → XR (write status back)

```yaml
patches:
  # Copy MR status (endpoint) → XR status
  - type: ToCompositeFieldPath
    fromFieldPath: status.atProvider.endpoint
    toFieldPath: status.endpoint
```

### CombineFromComposite — Combine multiple XR fields into one MR field

```yaml
patches:
  - type: CombineFromComposite
    combine:
      variables:
        - fromFieldPath: metadata.name
        - fromFieldPath: spec.parameters.engine
      strategy: string
      string:
        fmt: "%s-%s-db"              # e.g., "taskapp-postgres-db"
    toFieldPath: metadata.annotations["crossplane.io/external-name"]
```

---

## Transforms

Transforms modify values during patching:

### Map Transform — enum → concrete value

```yaml
patches:
  - type: FromCompositeFieldPath
    fromFieldPath: spec.parameters.size
    toFieldPath: spec.forProvider.instanceClass
    transforms:
      - type: map
        map:
          small:  db.t3.micro
          medium: db.t3.medium
          large:  db.r5.large

  - type: FromCompositeFieldPath
    fromFieldPath: spec.parameters.size
    toFieldPath: spec.forProvider.allocatedStorage
    transforms:
      - type: map
        map:
          small:  20
          medium: 100
          large:  500
```

### Convert Transform — type coercion

```yaml
patches:
  - type: FromCompositeFieldPath
    fromFieldPath: spec.parameters.storageGB
    toFieldPath: spec.forProvider.allocatedStorage
    transforms:
      - type: convert
        convert:
          toType: int64              # ensure it's an integer
```

### String Transform — format a string

```yaml
patches:
  - type: FromCompositeFieldPath
    fromFieldPath: metadata.name
    toFieldPath: metadata.annotations["crossplane.io/external-name"]
    transforms:
      - type: string
        string:
          type: Format
          fmt: "prod-%s"             # prefix all resource names

  # Regex extract
  - type: FromCompositeFieldPath
    fromFieldPath: spec.parameters.region
    toFieldPath: spec.forProvider.availabilityZone
    transforms:
      - type: string
        string:
          type: Format
          fmt: "%sa"                 # "us-east-1" → "us-east-1a"
```

### Math Transform

```yaml
patches:
  - type: FromCompositeFieldPath
    fromFieldPath: spec.parameters.storageGB
    toFieldPath: spec.forProvider.maxAllocatedStorage
    transforms:
      - type: math
        math:
          type: Multiply
          x: 2                       # maxStorage = storageGB * 2
```

---

## Complete Composition — Database

```yaml
# composition-database-aws.yaml
apiVersion: apiextensions.crossplane.io/v1
kind: Composition
metadata:
  name: database-aws-rds
  labels:
    provider: aws
    db-type: rds
spec:
  compositeTypeRef:
    apiVersion: platform.mycompany.com/v1alpha1
    kind: XDatabase

  resources:
    # Resource 1: RDS Parameter Group
    - name: parameter-group
      base:
        apiVersion: rds.aws.upbound.io/v1beta1
        kind: ParameterGroup
        spec:
          forProvider:
            region: us-east-1
            family: postgres15
            description: "Managed by Crossplane"
          providerConfigRef:
            name: default
      patches:
        - type: FromCompositeFieldPath
          fromFieldPath: metadata.name
          toFieldPath: metadata.name
          transforms:
            - type: string
              string:
                type: Format
                fmt: "%s-params"

    # Resource 2: RDS Instance
    - name: rds-instance
      base:
        apiVersion: rds.aws.upbound.io/v1beta1
        kind: Instance
        spec:
          forProvider:
            region: us-east-1
            engine: postgres
            engineVersion: "15.4"
            instanceClass: db.t3.micro    # overridden by patch
            allocatedStorage: 20           # overridden by patch
            skipFinalSnapshot: true
            publiclyAccessible: false
            autoMinorVersionUpgrade: true
            backupRetentionPeriod: 7
            multiAz: false                 # overridden by patch
            dbSubnetGroupName: platform-db-subnet-group
            vpcSecurityGroupIds:
              - sg-0123456789abcdef0
            parameterGroupNameRef:
              name: ""                     # patched below
            passwordSecretRef:
              namespace: crossplane-system
              name: ""                     # patched below
              key: password
          providerConfigRef:
            name: default
          deletionPolicy: Orphan
          writeConnectionSecretToRef:
            namespace: crossplane-system
            name: ""                       # patched below
        connectionDetails:
          - type: FromFieldPath
            name: endpoint
            fromFieldPath: status.atProvider.endpoint
          - type: FromFieldPath
            name: port
            fromFieldPath: status.atProvider.port
          - type: FromValue
            name: username
            value: taskapp_admin
          - type: FromConnectionSecretKey
            name: password
            fromConnectionSecretKey: password

      patches:
        # Size → instanceClass
        - type: FromCompositeFieldPath
          fromFieldPath: spec.parameters.size
          toFieldPath: spec.forProvider.instanceClass
          transforms:
            - type: map
              map:
                small:  db.t3.micro
                medium: db.m5.large
                large:  db.r5.xlarge

        # Size → allocatedStorage
        - type: FromCompositeFieldPath
          fromFieldPath: spec.parameters.size
          toFieldPath: spec.forProvider.allocatedStorage
          transforms:
            - type: map
              map:
                small:  20
                medium: 100
                large:  500

        # HA → multiAz
        - type: FromCompositeFieldPath
          fromFieldPath: spec.parameters.highAvailability
          toFieldPath: spec.forProvider.multiAz

        # XR name → connection secret name
        - type: FromCompositeFieldPath
          fromFieldPath: metadata.name
          toFieldPath: spec.writeConnectionSecretToRef.name
          transforms:
            - type: string
              string:
                type: Format
                fmt: "%s-conn"

        # XR name → external resource name
        - type: FromCompositeFieldPath
          fromFieldPath: metadata.name
          toFieldPath: metadata.annotations["crossplane.io/external-name"]

        # XR name → parameter group ref
        - type: FromCompositeFieldPath
          fromFieldPath: metadata.name
          toFieldPath: spec.forProvider.parameterGroupNameRef.name
          transforms:
            - type: string
              string:
                type: Format
                fmt: "%s-params"

        # Copy endpoint back to XR status
        - type: ToCompositeFieldPath
          fromFieldPath: status.atProvider.endpoint
          toFieldPath: status.endpoint

  # Published connection details (flow from MR → XR → Claim Secret)
  writeConnectionSecretsToNamespace: crossplane-system
```

---

## CompositionSelector — Multiple Compositions for One XRD

You can have multiple Compositions for the same XRD (e.g., one for AWS, one for GCP):

```yaml
# Composition for AWS
metadata:
  name: database-aws-rds
  labels:
    provider: aws

# Composition for GCP
metadata:
  name: database-gcp-cloudsql
  labels:
    provider: gcp
```

The XR or Claim selects which Composition to use:

```yaml
# In the Claim or XR
spec:
  compositionSelector:
    matchLabels:
      provider: aws       # selects database-aws-rds
```

Or set a default Composition on the XRD:

```yaml
spec:
  defaultCompositionRef:
    name: database-aws-rds
```

---

## Readiness Checks

Tell Crossplane when a resource is truly ready (beyond just Synced):

```yaml
resources:
  - name: rds-instance
    base: ...
    readinessChecks:
      # Ready when the instance has an endpoint
      - type: MatchString
        fieldPath: status.atProvider.endpoint
        matchString: ""
        # type options: NonEmpty | MatchString | MatchTrue | MatchFalse

      # Ready when status condition is True
      - type: MatchTrue
        fieldPath: status.conditions[0].status
```

---

## Verify a Composition

```bash
kubectl apply -f composition-database-aws.yaml

kubectl get composition
# NAME                    XR-KIND     XR-APIVERSION                        AGE
# database-aws-rds        XDatabase   platform.mycompany.com/v1alpha1      10s

# Preview what the Composition renders for an XR (without applying)
crossplane render xr.yaml composition-database-aws.yaml

# Output: shows all MRs that would be created, with patches applied
```

---

## Gotchas

1. **Patch `fromFieldPath` must exist** — if the source field doesn't exist on the XR, the patch is silently skipped (default) or causes an error. Set `policy: { fromFieldPath: Required }` to make missing fields an error.
2. **`map` transform values must be strings initially** — even if you're mapping to an integer, write the map values as strings. Use a `convert` transform after the `map` transform to convert to the right type.
3. **Connection details are the weakest link** — if a managed resource doesn't publish connection details, they won't flow to the Claim secret. Check each MR's `connectionDetails` block.
4. **Composition doesn't validate MR schemas** — the Composition will render MRs with whatever fields you patch, even invalid ones. The MR controller will reject the invalid spec, but the error is on the MR, not the Composition.

---

## Practice

1. Write a Composition for the `XObjectStorage` XRD from Day 05. Map `versioning` and `region` parameters to an S3 Bucket MR. Apply and verify with `crossplane render`.
2. Add a `map` transform that converts `size: small | medium | large` to storage sizes. Verify the transform works correctly.
3. Add a `ToCompositeFieldPath` patch that copies the MR status (e.g., bucket ARN) back to the XR status.
4. Create two Compositions for the same XRD with different labels. Create an XR with `compositionSelector.matchLabels` and verify the correct Composition is selected.

---

## Key Takeaways

- A Composition maps XR parameters to managed resources via patches. It is the implementation behind the API.
- `FromCompositeFieldPath` copies XR fields to MR fields. `ToCompositeFieldPath` copies MR status back to XR.
- Transforms (`map`, `convert`, `string`, `math`) modify values during patching — use `map` to convert enums to concrete cloud values.
- Multiple Compositions per XRD enable multi-cloud or multi-tier implementations selected by labels.
