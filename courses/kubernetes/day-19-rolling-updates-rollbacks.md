# Day 19 — Rolling Updates & Rollbacks

## Learning Objectives
- Configure rolling update strategies for zero downtime
- Use readiness probes to gate rollout progress
- Roll back bad deployments quickly
- Implement blue/green and canary deployments

---

## Rolling Update Deep Dive

```yaml
# deployment-rolling.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api-service
  annotations:
    kubernetes.io/change-cause: "v2.0: add rate limiting, fix auth bug"
spec:
  replicas: 6
  selector:
    matchLabels:
      app: api-service

  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 2           # up to 8 pods during rollout (6+2)
      maxUnavailable: 0     # never fewer than 6 serving traffic

  minReadySeconds: 30       # pod must be ready for 30s before counting as available
                            # prevents bad pods from advancing the rollout

  revisionHistoryLimit: 10  # keep 10 ReplicaSets for rollback

  template:
    metadata:
      labels:
        app: api-service
    spec:
      terminationGracePeriodSeconds: 60   # allow in-flight requests to complete

      containers:
        - name: api
          image: myapi:2.0

          readinessProbe:       # rollout waits for this before continuing
            httpGet:
              path: /ready
              port: 8080
            periodSeconds: 5
            failureThreshold: 3
            successThreshold: 2    # must be ready twice before advancing

          lifecycle:
            preStop:
              exec:
                command: ["/bin/sh", "-c", "sleep 5"]  # drain in-flight before SIGTERM
```

---

## The Rollout Sequence

With replicas=6, maxSurge=2, maxUnavailable=0:

```
Step 1: Start 2 new pods  →  [old×6]  [new×2]  total=8
Step 2: New pods pass readiness → remove 2 old  →  [old×4]  [new×2]  total=6
Step 3: Start 2 new pods  →  [old×4]  [new×4]  total=8
Step 4: Remove 2 old      →  [old×2]  [new×4]  total=6
Step 5: Start 2 new pods  →  [old×2]  [new×6]  total=8
Step 6: Remove 2 old      →  [old×0]  [new×6]  total=6 ✓
```

If a new pod fails readiness, the rollout stops — old pods keep serving.

---

## Monitoring a Rollout

```bash
kubectl rollout status deployment/api-service
# Waiting for deployment "api-service" rollout to finish: 2 out of 6 new replicas have been updated...
# Waiting for deployment "api-service" rollout to finish: 4 out of 6 new replicas have been updated...
# deployment "api-service" successfully rolled out

kubectl rollout history deployment/api-service
# REVISION  CHANGE-CAUSE
# 1         v1.0: initial deployment
# 2         v2.0: add rate limiting, fix auth bug

kubectl rollout history deployment/api-service --revision=2
# Shows full pod template for revision 2
```

---

## Rollback

```bash
# Immediate rollback to previous revision
kubectl rollout undo deployment/api-service

# Rollback to specific revision
kubectl rollout undo deployment/api-service --to-revision=1

# Pause a bad rollout mid-flight
kubectl rollout pause deployment/api-service
# (investigate, then resume or undo)
kubectl rollout resume deployment/api-service
```

---

## Blue/Green Deployment

Zero-downtime deployment with instant cutover:

```yaml
# blue-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api-blue
spec:
  replicas: 3
  selector:
    matchLabels:
      app: api
      slot: blue
  template:
    metadata:
      labels:
        app: api
        slot: blue
        version: "1.0"
    spec:
      containers:
        - name: api
          image: myapi:1.0
---
# green-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api-green
spec:
  replicas: 3
  selector:
    matchLabels:
      app: api
      slot: green
  template:
    metadata:
      labels:
        app: api
        slot: green
        version: "2.0"
    spec:
      containers:
        - name: api
          image: myapi:2.0
---
# service.yaml — points to ONE slot at a time
apiVersion: v1
kind: Service
metadata:
  name: api-service
spec:
  selector:
    app: api
    slot: blue        # ← change to "green" to cut over
  ports:
    - port: 80
      targetPort: 8080
```

```bash
# Deploy green alongside blue
kubectl apply -f green-deployment.yaml

# Verify green is healthy
kubectl get pods -l slot=green

# Instant cutover: patch the service selector
kubectl patch service api-service -p '{"spec":{"selector":{"slot":"green"}}}'

# Verify traffic is going to green
kubectl exec test-pod -- curl http://api-service/version

# Keep blue running for rollback; delete after confidence
kubectl delete deployment api-blue
```

---

## Canary Deployment

Route a small percentage of traffic to the new version:

```yaml
# canary-stable.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api-stable
spec:
  replicas: 9                # 90% of traffic
  selector:
    matchLabels:
      app: api
      track: stable
  template:
    metadata:
      labels:
        app: api
        track: stable
    spec:
      containers:
        - name: api
          image: myapi:1.0
---
# canary-new.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api-canary
spec:
  replicas: 1                # 10% of traffic
  selector:
    matchLabels:
      app: api
      track: canary
  template:
    metadata:
      labels:
        app: api
        track: canary
    spec:
      containers:
        - name: api
          image: myapi:2.0
---
# service.yaml — routes to BOTH (no track selector)
apiVersion: v1
kind: Service
metadata:
  name: api-service
spec:
  selector:
    app: api              # matches both stable and canary pods
  ports:
    - port: 80
      targetPort: 8080
```

```bash
# Gradually increase canary traffic
kubectl scale deployment api-canary --replicas=3    # 30%
kubectl scale deployment api-canary --replicas=5    # 50%
kubectl scale deployment api-canary --replicas=9    # 90%

# Full cutover — scale stable down, canary up
kubectl scale deployment api-stable --replicas=0
kubectl scale deployment api-canary --replicas=9
```

---

## Deployment with PreStop Hook

Ensures graceful shutdown — pods finish in-flight requests before terminating:

```yaml
containers:
  - name: api
    image: myapi:2.0
    lifecycle:
      preStop:
        exec:
          command:
            - /bin/sh
            - -c
            - |
              # Signal app to stop accepting new requests
              kill -SIGTERM $(pidof myapi)
              # Wait for in-flight requests to complete
              sleep 15
    terminationGracePeriodSeconds: 30   # pod-level: SIGKILL after 30s
```

---

## Gotchas

1. **Rollout blocked by failing readiness probe** — if new pods never pass readiness, the rollout stalls. Old pods continue serving. Fix the bug and push a new image.
2. **`minReadySeconds: 0`** (default) — pods advance the rollout as soon as they pass readiness once. Set to 30–60 seconds in production for stability confirmation.
3. **`revisionHistoryLimit: 0`** disables rollback — never do this in production.
4. **Blue/green uses 2x resources** — you need enough cluster capacity to run both environments simultaneously.

---

## Practice

1. Perform a rolling update. Deliberately break the new image (bad command) — watch the rollout stall. Roll back.
2. Implement blue/green with instant cutover. Verify zero dropped requests during switchover.
3. Implement a canary at 10%, verify it's serving ~10% of requests, then gradually promote it.
4. Add a `preStop` hook that sleeps 10 seconds. Verify graceful shutdown during a rollout.

---

## Key Takeaways

- `maxUnavailable: 0` + `maxSurge > 0` = zero-downtime rolling update.
- Rollouts gate on readiness probes — a pod that never becomes ready stalls the rollout without breaking traffic.
- Blue/green = instant full cutover (patch Service selector). Canary = gradual via replica ratio.
- Always annotate deployments with `kubernetes.io/change-cause` — makes rollout history meaningful.
