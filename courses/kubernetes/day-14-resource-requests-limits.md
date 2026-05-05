# Day 14 — Resource Requests & Limits

## Learning Objectives
- Understand CPU and memory requests vs limits
- Configure QoS classes
- Use LimitRange to set namespace defaults
- Identify and fix OOMKilled and CPU throttling issues

---

## Requests vs Limits

```yaml
resources:
  requests:       # GUARANTEED minimum — used for scheduling decisions
    cpu: "250m"   # scheduler finds a node with at least 250m free CPU
    memory: "256Mi"
  limits:         # MAXIMUM allowed — enforced at runtime
    cpu: "1"      # container is throttled if it exceeds this
    memory: "512Mi"  # container is OOMKilled if it exceeds this
```

| | Requests | Limits |
|---|---|---|
| Purpose | Scheduling guarantee | Runtime cap |
| CPU enforcement | Not enforced (can use more if available) | Throttled by cgroups |
| Memory enforcement | Not enforced | OOMKilled if exceeded |
| Effect on scheduling | Scheduler uses this to pick a node | No scheduling effect |

---

## CPU Units

```yaml
cpu: "1"          # 1 full CPU core
cpu: "0.5"        # half a core
cpu: "500m"       # 500 millicores = 0.5 core
cpu: "100m"       # 100 millicores = 0.1 core (minimum useful)
cpu: "2500m"      # 2.5 cores
```

---

## Memory Units

```yaml
memory: "128Mi"   # 128 mebibytes  (1 Mi = 1,048,576 bytes)
memory: "1Gi"     # 1 gibibyte
memory: "512M"    # 512 megabytes  (1 M = 1,000,000 bytes)
memory: "1G"      # 1 gigabyte
```

Always use `Mi` and `Gi` — they are unambiguous.

---

## QoS Classes

Kubernetes assigns a QoS class based on requests/limits configuration. This determines eviction order when a node runs out of memory.

### Guaranteed (highest priority — never evicted first)
```yaml
resources:
  requests:
    cpu: "500m"
    memory: "256Mi"
  limits:
    cpu: "500m"       # requests == limits for BOTH cpu and memory
    memory: "256Mi"
```

### Burstable (medium priority)
```yaml
resources:
  requests:
    cpu: "100m"
    memory: "128Mi"
  limits:
    cpu: "500m"       # limits > requests
    memory: "512Mi"
```

### BestEffort (lowest priority — evicted first)
```yaml
# No resources specified at all
containers:
  - name: app
    image: nginx:alpine
    # no resources block
```

```bash
kubectl get pod my-pod -o jsonpath='{.status.qosClass}'
# Guaranteed | Burstable | BestEffort
```

---

## Realistic Resource Profiles

```yaml
# Full deployment with well-configured resources
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api-service
spec:
  replicas: 3
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
          image: myapi:1.0

          resources:
            requests:
              cpu: "200m"         # guaranteed; scheduler uses this
              memory: "256Mi"
            limits:
              cpu: "1000m"        # can burst up to 1 core
              memory: "512Mi"     # OOMKilled if exceeded

        - name: sidecar-proxy
          image: envoy:v1.28
          resources:
            requests:
              cpu: "50m"
              memory: "64Mi"
            limits:
              cpu: "200m"
              memory: "128Mi"
```

---

## LimitRange — Namespace Defaults

```yaml
# limitrange.yaml
apiVersion: v1
kind: LimitRange
metadata:
  name: default-limits
  namespace: production
spec:
  limits:
    - type: Container
      default:             # applied if container has no limits
        cpu: "500m"
        memory: "256Mi"
      defaultRequest:      # applied if container has no requests
        cpu: "100m"
        memory: "128Mi"
      max:                 # ceiling — container cannot exceed
        cpu: "2"
        memory: "2Gi"
      min:                 # floor — container cannot go below
        cpu: "50m"
        memory: "32Mi"
      maxLimitRequestRatio:
        cpu: "10"          # limits cannot be more than 10x requests
        memory: "4"
```

---

## ResourceQuota with Limits

```yaml
# resourcequota.yaml
apiVersion: v1
kind: ResourceQuota
metadata:
  name: production-quota
  namespace: production
spec:
  hard:
    requests.cpu: "20"
    requests.memory: 40Gi
    limits.cpu: "40"
    limits.memory: 80Gi
    pods: "100"
```

---

## Diagnosing OOMKilled

```bash
kubectl get pods
# NAME       READY   STATUS      RESTARTS   AGE
# my-pod     0/1     OOMKilled   3          2m

kubectl describe pod my-pod
# Last State: Terminated
#   Reason: OOMKilled
#   Exit Code: 137
#   Started: ...
#   Finished: ...

# Check memory usage trends
kubectl top pods
kubectl top pods --sort-by=memory

# Fix: increase memory limit
# requests.memory: "128Mi" → "256Mi"
# limits.memory: "256Mi"  → "512Mi"
```

---

## Diagnosing CPU Throttling

CPU throttling doesn't kill the container — it just slows it down. Detect it via metrics:

```bash
kubectl top pods
# NAME       CPU(cores)   MEMORY(bytes)
# my-pod     998m         128Mi        ← consistently near the 1000m limit = throttled

# Check in Prometheus (if available)
# container_cpu_cfs_throttled_seconds_total
# container_cpu_cfs_throttled_periods_total
```

Fix by increasing the CPU limit or optimizing the application.

---

## VPA (Vertical Pod Autoscaler) — Automatic Sizing

VPA recommends or automatically adjusts resource requests based on actual usage:

```yaml
# vpa.yaml
apiVersion: autoscaling.k8s.io/v1
kind: VerticalPodAutoscaler
metadata:
  name: api-service-vpa
spec:
  targetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: api-service
  updatePolicy:
    updateMode: "Off"        # Off | Initial | Recreate | Auto
                             # Off = recommendations only (safe starting point)
  resourcePolicy:
    containerPolicies:
      - containerName: api
        minAllowed:
          cpu: "100m"
          memory: "128Mi"
        maxAllowed:
          cpu: "4"
          memory: "4Gi"
```

```bash
kubectl get vpa api-service-vpa
kubectl describe vpa api-service-vpa
# Shows recommended requests for each container
```

---

## Node Capacity and Allocatable

```bash
kubectl describe node k3d-devcluster-agent-0
# Capacity:
#   cpu:    4
#   memory: 8Gi
# Allocatable:            ← what's available for pods (capacity - system reserved)
#   cpu:    3800m
#   memory: 7.5Gi
# Allocated resources:    ← what's already claimed by pods
#   cpu:    1200m
#   memory: 2Gi
```

---

## Gotchas

1. **OOMKilled exit code is 137** (128 + SIGKILL). If you see restarts with exit code 137, increase memory limit.
2. **CPU limit throttling is invisible** — the container runs but slowly. Monitor `container_cpu_cfs_throttled_periods_total`.
3. **No limits = BestEffort = first to be evicted** — always set limits in production.
4. **Setting requests == limits gives Guaranteed QoS** — best for critical services that need predictable performance.

---

## Practice

1. Deploy an app without resource requests/limits. Check its QoS class.
2. Deploy the same app with requests == limits. Confirm `Guaranteed` QoS.
3. Deliberately set a low memory limit (10Mi for nginx). Observe OOMKilled status.
4. Use `kubectl top pods` to see current resource usage and compare to limits.

---

## Key Takeaways

- Requests = scheduling guarantee; Limits = runtime cap.
- Memory over limit → OOMKilled (exit 137). CPU over limit → throttled (no kill).
- Guaranteed QoS (requests == limits) = never the first to be evicted.
- Always set both requests and limits in production — BestEffort pods are first to die under pressure.
