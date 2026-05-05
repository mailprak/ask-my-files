# Day 20 — Init Containers & Sidecars

## Learning Objectives
- Use init containers for setup tasks before the app starts
- Implement the sidecar pattern for logging, proxying, and syncing
- Use native sidecar containers (k8s 1.29+)
- Share data between containers via volumes

---

## Init Containers

Init containers run to completion **sequentially** before any app container starts. If an init container fails, the Pod restarts.

```yaml
# pod-init-full.yaml
apiVersion: v1
kind: Pod
metadata:
  name: app-with-init
spec:
  initContainers:
    # Step 1: wait for the database to be ready
    - name: wait-for-db
      image: busybox:1.36
      command:
        - sh
        - -c
        - |
          echo "Waiting for postgres..."
          until nc -z postgres.default.svc.cluster.local 5432; do
            echo "postgres not ready, sleeping..."
            sleep 2
          done
          echo "postgres is ready!"

    # Step 2: run database migrations
    - name: run-migrations
      image: myapp:2.0
      command: ["./migrate", "--direction=up"]
      env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: db-secret
              key: url

    # Step 3: download config from S3
    - name: fetch-config
      image: amazon/aws-cli:latest
      command:
        - sh
        - -c
        - aws s3 cp s3://my-bucket/config/app.yaml /config/app.yaml
      volumeMounts:
        - name: config-vol
          mountPath: /config
      env:
        - name: AWS_DEFAULT_REGION
          value: us-east-1

  containers:
    - name: app
      image: myapp:2.0
      command: ["./server", "--config=/config/app.yaml"]
      volumeMounts:
        - name: config-vol
          mountPath: /config
          readOnly: true

  volumes:
    - name: config-vol
      emptyDir: {}
```

---

## Sidecar Pattern — Log Shipping

The log-shipping sidecar reads log files written by the app and ships them to a central log system:

```yaml
# pod-log-sidecar.yaml
apiVersion: v1
kind: Pod
metadata:
  name: app-with-logger
spec:
  volumes:
    - name: log-vol
      emptyDir: {}

  containers:
    # Main app — writes logs to a file
    - name: app
      image: myapp:2.0
      command:
        - sh
        - -c
        - |
          while true; do
            echo "$(date) - processing request" >> /logs/app.log
            sleep 1
          done
      volumeMounts:
        - name: log-vol
          mountPath: /logs

    # Sidecar — ships logs to Elasticsearch
    - name: log-shipper
      image: fluent/fluent-bit:2.2
      volumeMounts:
        - name: log-vol
          mountPath: /logs
          readOnly: true
        - name: fluent-bit-config
          mountPath: /fluent-bit/etc/
      resources:
        requests:
          cpu: "50m"
          memory: "50Mi"
        limits:
          cpu: "100m"
          memory: "100Mi"

  volumes:
    - name: log-vol
      emptyDir: {}
    - name: fluent-bit-config
      configMap:
        name: fluent-bit-config
```

---

## Sidecar Pattern — Envoy Proxy

The proxy sidecar intercepts all network traffic for the Pod:

```yaml
# pod-envoy-sidecar.yaml
apiVersion: v1
kind: Pod
metadata:
  name: app-with-proxy
  annotations:
    sidecar.istio.io/inject: "false"   # we're doing it manually
spec:
  containers:
    - name: app
      image: myapp:2.0
      ports:
        - containerPort: 8080
      # App only listens on localhost — proxy handles external traffic
      env:
        - name: LISTEN_ADDR
          value: "127.0.0.1:8080"

    - name: envoy-proxy
      image: envoyproxy/envoy:v1.28
      ports:
        - name: http
          containerPort: 80       # external traffic comes in here
        - name: admin
          containerPort: 9901     # envoy admin interface
      volumeMounts:
        - name: envoy-config
          mountPath: /etc/envoy
      command: ["envoy", "-c", "/etc/envoy/envoy.yaml"]
      resources:
        requests:
          cpu: "100m"
          memory: "128Mi"

  volumes:
    - name: envoy-config
      configMap:
        name: envoy-config
```

---

## Sidecar Pattern — Config Sync (Git Sync)

Keep config files up-to-date by syncing from Git:

```yaml
# pod-git-sync.yaml
apiVersion: v1
kind: Pod
metadata:
  name: nginx-with-git-config
spec:
  initContainers:
    - name: git-clone
      image: alpine/git:latest
      command:
        - git
        - clone
        - https://github.com/myorg/nginx-config.git
        - /config
      volumeMounts:
        - name: config-vol
          mountPath: /config

  containers:
    - name: nginx
      image: nginx:alpine
      volumeMounts:
        - name: config-vol
          mountPath: /etc/nginx/conf.d
          readOnly: true

    - name: git-sync
      image: registry.k8s.io/git-sync/git-sync:v4.1.0
      args:
        - --repo=https://github.com/myorg/nginx-config.git
        - --branch=main
        - --root=/config
        - --period=60s              # sync every 60 seconds
        - --one-time=false
      volumeMounts:
        - name: config-vol
          mountPath: /config
      resources:
        requests:
          cpu: "10m"
          memory: "16Mi"

  volumes:
    - name: config-vol
      emptyDir: {}
```

---

## Native Sidecar Containers (k8s 1.29+)

Regular sidecars have a problem: they may start before the app is ready or outlive it. Native sidecars fix this:

```yaml
# pod-native-sidecar.yaml (k8s 1.29+)
apiVersion: v1
kind: Pod
metadata:
  name: app-native-sidecar
spec:
  initContainers:
    - name: log-shipper          # declared as initContainer but with restartPolicy
      image: fluent/fluent-bit:2.2
      restartPolicy: Always       # ← makes this a native sidecar container
                                  # starts before app, stays alive with app
      volumeMounts:
        - name: log-vol
          mountPath: /logs
          readOnly: true

  containers:
    - name: app
      image: myapp:2.0
      volumeMounts:
        - name: log-vol
          mountPath: /logs

  volumes:
    - name: log-vol
      emptyDir: {}
```

Native sidecars:
- Start after init containers, before app containers
- Restart if they die (unlike regular sidecars — if a regular sidecar dies, the pod doesn't restart)
- Terminate after app containers (so logs aren't lost)

---

## Shared Memory Between Containers

```yaml
# pod-shared-memory.yaml
apiVersion: v1
kind: Pod
metadata:
  name: shared-mem-demo
spec:
  containers:
    - name: writer
      image: busybox:1.36
      command: ["sh", "-c", "while true; do echo hello > /dev/shm/data; sleep 1; done"]
      volumeMounts:
        - name: shm
          mountPath: /dev/shm

    - name: reader
      image: busybox:1.36
      command: ["sh", "-c", "while true; do cat /dev/shm/data; sleep 1; done"]
      volumeMounts:
        - name: shm
          mountPath: /dev/shm

  volumes:
    - name: shm
      emptyDir:
        medium: Memory      # memory-backed tmpfs — fast shared memory
        sizeLimit: 64Mi
```

---

## Deployment with Init + Sidecar

```yaml
# deployment-init-sidecar.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: full-stack-app
spec:
  replicas: 3
  selector:
    matchLabels:
      app: full-stack-app
  template:
    metadata:
      labels:
        app: full-stack-app
    spec:
      initContainers:
        - name: wait-for-db
          image: busybox:1.36
          command: ['sh', '-c', 'until nc -z postgres 5432; do sleep 2; done']

      containers:
        - name: app
          image: myapp:2.0
          ports:
            - containerPort: 8080
          resources:
            requests:
              cpu: "200m"
              memory: "256Mi"
            limits:
              cpu: "1"
              memory: "512Mi"
          volumeMounts:
            - name: logs
              mountPath: /app/logs

        - name: log-agent
          image: fluent/fluent-bit:2.2
          resources:
            requests:
              cpu: "50m"
              memory: "64Mi"
            limits:
              cpu: "100m"
              memory: "128Mi"
          volumeMounts:
            - name: logs
              mountPath: /logs
              readOnly: true

      volumes:
        - name: logs
          emptyDir: {}
```

---

## Gotchas

1. **Init containers run sequentially** — if init container 1 fails, container 2 never starts.
2. **Sidecar dies = pod doesn't restart** — in regular sidecars, the Pod only restarts if the main container fails. Monitor sidecar health separately.
3. **Resource requests apply to each container independently** — a Pod with a 256Mi app + 64Mi sidecar requires 320Mi total capacity on the node.
4. **`emptyDir` is ephemeral** — data in `emptyDir` is lost when the Pod is deleted. Use PVCs for persistence.

---

## Practice

1. Write an init container that waits for a Service to exist before the app starts.
2. Create a sidecar that tails `/logs/app.log` and writes to stdout. View it with `kubectl logs pod -c sidecar`.
3. Use an `emptyDir` volume to pass a generated config file from an init container to the main app.
4. Use native sidecars (if on k8s 1.29+) and compare the startup sequence vs regular sidecars.

---

## Key Takeaways

- Init containers: sequential setup before app starts — DB waits, migrations, config downloads.
- Sidecars: co-located helpers (logging, proxying, syncing) that run alongside the main app.
- Share data between containers using `emptyDir` volumes — memory-backed for shared memory, disk for files.
- Native sidecars (k8s 1.29+) have proper lifecycle management — they start and stop in sync with the app.
