# Day 03 — Providers & ProviderConfig

## Learning Objectives
- Understand how Providers work and how they are installed
- Configure ProviderConfig for AWS, GCP, and Azure
- Use IRSA / Workload Identity for credential-free auth
- Manage provider upgrades and multiple provider configs

---

## What Is a Provider?

A Provider is a Kubernetes controller packaged as an OCI image. It:
1. Registers CRDs for cloud resources (one CRD per resource type)
2. Watches those CRDs for changes
3. Calls the cloud API to reconcile desired vs actual state
4. Writes status (Ready, Synced, connection details) back to the resource

```bash
# Upbound maintains official providers (recommended)
# provider-aws    → 900+ AWS resource CRDs
# provider-gcp    → 600+ GCP resource CRDs
# provider-azure  → 700+ Azure resource CRDs

# Community providers
# provider-kubernetes → manage Kubernetes resources
# provider-helm       → manage Helm releases
# provider-github     → manage GitHub repos, teams, secrets

# List all installed providers
kubectl get providers
```

---

## Provider Families

Large providers are split into families of sub-providers to reduce memory footprint:

```yaml
# Install only the S3 sub-provider (not all 900+ AWS resources)
apiVersion: pkg.crossplane.io/v1
kind: Provider
metadata:
  name: provider-aws-s3
spec:
  package: xpkg.upbound.io/upbound/provider-aws-s3:v1.1.0
---
# Install the RDS sub-provider separately
apiVersion: pkg.crossplane.io/v1
kind: Provider
metadata:
  name: provider-aws-rds
spec:
  package: xpkg.upbound.io/upbound/provider-aws-rds:v1.1.0
---
# Install the family provider — installs all sub-providers at once
apiVersion: pkg.crossplane.io/v1
kind: Provider
metadata:
  name: upbound-provider-family-aws
spec:
  package: xpkg.upbound.io/upbound/provider-family-aws:v1.1.0
```

```bash
# Watch all providers become healthy
kubectl get providers -w
# NAME                        INSTALLED   HEALTHY   PACKAGE
# provider-aws-s3             True        True      ...
# provider-aws-rds            True        True      ...
# upbound-provider-family-aws True        True      ...
```

---

## ProviderConfig — AWS (Access Keys)

```yaml
# Step 1: Store credentials in a Secret
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
---
# Step 2: Create a ProviderConfig that references the Secret
apiVersion: aws.upbound.io/v1beta1
kind: ProviderConfig
metadata:
  name: default          # resources use this by default
spec:
  credentials:
    source: Secret
    secretRef:
      namespace: crossplane-system
      name: aws-credentials
      key: credentials
```

---

## ProviderConfig — AWS (IRSA — No Long-lived Keys)

For EKS clusters, use IAM Roles for Service Accounts (IRSA) — no credentials stored in Kubernetes:

```yaml
# providerconfig-irsa.yaml
apiVersion: aws.upbound.io/v1beta1
kind: ProviderConfig
metadata:
  name: default
spec:
  credentials:
    source: IRSA           # uses the pod's projected service account token
  # The provider pod needs the eks.amazonaws.com/role-arn annotation on its SA
  # This is set via ControllerConfig (see below)
---
# Wire the IAM role to the provider's service account
apiVersion: pkg.crossplane.io/v1alpha1
kind: ControllerConfig
metadata:
  name: aws-irsa
  annotations:
    eks.amazonaws.com/role-arn: arn:aws:iam::123456789:role/crossplane-provider-aws
spec:
  serviceAccountAnnotations:
    eks.amazonaws.com/role-arn: arn:aws:iam::123456789:role/crossplane-provider-aws
---
apiVersion: pkg.crossplane.io/v1
kind: Provider
metadata:
  name: provider-aws-s3
spec:
  package: xpkg.upbound.io/upbound/provider-aws-s3:v1.1.0
  controllerConfigRef:
    name: aws-irsa           # link provider to the ControllerConfig
```

---

## ProviderConfig — GCP (Service Account Key)

```yaml
# gcp-credentials-secret.yaml
apiVersion: v1
kind: Secret
metadata:
  name: gcp-credentials
  namespace: crossplane-system
type: Opaque
stringData:
  credentials: |
    {
      "type": "service_account",
      "project_id": "my-project",
      "private_key_id": "key-id",
      "private_key": "-----BEGIN RSA PRIVATE KEY-----\n...",
      "client_email": "crossplane@my-project.iam.gserviceaccount.com",
      "client_id": "12345",
      "auth_uri": "https://accounts.google.com/o/oauth2/auth",
      "token_uri": "https://oauth2.googleapis.com/token"
    }
---
apiVersion: gcp.upbound.io/v1beta1
kind: ProviderConfig
metadata:
  name: default
spec:
  projectID: my-gcp-project
  credentials:
    source: Secret
    secretRef:
      namespace: crossplane-system
      name: gcp-credentials
      key: credentials
```

---

## ProviderConfig — GCP (Workload Identity)

```yaml
# providerconfig-workload-identity.yaml
apiVersion: gcp.upbound.io/v1beta1
kind: ProviderConfig
metadata:
  name: default
spec:
  projectID: my-gcp-project
  credentials:
    source: InjectedIdentity    # uses GKE Workload Identity — no key file
---
apiVersion: pkg.crossplane.io/v1alpha1
kind: ControllerConfig
metadata:
  name: gcp-wi
  annotations:
    iam.gke.io/gcp-service-account: crossplane@my-project.iam.gserviceaccount.com
spec:
  serviceAccountAnnotations:
    iam.gke.io/gcp-service-account: crossplane@my-project.iam.gserviceaccount.com
```

---

## ProviderConfig — Azure

```yaml
# azure-credentials-secret.yaml
apiVersion: v1
kind: Secret
metadata:
  name: azure-credentials
  namespace: crossplane-system
type: Opaque
stringData:
  credentials: |
    {
      "clientId": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
      "clientSecret": "your-client-secret",
      "subscriptionId": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
      "tenantId": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
      "activeDirectoryEndpointUrl": "https://login.microsoftonline.com",
      "resourceManagerEndpointUrl": "https://management.azure.com/",
      "activeDirectoryGraphResourceId": "https://graph.windows.net/",
      "sqlManagementEndpointUrl": "https://management.core.windows.net:8443/",
      "galleryEndpointUrl": "https://gallery.azure.com/",
      "managementEndpointUrl": "https://management.core.windows.net/"
    }
---
apiVersion: azure.upbound.io/v1beta1
kind: ProviderConfig
metadata:
  name: default
spec:
  credentials:
    source: Secret
    secretRef:
      namespace: crossplane-system
      name: azure-credentials
      key: credentials
```

---

## Multiple ProviderConfigs (Multi-Account)

You can have multiple ProviderConfigs for different accounts or environments:

```yaml
# Production account
apiVersion: aws.upbound.io/v1beta1
kind: ProviderConfig
metadata:
  name: aws-production
spec:
  credentials:
    source: Secret
    secretRef:
      name: aws-prod-credentials
      namespace: crossplane-system
      key: credentials
---
# Staging account
apiVersion: aws.upbound.io/v1beta1
kind: ProviderConfig
metadata:
  name: aws-staging
spec:
  credentials:
    source: Secret
    secretRef:
      name: aws-staging-credentials
      namespace: crossplane-system
      key: credentials
```

```yaml
# Managed resource references a specific ProviderConfig
apiVersion: s3.aws.upbound.io/v1beta1
kind: Bucket
metadata:
  name: prod-bucket
spec:
  forProvider:
    region: us-east-1
  providerConfigRef:
    name: aws-production    # explicit reference

---
apiVersion: s3.aws.upbound.io/v1beta1
kind: Bucket
metadata:
  name: staging-bucket
spec:
  forProvider:
    region: us-east-1
  providerConfigRef:
    name: aws-staging       # different account
```

---

## Provider Upgrades

```bash
# Check current provider version
kubectl get provider provider-aws-s3 -o jsonpath='{.spec.package}'

# Upgrade: edit the package version
kubectl patch provider provider-aws-s3 \
  --type=merge \
  -p '{"spec":{"package":"xpkg.upbound.io/upbound/provider-aws-s3:v1.2.0"}}'

# Watch the upgrade — old revision stays active until new one is healthy
kubectl get providerrevision -w
# NAME                         HEALTHY   REVISION   STATE      AGE
# provider-aws-s3-abc          True      1          Inactive   10m
# provider-aws-s3-xyz          True      2          Active     1m

# Rollback: reactivate old revision
kubectl patch providerrevision provider-aws-s3-abc \
  --type=merge \
  -p '{"spec":{"desiredState":"Active"}}'
```

---

## Verify Provider Health

```bash
# Overall health
kubectl get providers
# INSTALLED=True means the provider package was downloaded and installed
# HEALTHY=True means the provider pod is running and ready

# Describe provider for events
kubectl describe provider provider-aws-s3

# Check provider pod logs
kubectl logs -n crossplane-system \
  -l pkg.crossplane.io/revision=provider-aws-s3-xxxx \
  --tail=50

# Check if CRDs were registered
kubectl get crds | grep s3.aws.upbound.io
# buckets.s3.aws.upbound.io
# bucketacls.s3.aws.upbound.io
# bucketcorsconfigurations.s3.aws.upbound.io
# ... (many more)
```

---

## Gotchas

1. **`INSTALLED: True` but `HEALTHY: False`** — the package was downloaded but the pod crashed. Check `kubectl logs` in `crossplane-system` for the provider pod.
2. **ProviderConfig named `default` is used automatically** — managed resources without an explicit `providerConfigRef` use the `default` ProviderConfig. Name your primary config `default` to reduce boilerplate.
3. **Sub-providers share credentials** — when using provider families, all sub-providers use the same ProviderConfig. If you need per-sub-provider credentials, use explicit `providerConfigRef` on each MR.
4. **Never store credentials in Git** — use Sealed Secrets or External Secrets Operator to store the credentials Secret (see Kubernetes Course Day 25).

---

## Practice

1. Install `provider-nop` and create a `NopProviderConfig`. Verify the provider is INSTALLED and HEALTHY.
2. If you have AWS credentials, install `provider-aws-s3` and create a ProviderConfig using the Secret source.
3. Create two ProviderConfigs (`aws-dev` and `aws-prod`). Create a NopResource that explicitly references `aws-dev`.
4. Upgrade `provider-nop` to a newer version (or re-apply the same version). Watch the provider revision transition from Inactive to Active.

---

## Key Takeaways

- Providers are OCI images that add cloud resource CRDs and a controller to your cluster.
- Large providers (AWS, GCP, Azure) are split into sub-provider families — install only what you need.
- ProviderConfig holds the credentials. Name the primary one `default` so MRs use it automatically.
- Prefer IRSA/Workload Identity over long-lived key credentials — no secrets to rotate or accidentally commit.
