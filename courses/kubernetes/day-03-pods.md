# Day 03 — Pods

## Learning Objectives
- Understand what a Pod is and why it's the basic unit
- Write Pod manifests with multiple containers
- Configure environment variables, commands, and args
- Understand Pod lifecycle and restart policies

---

## What Is a Pod?

A Pod is one or more containers that share:
- **Network namespace** — same IP address, communicate via localhost
- **Storage** — can share volumes
- **Lifecycle** — scheduled and killed together

You rarely create Pods directly — Deployments manage them. But understanding Pods is foundational.

---

## Minimal Pod

```yaml
# pod-minimal.yaml
apiVersion: v1
kind: Pod
metadata:
  name: nginx
  namespace: default
  labels:
    app: nginx
spec:
  containers:
    - name: nginx
      image: nginx:alpine       # always pin a version in production
      ports:
        - containerPort: 80     # informational only — doesn't actually expose anything
```

```bash
kubectl apply -f pod-minimal.yaml
kubectl get pods
kubectl describe pod nginx
kubectl port-forward pod/nginx 8080:80
curl http://localhost:8080
```

---

## Pod with Environment Variables

```yaml
# pod-env.yaml
apiVersion: v1
kind: Pod
metadata:
  name: app-with-env
spec:
  containers:
    - name: app
      image: busybox:1.36
      command: ["sh", "-c", "echo $APP_ENV $DB_HOST && sleep 3600"]
      env:
        - name: APP_ENV
          value: "production"
        - name: DB_HOST
          value: "postgres.default.svc.cluster.local"
        - name: POD_NAME              # inject pod metadata
          valueFrom:
            fieldRef:
              fieldPath: metadata.name
        - name: POD_NAMESPACE
          valueFrom:
            fieldRef:
              fieldPath: metadata.namespace
        - name: MEMORY_LIMIT          # inject resource limits
          valueFrom:
            resourceFieldRef:
              containerName: app
              resource: limits.memory
```

```bash
kubectl apply -f pod-env.yaml
kubectl logs app-with-env
# production postgres.default.svc.cluster.local
```

---

## Pod with Command and Args

```yaml
# pod-command.yaml
apiVersion: v1
kind: Pod
metadata:
  name: counter
spec:
  containers:
    - name: counter
      image: busybox:1.36
      command: ["/bin/sh"]      # overrides the image ENTRYPOINT
      args:
        - "-c"
        - |
          i=0
          while true; do
            echo "count: $i"
            i=$((i+1))
            sleep 1
          done
```

```bash
kubectl apply -f pod-command.yaml
kubectl logs counter -f
```

---

## Multi-Container Pod (Sidecar Pattern)

Both containers share the same network and can share volumes:

```yaml
# pod-sidecar.yaml
apiVersion: v1
kind: Pod
metadata:
  name: app-with-sidecar
spec:
  volumes:
    - name: shared-logs
      emptyDir: {}             # temporary directory shared between containers

  containers:
    - name: app
      image: busybox:1.36
      command: ["sh", "-c", "while true; do echo $(date) >> /logs/app.log; sleep 2; done"]
      volumeMounts:
        - name: shared-logs
          mountPath: /logs

    - name: log-reader         # sidecar reads logs written by app
      image: busybox:1.36
      command: ["sh", "-c", "tail -f /logs/app.log"]
      volumeMounts:
        - name: shared-logs
          mountPath: /logs
```

```bash
kubectl apply -f pod-sidecar.yaml
kubectl logs app-with-sidecar -c log-reader -f
```

---

## Resource Requests and Limits

```yaml
# pod-resources.yaml
apiVersion: v1
kind: Pod
metadata:
  name: resource-demo
spec:
  containers:
    - name: app
      image: nginx:alpine
      resources:
        requests:             # minimum guaranteed resources
          cpu: "100m"         # 100 millicores = 0.1 CPU core
          memory: "64Mi"      # 64 mebibytes
        limits:               # maximum allowed — container killed if exceeded
          cpu: "500m"
          memory: "256Mi"
```

---

## Restart Policies

```yaml
# pod-restart.yaml
apiVersion: v1
kind: Pod
metadata:
  name: restart-demo
spec:
  restartPolicy: Always       # Always (default) | OnFailure | Never

  containers:
    - name: app
      image: busybox:1.36
      command: ["sh", "-c", "echo hello && exit 1"]   # always fails
```

| Policy | Behaviour |
|---|---|
| `Always` | Always restart (default — for long-running services) |
| `OnFailure` | Restart only on non-zero exit (for Jobs) |
| `Never` | Never restart (for one-shot tasks) |

---

## Init Containers

Init containers run to completion **before** any app containers start. Use them for setup tasks.

```yaml
# pod-init.yaml
apiVersion: v1
kind: Pod
metadata:
  name: init-demo
spec:
  initContainers:
    - name: wait-for-db
      image: busybox:1.36
      command: ['sh', '-c', 'until nc -z postgres 5432; do echo waiting for db; sleep 2; done']

    - name: run-migrations
      image: myapp:latest
      command: ["./migrate", "up"]
      env:
        - name: DB_URL
          value: "postgres://postgres:5432/mydb"

  containers:
    - name: app
      image: myapp:latest
      command: ["./server"]
```

Init containers run sequentially. The app container only starts after all init containers succeed.

---

## Pod Lifecycle

```
Pending → Running → Succeeded / Failed
                 ↘ Unknown (node lost)
```

| Phase | Meaning |
|---|---|
| `Pending` | Accepted by cluster but not yet scheduled or images still pulling |
| `Running` | At least one container is running |
| `Succeeded` | All containers exited with code 0 |
| `Failed` | At least one container exited with non-zero code |
| `Unknown` | Node communication lost |

```bash
kubectl get pod nginx -o jsonpath='{.status.phase}'
kubectl get pod nginx -o jsonpath='{.status.conditions[*].type}'
```

---

## Debugging a Failing Pod

```bash
# Step 1: get phase and conditions
kubectl describe pod my-pod

# Step 2: check logs
kubectl logs my-pod
kubectl logs my-pod --previous        # if it crashed and restarted

# Step 3: exec in if it's running
kubectl exec -it my-pod -- /bin/sh

# Step 4: debug with an ephemeral container (k8s 1.23+)
kubectl debug -it my-pod --image=busybox --target=app
```

---

## Gotchas

1. **`containerPort` is documentation only** — it doesn't open a firewall port. Services handle routing.
2. **Pods are mortal** — when a Pod dies and is replaced, it gets a new IP. Never hardcode Pod IPs.
3. **`image: nginx` without a tag pulls `latest`** — always pin: `nginx:1.25-alpine`.
4. **Multi-container pods share the network** — if container A listens on 8080, container B reaches it at `localhost:8080`.

---

## Practice

1. Run an nginx Pod and port-forward to access it on `localhost:8080`.
2. Create a Pod that prints its own name and namespace using `fieldRef`.
3. Create a multi-container Pod where container A writes to a shared volume and container B reads from it.
4. Create a Pod with `restartPolicy: Never` that exits with code 1 — observe the `Error` status.

---

## Key Takeaways

- A Pod is one or more containers sharing network and storage — it's the atomic unit of Kubernetes.
- Multi-container Pods share `localhost` — perfect for sidecar patterns (logging, proxies).
- Init containers run sequentially before app containers — use for DB waits and migrations.
- Pods are ephemeral — use Deployments to manage them, never run naked Pods in production.
