# Day 11 — GitOps with Crossplane

## Learning Objectives
- Structure a GitOps repository for Crossplane
- Integrate Crossplane with ArgoCD and FluxCD
- Handle dependency ordering in GitOps
- Detect and respond to infrastructure drift
- Manage secrets for providers in a GitOps-safe way

---

## Crossplane + GitOps = Infrastructure as Code That Heals

Traditional IaC + GitOps:
```
Git → CI/CD pipeline → terraform apply → cloud resource
       (one-shot, not continuous)
```

Crossplane + GitOps:
```
Git → ArgoCD/FluxCD → kubectl apply → Crossplane controller → cloud resource
                       (continuous reconciliation — drift is auto-corrected)
```

The Crossplane controller runs in the cluster at all times. If someone manually changes a cloud resource (e.g., changes RDS instance type in the AWS console), Crossplane detects it and reverts to the desired state from Git.

---

## Repository Structure

```
platform/
├── crossplane/
│   ├── providers/
│   │   ├── provider-aws-s3.yaml
│   │   ├── provider-aws-rds.yaml
│   │   └── provider-kubernetes.yaml
│   ├── providerconfigs/
│   │   └── aws-default.yaml          # ProviderConfig (no credentials — uses IRSA)
│   └── configurations/
│       └── platform-aws.yaml         # Configuration package install
│
├── platform-apis/
│   ├── database/
│   │   ├── xrd.yaml
│   │   └── composition-aws.yaml
│   └── objectstorage/
│       ├── xrd.yaml
│       └── composition-aws.yaml
│
└── claims/
    ├── team-backend/
    │   ├── database-taskapp.yaml
    │   └── objectstorage-assets.yaml
    └── team-data/
        └── database-analytics.yaml
```

---

## ArgoCD Integration

### ArgoCD App-of-Apps Pattern

```yaml
# argocd/apps/crossplane-platform.yaml
# The "root" ArgoCD Application that manages all others
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: crossplane-platform
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/mycompany/platform
    targetRevision: main
    path: argocd/app-of-apps        # contains child Application manifests
  destination:
    server: https://kubernetes.default.svc
    namespace: argocd
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
```

```yaml
# argocd/app-of-apps/crossplane-providers.yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: crossplane-providers
  namespace: argocd
spec:
  source:
    repoURL: https://github.com/mycompany/platform
    targetRevision: main
    path: crossplane/providers
  destination:
    server: https://kubernetes.default.svc
    namespace: crossplane-system
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
      - ServerSideApply=true    # required for CRDs and large resources
---
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: platform-apis
  namespace: argocd
spec:
  source:
    repoURL: https://github.com/mycompany/platform
    targetRevision: main
    path: platform-apis
  destination:
    server: https://kubernetes.default.svc
    namespace: crossplane-system
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - ServerSideApply=true
---
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: team-backend-claims
  namespace: argocd
spec:
  source:
    repoURL: https://github.com/mycompany/platform
    targetRevision: main
    path: claims/team-backend
  destination:
    server: https://kubernetes.default.svc
    namespace: team-backend
  syncPolicy:
    automated:
      prune: false              # DON'T prune claims — would delete cloud resources!
      selfHeal: true
```

---

## Dependency Ordering — Providers Before XRDs

ArgoCD syncs all resources simultaneously by default. Crossplane needs:
1. Providers installed first (registers CRDs)
2. XRDs applied after CRDs exist
3. Compositions applied after XRDs
4. Claims filed after Compositions

Use ArgoCD sync waves to enforce order:

```yaml
# Add annotations to control sync order
# crossplane/providers/provider-aws-rds.yaml
apiVersion: pkg.crossplane.io/v1
kind: Provider
metadata:
  name: provider-aws-rds
  annotations:
    argocd.argoproj.io/sync-wave: "0"    # wave 0: install providers first
spec:
  package: xpkg.upbound.io/upbound/provider-aws-rds:v1.1.0
```

```yaml
# platform-apis/database/xrd.yaml
apiVersion: apiextensions.crossplane.io/v1
kind: CompositeResourceDefinition
metadata:
  name: xdatabases.platform.mycompany.com
  annotations:
    argocd.argoproj.io/sync-wave: "1"    # wave 1: XRDs after providers
```

```yaml
# platform-apis/database/composition-aws.yaml
apiVersion: apiextensions.crossplane.io/v1
kind: Composition
metadata:
  name: database-aws-rds
  annotations:
    argocd.argoproj.io/sync-wave: "2"    # wave 2: compositions after XRDs
```

```yaml
# claims/team-backend/database-taskapp.yaml
apiVersion: platform.mycompany.com/v1alpha1
kind: Database
metadata:
  name: taskapp-db
  namespace: team-backend
  annotations:
    argocd.argoproj.io/sync-wave: "3"    # wave 3: claims last
spec:
  parameters:
    engine: postgres
    size: small
  writeConnectionSecretToRef:
    name: taskapp-db-conn
```

---

## FluxCD Integration

```yaml
# flux/sources/platform.yaml — watch the Git repo
apiVersion: source.toolkit.fluxcd.io/v1
kind: GitRepository
metadata:
  name: platform
  namespace: flux-system
spec:
  interval: 1m
  url: https://github.com/mycompany/platform
  ref:
    branch: main
  secretRef:
    name: github-token         # for private repos
---
# flux/kustomizations/crossplane-providers.yaml
apiVersion: kustomize.toolkit.fluxcd.io/v1
kind: Kustomization
metadata:
  name: crossplane-providers
  namespace: flux-system
spec:
  interval: 5m
  path: ./crossplane/providers
  prune: true
  sourceRef:
    kind: GitRepository
    name: platform
  targetNamespace: crossplane-system
  healthChecks:
    - apiVersion: pkg.crossplane.io/v1
      kind: Provider
      name: provider-aws-rds
      namespace: ""             # cluster-scoped
---
# flux/kustomizations/platform-apis.yaml
apiVersion: kustomize.toolkit.fluxcd.io/v1
kind: Kustomization
metadata:
  name: platform-apis
  namespace: flux-system
spec:
  interval: 5m
  path: ./platform-apis
  prune: true
  sourceRef:
    kind: GitRepository
    name: platform
  dependsOn:
    - name: crossplane-providers   # wait for providers to be healthy
---
# flux/kustomizations/team-backend-claims.yaml
apiVersion: kustomize.toolkit.fluxcd.io/v1
kind: Kustomization
metadata:
  name: team-backend-claims
  namespace: flux-system
spec:
  interval: 5m
  path: ./claims/team-backend
  prune: false                    # DON'T prune claims
  sourceRef:
    kind: GitRepository
    name: platform
  targetNamespace: team-backend
  dependsOn:
    - name: platform-apis         # wait for XRDs and Compositions
```

---

## GitOps-Safe Secret Management

Never commit credentials to Git. Use one of these approaches:

### Option 1: Sealed Secrets for ProviderConfig credentials

```bash
# Create and seal the AWS credentials secret
kubectl create secret generic aws-credentials \
  --from-literal=credentials="[default]
aws_access_key_id=AKIAIOSFODNN7EXAMPLE
aws_secret_access_key=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY" \
  --namespace crossplane-system \
  --dry-run=client -o yaml | \
  kubeseal --format yaml > crossplane/providerconfigs/aws-credentials-sealed.yaml

# Commit the sealed secret — safe to store in Git
git add crossplane/providerconfigs/aws-credentials-sealed.yaml
```

### Option 2: External Secrets Operator

```yaml
# crossplane/providerconfigs/aws-credentials-eso.yaml
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: aws-credentials
  namespace: crossplane-system
spec:
  refreshInterval: 1h
  secretStoreRef:
    name: vault-backend
    kind: ClusterSecretStore
  target:
    name: aws-credentials
    creationPolicy: Owner
    template:
      data:
        credentials: |
          [default]
          aws_access_key_id = {{ .access_key_id }}
          aws_secret_access_key = {{ .secret_access_key }}
  data:
    - secretKey: access_key_id
      remoteRef:
        key: platform/aws
        property: access_key_id
    - secretKey: secret_access_key
      remoteRef:
        key: platform/aws
        property: secret_access_key
```

### Option 3: IRSA (Preferred — Zero Secrets)

```yaml
# ProviderConfig with no credentials at all
apiVersion: aws.upbound.io/v1beta1
kind: ProviderConfig
metadata:
  name: default
spec:
  credentials:
    source: IRSA    # uses EKS node IAM role — nothing to store in Git
```

---

## Drift Detection

Crossplane continuously reconciles. If someone changes the cloud resource:

```bash
# Simulate drift: change RDS instance class in AWS Console
# (set db.t3.micro → db.t3.small manually in AWS)

# Crossplane detects drift within 1 minute (default poll interval)
kubectl get instance taskapp-db -w
# NAME         READY   SYNCED   AGE
# taskapp-db   True    False    10m   ← Synced goes False when drift detected
# taskapp-db   True    True     11m   ← Crossplane reverts to db.t3.micro

# Check what happened
kubectl describe instance taskapp-db
# Events:
#   Warning  CannotObserveExternalResource  detected drift, reverting
#   Normal   ExternalResourcePatched         instance class reverted to db.t3.micro
```

---

## Pause Reconciliation (Emergency)

```bash
# Pause a managed resource (stop reconciling, allow manual cloud changes)
kubectl annotate managed taskapp-db crossplane.io/paused=true

# Make manual changes in AWS console...

# Resume reconciliation
kubectl annotate managed taskapp-db crossplane.io/paused-

# Pause all resources in a namespace (via Claim)
kubectl annotate database taskapp-db -n team-backend crossplane.io/paused=true
```

---

## Gotchas

1. **`prune: false` on Claims — always** — if ArgoCD prunes Claims (when removed from Git), the cloud resources are deleted. Always set `prune: false` for the directory containing Claims.
2. **CRD sync race condition** — ArgoCD may try to apply XRDs before the Provider CRDs exist, causing sync failures. Use sync waves to enforce order.
3. **`ServerSideApply: true` for large CRDs** — Crossplane CRDs (especially AWS) are very large. Client-side apply may fail with annotation size limits. Use `ServerSideApply` in ArgoCD sync options.
4. **Drift revert can cause downtime** — if someone manually scales up RDS during an incident and Crossplane reverts it, that can worsen the situation. Pause reconciliation during incidents.

---

## Practice

1. Set up ArgoCD on k3d. Create an Application that syncs `crossplane/providers/` from a Git repo. Verify providers are installed.
2. Add sync wave annotations to providers (wave 0), XRDs (wave 1), and compositions (wave 2). Verify ArgoCD applies them in order.
3. Simulate drift: create a managed resource, change a field directly via `kubectl patch`, watch Crossplane revert it.
4. Use Sealed Secrets to store AWS credentials and reference them in a ProviderConfig. Commit the sealed secret to Git.

---

## Key Takeaways

- Crossplane + GitOps = continuous reconciliation. Drift is auto-corrected without manual intervention.
- Use sync waves (ArgoCD) or `dependsOn` (FluxCD) to enforce: providers → XRDs → compositions → claims.
- Never commit raw credentials to Git. Use Sealed Secrets, External Secrets Operator, or IRSA.
- Set `prune: false` on Claim directories in ArgoCD/FluxCD — removing a YAML file must not delete the cloud resource.
