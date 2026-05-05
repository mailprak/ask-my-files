# Day 08 — Labels, Selectors & Annotations

## Learning Objectives
- Use labels to organise and select resources
- Write label selectors (equality and set-based)
- Use annotations for metadata that isn't selection criteria
- Apply recommended Kubernetes label conventions

---

## Labels

Labels are key-value pairs attached to any Kubernetes object. They are the primary mechanism for grouping and selecting resources.

```yaml
# pod-labels.yaml
apiVersion: v1
kind: Pod
metadata:
  name: myapp-v2-prod
  labels:
    # Recommended standard labels
    app.kubernetes.io/name: myapp
    app.kubernetes.io/version: "2.0"
    app.kubernetes.io/component: frontend
    app.kubernetes.io/part-of: my-platform
    app.kubernetes.io/managed-by: helm

    # Custom labels for your use
    environment: production
    team: backend
    tier: web
    release: stable
spec:
  containers:
    - name: app
      image: nginx:alpine
```

```bash
kubectl apply -f pod-labels.yaml
kubectl get pods --show-labels
kubectl get pods -l environment=production
kubectl get pods -l app.kubernetes.io/name=myapp
```

---

## Adding and Removing Labels Imperatively

```bash
# Add a label
kubectl label pod myapp-v2-prod canary=true

# Update a label
kubectl label pod myapp-v2-prod environment=staging --overwrite

# Remove a label
kubectl label pod myapp-v2-prod canary-

# Label all pods matching a selector
kubectl label pods -l app=myapp version=2.0
```

---

## Equality-Based Selectors

```bash
# Exact match
kubectl get pods -l environment=production
kubectl get pods -l environment=production,team=backend   # AND

# Not equal
kubectl get pods -l environment!=production

# Key exists
kubectl get pods -l canary

# Key does not exist
kubectl get pods -l '!canary'
```

In YAML (used in Services, ReplicaSets):

```yaml
selector:
  matchLabels:
    app: myapp
    environment: production
```

---

## Set-Based Selectors

More expressive — used in Deployments, Jobs, and NodeAffinity:

```yaml
selector:
  matchExpressions:
    - key: environment
      operator: In
      values: [production, staging]

    - key: tier
      operator: NotIn
      values: [database]

    - key: canary
      operator: DoesNotExist   # key must not be present

    - key: app
      operator: Exists         # key must be present (any value)
```

```bash
# Set-based in kubectl
kubectl get pods -l 'environment in (production,staging)'
kubectl get pods -l 'tier notin (database,cache)'
```

---

## Annotations

Annotations store arbitrary non-identifying metadata. They are NOT used for selection — use them for tooling, documentation, and operational data.

```yaml
# pod-annotated.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: myapp
  annotations:
    # Documentation
    description: "Main web application for the customer portal"
    team-slack: "#team-backend"
    runbook: "https://wiki.example.com/myapp/runbook"

    # Tooling integration
    prometheus.io/scrape: "true"
    prometheus.io/port: "9090"
    prometheus.io/path: "/metrics"

    # Deployment tracking
    kubernetes.io/change-cause: "deploy version 2.0 with new auth module"
    deployment.kubernetes.io/revision: "3"

    # Sidecar injection (Istio, Linkerd)
    sidecar.istio.io/inject: "true"

spec:
  replicas: 2
  selector:
    matchLabels:
      app: myapp
  template:
    metadata:
      labels:
        app: myapp
      annotations:
        prometheus.io/scrape: "true"   # annotations on pod template too
        prometheus.io/port: "9090"
    spec:
      containers:
        - name: app
          image: nginx:alpine
```

```bash
kubectl annotate deployment myapp owner="john@example.com"
kubectl annotate deployment myapp owner-          # remove
kubectl describe deployment myapp | grep -A5 Annotations
```

---

## Labels vs Annotations: When to Use Which

| Labels | Annotations |
|---|---|
| Used for selection and grouping | Used for metadata only — never for selection |
| Affect routing (Services, Deployments) | Tooling hints (Prometheus, Istio, ArgoCD) |
| Short, simple values | Can be long — URLs, JSON blobs, descriptions |
| Immutable after object creation for selectors | Can be changed at any time |

---

## Recommended Label Conventions

```yaml
labels:
  app.kubernetes.io/name: myapp           # name of the app
  app.kubernetes.io/instance: myapp-prod  # unique instance name
  app.kubernetes.io/version: "2.1.0"      # current version
  app.kubernetes.io/component: frontend   # component type
  app.kubernetes.io/part-of: my-platform  # larger system this belongs to
  app.kubernetes.io/managed-by: helm      # tool managing this object
```

These are the official Kubernetes recommended labels — use them for interoperability with Helm, ArgoCD, Lens, and other tools.

---

## Using Labels for Canary Deployments

```yaml
# deployment-stable.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: myapp-stable
spec:
  replicas: 9              # 90% of traffic
  selector:
    matchLabels:
      app: myapp
      track: stable
  template:
    metadata:
      labels:
        app: myapp         # Service selects on this
        track: stable
    spec:
      containers:
        - name: app
          image: myapp:1.0
---
# deployment-canary.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: myapp-canary
spec:
  replicas: 1              # 10% of traffic
  selector:
    matchLabels:
      app: myapp
      track: canary
  template:
    metadata:
      labels:
        app: myapp         # same label — Service routes to BOTH deployments
        track: canary
    spec:
      containers:
        - name: app
          image: myapp:2.0
---
apiVersion: v1
kind: Service
metadata:
  name: myapp
spec:
  selector:
    app: myapp             # selects pods from BOTH deployments
  ports:
    - port: 80
      targetPort: 8080
```

10 pods total: 9 stable + 1 canary → ~10% of requests hit canary.

---

## Gotchas

1. **Label selectors in Services and ReplicaSets are immutable** — you cannot change `selector` after creation.
2. **Overlapping selectors cause cross-adoption** — if two Deployments select the same pods, one controller will steal the other's pods.
3. **`matchLabels` is an AND** — every key-value pair must match.
4. **Annotation values are always strings** — even if you write `"true"` or `"80"`, it's a string.

---

## Practice

1. Create three Pods with labels `env=prod`, `env=staging`, `env=dev`. Use selectors to list only prod and staging together.
2. Implement a canary deployment: 9 replicas of v1, 1 replica of v2, one Service routing to both.
3. Add Prometheus scraping annotations to a Deployment.
4. Use `matchExpressions` with the `In` operator to select pods from multiple environments.

---

## Key Takeaways

- Labels are for selection and grouping — keep them short and consistent.
- Annotations are for metadata — tooling, docs, operational notes.
- Set-based selectors (`In`, `NotIn`, `Exists`) are more expressive than equality selectors.
- Use the official `app.kubernetes.io/*` label convention for interoperability.
