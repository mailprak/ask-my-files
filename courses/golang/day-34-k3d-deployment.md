# Day 34 — Deploying the Task Microservice on k3d

## Learning Objectives
- Containerize the Go service with a multi-stage Dockerfile
- Create a local k3d Kubernetes cluster
- Write Deployment, Service, ConfigMap, Secret, and PVC manifests
- Deploy, test, and iterate on k3d
- Understand how the file store works with a PersistentVolume

---

## What Is k3d?

k3d runs k3s (a lightweight Kubernetes distribution) inside Docker containers. You get a full Kubernetes cluster on your laptop with a single command — perfect for local development and CI.

```
Your machine (Docker)
└── k3d cluster
    ├── control-plane node (Docker container)
    └── worker node(s) (Docker containers)
        └── taskservice Pod
            └── taskservice container (your Go binary)
                └── /data/tasks.json (PersistentVolume)
```

---

## Prerequisites

```bash
# Install k3d
curl -s https://raw.githubusercontent.com/k3d-io/k3d/main/install.sh | bash

# Install kubectl
curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
chmod +x kubectl && mv kubectl /usr/local/bin/

# Verify
k3d version
kubectl version --client
docker version
```

---

## Step 1: Create the k3d Cluster

```bash
# Create a cluster named "taskcluster" with:
# - 1 server (control plane)
# - 1 agent (worker node)
# - Port 8080 on your machine mapped to port 80 on the load balancer
k3d cluster create taskcluster \
  --servers 1 \
  --agents 1 \
  --port "8080:80@loadbalancer" \
  --registry-create taskregistry:5000

# Verify nodes are Ready
kubectl get nodes
# NAME                        STATUS   ROLES
# k3d-taskcluster-server-0    Ready    control-plane
# k3d-taskcluster-agent-0     Ready    <none>
```

The `--registry-create taskregistry:5000` flag creates a local Docker registry inside the cluster. You push images to it without needing Docker Hub.

---

## Step 2: Multi-Stage Dockerfile

```dockerfile
# Dockerfile
# ── Stage 1: Build ──────────────────────────────────────────────────────────
FROM golang:1.22-alpine AS builder

WORKDIR /src

# Cache dependencies separately from source code
COPY go.mod go.sum ./
RUN go mod download

# Build the binary
COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -ldflags="-s -w" -o /taskservice ./...

# ── Stage 2: Run ────────────────────────────────────────────────────────────
FROM scratch

# Copy CA certs (needed for HTTPS outbound calls)
COPY --from=builder /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/

# Copy only the binary
COPY --from=builder /taskservice /taskservice

# Non-root user
USER 1000:1000

EXPOSE 8080

ENTRYPOINT ["/taskservice"]
```

**Why multi-stage?**
- `builder` stage has the entire Go toolchain (~600 MB)
- `scratch` final image contains only the binary (~8 MB)
- No shell, no package manager — minimal attack surface

```bash
# Build and verify size
docker build -t taskservice:latest .
docker images taskservice
# REPOSITORY    TAG     IMAGE ID    SIZE
# taskservice   latest  abc123...   8.2MB
```

---

## Step 3: Push to k3d Registry

```bash
# Tag for the local k3d registry
docker tag taskservice:latest localhost:5000/taskservice:latest

# Push to the registry inside the cluster
docker push localhost:5000/taskservice:latest
```

---

## Step 4: Kubernetes Manifests

Create a `k8s/` directory in the project:

```
taskservice/
├── k8s/
│   ├── namespace.yaml
│   ├── secret.yaml
│   ├── pvc.yaml
│   ├── deployment.yaml
│   └── service.yaml
```

### k8s/namespace.yaml

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: tasks
```

### k8s/secret.yaml

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: taskservice-secret
  namespace: tasks
type: Opaque
stringData:
  api-token: "supersecrettoken123"   # change this — or use a generator
```

Secrets in Kubernetes are base64-encoded (not encrypted by default). For production use sealed-secrets or an external vault. For local k3d development, `stringData` is fine.

### k8s/pvc.yaml

The PersistentVolumeClaim gives the Pod durable storage for `tasks.json`:

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: taskservice-data
  namespace: tasks
spec:
  accessModes:
    - ReadWriteOnce          # one node at a time (fine for single-replica)
  storageClassName: local-path  # k3d's default storage class
  resources:
    requests:
      storage: 100Mi
```

k3s ships with the `local-path` provisioner — it creates a directory on the node's filesystem. Data persists across Pod restarts.

### k8s/deployment.yaml

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: taskservice
  namespace: tasks
  labels:
    app: taskservice
spec:
  replicas: 1                  # 1 replica — file store is single-writer safe
  selector:
    matchLabels:
      app: taskservice
  template:
    metadata:
      labels:
        app: taskservice
    spec:
      securityContext:
        runAsNonRoot: true
        runAsUser: 1000
        fsGroup: 1000            # ensures volume is group-writable

      containers:
        - name: taskservice
          image: k3d-taskregistry:5000/taskservice:latest
          imagePullPolicy: Always

          ports:
            - containerPort: 8080
              name: http

          env:
            - name: DATA_PATH
              value: /data/tasks.json
            - name: API_TOKEN
              valueFrom:
                secretKeyRef:
                  name: taskservice-secret
                  key: api-token

          volumeMounts:
            - name: data
              mountPath: /data      # tasks.json lives here

          resources:
            requests:
              cpu: "50m"
              memory: "32Mi"
            limits:
              cpu: "200m"
              memory: "128Mi"

          # Liveness: restart the Pod if the health endpoint stops responding
          livenessProbe:
            httpGet:
              path: /health
              port: 8080
            initialDelaySeconds: 5
            periodSeconds: 10
            failureThreshold: 3

          # Readiness: don't route traffic until the service is ready
          readinessProbe:
            httpGet:
              path: /health
              port: 8080
            initialDelaySeconds: 3
            periodSeconds: 5

      volumes:
        - name: data
          persistentVolumeClaim:
            claimName: taskservice-data
```

### k8s/service.yaml

```yaml
apiVersion: v1
kind: Service
metadata:
  name: taskservice
  namespace: tasks
spec:
  selector:
    app: taskservice
  ports:
    - name: http
      port: 80             # Service port (cluster-internal)
      targetPort: 8080     # Container port
  type: ClusterIP          # Internal only; Ingress or LoadBalancer for external
---
# Ingress to expose via the k3d load balancer (port 8080 on your machine)
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: taskservice
  namespace: tasks
  annotations:
    ingress.kubernetes.io/ssl-redirect: "false"
spec:
  rules:
    - http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: taskservice
                port:
                  number: 80
```

k3d ships with Traefik as the ingress controller. The Ingress routes `localhost:8080/*` → `taskservice:80` → container `:8080`.

---

## Step 5: Deploy

```bash
# Apply all manifests in order
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/secret.yaml
kubectl apply -f k8s/pvc.yaml
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml

# Watch the Pod come up
kubectl get pods -n tasks -w
# NAME                          READY   STATUS    RESTARTS   AGE
# taskservice-6d8f9b7c5-xk2p9   1/1     Running   0          15s

# Check logs
kubectl logs -n tasks deployment/taskservice
# 2024/01/15 10:30:00 using file store: /data/tasks.json
# 2024/01/15 10:30:00 server listening on :8080
```

---

## Step 6: Test the Deployed Service

```bash
TOKEN="supersecrettoken123"

# Health check (no auth needed)
curl http://localhost:8080/health
# {"status":"ok"}

# Create a task
curl -X POST http://localhost:8080/tasks \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"title":"Deploy on k3d","description":"Day 34 exercise"}'
# {"id":"abc-123","title":"Deploy on k3d","status":"todo",...}

# List tasks
curl http://localhost:8080/tasks \
  -H "Authorization: Bearer $TOKEN"

# Verify persistence: delete the Pod, let it restart, check data survived
kubectl delete pod -n tasks -l app=taskservice
kubectl get pods -n tasks -w   # watch it restart

curl http://localhost:8080/tasks \
  -H "Authorization: Bearer $TOKEN"
# tasks are still there — PVC preserved them
```

---

## Step 7: Updating the Service

```bash
# Rebuild and push the new image
docker build -t localhost:5000/taskservice:v2 .
docker push localhost:5000/taskservice:v2

# Update the deployment image
kubectl set image deployment/taskservice \
  taskservice=k3d-taskregistry:5000/taskservice:v2 \
  -n tasks

# Watch the rolling update
kubectl rollout status deployment/taskservice -n tasks

# Roll back if something breaks
kubectl rollout undo deployment/taskservice -n tasks
```

---

## Scaling Considerations for File Store

The file store uses `sync.RWMutex` which is **per-process only**. With `replicas: 1` this is fine. If you scale to multiple replicas:

```yaml
# This will cause data corruption — two Pods write to different PVC instances
replicas: 3   # ❌ with file store

replicas: 1   # ✅ with file store + ReadWriteOnce PVC
```

To scale beyond one replica, replace FileStore with a proper database (Postgres, SQLite with WAL, bbolt) and use a `ReadWriteMany` PVC or a StatefulSet.

---

## Useful k3d & kubectl Commands

```bash
# Cluster management
k3d cluster list
k3d cluster stop taskcluster
k3d cluster start taskcluster
k3d cluster delete taskcluster

# Debugging
kubectl describe pod -n tasks <pod-name>       # events + status
kubectl logs -n tasks <pod-name> --previous    # logs from crashed container
kubectl exec -n tasks <pod-name> -- ls /data   # exec into running container
kubectl get events -n tasks --sort-by='.lastTimestamp'

# Inspect the PVC and its data
kubectl get pvc -n tasks
kubectl exec -n tasks deployment/taskservice -- cat /data/tasks.json

# Port-forward directly (bypasses ingress — useful for debugging)
kubectl port-forward -n tasks deployment/taskservice 9090:8080
curl http://localhost:9090/health
```

---

## Complete Makefile

```makefile
REGISTRY  = localhost:5000
IMAGE     = taskservice
TAG       = latest
NAMESPACE = tasks

.PHONY: build push deploy test clean

build:
	docker build -t $(REGISTRY)/$(IMAGE):$(TAG) .

push: build
	docker push $(REGISTRY)/$(IMAGE):$(TAG)

deploy: push
	kubectl apply -f k8s/

test:
	go test -race -cover ./...

logs:
	kubectl logs -n $(NAMESPACE) deployment/taskservice -f

status:
	kubectl get pods,svc,pvc,ingress -n $(NAMESPACE)

clean:
	k3d cluster delete taskcluster
```

---

## Gotchas

1. **Image name in Deployment** — use `k3d-taskregistry:5000/...` (the in-cluster DNS name), not `localhost:5000/...` (which is only valid on your host machine).
2. **`imagePullPolicy: Always`** — required when using the same tag (`latest`) so the cluster always pulls the updated image.
3. **PVC is `ReadWriteOnce`** — can only be mounted by one node. Don't scale Deployment replicas > 1 with this PVC type and file store.
4. **`fsGroup` in securityContext** — needed so the mounted volume is writable by the non-root user inside the container.
5. **k3d registry DNS** — inside the cluster, the registry is `k3d-taskregistry:5000`. On your host machine it's `localhost:5000`.

---

## Practice

1. Deploy the complete service end-to-end on k3d and create/list/delete tasks.
2. Verify persistence: kill the Pod, wait for it to restart, confirm tasks survived.
3. Add a `ConfigMap` for non-sensitive config (log level, max request size) and mount it as an env var.
4. Write a Kubernetes `CronJob` that calls `GET /tasks?status=todo` every minute and logs overdue tasks.

---

## Key Takeaways

- `k3d cluster create` gives you a full Kubernetes cluster in seconds — no cloud needed.
- Multi-stage Docker builds keep the final image minimal (~8 MB for a Go binary).
- Push to the k3d local registry (`localhost:5000`) — no Docker Hub required.
- `ReadWriteOnce` PVC + single replica = safe file store; scale beyond 1 requires a real database.
- Liveness + readiness probes are essential — without them, Kubernetes can't tell if your service is healthy.
