# Day 26 — Horizontal Pod Autoscaler (HPA) & Autoscaling

## Learning Objectives
- Configure HPA based on CPU and memory
- Scale on custom metrics using KEDA
- Understand VPA (Vertical Pod Autoscaler)
- Use Cluster Autoscaler concepts

---

## HPA Overview

HPA automatically scales the number of pod replicas based on observed metrics.

```
HPA  →  reads Metrics Server  →  adjusts Deployment replicas
         (CPU, Memory,              (scale up/down)
          custom metrics)
```

### Install Metrics Server (required for HPA)

```bash
# k3d comes with metrics-server — verify it's running
kubectl get deployment metrics-server -n kube-system

# If not installed:
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml

# Verify metrics collection
kubectl top nodes
kubectl top pods
```

---

## Basic HPA — CPU

```yaml
# hpa-cpu.yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: api-hpa
  namespace: production
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: api-service              # target deployment

  minReplicas: 2                   # never scale below this
  maxReplicas: 10                  # never scale above this

  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 60   # scale up when avg CPU > 60%
                                   # scale down when avg CPU < 60%
```

The HPA controller runs every 15 seconds. It scales up immediately but waits 5 minutes before scaling down (stabilisation window) to avoid flapping.

---

## HPA — CPU + Memory

```yaml
# hpa-cpu-memory.yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: api-hpa
  namespace: production
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: api-service

  minReplicas: 2
  maxReplicas: 20

  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70

    - type: Resource
      resource:
        name: memory
        target:
          type: AverageValue
          averageValue: 400Mi      # scale up when avg memory > 400Mi per pod

  behavior:
    scaleUp:
      stabilizationWindowSeconds: 60     # wait 60s before scaling up again
      policies:
        - type: Pods
          value: 4                       # add up to 4 pods per period
          periodSeconds: 60
        - type: Percent
          value: 100                     # or double the pods
          periodSeconds: 60
      selectPolicy: Max                  # use whichever allows more pods

    scaleDown:
      stabilizationWindowSeconds: 300    # wait 5 min before scaling down (default)
      policies:
        - type: Pods
          value: 2                       # remove at most 2 pods per 60 seconds
          periodSeconds: 60
      selectPolicy: Min                  # use whichever allows fewer removals (conservative)
```

---

## Deployment for HPA — Resource Requests Required

HPA cannot work without resource requests. The percentage is relative to the request:

```yaml
# deployment-with-resources.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api-service
  namespace: production
spec:
  replicas: 2                      # HPA overrides this — set to minReplicas
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
          image: myapi:2.0
          ports:
            - containerPort: 8080
          resources:
            requests:
              cpu: "250m"          # HPA measures against this — 60% = 150m
              memory: "256Mi"
            limits:
              cpu: "1"
              memory: "512Mi"
```

---

## HPA Status & Commands

```bash
# View HPA status
kubectl get hpa -n production
# NAME      REFERENCE           TARGETS         MINPODS   MAXPODS   REPLICAS
# api-hpa   Deployment/api-service  45%/60%     2         20        3

# Describe for detailed events
kubectl describe hpa api-hpa -n production

# Watch HPA in real time
kubectl get hpa -n production -w

# Trigger load (to test scaling)
kubectl run load-gen --image=busybox --rm -it -- \
  /bin/sh -c "while true; do wget -q -O- http://api-service; done"
```

---

## KEDA — Kubernetes Event-Driven Autoscaling

KEDA scales on any event source: Kafka lag, queue depth, cron schedule, HTTP request rate, etc.

```bash
# Install KEDA
helm repo add kedacore https://kedacore.github.io/charts
helm install keda kedacore/keda --namespace keda --create-namespace
```

### KEDA ScaledObject — Scale on Kafka Lag

```yaml
# keda-kafka.yaml
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
  name: kafka-consumer-scaler
  namespace: production
spec:
  scaleTargetRef:
    name: kafka-consumer            # deployment to scale

  minReplicaCount: 0               # scale to zero when no messages!
  maxReplicaCount: 30

  triggers:
    - type: kafka
      metadata:
        bootstrapServers: kafka.production.svc.cluster.local:9092
        consumerGroup: my-consumer-group
        topic: orders
        lagThreshold: "100"         # 1 replica per 100 messages of lag
        offsetResetPolicy: latest
```

### KEDA ScaledObject — HTTP Request Rate

```yaml
# keda-http.yaml
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
  name: http-scaler
  namespace: production
spec:
  scaleTargetRef:
    name: api-service

  minReplicaCount: 1
  maxReplicaCount: 50

  triggers:
    - type: prometheus
      metadata:
        serverAddress: http://prometheus.monitoring.svc.cluster.local:9090
        metricName: http_requests_per_second
        threshold: "100"            # 1 replica per 100 req/sec
        query: |
          sum(rate(http_requests_total{job="api-service"}[2m]))
```

### KEDA ScaledObject — Cron Schedule

```yaml
# keda-cron.yaml — scale up for business hours, scale to zero at night
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
  name: business-hours-scaler
  namespace: production
spec:
  scaleTargetRef:
    name: api-service

  triggers:
    - type: cron
      metadata:
        timezone: America/New_York
        start: "0 8 * * 1-5"      # 8am Mon-Fri — scale up
        end: "0 20 * * 1-5"       # 8pm Mon-Fri — scale down
        desiredReplicas: "10"      # during business hours: 10 replicas
```

---

## Vertical Pod Autoscaler (VPA)

VPA adjusts resource requests and limits based on actual usage. Pods are restarted when recommendations change.

```bash
# Install VPA
git clone https://github.com/kubernetes/autoscaler
cd autoscaler/vertical-pod-autoscaler
./hack/vpa-install.sh
```

```yaml
# vpa.yaml
apiVersion: autoscaling.k8s.io/v1
kind: VerticalPodAutoscaler
metadata:
  name: api-vpa
  namespace: production
spec:
  targetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: api-service

  updatePolicy:
    updateMode: "Off"     # Off = recommend only (don't change pods)
                          # Auto = update pods automatically (restarts pods)
                          # Initial = only set on pod creation

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
# Check VPA recommendations
kubectl describe vpa api-vpa -n production
# Containers:
#   Container Name: api
#     Lower Bound: cpu:100m, memory:128Mi
#     Target:      cpu:320m, memory:256Mi    ← suggested requests
#     Upper Bound: cpu:1200m, memory:1Gi
```

---

## HPA + VPA Together

Use VPA in `Off` mode to get recommendations, and HPA for horizontal scaling:

```
┌─────────────────────────────────────────────────────┐
│  VPA (mode: Off)   →  reads usage → shows target    │
│  HPA               →  reads usage → scales replicas │
└─────────────────────────────────────────────────────┘
Do NOT use VPA Auto with HPA CPU — they conflict.
Use VPA Auto only with HPA scaling on custom metrics.
```

---

## Gotchas

1. **Resource requests are mandatory for HPA** — without requests, `averageUtilization` target cannot be computed.
2. **HPA and manual `kubectl scale` conflict** — HPA overrides manual scale. Don't use both.
3. **VPA restarts pods** — `updateMode: Auto` evicts pods to apply new resources. Use with PodDisruptionBudgets to limit disruption.
4. **`minReplicas: 0` requires KEDA** — native HPA cannot scale to zero. KEDA handles this.

---

## Practice

1. Deploy an app with CPU requests. Create an HPA. Generate load and watch replicas increase with `kubectl get hpa -w`.
2. Set `behavior.scaleDown.stabilizationWindowSeconds: 30`. Stop the load and watch pods scale down faster.
3. Install KEDA. Create a ScaledObject with a cron trigger. Verify replicas change at the scheduled time.
4. Install VPA in `Off` mode. Let it observe your app for a few minutes. Check recommendations with `kubectl describe vpa`.

---

## Key Takeaways

- HPA scales replicas based on CPU, memory, or custom metrics. Requires resource requests.
- Use `behavior.scaleDown.stabilizationWindowSeconds` to control scale-down aggressiveness.
- KEDA extends HPA to event sources: Kafka, queues, Prometheus metrics, cron schedules — and can scale to zero.
- VPA in `Off` mode gives right-sizing recommendations without touching running pods — use it to tune requests.
