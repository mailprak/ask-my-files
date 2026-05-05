# Day 05 — CompositeResourceDefinitions (XRDs)

## Learning Objectives
- Understand what an XRD defines and why it exists
- Write an XRD with a typed schema using OpenAPI v3
- Define both Composite Resources (XR) and Claims
- Understand the relationship between XRD, XR, and Claim

---

## What Is an XRD?

A CompositeResourceDefinition (XRD) defines a new Kubernetes API type that the platform team creates for developers. It specifies:

1. The **name** of the new resource kind (e.g., `XDatabase`, `XObjectStorage`)
2. The **schema** — what fields developers can set (e.g., `engine`, `size`, `storageGB`)
3. Whether developers access it as a **Claim** (namespace-scoped) or directly as a **Composite Resource** (cluster-scoped)
4. What **connection details** are published back (e.g., `endpoint`, `password`)

```
XRD defines:  "What is a Database?"
Composition defines: "How is a Database built?" (Day 06)
Claim creates:  "Give me a Database" (Day 07)
```

---

## XRD Structure

```yaml
apiVersion: apiextensions.crossplane.io/v1
kind: CompositeResourceDefinition
metadata:
  name: xdatabases.platform.mycompany.com   # must be: <plural>.<group>
spec:
  group: platform.mycompany.com            # your API group

  names:
    kind: XDatabase                        # cluster-scoped composite resource kind
    plural: xdatabases

  claimNames:                              # optional: enable namespace-scoped claims
    kind: Database                         # developers use this kind
    plural: databases

  connectionSecretKeys:                    # which keys to publish in the connection secret
    - endpoint
    - port
    - username
    - password
    - database

  versions:
    - name: v1alpha1
      served: true                         # this version is active
      referenceable: true                  # Compositions reference this version

      schema:
        openAPIV3Schema:                   # JSON Schema for the spec.parameters
          type: object
          properties:
            spec:
              type: object
              properties:
                parameters:
                  type: object
                  required:
                    - engine
                    - size
                  properties:
                    engine:
                      type: string
                      enum: [postgres, mysql]
                      description: "Database engine"
                    size:
                      type: string
                      enum: [small, medium, large]
                      description: "Instance size tier"
                    storageGB:
                      type: integer
                      default: 20
                      minimum: 10
                      maximum: 1000
                      description: "Storage in GB"
                    highAvailability:
                      type: boolean
                      default: false
                      description: "Enable multi-AZ high availability"
                    backupRetentionDays:
                      type: integer
                      default: 7
                      minimum: 1
                      maximum: 35
```

---

## Full XRD — Object Storage

```yaml
# xrd-objectstorage.yaml
apiVersion: apiextensions.crossplane.io/v1
kind: CompositeResourceDefinition
metadata:
  name: xobjectstorages.platform.mycompany.com
spec:
  group: platform.mycompany.com

  names:
    kind: XObjectStorage
    plural: xobjectstorages

  claimNames:
    kind: ObjectStorage
    plural: objectstorages

  connectionSecretKeys:
    - bucket-name
    - region
    - access-key-id
    - secret-access-key

  versions:
    - name: v1alpha1
      served: true
      referenceable: true

      schema:
        openAPIV3Schema:
          type: object
          properties:
            spec:
              type: object
              properties:
                parameters:
                  type: object
                  required:
                    - region
                  properties:
                    region:
                      type: string
                      description: "AWS region for the bucket"
                    versioning:
                      type: boolean
                      default: false
                      description: "Enable object versioning"
                    publicAccess:
                      type: boolean
                      default: false
                      description: "Allow public read access"
                    lifecycleRules:
                      type: array
                      description: "Object lifecycle rules"
                      items:
                        type: object
                        properties:
                          prefix:
                            type: string
                          expirationDays:
                            type: integer
```

---

## Full XRD — Network (VPC)

```yaml
# xrd-network.yaml
apiVersion: apiextensions.crossplane.io/v1
kind: CompositeResourceDefinition
metadata:
  name: xnetworks.platform.mycompany.com
spec:
  group: platform.mycompany.com

  names:
    kind: XNetwork
    plural: xnetworks

  # No claimNames — cluster-scoped only (used by platform team, not developers)

  connectionSecretKeys:
    - vpc-id
    - subnet-ids
    - security-group-id

  versions:
    - name: v1alpha1
      served: true
      referenceable: true

      schema:
        openAPIV3Schema:
          type: object
          properties:
            spec:
              type: object
              properties:
                parameters:
                  type: object
                  required:
                    - region
                    - cidrBlock
                  properties:
                    region:
                      type: string
                    cidrBlock:
                      type: string
                      pattern: '^([0-9]{1,3}\.){3}[0-9]{1,3}/[0-9]{1,2}$'
                    availabilityZones:
                      type: array
                      items:
                        type: string
                      minItems: 2
                    enableNat:
                      type: boolean
                      default: false
```

---

## Apply XRDs

```bash
kubectl apply -f xrd-database.yaml
kubectl apply -f xrd-objectstorage.yaml
kubectl apply -f xrd-network.yaml

# Verify XRDs were registered
kubectl get xrd
# NAME                                      ESTABLISHED   OFFERED   AGE
# xdatabases.platform.mycompany.com         True          True      10s
# xobjectstorages.platform.mycompany.com    True          True      10s
# xnetworks.platform.mycompany.com          True          False     10s   ← no claims

# ESTABLISHED=True: new API type is registered
# OFFERED=True: namespace-scoped Claims are available

# Verify new API types
kubectl api-resources | grep platform.mycompany.com
# databases          platform.mycompany.com/v1alpha1   true    Database       (namespaced claim)
# xdatabases         platform.mycompany.com/v1alpha1   false   XDatabase      (cluster-scoped)
# objectstorages     platform.mycompany.com/v1alpha1   true    ObjectStorage
# xobjectstorages    platform.mycompany.com/v1alpha1   false   XObjectStorage
# xnetworks          platform.mycompany.com/v1alpha1   false   XNetwork
```

---

## XR vs Claim — The Difference

```
XDatabase (XR)          — cluster-scoped, created by Crossplane when a Claim is filed
                           or can be created directly by platform team
Database (Claim)        — namespace-scoped, filed by developers
                           Crossplane creates an XDatabase on behalf of the developer
```

```yaml
# Platform team can create XRs directly (cluster-scoped)
apiVersion: platform.mycompany.com/v1alpha1
kind: XDatabase
metadata:
  name: shared-analytics-db        # cluster-scoped: no namespace
spec:
  parameters:
    engine: postgres
    size: large
    highAvailability: true
  compositionRef:
    name: database-aws-rds          # which Composition to use
```

```yaml
# Developer files a Claim (namespace-scoped)
apiVersion: platform.mycompany.com/v1alpha1
kind: Database
metadata:
  name: taskapp-db
  namespace: team-backend           # developer's namespace
spec:
  parameters:
    engine: postgres
    size: small
  writeConnectionSecretToRef:
    name: taskapp-db-conn           # secret written to developer's namespace!
```

---

## Schema Validation

The XRD schema is enforced at the Kubernetes API level:

```bash
# Try to create with invalid engine
kubectl apply -f - <<EOF
apiVersion: platform.mycompany.com/v1alpha1
kind: Database
metadata:
  name: bad-db
  namespace: team-backend
spec:
  parameters:
    engine: oracle      # not in enum: [postgres, mysql]
    size: small
EOF
# Error: spec.parameters.engine: Unsupported value "oracle": supported values: "postgres", "mysql"

# Try to create without required field
kubectl apply -f - <<EOF
apiVersion: platform.mycompany.com/v1alpha1
kind: Database
metadata:
  name: bad-db
  namespace: team-backend
spec:
  parameters:
    size: small           # missing required: engine
EOF
# Error: spec.parameters.engine: Required value
```

---

## Versioning XRDs

When you need to update the schema without breaking existing resources:

```yaml
spec:
  versions:
    - name: v1alpha1
      served: true
      referenceable: false     # old version: still served but not used by new Compositions
      schema: ...              # old schema

    - name: v1beta1
      served: true
      referenceable: true      # new Compositions reference this version
      schema: ...              # new schema with additional fields
```

---

## Gotchas

1. **XRD name must follow the pattern `<plural>.<group>`** — e.g., `xdatabases.platform.mycompany.com`. Kubernetes rejects other naming patterns.
2. **`referenceable: true` on only one version** — only one version can be `referenceable`. This is the version Compositions use. Mark newer versions as referenceable when you're ready to migrate.
3. **Deleting an XRD deletes all XRs and Claims** — with no warning. Only delete XRDs when all resources built from them are also deleted.
4. **Schema changes are not automatically migrated** — if you add a new required field to the schema, existing XRs/Claims that don't have that field will fail validation on next update. Add new fields as optional with defaults.

---

## Practice

1. Write an XRD for a `Cache` resource (e.g., Redis) with parameters: `size` (small/medium/large), `engine` (redis/memcached), `evictionPolicy`. Apply it and verify `kubectl get xrd` shows `ESTABLISHED: True`.
2. Check that your XRD's schema validation works: try to create an XR with an invalid enum value and observe the rejection.
3. Add `claimNames` to your XRD. Verify that both the cluster-scoped `XCache` and namespace-scoped `Cache` API types are registered with `kubectl api-resources`.
4. Check `OFFERED` column — what does it mean when `OFFERED: False`?

---

## Key Takeaways

- XRDs define the schema for your internal developer platform API. They are the "what can developers request" definition.
- `names.kind` = cluster-scoped Composite Resource. `claimNames.kind` = namespace-scoped Claim for developers.
- Schema validation is enforced by the Kubernetes API server — invalid values are rejected at `kubectl apply` time.
- `connectionSecretKeys` declares which connection detail keys flow from the managed resources up to the Claim's namespace.
