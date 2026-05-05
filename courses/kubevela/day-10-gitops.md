# Day 10 — GitOps with KubeVela

## Learning Objectives
- Understand how KubeVela implements GitOps
- Use ApplicationRevision for versioning and rollback
- Sync Applications automatically from a Git repository
- Integrate KubeVela with ArgoCD and FluxCD
- Structure a GitOps repository for KubeVela

---

## GitOps with KubeVela

KubeVela fits naturally into GitOps: Application CRs are YAML files committed to Git. A GitOps engine (ArgoCD, FluxCD) applies them to the cluster.

```
Git Repo (source of truth)
    │
    │  Application YAML committed
    ▼
ArgoCD / FluxCD (syncs to cluster)
    │
    │  kubectl apply -f app.yaml
    ▼
KubeVela Controller (reconciles Application CR)
    │
    │  generates Kubernetes resources
    ▼
Deployment, Service, Ingress, HPA...
```

---

## ApplicationRevision — Built-in Versioning

Every time an Application changes, KubeVela creates an `ApplicationRevision`:

```bash
# List all revisions of an Application
kubectl get applicationrevision -n production
# NAME              REVISION   PUBLISH-VERSION
# taskapp-v1        1          -
# taskapp-v2        2          -
# taskapp-v3        3          published

# Inspect a specific revision (full Application spec at that point)
kubectl get applicationrevision taskapp-v2 -o yaml

# Roll back to revision 1
vela workflow rollback taskapp --revision-version 1

# Or use the workflow command
vela revision list taskapp
vela revision rollback taskapp --revision taskapp-v1
```

---

## Git Repository Structure

Organise your repo so each environment has its own Application YAML:

```
platform/
├── apps/
│   └── taskapp/
│       ├── base/
│       │   └── app.yaml          # base Application CR
│       ├── staging/
│       │   └── app.yaml          # staging-specific Application CR
│       └── production/
│           └── app.yaml          # production-specific Application CR
├── definitions/
│   ├── components/
│   │   ├── secured-webservice.yaml
│   │   └── postgresql.yaml
│   └── traits/
│       ├── pod-disruption-budget.yaml
│       └── node-selector.yaml
└── addons/
    └── enabled-addons.txt
```

---

## Application YAML per Environment

```yaml
# apps/taskapp/staging/app.yaml
apiVersion: core.oam.dev/v1beta1
kind: Application
metadata:
  name: taskapp
  namespace: staging
  annotations:
    app.oam.dev/publishVersion: "v1.5.0-rc1"    # tag this revision
spec:
  components:
    - name: api
      type: webservice
      properties:
        image: myapi:1.5.0-rc1     # staging: RC image
        port: 8080
        replicas: 1                # staging: fewer replicas
        env:
          - name: APP_ENV
            value: staging
      traits:
        - type: ingress
          properties:
            domain: api.staging.mycompany.com
            http:
              "/": 8080
```

```yaml
# apps/taskapp/production/app.yaml
apiVersion: core.oam.dev/v1beta1
kind: Application
metadata:
  name: taskapp
  namespace: production
  annotations:
    app.oam.dev/publishVersion: "v1.4.2"         # production: stable
spec:
  components:
    - name: api
      type: webservice
      properties:
        image: myapi:1.4.2          # production: last stable image
        port: 8080
        replicas: 5
        env:
          - name: APP_ENV
            value: production
      traits:
        - type: ingress
          properties:
            domain: api.mycompany.com
            http:
              "/": 8080
        - type: scaler
          properties:
            min: 5
            max: 20
            cpuPercent: 70
```

---

## ArgoCD Integration

ArgoCD syncs Application YAMLs from Git to the cluster. KubeVela then reconciles them.

### Install ArgoCD

```bash
kubectl create namespace argocd
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml

kubectl port-forward svc/argocd-server -n argocd 8443:443
# argocd login localhost:8443 --username admin --password $(kubectl get secret argocd-initial-admin-secret -n argocd -o jsonpath='{.data.password}' | base64 -d)
```

### ArgoCD Application for KubeVela Apps

```yaml
# argocd-app.yaml — ArgoCD watches the Git repo and applies KubeVela Application CRs
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: taskapp-production
  namespace: argocd
spec:
  project: default

  source:
    repoURL: https://github.com/myorg/platform
    targetRevision: main
    path: apps/taskapp/production      # watches this directory

  destination:
    server: https://kubernetes.default.svc
    namespace: production              # where to apply the KubeVela Application CR

  syncPolicy:
    automated:
      prune: true          # delete resources removed from Git
      selfHeal: true       # revert manual changes to the cluster
    syncOptions:
      - CreateNamespace=true
```

```bash
# Apply the ArgoCD app
kubectl apply -f argocd-app.yaml

# Sync manually (or wait for auto-sync)
argocd app sync taskapp-production

# Check status
argocd app status taskapp-production
```

---

## FluxCD Integration

FluxCD is the other popular GitOps engine. Enable the KubeVela fluxcd addon for Helm chart support, and use FluxCD's GitRepository + Kustomization for syncing:

```bash
# Install FluxCD
flux install

# Create a GitRepository source
flux create source git platform \
  --url=https://github.com/myorg/platform \
  --branch=main \
  --interval=1m

# Create a Kustomization that syncs KubeVela Application CRs
flux create kustomization taskapp-production \
  --source=GitRepository/platform \
  --path=./apps/taskapp/production \
  --prune=true \
  --interval=5m \
  --target-namespace=production
```

```bash
# Check FluxCD sync status
flux get kustomizations
# NAME                   REVISION   SUSPENDED   READY   MESSAGE
# taskapp-production     main/abc   False       True    Applied revision: main/abc
```

---

## CI/CD Pipeline Integration

Typical GitOps pipeline with KubeVela:

```yaml
# .github/workflows/deploy.yaml
name: Deploy

on:
  push:
    branches: [main]

jobs:
  update-staging:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Update staging image tag
        run: |
          # Update the image tag in the staging Application YAML
          sed -i "s|image: myapi:.*|image: myapi:${{ github.sha }}|" \
            apps/taskapp/staging/app.yaml

      - name: Commit and push
        run: |
          git config user.email "ci@mycompany.com"
          git config user.name "CI Bot"
          git add apps/taskapp/staging/app.yaml
          git commit -m "chore: update staging to ${{ github.sha }}"
          git push
        # ArgoCD/FluxCD picks up the change and applies it automatically

  promote-to-production:
    runs-on: ubuntu-latest
    needs: staging-tests
    if: github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v3

      - name: Promote staging tag to production
        run: |
          STAGING_TAG=$(grep "image: myapi:" apps/taskapp/staging/app.yaml | awk '{print $2}')
          sed -i "s|image: myapi:.*|image: $STAGING_TAG|" \
            apps/taskapp/production/app.yaml

      - name: Update publishVersion annotation
        run: |
          # Update the version annotation for ApplicationRevision tracking
          TIMESTAMP=$(date -u +%Y%m%d%H%M%S)
          sed -i "s|app.oam.dev/publishVersion:.*|app.oam.dev/publishVersion: \"$TIMESTAMP\"|" \
            apps/taskapp/production/app.yaml

      - name: Commit production promotion
        run: |
          git config user.email "ci@mycompany.com"
          git config user.name "CI Bot"
          git add apps/taskapp/production/app.yaml
          git commit -m "chore: promote $STAGING_TAG to production"
          git push
```

---

## Rollback in GitOps

In GitOps, rollback = revert the Git commit:

```bash
# Option 1: Revert the Git commit (preferred in GitOps)
git revert HEAD
git push
# ArgoCD/FluxCD applies the reverted YAML → KubeVela deploys old version

# Option 2: Rollback via vela (bypasses Git — not true GitOps)
vela workflow rollback taskapp --revision-version 2
# Note: This creates drift between Git and cluster state
```

---

## ApplicationRevision Retention

```yaml
# Set how many revisions to keep
apiVersion: core.oam.dev/v1beta1
kind: Application
metadata:
  name: taskapp
  namespace: production
  annotations:
    app.oam.dev/publishVersion: "v1.5.0"    # creates a named revision
spec:
  # ...
```

```bash
# List revisions
vela revision list taskapp
# REVISION   PUBLISH-VERSION   PHASE      CREATED-TIME
# 1          v1.3.0            succeeded  2024-01-01T10:00:00Z
# 2          v1.4.0            succeeded  2024-02-01T10:00:00Z
# 3          v1.5.0            succeeded  2024-03-01T10:00:00Z

# Prune old revisions (keep last 5)
kubectl patch application taskapp -p '{"spec":{"revisionHistoryLimit":5}}' --type=merge
```

---

## Gotchas

1. **ArgoCD + KubeVela resource management conflict** — ArgoCD prunes resources it doesn't recognise. Ensure ArgoCD is configured to sync the KubeVela Application CR, not the generated Deployment/Service (those are managed by KubeVela, not ArgoCD).
2. **`publishVersion` annotation is required for named revisions** — without it, revisions are auto-named `appname-vN`. With it, you get meaningful version names for rollbacks.
3. **GitOps rollback creates a new revision** — `git revert` creates a new commit and thus a new ApplicationRevision. Don't confuse with `vela rollback` which bypasses Git.
4. **FluxCD and KubeVela fluxcd addon** — the KubeVela `fluxcd` addon installs FluxCD controllers for Helm. If you're also using FluxCD for GitOps sync, they share the same controllers — no conflict, but be aware.

---

## Practice

1. Create a Git repo with staging and production Application YAMLs. Install ArgoCD. Point it at your repo and verify it syncs the Applications to the cluster.
2. Change the image tag in the staging YAML, commit and push. Watch ArgoCD pick up the change and KubeVela deploy the new version.
3. Add `app.oam.dev/publishVersion: "v1.0"` annotation. Update it to `"v2.0"`. List revisions and roll back to v1.0.
4. Simulate a bad deploy: commit a broken image tag. Revert the commit. Verify KubeVela automatically deploys the previous version.

---

## Key Takeaways

- KubeVela Application CRs are just YAML — commit them to Git and let ArgoCD or FluxCD apply them.
- `ApplicationRevision` tracks every change automatically. `publishVersion` annotation gives meaningful names.
- True GitOps rollback = revert the Git commit. `vela rollback` is an escape hatch that creates cluster drift.
- Structure your repo by environment (staging/, production/) — each has its own Application YAML with environment-specific image tags and replica counts.
