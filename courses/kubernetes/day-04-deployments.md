# Day 04 — Deployments

## Learning Objectives
- Create and manage Deployments
- Understand ReplicaSets and how Deployments use them
- Configure rolling update strategy
- Scale, update, and roll back Deployments

---

## What Is a Deployment?

A Deployment manages a ReplicaSet which manages Pods. You declare desired state; the Deployment controller reconciles reality.

```
Deployment
  └── ReplicaSet (current)
        ├── Pod
        ├── Pod
        └── Pod
```

When you update the image, a new ReplicaSet is created and the old one is scaled down — this is a rolling update.

---

## Complete Deployment Manifest

```yaml
# deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: taskservice
  namespace: default
  labels:
    app: taskservice
    version: "1.0"
spec:
  replicas: 3                        # desired number of pods

  selector:
    matchLabels:
      app: taskservice               # must match template.metadata.labels

  strategy:
    type: RollingUpdate              # RollingUpdate (default) | Recreate
    rollingUpdate:
      maxSurge: 1                    # max pods ABOVE desired during update
      maxUnavailable: 0              # max pods BELOW desired during update
                                     # (0 = never reduce below 3)

  minReadySeconds: 10                # wait 10s after pod ready before marking available

  revisionHistoryLimit: 5            # keep 5 old ReplicaSets for rollback

  template:                          # Pod template — everything below is a Pod spec
    metadata:
      labels:
        app: taskservice             # MUST match selector.matchLabels
        version: "1.0"
    spec:
      terminationGracePeriodSeconds: 30   # time to drain before SIGKILL

      containers:
        - name: taskservice
          image: nginx:1.25-alpine        # always pin versions
          imagePullPolicy: IfNotPresent   # Always | IfNotPresent | Never

          ports:
            - name: http
              containerPort: 8080
              protocol: TCP

          env:
            - name: APP_ENV
              value: "production"

          resources:
            requests:
              cpu: "100m"
              memory: "64Mi"
            limits:
              cpu: "500m"
              memory: "256Mi"

          readinessProbe:               # pod is ready to receive traffic
            httpGet:
              path: /health
              port: 8080
            initialDelaySeconds: 5
            periodSeconds: 10
            failureThreshold: 3

          livenessProbe:                # restart pod if this fails
            httpGet:
              path: /health
              port: 8080
            initialDelaySeconds: 15
            periodSeconds: 20
            failureThreshold: 3
```

```bash
kubectl apply -f deployment.yaml
kubectl get deployments
kubectl get replicasets
kubectl get pods -l app=taskservice
```

---

## Scaling

```bash
# Imperative
kubectl scale deployment taskservice --replicas=5

# Declarative (preferred) — edit replicas in deployment.yaml then:
kubectl apply -f deployment.yaml

# Autoscaling (covered Day 26)
kubectl autoscale deployment taskservice --min=2 --max=10 --cpu-percent=70
```

---

## Updating the Image (Rolling Update)

```bash
# Imperative
kubectl set image deployment/taskservice taskservice=myapp:2.0

# Declarative (preferred) — update image in deployment.yaml then:
kubectl apply -f deployment.yaml

# Watch the rollout
kubectl rollout status deployment/taskservice
# Waiting for deployment "taskservice" rollout to finish: 1 out of 3 new replicas have been updated...
# Waiting for deployment "taskservice" rollout to finish: 2 out of 3 new replicas have been updated...
# deployment "taskservice" successfully rolled out
```

During rolling update with `maxSurge:1, maxUnavailable:0`:
```
replicas=3  →  old:3 new:0  →  old:3 new:1  →  old:2 new:2  →  old:1 new:3  →  old:0 new:3
```

---

## Rollback

```bash
# View rollout history
kubectl rollout history deployment/taskservice
# REVISION  CHANGE-CAUSE
# 1         <none>
# 2         <none>

# Add change cause (good practice)
kubectl annotate deployment taskservice kubernetes.io/change-cause="upgrade to v2.0"

# Roll back to previous revision
kubectl rollout undo deployment/taskservice

# Roll back to specific revision
kubectl rollout undo deployment/taskservice --to-revision=1

# Verify
kubectl rollout status deployment/taskservice
```

---

## Recreate Strategy (for stateful apps)

```yaml
# deployment-recreate.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: myapp-recreate
spec:
  replicas: 3
  selector:
    matchLabels:
      app: myapp
  strategy:
    type: Recreate             # kill ALL old pods, then create new ones
                               # causes downtime — use for apps that can't run two versions
  template:
    metadata:
      labels:
        app: myapp
    spec:
      containers:
        - name: app
          image: myapp:2.0
```

---

## Pausing and Resuming a Rollout

Useful when applying many changes at once:

```bash
kubectl rollout pause deployment/taskservice

# Make multiple changes
kubectl set image deployment/taskservice taskservice=myapp:2.1
kubectl set resources deployment/taskservice -c taskservice --limits=cpu=1,memory=512Mi

# Apply all changes at once
kubectl rollout resume deployment/taskservice
```

---

## Inspecting a Deployment

```bash
# See current ReplicaSets
kubectl get rs -l app=taskservice

# Full deployment details
kubectl describe deployment taskservice

# YAML of the live object
kubectl get deployment taskservice -o yaml

# See rollout history with details
kubectl rollout history deployment/taskservice --revision=2
```

---

## Gotchas

1. **`selector` is immutable after creation** — you can't change `matchLabels` on an existing Deployment. Delete and recreate.
2. **`maxUnavailable: 0` needs `maxSurge > 0`** — otherwise nothing can update (no room for new pods).
3. **Pods not rolling when only annotations change** — template labels/annotations changes trigger rollouts; spec changes do too, but only `template.spec` changes, not `metadata` changes outside the template.
4. **`revisionHistoryLimit: 0`** — disables rollback. Keep at least 3.

---

## Practice

1. Create a Deployment with 3 replicas of `nginx:1.24-alpine`. Verify all 3 pods are running.
2. Update the image to `nginx:1.25-alpine` and watch the rolling update with `kubectl rollout status`.
3. Roll back to the previous version.
4. Scale to 5 replicas, then scale back to 2.

---

## Key Takeaways

- A Deployment manages ReplicaSets which manage Pods — you work at the Deployment level.
- Rolling update: `maxSurge=1, maxUnavailable=0` is the safest zero-downtime strategy.
- Always pin image tags — `nginx:latest` is a deployment landmine.
- `kubectl rollout undo` is your quick recovery tool — `revisionHistoryLimit` controls how far back you can go.
