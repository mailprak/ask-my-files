# Day 07 — Claims: Developer Self-Service

## Learning Objectives
- File Claims as a developer to provision infrastructure
- Understand how Claims relate to Composite Resources
- Access connection secrets from within a namespace
- Use RBAC to control who can file which Claims

---

## What Is a Claim?

A Claim is the developer-facing, namespace-scoped API for requesting infrastructure. When a developer creates a Claim:

1. Crossplane creates a cluster-scoped **Composite Resource (XR)** on their behalf
2. The Composition renders **Managed Resources** from the XR
3. The cloud resource is created
4. **Connection details** are written into a Secret in the **developer's namespace**

```
Developer's Namespace:
  Database (Claim)  →  owned by developer

Cluster Level:
  XDatabase (XR)    →  created by Crossplane, owned by the Claim

Cloud:
  RDS Instance      →  created by the provider
  Connection Secret →  written back to developer's namespace
```

---

## Filing a Claim

```yaml
# database-claim.yaml
apiVersion: platform.mycompany.com/v1alpha1
kind: Database                          # the Claim kind (from XRD claimNames)
metadata:
  name: taskapp-db
  namespace: team-backend               # developer's namespace
spec:
  parameters:
    engine: postgres
    size: small
    storageGB: 20
    highAvailability: false

  compositionSelector:
    matchLabels:
      provider: aws                     # select AWS composition

  # Connection secret written here (developer's namespace)
  writeConnectionSecretToRef:
    name: taskapp-db-conn               # Secret name in team-backend namespace
```

```bash
# Developer applies the Claim
kubectl apply -f database-claim.yaml -n team-backend

# Watch the Claim bind to an XR
kubectl get database taskapp-db -n team-backend -w
# NAME         READY   CONNECTION-SECRET   AGE
# taskapp-db   False   taskapp-db-conn     5s
# taskapp-db   True    taskapp-db-conn     8m   ← Ready when RDS is up

# Connection secret is in the developer's namespace
kubectl get secret taskapp-db-conn -n team-backend
# NAME              TYPE     DATA   AGE
# taskapp-db-conn   Opaque   5      8m

# Decode connection details
kubectl get secret taskapp-db-conn -n team-backend \
  -o jsonpath='{.data.endpoint}' | base64 -d
# taskapp-db.xxxxx.us-east-1.rds.amazonaws.com
```

---

## Using the Connection Secret in an App

```yaml
# deployment-with-claim-secret.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
  namespace: team-backend
spec:
  replicas: 2
  selector:
    matchLabels:
      app: api
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
        - name: api
          image: myapi:1.0
          env:
            # All connection details come from the Claim's connection secret
            - name: DB_HOST
              valueFrom:
                secretKeyRef:
                  name: taskapp-db-conn     # same namespace as the Claim
                  key: endpoint
            - name: DB_PORT
              valueFrom:
                secretKeyRef:
                  name: taskapp-db-conn
                  key: port
            - name: DB_USER
              valueFrom:
                secretKeyRef:
                  name: taskapp-db-conn
                  key: username
            - name: DB_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: taskapp-db-conn
                  key: password
            - name: DB_NAME
              valueFrom:
                secretKeyRef:
                  name: taskapp-db-conn
                  key: database
```

---

## Claim → XR Relationship

```bash
# The Claim shows which XR it created
kubectl describe database taskapp-db -n team-backend
# ...
# Spec:
#   Resource Ref:
#     API Version:  platform.mycompany.com/v1alpha1
#     Kind:         XDatabase
#     Name:         team-backend-taskapp-db-xxxxx    ← auto-generated XR name

# View the XR (cluster-scoped)
kubectl get xdatabase
# NAME                               READY   COMPOSITION          AGE
# team-backend-taskapp-db-xxxxx      True    database-aws-rds     8m

# See all managed resources created by the XR
kubectl describe xdatabase team-backend-taskapp-db-xxxxx
# Resource Refs:
#   Kind: Instance       Name: team-backend-taskapp-db-xxxxx-rds
#   Kind: ParameterGroup Name: team-backend-taskapp-db-xxxxx-params
```

---

## Multiple Claims per Team

Each team can file multiple Claims of the same type:

```bash
# team-backend namespace
kubectl apply -f - <<EOF
apiVersion: platform.mycompany.com/v1alpha1
kind: Database
metadata:
  name: api-db
  namespace: team-backend
spec:
  parameters:
    engine: postgres
    size: small
  writeConnectionSecretToRef:
    name: api-db-conn
EOF

kubectl apply -f - <<EOF
apiVersion: platform.mycompany.com/v1alpha1
kind: Database
metadata:
  name: analytics-db
  namespace: team-backend
spec:
  parameters:
    engine: postgres
    size: large
    storageGB: 500
  writeConnectionSecretToRef:
    name: analytics-db-conn
EOF

kubectl get database -n team-backend
# NAME           READY   CONNECTION-SECRET     AGE
# api-db         True    api-db-conn           5m
# analytics-db   True    analytics-db-conn     12m
```

---

## RBAC for Claims

Developers should only be able to file Claims in their own namespace. Cluster admins control which Claim types are available per namespace.

```yaml
# rbac-database-claims.yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: database-claim-creator
  namespace: team-backend
rules:
  - apiGroups: ["platform.mycompany.com"]
    resources: ["databases"]              # the Claim kind (lowercase)
    verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]

  - apiGroups: ["platform.mycompany.com"]
    resources: ["databases/status"]
    verbs: ["get"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: team-backend-db-claims
  namespace: team-backend
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: database-claim-creator
subjects:
  - kind: Group
    name: team-backend-developers
    apiGroup: rbac.authorization.k8s.io
```

```yaml
# Restrict object storage claims to specific namespaces
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: objectstorage-claim-creator
rules:
  - apiGroups: ["platform.mycompany.com"]
    resources: ["objectstorages"]
    verbs: ["get", "list", "watch", "create", "update", "delete"]
---
# Bind only to the team-data namespace
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: team-data-storage-claims
  namespace: team-data
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: objectstorage-claim-creator
subjects:
  - kind: Group
    name: team-data-engineers
    apiGroup: rbac.authorization.k8s.io
```

---

## Claim Deletion and Resource Lifecycle

```bash
# Deleting a Claim deletes the XR, which deletes all MRs
kubectl delete database taskapp-db -n team-backend

# If MRs have deletionPolicy: Orphan, the cloud resource is kept
# If MRs have deletionPolicy: Delete (default), cloud resource is deleted

# Check what happens to the XR
kubectl get xdatabase   # XR is gone after Claim is deleted

# Prevent accidental deletion with a finalizer
kubectl annotate database taskapp-db -n team-backend \
  crossplane.io/paused=true    # pauses reconciliation — claim won't be processed
```

---

## Claim Status and Troubleshooting

```bash
# Claim is not Ready — find out why
kubectl describe database taskapp-db -n team-backend

# Status conditions:
# Type: Ready, Status: False
# Reason: WaitingForManagedResourceReadiness
# Message: Waiting for managed resources to become ready

# Go one level deeper — check the XR
kubectl get xdatabase -o wide

# Go deeper — check the managed resources
kubectl get managed | grep taskapp-db

# Check events on a specific MR
kubectl describe instance team-backend-taskapp-db-xxxxx

# Common issues:
# Synced=False: credential error, API error
# Ready=False: resource is still provisioning (normal for RDS ~8min)
# Ready=False with error: configuration issue (check message)
```

---

## Share a Claim Between Teams (XR Reference)

A team can reference an existing XR instead of creating a new one:

```yaml
# Share an existing XR (platform team created the XR directly)
apiVersion: platform.mycompany.com/v1alpha1
kind: Database
metadata:
  name: shared-analytics-db
  namespace: team-analytics
spec:
  resourceRef:
    apiVersion: platform.mycompany.com/v1alpha1
    kind: XDatabase
    name: shared-analytics-db-xr     # reference existing XR
  writeConnectionSecretToRef:
    name: analytics-db-conn
```

---

## Gotchas

1. **Connection secret namespace must be the Claim's namespace** — `writeConnectionSecretToRef.namespace` is ignored for Claims; the secret always lands in the Claim's namespace. Don't set a different namespace.
2. **Claim name ≠ XR name** — Crossplane generates a unique XR name from the Claim name + namespace. You can't predict it; use `kubectl describe claim` to find it.
3. **Deleting a Claim is permanent** — if the MRs have `deletionPolicy: Delete`, the cloud resource (and its data) is deleted when the Claim is deleted. Always set `Orphan` for databases in Compositions.
4. **RBAC on Claims ≠ RBAC on cloud resources** — granting access to create a Database Claim doesn't mean you can see the underlying XR or MRs (cluster-scoped). Claims are the safe abstraction layer.

---

## Practice

1. Apply the XRD and Composition from Days 05–06. Create a `Database` Claim in a new namespace. Watch the Claim become Ready.
2. Verify the connection secret appears in the Claim's namespace. Access the secret values with `kubectl get secret ... -o jsonpath`.
3. Apply the RBAC Role and RoleBinding to a test user. Verify they can create Claims but not view XRs or MRs.
4. Delete the Claim. Verify the XR and MRs are also deleted (unless `deletionPolicy: Orphan`).

---

## Key Takeaways

- Claims are namespace-scoped — developers file them in their own namespace without cluster-admin rights.
- Crossplane automatically creates the cluster-scoped XR from the Claim, runs the Composition, and writes connection details back to the developer's namespace.
- Use RBAC Roles + RoleBindings to control which teams can create which Claim types in which namespaces.
- Connection secrets land in the Claim's namespace automatically — apps reference them like any other Secret.
