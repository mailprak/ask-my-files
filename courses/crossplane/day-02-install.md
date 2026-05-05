# Day 02 — Install Crossplane on k3d

## Learning Objectives
- Install Crossplane using Helm on k3d
- Use the `crossplane` CLI
- Install and configure `provider-nop` for local practice
- Understand the Crossplane resource model in the cluster

---

## Prerequisites

```bash
# k3d cluster
k3d cluster create crossplane-lab \
  --agents 2 \
  --port "80:80@loadbalancer"

kubectl get nodes
# NAME                           STATUS   ROLES
# k3d-crossplane-lab-server-0    Ready    control-plane,master
# k3d-crossplane-lab-agent-0     Ready    <none>
# k3d-crossplane-lab-agent-1     Ready    <none>
```

---

## Install Crossplane via Helm

```bash
# Add the Crossplane Helm repo
helm repo add crossplane-stable https://charts.crossplane.io/stable
helm repo update

# Install Crossplane into its own namespace
helm install crossplane crossplane-stable/crossplane \
  --namespace crossplane-system \
  --create-namespace \
  --set args='{"--debug"}' \
  --wait

# Verify installation
kubectl get pods -n crossplane-system
# NAME                                        READY   STATUS    RESTARTS
# crossplane-xxxx                             1/1     Running   0
# crossplane-rbac-manager-xxxx               1/1     Running   0

# List CRDs installed by Crossplane
kubectl get crds | grep crossplane
# compositeresourcedefinitions.apiextensions.crossplane.io
# compositions.apiextensions.crossplane.io
# configurationrevisions.pkg.crossplane.io
# configurations.pkg.crossplane.io
# controllerconfigs.pkg.crossplane.io
# locks.pkg.crossplane.io
# providerrevisions.pkg.crossplane.io
# providers.pkg.crossplane.io
```

---

## Install the crossplane CLI

```bash
# macOS
brew install crossplane

# Linux
curl -sL "https://raw.githubusercontent.com/crossplane/crossplane/master/install.sh" | sh
sudo mv crossplane /usr/local/bin

# Verify
crossplane version
# Client Version: v1.15.x
```

---

## Install provider-nop (Local Practice)

`provider-nop` is a no-operation provider — it accepts any managed resource YAML and pretends to reconcile it without calling any real cloud API. Perfect for learning Crossplane locally without cloud credentials.

```yaml
# provider-nop.yaml
apiVersion: pkg.crossplane.io/v1
kind: Provider
metadata:
  name: provider-nop
spec:
  package: xpkg.upbound.io/crossplane-contrib/provider-nop:v0.2.0
  installationPolicy: Automatic
  revisionActivationPolicy: Automatic
```

```bash
kubectl apply -f provider-nop.yaml

# Watch provider install (downloads and runs the provider pod)
kubectl get provider provider-nop -w
# NAME           INSTALLED   HEALTHY   PACKAGE                              AGE
# provider-nop   True        True      crossplane-contrib/provider-nop:... 30s

# See CRDs the provider registered
kubectl get crds | grep nop
# nopresources.nop.crossplane.io
```

---

## Provider Config for nop

```yaml
# providerconfig-nop.yaml
apiVersion: nop.crossplane.io/v1alpha1
kind: NopProviderConfig
metadata:
  name: default
spec:
  dummy: "unused"    # nop provider needs no credentials
```

```bash
kubectl apply -f providerconfig-nop.yaml
```

---

## Your First Managed Resource (nop)

```yaml
# nopresource.yaml
apiVersion: nop.crossplane.io/v1alpha1
kind: NopResource
metadata:
  name: my-first-resource
spec:
  forProvider:
    conditionAfter:
      - conditionType: Ready
        conditionStatus: "True"
        time: 5s              # becomes Ready after 5 seconds (simulated)
  providerConfigRef:
    name: default
```

```bash
kubectl apply -f nopresource.yaml

# Watch it become Ready
kubectl get nopresource my-first-resource -w
# NAME                READY   SYNCED   AGE
# my-first-resource   False   True     2s
# my-first-resource   True    True     7s   ← Ready after 5s

# Describe to see Crossplane conditions
kubectl describe nopresource my-first-resource
# Status:
#   Conditions:
#     Type:    Ready
#     Status:  True
#     Reason:  Available
#     Type:    Synced
#     Status:  True
#     Reason:  ReconcileSuccess
```

---

## Crossplane Resource Conditions

Every Crossplane managed resource has two key conditions:

| Condition | Meaning |
|---|---|
| `Synced: True` | Crossplane successfully called the cloud API |
| `Synced: False` | Error calling the cloud API (check message) |
| `Ready: True` | Cloud resource is fully provisioned and available |
| `Ready: False` | Cloud resource is provisioning or in error state |

---

## Explore the Crossplane Control Plane

```bash
# List all provider installations
kubectl get providers
# NAME           INSTALLED   HEALTHY   PACKAGE
# provider-nop   True        True      ...

# List all provider revisions (versions)
kubectl get providerrevision
# NAME                    HEALTHY   REVISION   IMAGE                           STATE    AGE
# provider-nop-xxxx       True      1          crossplane-contrib/provider-nop Active   5m

# List all managed resources across all providers
kubectl get managed
# No resources found   ← empty until you create MRs

# After creating nopresource:
kubectl get managed
# NAME                                            READY   SYNCED   AGE
# nopresource.nop.crossplane.io/my-first-resource True    True     1m

# Get all Crossplane CRDs grouped by provider
kubectl api-resources | grep nop
# nopresources   nop.crossplane.io/v1alpha1   false   NopResource
```

---

## Crossplane Namespace Layout

```bash
kubectl get all -n crossplane-system
# The Crossplane controller pods live here

kubectl get providers          # cluster-scoped
kubectl get managed            # cluster-scoped (all managed resources)
kubectl get composite          # cluster-scoped (all XRs)
kubectl get claim --all-namespaces  # namespace-scoped
```

Managed Resources and Providers are cluster-scoped — they exist outside any namespace.
Claims are namespace-scoped — one per team/project namespace.

---

## crossplane CLI Commands

```bash
# Install a provider
crossplane xpkg install provider xpkg.upbound.io/crossplane-contrib/provider-nop:v0.2.0

# Build a configuration package
crossplane xpkg build

# Push a package to a registry
crossplane xpkg push

# Render a composition (preview output without applying)
crossplane render xr.yaml composition.yaml functions.yaml

# Validate compositions and XRDs
crossplane validate --help

# Beta: convert Terraform to Crossplane
crossplane beta convert terraform main.tf
```

---

## Install provider-aws (Real Cloud — Optional)

For the remaining days, we will show AWS examples. You can follow along with `provider-nop` locally, or connect to a real AWS account:

```yaml
# provider-aws.yaml
apiVersion: pkg.crossplane.io/v1
kind: Provider
metadata:
  name: provider-aws-s3
spec:
  package: xpkg.upbound.io/upbound/provider-aws-s3:v1.1.0
  installationPolicy: Automatic
```

```bash
kubectl apply -f provider-aws.yaml

# Wait for provider to be healthy
kubectl get provider provider-aws-s3 -w
```

```yaml
# aws-credentials-secret.yaml
apiVersion: v1
kind: Secret
metadata:
  name: aws-credentials
  namespace: crossplane-system
type: Opaque
stringData:
  credentials: |
    [default]
    aws_access_key_id = AKIAIOSFODNN7EXAMPLE
    aws_secret_access_key = wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
```

```yaml
# providerconfig-aws.yaml
apiVersion: aws.upbound.io/v1beta1
kind: ProviderConfig
metadata:
  name: default
spec:
  credentials:
    source: Secret
    secretRef:
      namespace: crossplane-system
      name: aws-credentials
      key: credentials
```

---

## Gotchas

1. **Provider installation downloads an OCI image** — `provider-nop` is ~50MB. On slow networks, allow 2–3 minutes for `INSTALLED: True`.
2. **`kubectl get managed` shows nothing until providers are installed** — the `managed` category is only registered after at least one provider is active.
3. **Crossplane pods need cluster-admin** — Crossplane's RBAC manager grants itself broad permissions to manage CRDs and cluster-scoped resources. This is expected.
4. **`provider-nop` is not for production** — it simulates resource creation without doing anything. Never use it in a real environment as it will claim resources are Ready when nothing was actually created.

---

## Practice

1. Create a k3d cluster and install Crossplane via Helm. Verify both pods in `crossplane-system` are Running.
2. Install `provider-nop`. Watch the provider pod start and the CRDs register.
3. Create a `NopResource` with a 10-second Ready delay. Watch it transition from `Ready: False` to `Ready: True`.
4. Run `kubectl get managed` and `kubectl get providers`. Understand the difference between cluster-scoped and namespace-scoped resources.

---

## Key Takeaways

- Crossplane installs into `crossplane-system`. Providers run as pods in the same namespace.
- Every managed resource has `Synced` (API call succeeded) and `Ready` (resource is available) conditions.
- `provider-nop` lets you practice Crossplane locally without cloud credentials — use it for Days 3–6.
- The `crossplane` CLI adds `render`, `validate`, and `xpkg` commands for building and testing compositions.
