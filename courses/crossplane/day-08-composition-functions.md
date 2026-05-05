# Day 08 — Composition Functions

## Learning Objectives
- Understand why Composition Functions exist (limits of patch-based compositions)
- Use built-in functions: function-patch-and-transform, function-auto-ready
- Write a Go-based Composition Function
- Use function-kcl for logic-heavy compositions

---

## Why Composition Functions?

Patch-based Compositions (Day 06) have limits:
- No conditionals: you can't say "if size=large AND ha=true, add a read replica"
- No loops: you can't create N resources based on a count parameter
- Limited logic: complex transforms require many chained patches

Composition Functions solve this by replacing or augmenting the patch engine with real code.

```
Pipeline mode (Functions):
  XR → Function 1 (patches) → Function 2 (custom logic) → Function N → Managed Resources
```

---

## Function-Based Composition Structure

```yaml
# composition-with-functions.yaml
apiVersion: apiextensions.crossplane.io/v1
kind: Composition
metadata:
  name: database-aws-functions
spec:
  compositeTypeRef:
    apiVersion: platform.mycompany.com/v1alpha1
    kind: XDatabase

  mode: Pipeline              # enable pipeline mode (functions)

  pipeline:
    # Step 1: standard patch-and-transform
    - step: patch-and-transform
      functionRef:
        name: function-patch-and-transform

      input:
        apiVersion: pt.fn.crossplane.io/v1beta1
        kind: Resources
        resources:
          - name: rds-instance
            base:
              apiVersion: rds.aws.upbound.io/v1beta1
              kind: Instance
              spec:
                forProvider:
                  region: us-east-1
                  engine: postgres
            patches:
              - type: FromCompositeFieldPath
                fromFieldPath: spec.parameters.size
                toFieldPath: spec.forProvider.instanceClass
                transforms:
                  - type: map
                    map:
                      small:  db.t3.micro
                      medium: db.m5.large
                      large:  db.r5.xlarge

    # Step 2: auto-mark resources ready when underlying MRs are ready
    - step: auto-ready
      functionRef:
        name: function-auto-ready
```

---

## Install Built-in Functions

```yaml
# function-patch-and-transform.yaml
apiVersion: pkg.crossplane.io/v1beta1
kind: Function
metadata:
  name: function-patch-and-transform
spec:
  package: xpkg.upbound.io/crossplane-contrib/function-patch-and-transform:v0.6.0
---
apiVersion: pkg.crossplane.io/v1beta1
kind: Function
metadata:
  name: function-auto-ready
spec:
  package: xpkg.upbound.io/crossplane-contrib/function-auto-ready:v0.2.0
---
apiVersion: pkg.crossplane.io/v1beta1
kind: Function
metadata:
  name: function-kcl
spec:
  package: xpkg.upbound.io/crossplane-contrib/function-kcl:v0.10.0
```

```bash
kubectl apply -f function-patch-and-transform.yaml
kubectl apply -f function-auto-ready.yaml
kubectl apply -f function-kcl.yaml

kubectl get functions
# NAME                           INSTALLED   HEALTHY
# function-patch-and-transform   True        True
# function-auto-ready            True        True
# function-kcl                   True        True
```

---

## function-kcl — Logic in KCL

KCL (Kubernetes Configuration Language) is a Python-like language for writing composition logic. It's safer than Go for platform engineers who aren't Go developers.

```yaml
# composition-database-kcl.yaml
apiVersion: apiextensions.crossplane.io/v1
kind: Composition
metadata:
  name: database-aws-kcl
spec:
  compositeTypeRef:
    apiVersion: platform.mycompany.com/v1alpha1
    kind: XDatabase

  mode: Pipeline

  pipeline:
    - step: create-resources
      functionRef:
        name: function-kcl

      input:
        apiVersion: krm.kcl.dev/v1alpha1
        kind: KCLRun
        metadata:
          name: database-resources
        spec:
          source: |
            # Access XR parameters
            params = option("params").oxr.spec.parameters
            name   = option("params").oxr.metadata.name

            # Map size to instanceClass
            sizeMap = {
              "small":  "db.t3.micro"
              "medium": "db.m5.large"
              "large":  "db.r5.xlarge"
            }

            sizeStorageMap = {
              "small":  20
              "medium": 100
              "large":  500
            }

            # Conditionally create a read replica only for large HA databases
            createReplica = params.size == "large" and params.highAvailability

            # Build the primary RDS instance
            rdsInstance = {
              apiVersion = "rds.aws.upbound.io/v1beta1"
              kind = "Instance"
              metadata.name = name + "-primary"
              spec.forProvider = {
                region = "us-east-1"
                engine = params.engine
                engineVersion = "15.4"
                instanceClass = sizeMap[params.size]
                allocatedStorage = sizeStorageMap[params.size]
                multiAz = params.highAvailability
                skipFinalSnapshot = True
                publiclyAccessible = False
              }
            }

            # Build read replica only if needed (conditional resource creation!)
            rdsReplica = {
              apiVersion = "rds.aws.upbound.io/v1beta1"
              kind = "Instance"
              metadata.name = name + "-replica"
              spec.forProvider = {
                region = "us-east-1"
                replicateSourceDb = name + "-primary"
                instanceClass = sizeMap[params.size]
                skipFinalSnapshot = True
              }
            } if createReplica else {}

            # Output all resources (filter empty ones)
            items = [rdsInstance] + ([rdsReplica] if createReplica else [])

    - step: auto-ready
      functionRef:
        name: function-auto-ready
```

---

## Go Composition Function

For maximum flexibility, write a function in Go. The function receives the XR and returns desired managed resources.

### Project Structure

```
function-database/
├── fn.go               # main function logic
├── main.go             # gRPC server setup
├── Dockerfile
├── go.mod
└── package/
    └── crossplane.yaml
```

### fn.go

```go
package main

import (
    "context"

    "github.com/crossplane/crossplane-runtime/pkg/errors"
    fnv1beta1 "github.com/crossplane/function-sdk-go/proto/v1beta1"
    "github.com/crossplane/function-sdk-go/request"
    "github.com/crossplane/function-sdk-go/resource"
    "github.com/crossplane/function-sdk-go/response"
)

// RunFunction is the main entry point called by Crossplane
func (f *Function) RunFunction(_ context.Context, req *fnv1beta1.RunFunctionRequest) (*fnv1beta1.RunFunctionResponse, error) {
    rsp := response.To(req, response.DefaultTTL)

    // Get the XR (Composite Resource)
    xr, err := request.GetObservedCompositeResource(req)
    if err != nil {
        response.Fatal(rsp, errors.Wrap(err, "cannot get XR"))
        return rsp, nil
    }

    // Read parameters from XR spec
    size, err := xr.Resource.GetString("spec.parameters.size")
    if err != nil {
        response.Fatal(rsp, errors.Wrap(err, "cannot get size parameter"))
        return rsp, nil
    }

    ha, _ := xr.Resource.GetBool("spec.parameters.highAvailability")
    name := xr.Resource.GetName()

    // Map size to instance class
    instanceClass := map[string]string{
        "small":  "db.t3.micro",
        "medium": "db.m5.large",
        "large":  "db.r5.xlarge",
    }[size]

    // Build desired managed resources
    desired := map[resource.Name]resource.DesiredComposed{}

    // Always create primary instance
    primary := resource.NewDesiredComposed()
    primary.Resource.SetAPIVersion("rds.aws.upbound.io/v1beta1")
    primary.Resource.SetKind("Instance")
    primary.Resource.SetName(name + "-primary")
    primary.Resource.SetString("spec.forProvider.region", "us-east-1")
    primary.Resource.SetString("spec.forProvider.instanceClass", instanceClass)
    primary.Resource.SetBool("spec.forProvider.multiAz", ha)
    desired["primary"] = primary

    // Conditionally add read replica for large HA deployments
    if size == "large" && ha {
        replica := resource.NewDesiredComposed()
        replica.Resource.SetAPIVersion("rds.aws.upbound.io/v1beta1")
        replica.Resource.SetKind("Instance")
        replica.Resource.SetName(name + "-replica")
        replica.Resource.SetString("spec.forProvider.replicateSourceDb", name+"-primary")
        replica.Resource.SetString("spec.forProvider.instanceClass", instanceClass)
        desired["replica"] = replica
    }

    // Write desired resources to response
    if err := response.SetDesiredComposedResources(rsp, desired); err != nil {
        response.Fatal(rsp, errors.Wrap(err, "cannot set desired resources"))
        return rsp, nil
    }

    return rsp, nil
}
```

### Build and Push the Function

```bash
# Build the function OCI image
docker build -t myregistry/function-database:v0.1.0 .
docker push myregistry/function-database:v0.1.0

# Or use crossplane CLI
crossplane xpkg build --package-root=package/ --embed-runtime-image=myregistry/function-database:v0.1.0
crossplane xpkg push --package=function-database-v0.1.0.xpkg myregistry/function-database:v0.1.0
```

```yaml
# Install the custom function
apiVersion: pkg.crossplane.io/v1beta1
kind: Function
metadata:
  name: function-database
spec:
  package: myregistry/function-database:v0.1.0
```

---

## Test with crossplane render

```bash
# xr.yaml — the Composite Resource input
cat > xr.yaml << EOF
apiVersion: platform.mycompany.com/v1alpha1
kind: XDatabase
metadata:
  name: test-db
spec:
  parameters:
    engine: postgres
    size: large
    highAvailability: true
  compositionRef:
    name: database-aws-kcl
EOF

# Preview what the function would produce
crossplane render xr.yaml composition-database-kcl.yaml functions.yaml

# Output shows:
# - Instance/test-db-primary   (always created)
# - Instance/test-db-replica   (created because size=large AND ha=true)
```

---

## Gotchas

1. **Pipeline mode replaces patch mode** — `mode: Pipeline` means all logic must be in functions. You can't mix pipeline and non-pipeline patches in the same Composition.
2. **function-patch-and-transform is not installed by default** — it's a separate package. Install it explicitly before using `mode: Pipeline` with standard patches.
3. **Functions run in order** — each function in the pipeline receives the output of the previous function as input. Order matters.
4. **Go functions need to be built and pushed as OCI images** — unlike Compositions (pure YAML), Go functions require a build pipeline. Use KCL or patch-and-transform if your team doesn't have Go expertise.

---

## Practice

1. Install `function-patch-and-transform` and rewrite a patch-based Composition from Day 06 in pipeline mode. Verify the output matches with `crossplane render`.
2. Install `function-kcl`. Write a KCL function that conditionally creates a second resource only when `size: large`. Test with `crossplane render` using different size values.
3. Use `function-auto-ready` as the final step in a pipeline. Verify the XR becomes Ready automatically when all MRs are Ready.
4. Use `crossplane render` to preview a composition without applying it to the cluster.

---

## Key Takeaways

- Composition Functions replace patch limitations with real programming logic: conditionals, loops, dynamic resource counts.
- `function-patch-and-transform` is the pipeline-mode equivalent of patch-based compositions — start here.
- `function-kcl` is the best choice for platform engineers who want readable logic without writing Go.
- Go functions give maximum flexibility for complex composition logic. Build, push as OCI image, install as a `Function` package.
