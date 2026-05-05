# Day 03 — Built-in Components

## Learning Objectives
- Use all five built-in component types: webservice, worker, task, cron-task, daemon
- Configure component properties: image, env, resources, volumes, health checks
- Run multiple components in one Application
- Understand when to use each component type

---

## Component Types Overview

| Type | Kubernetes Kind | Use For |
|---|---|---|
| `webservice` | Deployment + Service | HTTP APIs, web apps — receives traffic |
| `worker` | Deployment | Background processing — no inbound traffic |
| `task` | Job | One-shot work: migrations, batch jobs |
| `cron-task` | CronJob | Scheduled recurring work |
| `daemon` | DaemonSet | Node-level agents: log shippers, monitors |

---

## webservice — Full Example

```yaml
# app-webservice.yaml
apiVersion: core.oam.dev/v1beta1
kind: Application
metadata:
  name: api-app
  namespace: production
spec:
  components:
    - name: api
      type: webservice
      properties:
        image: myapi:2.0
        imagePullPolicy: IfNotPresent

        port: 8080                  # container port (also creates a Service on this port)
        replicas: 3

        # Environment variables
        env:
          - name: APP_ENV
            value: production
          - name: LOG_LEVEL
            value: info
          - name: DB_PASSWORD
            valueFrom:
              secretKeyRef:
                name: db-secret
                key: password

        # CPU and memory
        cpu: "500m"
        memory: "512Mi"

        # Override the container command
        cmd:
          - ./server
          - --config=/etc/config/app.yaml

        # Volume mounts
        volumeMounts:
          - name: config
            mountPath: /etc/config
            configMap:
              name: app-config       # references a ConfigMap in the same namespace
          - name: tmp
            mountPath: /tmp
            emptyDir: {}

        # Liveness and readiness probes
        livenessProbe:
          httpGet:
            path: /health/live
            port: 8080
          initialDelaySeconds: 30
          periodSeconds: 10

        readinessProbe:
          httpGet:
            path: /health/ready
            port: 8080
          initialDelaySeconds: 5
          periodSeconds: 5

        # Expose additional ports (the primary port is already exposed)
        exposeType: ClusterIP        # ClusterIP | NodePort | LoadBalancer
```

---

## worker — Background Service

```yaml
# app-worker.yaml
apiVersion: core.oam.dev/v1beta1
kind: Application
metadata:
  name: worker-app
  namespace: production
spec:
  components:
    - name: queue-processor
      type: worker                  # Deployment with no Service — no inbound traffic
      properties:
        image: myworker:1.0
        replicas: 2

        cmd:
          - ./worker
          - --queue=tasks
          - --concurrency=5

        env:
          - name: QUEUE_URL
            value: redis://redis:6379
          - name: APP_ENV
            value: production

        cpu: "250m"
        memory: "256Mi"

        livenessProbe:
          exec:
            command:
              - sh
              - -c
              - "pgrep worker"       # check the process is still running
          periodSeconds: 30
```

---

## task — One-Shot Job

```yaml
# app-task.yaml
apiVersion: core.oam.dev/v1beta1
kind: Application
metadata:
  name: db-migration
  namespace: production
spec:
  components:
    - name: migrate
      type: task
      properties:
        image: myapp:2.0
        cmd:
          - ./migrate
          - --direction=up
          - --env=production

        env:
          - name: DATABASE_URL
            valueFrom:
              secretKeyRef:
                name: db-secret
                key: url

        count: 1                    # number of Job completions required
        restart: Never              # OnFailure | Never
```

```bash
# Check job status
vela status db-migration
# NAME          COMPONENT   TYPE   PHASE       HEALTHY
# db-migration  migrate     task   succeeded   true
```

---

## cron-task — Scheduled Job

```yaml
# app-cron.yaml
apiVersion: core.oam.dev/v1beta1
kind: Application
metadata:
  name: nightly-report
  namespace: production
spec:
  components:
    - name: report-generator
      type: cron-task
      properties:
        image: myreporter:1.0
        cmd:
          - ./generate-report
          - --output=s3://my-bucket/reports

        schedule: "0 2 * * *"      # 2am every day (cron syntax)

        # Keep last 3 successful and 1 failed job
        successfulJobHistoryLimit: 3
        failedJobHistoryLimit: 1

        env:
          - name: AWS_REGION
            value: us-east-1
          - name: REPORT_FORMAT
            value: pdf

        cpu: "100m"
        memory: "256Mi"
```

---

## daemon — Node Agent

```yaml
# app-daemon.yaml
apiVersion: core.oam.dev/v1beta1
kind: Application
metadata:
  name: log-agent
  namespace: kube-system
spec:
  components:
    - name: fluent-bit
      type: daemon                  # DaemonSet — runs on every node
      properties:
        image: fluent/fluent-bit:2.2

        volumeMounts:
          - name: varlog
            mountPath: /var/log
            hostPath:
              path: /var/log        # mount host /var/log
          - name: varlibdockercontainers
            mountPath: /var/lib/docker/containers
            hostPath:
              path: /var/lib/docker/containers
            readOnly: true

        env:
          - name: LOG_LEVEL
            value: info

        cpu: "50m"
        memory: "64Mi"
```

---

## Multi-Component Application

A real app typically has multiple components in one Application:

```yaml
# app-full.yaml
apiVersion: core.oam.dev/v1beta1
kind: Application
metadata:
  name: taskapp
  namespace: production
spec:
  components:
    # API server — receives HTTP traffic
    - name: api
      type: webservice
      properties:
        image: taskapp-api:1.0
        port: 8080
        replicas: 2
        cpu: "500m"
        memory: "512Mi"
        env:
          - name: REDIS_URL
            value: redis://redis:6379
          - name: DB_HOST
            value: postgres
      traits:
        - type: ingress
          properties:
            domain: api.taskapp.local
            http:
              "/": 8080

    # Background worker — processes task queue
    - name: worker
      type: worker
      properties:
        image: taskapp-worker:1.0
        replicas: 2
        cpu: "250m"
        memory: "256Mi"
        env:
          - name: QUEUE_URL
            value: redis://redis:6379

    # Scheduled cleanup job
    - name: cleanup
      type: cron-task
      properties:
        image: taskapp-api:1.0
        cmd: ["./cleanup", "--older-than=30d"]
        schedule: "0 3 * * 0"     # 3am every Sunday
        cpu: "100m"
        memory: "128Mi"
```

---

## Checking Component Health

```bash
# Overall application status
vela status taskapp

# Hierarchical view of all components and their resources
vela status taskapp --tree
# APPLICATION   CLUSTER   NAMESPACE    COMPONENT   RESOURCE           STATUS
# taskapp       local     production   api         Deployment/api     Ready:2/2
# taskapp       local     production   api         Service/api        -
# taskapp       local     production   api         Ingress/api        -
# taskapp       local     production   worker      Deployment/worker  Ready:2/2
# taskapp       local     production   cleanup     CronJob/cleanup    -

# Logs from a specific component
vela logs taskapp --component worker

# Exec into a component
vela exec taskapp --component api -- sh
```

---

## Gotchas

1. **`task` type reruns on Application update** — if you update any property of a `task` component, the Job runs again. Use separate Applications for one-shot migrations.
2. **`worker` has no Service** — it cannot receive inbound traffic by design. If you need internal communication, use `webservice` instead.
3. **`daemon` on k3d** — k3d nodes are Docker containers. DaemonSets work, but `hostPath` volumes point to paths inside the container node, not your host machine.
4. **`replicas` ignored for `task` and `cron-task`** — use `count` (completions) for tasks instead.

---

## Practice

1. Deploy a `webservice` with a liveness probe and an env var from a Secret. Verify the probe is set on the generated Deployment.
2. Deploy a `worker` alongside a `webservice` in the same Application. Verify the worker has no Service.
3. Create a `cron-task` that runs every minute. Watch the Jobs it creates with `kubectl get jobs -w`.
4. Run `vela status myapp --tree` and trace each line back to the corresponding Kubernetes resource.

---

## Key Takeaways

- `webservice` = Deployment + Service (receives traffic). `worker` = Deployment only (no traffic).
- `task` and `cron-task` map to Job and CronJob. `daemon` maps to DaemonSet.
- Multiple components in one Application share lifecycle — deleting the Application removes all of them.
- `vela status --tree` shows the full resource hierarchy KubeVela is managing.
