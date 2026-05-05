# Day 09 — Packages: Build and Distribute Crossplane Configurations

## Learning Objectives
- Understand the Crossplane package system
- Build a Configuration package with XRDs and Compositions
- Publish and install packages from OCI registries
- Version and manage package dependencies

---

## What Are Packages?

Crossplane has two types of packages:

| Package Type | Contains | Installed As |
|---|---|---|
| `Provider` | CRDs + controller for a cloud (AWS, GCP, etc.) | `providers.pkg.crossplane.io` |
| `Configuration` | XRDs + Compositions + dependencies | `configurations.pkg.crossplane.io` |

A **Configuration package** lets you distribute your entire internal developer platform (all XRDs and Compositions) as a versioned OCI image. Teams install it with one `kubectl apply`.

```
Configuration package = XRDs + Compositions + Functions + crossplane.yaml
                        bundled as an OCI image
                        versioned and pushed to a registry
                        installed in any cluster with one resource
```

---

## Configuration Package Structure

```
my-platform/
├── crossplane.yaml          # package metadata + dependencies
├── apis/
│   ├── database/
│   │   ├── definition.yaml        # XRD for XDatabase / Database
│   │   └── composition-aws.yaml   # Composition for AWS
│   ├── objectstorage/
│   │   ├── definition.yaml
│   │   └── composition-aws.yaml
│   └── network/
│       ├── definition.yaml
│       └── composition-aws.yaml
└── functions/
    └── function-kcl.yaml          # function dependencies
```

---

## crossplane.yaml — Package Metadata

```yaml
# crossplane.yaml
apiVersion: meta.pkg.crossplane.io/v1alpha1
kind: Configuration
metadata:
  name: platform-aws
  annotations:
    meta.crossplane.io/maintainer: platform-team@mycompany.com
    meta.crossplane.io/source: https://github.com/mycompany/platform
    meta.crossplane.io/description: "Internal developer platform for AWS"

spec:
  crossplane:
    version: ">=v1.14.0-0"       # minimum Crossplane version required

  dependsOn:
    # Provider dependencies — installed automatically
    - provider: xpkg.upbound.io/upbound/provider-aws-s3
      version: ">=v1.0.0"

    - provider: xpkg.upbound.io/upbound/provider-aws-rds
      version: ">=v1.0.0"

    - provider: xpkg.upbound.io/upbound/provider-aws-ec2
      version: ">=v1.0.0"

    # Function dependencies
    - function: xpkg.upbound.io/crossplane-contrib/function-patch-and-transform
      version: ">=v0.4.0"

    - function: xpkg.upbound.io/crossplane-contrib/function-kcl
      version: ">=v0.10.0"

    # Other Configuration packages (compose configurations)
    - configuration: xpkg.upbound.io/mycompany/platform-base
      version: ">=v1.0.0"
```

---

## APIs in the Package

```yaml
# apis/database/definition.yaml — same XRD from Day 05
apiVersion: apiextensions.crossplane.io/v1
kind: CompositeResourceDefinition
metadata:
  name: xdatabases.platform.mycompany.com
spec:
  group: platform.mycompany.com
  names:
    kind: XDatabase
    plural: xdatabases
  claimNames:
    kind: Database
    plural: databases
  connectionSecretKeys:
    - endpoint
    - port
    - username
    - password
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
                  required: [engine, size]
                  properties:
                    engine:
                      type: string
                      enum: [postgres, mysql]
                    size:
                      type: string
                      enum: [small, medium, large]
```

```yaml
# apis/database/composition-aws.yaml — Composition from Day 06
apiVersion: apiextensions.crossplane.io/v1
kind: Composition
metadata:
  name: database-aws-rds
  labels:
    provider: aws
spec:
  compositeTypeRef:
    apiVersion: platform.mycompany.com/v1alpha1
    kind: XDatabase
  # ... rest of composition
```

---

## Build the Package

```bash
# Install crossplane CLI
brew install crossplane

# Build the package (OCI image)
crossplane xpkg build \
  --package-root=. \
  --output=platform-aws-v1.0.0.xpkg

# Verify the package
crossplane xpkg lint platform-aws-v1.0.0.xpkg
```

---

## Push to OCI Registry

```bash
# Push to GitHub Container Registry
crossplane xpkg push \
  --package=platform-aws-v1.0.0.xpkg \
  ghcr.io/mycompany/platform-aws:v1.0.0

# Push to Docker Hub
crossplane xpkg push \
  --package=platform-aws-v1.0.0.xpkg \
  mycompany/platform-aws:v1.0.0

# Push to AWS ECR
crossplane xpkg push \
  --package=platform-aws-v1.0.0.xpkg \
  123456789.dkr.ecr.us-east-1.amazonaws.com/platform-aws:v1.0.0
```

---

## Install a Configuration Package

```yaml
# install-platform.yaml
apiVersion: pkg.crossplane.io/v1
kind: Configuration
metadata:
  name: platform-aws
spec:
  package: ghcr.io/mycompany/platform-aws:v1.0.0
  installationPolicy: Automatic      # install immediately
  revisionActivationPolicy: Automatic
```

```bash
kubectl apply -f install-platform.yaml

# Watch installation — providers and functions are installed as dependencies
kubectl get configuration platform-aws -w
# NAME           INSTALLED   HEALTHY   PACKAGE                           AGE
# platform-aws   True        True      ghcr.io/mycompany/platform-aws:v1.0.0  2m

# All dependencies auto-installed
kubectl get providers
# NAME              INSTALLED   HEALTHY
# provider-aws-s3   True        True
# provider-aws-rds  True        True
# provider-aws-ec2  True        True

kubectl get functions
# NAME                           INSTALLED   HEALTHY
# function-patch-and-transform   True        True
# function-kcl                   True        True

# All XRDs auto-registered
kubectl get xrd
# NAME                                      ESTABLISHED   OFFERED
# xdatabases.platform.mycompany.com         True          True
# xobjectstorages.platform.mycompany.com    True          True
# xnetworks.platform.mycompany.com          True          False
```

---

## Upgrade a Configuration

```bash
# Upgrade to new version
kubectl patch configuration platform-aws \
  --type=merge \
  -p '{"spec":{"package":"ghcr.io/mycompany/platform-aws:v1.1.0"}}'

# Watch revision activation
kubectl get configurationrevision -w
# NAME                    HEALTHY   REVISION   STATE     AGE
# platform-aws-v1.0.0     True      1          Inactive  30m
# platform-aws-v1.1.0     True      2          Active    2m

# Rollback
kubectl patch configurationrevision platform-aws-v1.0.0 \
  --type=merge \
  -p '{"spec":{"desiredState":"Active"}}'
```

---

## Private Registry Authentication

```yaml
# For private OCI registries, create a pull secret
apiVersion: v1
kind: Secret
metadata:
  name: ghcr-pull-secret
  namespace: crossplane-system
type: kubernetes.io/dockerconfigjson
data:
  .dockerconfigjson: <base64-encoded-docker-config>
---
apiVersion: pkg.crossplane.io/v1
kind: Configuration
metadata:
  name: platform-aws
spec:
  package: ghcr.io/mycompany/platform-aws:v1.0.0
  packagePullSecrets:
    - name: ghcr-pull-secret      # reference pull secret
```

---

## CI/CD Pipeline for Package Releases

```yaml
# .github/workflows/release.yaml
name: Release Configuration Package

on:
  push:
    tags: ['v*']

jobs:
  release:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Install crossplane CLI
        run: |
          curl -sL https://raw.githubusercontent.com/crossplane/crossplane/master/install.sh | sh
          sudo mv crossplane /usr/local/bin

      - name: Login to GHCR
        run: |
          echo "${{ secrets.GITHUB_TOKEN }}" | \
            docker login ghcr.io -u ${{ github.actor }} --password-stdin

      - name: Build and push package
        run: |
          VERSION=${GITHUB_REF#refs/tags/}
          crossplane xpkg build \
            --package-root=. \
            --output=platform-aws-${VERSION}.xpkg

          crossplane xpkg push \
            --package=platform-aws-${VERSION}.xpkg \
            ghcr.io/mycompany/platform-aws:${VERSION}

          # Also tag as latest
          crossplane xpkg push \
            --package=platform-aws-${VERSION}.xpkg \
            ghcr.io/mycompany/platform-aws:latest

      - name: Validate package
        run: |
          crossplane xpkg lint platform-aws-${VERSION}.xpkg
```

---

## Package Lock

Crossplane maintains a `Lock` resource to track all installed packages and their dependencies:

```bash
# View the lock (dependency graph)
kubectl get lock lock -o yaml

# Shows all installed packages and their resolved versions
# Lock prevents conflicting provider versions
```

---

## Gotchas

1. **`crossplane.yaml` must be at the package root** — the CLI looks for `crossplane.yaml` in the directory specified by `--package-root`. If it's missing, the build fails.
2. **Dependencies are not pinned by default** — `version: ">=v1.0.0"` installs the latest matching version. Pin to specific versions (`version: "=v1.0.0"`) for reproducibility in production.
3. **Package revisions accumulate** — each install creates a new `ConfigurationRevision`. Old inactive revisions are kept for rollback but consume etcd space. Clean up old revisions periodically.
4. **CRD conflicts between packages** — if two Configurations install the same XRD (e.g., both define `xdatabases`), the second install fails. Use a base Configuration for shared XRDs.

---

## Practice

1. Create the `crossplane.yaml` file with a dependency on `provider-nop`. Run `crossplane xpkg build` and verify the output `.xpkg` file is created.
2. Push the package to a local OCI registry (`docker run -d -p 5000:5000 registry:2`) and install it in your k3d cluster.
3. Upgrade the package to a new version (change the tag in `crossplane.yaml` and rebuild). Watch the revision transition from Inactive → Active.
4. Install a public Configuration package from Upbound's marketplace: `xpkg.upbound.io/upbound/platform-ref-aws`. Explore what XRDs it provides.

---

## Key Takeaways

- Configuration packages bundle XRDs, Compositions, and function/provider dependencies into versioned OCI images.
- `crossplane xpkg build` creates the package. `crossplane xpkg push` publishes it. `Configuration` installs it.
- Dependencies (providers, functions, other configurations) are automatically installed when a Configuration is installed.
- Use CI/CD to build and push new package versions on Git tags — gives you versioned, auditable platform releases.
