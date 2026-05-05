# Day 06 — Namespaces & Resource Quotas

## Learning Objectives
- Create and use namespaces to organise resources
- Apply ResourceQuotas to limit namespace consumption
- Use LimitRanges to set per-Pod defaults and limits
- Understand namespace-scoped vs cluster-scoped resources

---

## What Are Namespaces?

Namespaces are virtual clusters within a physical cluster. They isolate resources by name — two Deployments named `app` can coexist in different namespaces.

Default namespaces:
- `default` — where resources go if no namespace is specified
- `kube-system` — Kubernetes control plane components
- `kube-public` — publicly readable (rarely used)
- `kube-node-lease` — node heartbeat leases

---

## Creating Namespaces

```yaml
# namespace.yaml
apiVersion: v1
kind: Namespace
metadata:
  name: staging
  labels:
    environment: staging
    team: backend
---
apiVersion: v1
kind: Namespace
metadata:
  name: production
  labels:
    environment: production
    team: backend
```

```bash
kubectl apply -f namespace.yaml
kubectl get namespaces
kubectl get ns    # short form
```

---

## Deploying to a Namespace

```yaml
# deployment-namespaced.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: taskservice
  namespace: staging          # always specify namespace in manifests
spec:
  replicas: 2
  selector:
    matchLabels:
      app: taskservice
  template:
    metadata:
      labels:
        app: taskservice
    spec:
      containers:
        - name: app
          image: nginx:alpine
          resources:
            requests:
              cpu: "100m"
              memory: "64Mi"
            limits:
              cpu: "200m"
              memory: "128Mi"
```

```bash
kubectl apply -f deployment-namespaced.yaml
kubectl get pods -n staging
kubectl get pods -A          # all namespaces
```

---

## ResourceQuota — Limit a Namespace

ResourceQuota caps the total resources a namespace can consume:

```yaml
# resourcequota.yaml
apiVersion: v1
kind: ResourceQuota
metadata:
  name: staging-quota
  namespace: staging
spec:
  hard:
    # Compute
    requests.cpu: "4"           # total CPU requests in namespace
    requests.memory: 4Gi        # total memory requests
    limits.cpu: "8"             # total CPU limits
    limits.memory: 8Gi          # total memory limits

    # Object counts
    pods: "20"                  # max pods
    services: "10"
    persistentvolumeclaims: "5"
    secrets: "20"
    configmaps: "20"

    # LoadBalancer services (expensive)
    services.loadbalancers: "2"
    services.nodeports: "0"     # disallow NodePort in this namespace
```

```bash
kubectl apply -f resourcequota.yaml
kubectl describe quota staging-quota -n staging
# Resource               Used  Hard
# --------               ----  ----
# limits.cpu             200m  8
# limits.memory          128Mi 8Gi
# pods                   1     20
# requests.cpu           100m  4
# requests.memory        64Mi  4Gi
```

When quota is set, **every Pod must specify requests and limits** — pods without them are rejected.

---

## LimitRange — Per-Pod Defaults and Limits

LimitRange sets default requests/limits for containers that don't specify them, and enforces min/max bounds:

```yaml
# limitrange.yaml
apiVersion: v1
kind: LimitRange
metadata:
  name: staging-limits
  namespace: staging
spec:
  limits:
    - type: Container
      default:                  # applied if container doesn't set limits
        cpu: "200m"
        memory: "128Mi"
      defaultRequest:           # applied if container doesn't set requests
        cpu: "100m"
        memory: "64Mi"
      max:                      # containers cannot exceed these
        cpu: "2"
        memory: "1Gi"
      min:                      # containers cannot go below these
        cpu: "50m"
        memory: "32Mi"

    - type: Pod
      max:                      # sum across all containers in a pod
        cpu: "4"
        memory: "2Gi"

    - type: PersistentVolumeClaim
      max:
        storage: 10Gi
      min:
        storage: 1Gi
```

```bash
kubectl apply -f limitrange.yaml
kubectl describe limitrange staging-limits -n staging
```

---

## Full Namespace Setup

A typical team namespace setup:

```yaml
# namespace-full.yaml
apiVersion: v1
kind: Namespace
metadata:
  name: team-alpha
  labels:
    team: alpha
---
apiVersion: v1
kind: ResourceQuota
metadata:
  name: team-alpha-quota
  namespace: team-alpha
spec:
  hard:
    requests.cpu: "8"
    requests.memory: 8Gi
    limits.cpu: "16"
    limits.memory: 16Gi
    pods: "50"
    services: "20"
    persistentvolumeclaims: "10"
---
apiVersion: v1
kind: LimitRange
metadata:
  name: team-alpha-limits
  namespace: team-alpha
spec:
  limits:
    - type: Container
      default:
        cpu: "250m"
        memory: "256Mi"
      defaultRequest:
        cpu: "100m"
        memory: "128Mi"
      max:
        cpu: "2"
        memory: "2Gi"
```

---

## Namespace-scoped vs Cluster-scoped Resources

| Namespace-scoped | Cluster-scoped |
|---|---|
| Pod, Deployment, Service | Node |
| ConfigMap, Secret | PersistentVolume |
| ServiceAccount | StorageClass |
| Role, RoleBinding | ClusterRole, ClusterRoleBinding |
| ResourceQuota, LimitRange | Namespace itself |

```bash
# See which resources are namespace-scoped
kubectl api-resources --namespaced=true
kubectl api-resources --namespaced=false
```

---

## Gotchas

1. **Quota requires requests/limits on all Pods** — if a namespace has a ResourceQuota for CPU/memory, every container must declare requests and limits or it will be rejected.
2. **Deleting a namespace deletes everything in it** — `kubectl delete namespace staging` is irreversible (minus backups).
3. **Services only route within their namespace** — a Service in `staging` is not reachable from `production` without a fully-qualified name.
4. **LimitRange applies to new Pods only** — existing Pods are not affected when you add a LimitRange.

---

## Practice

1. Create `dev`, `staging`, and `production` namespaces with appropriate labels.
2. Apply a ResourceQuota to `staging` limiting it to 4 CPU and 4Gi memory.
3. Try to deploy a Pod without resource requests in a quota-enabled namespace — observe the error.
4. Add a LimitRange with defaults so Pods without explicit resources still get assigned some.

---

## Key Takeaways

- Namespaces isolate names — two teams can both have a `database` Deployment without conflict.
- ResourceQuota prevents one team from consuming the entire cluster.
- LimitRange fills in missing requests/limits — essential when ResourceQuota is set.
- Deleting a namespace is permanent and deletes all resources inside it.
