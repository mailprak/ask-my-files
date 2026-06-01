# Day 28 — Kustomize

## Learning Objectives
- Understand Kustomize overlays and bases
- Patch resources without forking YAML
- Manage environment-specific configurations
- Use Kustomize with kubectl and in CI/CD pipelines

---

## What is Kustomize?

Kustomize is built into `kubectl`. It lets you customise Kubernetes YAML without forking files. You write a **base** (shared config) and **overlays** (environment-specific patches).

```
base/ (shared)  +  overlays/staging/ (patches)  →  staging manifests
base/ (shared)  +  overlays/production/ (patches)  →  production manifests
```

No templating language — pure YAML patching.

---

## Directory Structure

```
k8s/
├── base/
│   ├── kustomization.yaml
│   ├── deployment.yaml
│   ├── service.yaml
│   └── configmap.yaml
└── overlays/
    ├── staging/
    │   ├── kustomization.yaml
    │   └── patch-replicas.yaml
    └── production/
        ├── kustomization.yaml
        ├── patch-replicas.yaml
        └── patch-resources.yaml
```

---

## Base

```yaml
# base/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api-service
spec:
  replicas: 1
  selector:
    matchLabels:
      app: api-service
  template:
    metadata:
      labels:
        app: api-service
    spec:
      containers:
        - name: api
          image: myapi:latest
          ports:
            - containerPort: 8080
          resources:
            requests:
              cpu: "100m"
              memory: "128Mi"
            limits:
              cpu: "500m"
              memory: "256Mi"
          env:
            - name: LOG_LEVEL
              value: "info"
```

```yaml
# base/service.yaml
apiVersion: v1
kind: Service
metadata:
  name: api-service
spec:
  selector:
    app: api-service
  ports:
    - port: 80
      targetPort: 8080
```

```yaml
# base/kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

resources:                        # list all files in base
  - deployment.yaml
  - service.yaml
  - configmap.yaml

commonLabels:                     # added to all resources
  managed-by: kustomize
  team: platform
```

---

## Staging Overlay

```yaml
# overlays/staging/kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

resources:
  - ../../base                    # reference the base

namePrefix: staging-              # prefix all resource names: staging-api-service
namespace: staging                # override namespace for all resources

commonLabels:
  environment: staging

images:
  - name: myapi                   # find containers with this image name
    newTag: "1.5.0-rc1"           # override the tag

patches:
  - path: patch-replicas.yaml
  - path: patch-env.yaml

configMapGenerator:
  - name: app-config
    literals:
      - APP_ENV=staging
      - LOG_LEVEL=debug           # override log level for staging
```

```yaml
# overlays/staging/patch-replicas.yaml
# Strategic merge patch — merges with the base
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api-service
spec:
  replicas: 1                     # staging: 1 replica only
```

```yaml
# overlays/staging/patch-env.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api-service
spec:
  template:
    spec:
      containers:
        - name: api
          env:
            - name: LOG_LEVEL
              value: debug        # override env var
            - name: FEATURE_FLAG
              value: "true"       # add new env var
```

---

## Production Overlay

```yaml
# overlays/production/kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

resources:
  - ../../base

namespace: production

images:
  - name: myapi
    newTag: "1.5.0"               # stable tag for production

patches:
  - path: patch-replicas.yaml
  - path: patch-resources.yaml
  - path: patch-hpa.yaml         # add HPA only in production
```

```yaml
# overlays/production/patch-replicas.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api-service
spec:
  replicas: 5
```

```yaml
# overlays/production/patch-resources.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api-service
spec:
  template:
    spec:
      containers:
        - name: api
          resources:
            requests:
              cpu: "500m"
              memory: "512Mi"
            limits:
              cpu: "2"
              memory: "1Gi"
```

```yaml
# overlays/production/patch-hpa.yaml — add a new resource in the overlay
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: api-service
  namespace: production
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: api-service
  minReplicas: 5
  maxReplicas: 20
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
```

---

## JSON 6902 Patches (Precise Patching)

For when strategic merge is too blunt:

```yaml
# overlays/production/patch-json.yaml
# JSON 6902 patch — precise operations: add, remove, replace, move, copy
patches:
  - target:
      kind: Deployment
      name: api-service
    patch: |-
      - op: replace
        path: /spec/replicas
        value: 5
      - op: add
        path: /spec/template/spec/containers/0/env/-
        value:
          name: NEW_VAR
          value: "new-value"
      - op: remove
        path: /spec/template/spec/containers/0/env/0
```

---

## ConfigMap and Secret Generators

```yaml
# kustomization.yaml with generators
configMapGenerator:
  - name: app-config
    literals:
      - LOG_LEVEL=info
      - APP_ENV=production
    files:
      - config/app.properties     # reads file content as value
    options:
      disableNameSuffixHash: true  # prevent auto hash suffix (useful for stable names)

secretGenerator:
  - name: db-secret
    literals:
      - password=password
    type: Opaque
    options:
      disableNameSuffixHash: true
```

By default, Kustomize adds a hash suffix to generated ConfigMaps/Secrets: `app-config-abc12345`. This forces a Deployment rollout when config changes. Disable with `disableNameSuffixHash: true` if you manage rollouts separately.

---

## Applying with kubectl

```bash
# Preview what will be applied (dry run)
kubectl kustomize overlays/staging

# Apply staging
kubectl apply -k overlays/staging

# Apply production
kubectl apply -k overlays/production

# Diff: what would change?
kubectl diff -k overlays/production

# Delete everything in an overlay
kubectl delete -k overlays/staging
```

---

## Component Pattern — Reusable Patches

Components are reusable patches that can be composed:

```yaml
# components/monitoring/kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1alpha1
kind: Component

patches:
  - patch: |-
      - op: add
        path: /spec/template/metadata/annotations
        value:
          prometheus.io/scrape: "true"
          prometheus.io/port: "9090"
    target:
      kind: Deployment
```

```yaml
# overlays/production/kustomization.yaml
components:
  - ../../components/monitoring    # include the monitoring component
  - ../../components/pdb           # include pod disruption budget component
```

---

## Multiple Base Composition

```yaml
# overlays/production/kustomization.yaml
resources:
  - ../../base/api                 # multiple bases
  - ../../base/worker
  - ../../base/cron
  - extra-cronjob.yaml             # local resources added on top
```

---

## Kustomize in CI/CD

```yaml
# .github/workflows/deploy.yaml (example)
jobs:
  deploy:
    steps:
      - name: Deploy to staging
        run: |
          # Override image tag with the current commit SHA
          cd k8s/overlays/staging
          kustomize edit set image myapi=myapi:${{ github.sha }}
          kubectl apply -k .

      - name: Deploy to production
        run: |
          cd k8s/overlays/production
          kustomize edit set image myapi=myapi:${{ github.sha }}
          kubectl apply -k .
```

---

## Kustomize vs Helm

| Feature | Kustomize | Helm |
|---|---|---|
| Templating | No (YAML patches) | Yes (Go templates) |
| Dependencies | No | Yes (sub-charts) |
| Release tracking | No | Yes (helm history) |
| Rollback | kubectl rollout undo | helm rollback |
| Complexity | Simple | More complex |
| Built into kubectl | Yes | No (install separately) |
| Best for | Simple overlays | Reusable packages |

---

## Gotchas

1. **namePrefix applies to all resources** — including Secrets, ConfigMaps, and Service names referenced in Deployments. You may need to patch these references too.
2. **Strategic merge patches require the right kind + name** — Kustomize matches by `kind` + `metadata.name`. Wrong name = patch silently ignored.
3. **ConfigMap hash suffix** — the auto-hash changes the name, so Deployment `configMapRef` references need to match. Kustomize handles this automatically only if the ConfigMap was generated by the same `kustomization.yaml`.
4. **`kubectl apply -k` vs `kustomize build | kubectl apply -f`** — equivalent, but the latter lets you pipe through other tools for inspection.

---

## Practice

1. Create a base with a Deployment and Service. Add staging and production overlays that set different replica counts and image tags.
2. Use `kubectl kustomize overlays/staging` to preview the generated YAML without applying it.
3. Add a `configMapGenerator` to the base and override one value in each overlay.
4. Use `kubectl diff -k overlays/production` to see what would change before applying.

---

## Key Takeaways

- Kustomize = base + overlays. No templating — YAML patching with strategic merge or JSON 6902.
- `kubectl apply -k` is built in — no extra tools needed.
- Use `images[].newTag` to override the image tag per environment without editing the Deployment.
- Kustomize is simpler than Helm for managing environment variants. Use Helm for reusable, distributable packages.
