# Day 16 — Health Probes (Liveness, Readiness, Startup)

## Learning Objectives
- Configure Liveness, Readiness, and Startup probes
- Choose the right probe type (HTTP, TCP, exec, gRPC)
- Tune probe thresholds to avoid false positives
- Understand what happens when each probe fails

---

## Three Types of Probes

| Probe | Failure Action | Purpose |
|---|---|---|
| **Liveness** | Restart the container | Detect deadlock / hung process |
| **Readiness** | Remove from Service endpoints | Stop traffic during startup/overload |
| **Startup** | Restart the container | Give slow-starting apps time to boot |

---

## HTTP Probe

```yaml
# probes-http.yaml
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
          ports:
            - containerPort: 8080

          startupProbe:
            httpGet:
              path: /health
              port: 8080
              httpHeaders:
                - name: Accept
                  value: application/json
            initialDelaySeconds: 0    # start checking immediately
            periodSeconds: 5          # check every 5 seconds
            failureThreshold: 24      # allow up to 24*5=120 seconds to start
            successThreshold: 1       # 1 success = startup complete

          readinessProbe:
            httpGet:
              path: /ready            # separate endpoint — checks DB, cache etc.
              port: 8080
            initialDelaySeconds: 5
            periodSeconds: 10
            failureThreshold: 3       # 3 failures → removed from endpoints
            successThreshold: 1       # 1 success → added back

          livenessProbe:
            httpGet:
              path: /health
              port: 8080
            initialDelaySeconds: 30   # give startup probe time to complete first
            periodSeconds: 20
            failureThreshold: 3       # 3 failures → container restarted
            successThreshold: 1       # always 1 for liveness
            timeoutSeconds: 5         # probe must respond within 5s
```

---

## TCP Probe

For services that don't have HTTP endpoints:

```yaml
# probes-tcp.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: postgres
spec:
  replicas: 1
  selector:
    matchLabels:
      app: postgres
  template:
    metadata:
      labels:
        app: postgres
    spec:
      containers:
        - name: postgres
          image: postgres:16-alpine
          ports:
            - containerPort: 5432

          startupProbe:
            tcpSocket:
              port: 5432
            periodSeconds: 5
            failureThreshold: 30     # 150s to start

          readinessProbe:
            tcpSocket:
              port: 5432
            periodSeconds: 10
            failureThreshold: 3

          livenessProbe:
            tcpSocket:
              port: 5432
            periodSeconds: 20
            failureThreshold: 3
```

---

## Exec Probe

Run a command inside the container — healthy if exit code is 0:

```yaml
# probes-exec.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: postgres-exec
spec:
  replicas: 1
  selector:
    matchLabels:
      app: postgres-exec
  template:
    metadata:
      labels:
        app: postgres-exec
    spec:
      containers:
        - name: postgres
          image: postgres:16-alpine
          env:
            - name: POSTGRES_PASSWORD
              value: "password"
            - name: POSTGRES_USER
              value: "myuser"

          readinessProbe:
            exec:
              command:
                - /bin/sh
                - -c
                - pg_isready -U myuser -d postgres
            periodSeconds: 10
            failureThreshold: 3
            initialDelaySeconds: 10

          livenessProbe:
            exec:
              command:
                - /bin/sh
                - -c
                - |
                  pg_isready -U myuser && \
                  psql -U myuser -c "SELECT 1" > /dev/null
            periodSeconds: 30
            failureThreshold: 3
            initialDelaySeconds: 30
```

---

## gRPC Probe (k8s 1.24+)

```yaml
livenessProbe:
  grpc:
    port: 9090
    service: "grpc.health.v1.Health"   # standard gRPC health service name
  periodSeconds: 10
  failureThreshold: 3
```

---

## Separate /health and /ready Endpoints

Your app should expose two different endpoints:

```go
// Go example
http.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
    // Liveness: is the process alive and not deadlocked?
    w.WriteHeader(http.StatusOK)
    json.NewEncoder(w).Encode(map[string]string{"status": "ok"})
})

http.HandleFunc("/ready", func(w http.ResponseWriter, r *http.Request) {
    // Readiness: can I handle traffic right now?
    // Check: DB connection, cache connection, required config loaded
    if !db.Ping() || !cache.Ping() {
        w.WriteHeader(http.StatusServiceUnavailable)
        json.NewEncoder(w).Encode(map[string]string{"status": "not ready"})
        return
    }
    w.WriteHeader(http.StatusOK)
    json.NewEncoder(w).Encode(map[string]string{"status": "ready"})
})
```

---

## Complete Probe Configuration Reference

```yaml
livenessProbe:
  httpGet:
    path: /health
    port: 8080
    scheme: HTTP              # HTTP | HTTPS
  initialDelaySeconds: 30     # wait before first probe (use startupProbe instead)
  periodSeconds: 10           # how often to probe
  timeoutSeconds: 5           # probe timeout (default: 1)
  successThreshold: 1         # successes to mark healthy (must be 1 for liveness)
  failureThreshold: 3         # failures before action is taken
  terminationGracePeriodSeconds: 60  # override pod-level termination grace period
```

---

## Startup Probe — The Right Way to Handle Slow Starts

Without startup probe, slow-starting apps often get killed by liveness probes:

```yaml
# BAD: using initialDelaySeconds on liveness for slow apps
livenessProbe:
  httpGet:
    path: /health
    port: 8080
  initialDelaySeconds: 120    # hope it starts within 2 minutes
  periodSeconds: 10

# GOOD: startup probe handles the wait, liveness is tight
startupProbe:
  httpGet:
    path: /health
    port: 8080
  periodSeconds: 5
  failureThreshold: 60        # 5*60 = 5 minutes to start
  # once startup probe succeeds, liveness and readiness take over

livenessProbe:
  httpGet:
    path: /health
    port: 8080
  periodSeconds: 10
  failureThreshold: 3         # tight — 30 seconds to recover
```

---

## Observing Probe Behaviour

```bash
kubectl describe pod my-pod
# Events:
#   Warning  Unhealthy   2m  kubelet  Liveness probe failed: Get "http://172.16.0.5:8080/health": ...
#   Warning  BackOff     1m  kubelet  Back-off restarting failed container

kubectl get pods
# NAME       READY   STATUS             RESTARTS
# my-pod     0/1     CrashLoopBackOff   5        ← liveness killing and restarting
# my-pod     0/1     Running            0        ← readiness not passed yet (0/1)
# my-pod     1/1     Running            0        ← all probes passing

# Watch restart count
kubectl get pods -w
```

---

## Gotchas

1. **Liveness probe killing healthy pods** — if liveness is too aggressive (timeout too short, threshold too low), it restarts healthy pods. Start with loose thresholds and tighten.
2. **Readiness probe not configured** — Pods receive traffic immediately at startup, before the app is ready. Always configure readiness.
3. **`initialDelaySeconds` as a crutch** — guessing startup time is fragile. Use `startupProbe` instead.
4. **Liveness probe hitting the DB** — if liveness checks DB connectivity, a DB outage restarts all pods. Liveness should only check the app process itself.

---

## Practice

1. Deploy an app with all three probes. Kill the process inside the container — observe liveness triggering a restart.
2. Deploy without a readiness probe, then with one. Compare how traffic is handled at startup.
3. Deliberately make the readiness endpoint return 503. Watch the Pod removed from Service endpoints.
4. Configure a startup probe that allows 3 minutes to start, with a tight liveness probe after.

---

## Key Takeaways

- Liveness = is the process alive (restart if dead). Readiness = can it take traffic (remove from LB if not).
- Use Startup probe for slow-starting apps — don't rely on `initialDelaySeconds`.
- `/health` for liveness (process check only), `/ready` for readiness (dependency checks).
- Probe failures are noisy — tune thresholds carefully before going to production.
