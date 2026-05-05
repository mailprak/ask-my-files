# Day 10 — StatefulSets

## Learning Objectives
- Understand what makes StatefulSets different from Deployments
- Deploy a stateful application with stable network identity and storage
- Manage StatefulSet scaling and updates
- Use headless Services with StatefulSets

---

## Why StatefulSets?

Deployments treat all Pods as interchangeable. StatefulSets give each Pod:
- **Stable hostname**: `pod-0`, `pod-1`, `pod-2` (not random hash)
- **Stable DNS**: `pod-0.service.namespace.svc.cluster.local`
- **Stable storage**: each pod gets its own PVC that persists across restarts
- **Ordered startup/shutdown**: pod-0 starts first, pod-2 shuts down first

Use for: databases (Postgres, MySQL), Kafka, ZooKeeper, Redis clusters.

---

## Complete StatefulSet — PostgreSQL Example

```yaml
# statefulset-postgres.yaml
apiVersion: v1
kind: Service
metadata:
  name: postgres-headless
  namespace: default
  labels:
    app: postgres
spec:
  clusterIP: None             # headless — required for StatefulSet DNS
  selector:
    app: postgres
  ports:
    - name: postgres
      port: 5432
      targetPort: 5432
---
apiVersion: v1
kind: Service
metadata:
  name: postgres              # regular service for read access
  namespace: default
spec:
  selector:
    app: postgres
  ports:
    - port: 5432
      targetPort: 5432
---
apiVersion: v1
kind: Secret
metadata:
  name: postgres-secret
  namespace: default
type: Opaque
stringData:
  POSTGRES_USER: "myuser"
  POSTGRES_PASSWORD: "mysecretpassword"
  POSTGRES_DB: "mydb"
---
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: postgres
  namespace: default
spec:
  serviceName: postgres-headless    # MUST reference the headless service

  replicas: 3

  selector:
    matchLabels:
      app: postgres

  updateStrategy:
    type: RollingUpdate
    rollingUpdate:
      partition: 0             # update all pods; set to N to only update pods >= N

  podManagementPolicy: OrderedReady  # OrderedReady | Parallel

  template:
    metadata:
      labels:
        app: postgres
    spec:
      terminationGracePeriodSeconds: 60

      containers:
        - name: postgres
          image: postgres:16-alpine

          ports:
            - name: postgres
              containerPort: 5432

          envFrom:
            - secretRef:
                name: postgres-secret

          env:
            - name: PGDATA
              value: /var/lib/postgresql/data/pgdata   # data dir inside mount

          resources:
            requests:
              cpu: "250m"
              memory: "256Mi"
            limits:
              cpu: "1000m"
              memory: "1Gi"

          volumeMounts:
            - name: postgres-data
              mountPath: /var/lib/postgresql/data

          readinessProbe:
            exec:
              command:
                - /bin/sh
                - -c
                - pg_isready -U $(POSTGRES_USER) -d $(POSTGRES_DB)
            initialDelaySeconds: 10
            periodSeconds: 10
            failureThreshold: 6

          livenessProbe:
            exec:
              command:
                - /bin/sh
                - -c
                - pg_isready -U $(POSTGRES_USER)
            initialDelaySeconds: 30
            periodSeconds: 20
            failureThreshold: 3

  # Each pod gets its OWN PVC created automatically
  volumeClaimTemplates:
    - metadata:
        name: postgres-data
      spec:
        accessModes: ["ReadWriteOnce"]
        storageClassName: local-path    # k3d default storage class
        resources:
          requests:
            storage: 5Gi
```

```bash
kubectl apply -f statefulset-postgres.yaml

# Pods come up in order: postgres-0, then postgres-1, then postgres-2
kubectl get pods -l app=postgres -w

# Each pod gets its own PVC
kubectl get pvc
# NAME                    STATUS   VOLUME    CAPACITY   ACCESS MODES
# postgres-data-postgres-0  Bound  pvc-abc   5Gi        RWO
# postgres-data-postgres-1  Bound  pvc-def   5Gi        RWO
# postgres-data-postgres-2  Bound  pvc-ghi   5Gi        RWO
```

---

## Stable DNS Names

Each StatefulSet Pod gets a DNS entry via the headless Service:

```
postgres-0.postgres-headless.default.svc.cluster.local
postgres-1.postgres-headless.default.svc.cluster.local
postgres-2.postgres-headless.default.svc.cluster.local
```

Applications can always reach a specific Pod by name — essential for Postgres primary/replica setup.

```bash
# Test DNS from inside a pod
kubectl exec -it postgres-0 -- psql -U myuser -d mydb -c "SELECT version();"

# Connect to a specific replica
kubectl exec -it some-pod -- psql -h postgres-1.postgres-headless -U myuser mydb
```

---

## Scaling StatefulSets

```bash
# Scale up — new pods are added in order (postgres-3, postgres-4)
kubectl scale statefulset postgres --replicas=5

# Scale down — pods are removed in REVERSE order (postgres-4 first)
kubectl scale statefulset postgres --replicas=2

# PVCs are NOT deleted when scaling down — data is preserved
kubectl get pvc   # postgres-data-postgres-2 through 4 still exist
```

---

## Partition-Based Rolling Update

Update only a subset of pods (useful for canary testing within a StatefulSet):

```yaml
updateStrategy:
  type: RollingUpdate
  rollingUpdate:
    partition: 2    # only update pods with ordinal >= 2 (postgres-2)
                    # postgres-0 and postgres-1 stay on old version
```

```bash
kubectl patch statefulset postgres -p '{"spec":{"updateStrategy":{"rollingUpdate":{"partition":2}}}}'
kubectl set image statefulset/postgres postgres=postgres:17-alpine
# Only postgres-2 updates; postgres-0 and postgres-1 stay on postgres:16-alpine

# After verifying postgres-2 is healthy, update the rest
kubectl patch statefulset postgres -p '{"spec":{"updateStrategy":{"rollingUpdate":{"partition":0}}}}'
```

---

## Redis Cluster StatefulSet

```yaml
# statefulset-redis.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: redis-config
data:
  redis.conf: |
    appendonly yes
    protected-mode no
    cluster-enabled yes
    cluster-config-file /data/nodes.conf
    cluster-node-timeout 5000
---
apiVersion: v1
kind: Service
metadata:
  name: redis-headless
spec:
  clusterIP: None
  selector:
    app: redis
  ports:
    - name: redis
      port: 6379
    - name: cluster-bus
      port: 16379
---
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: redis
spec:
  serviceName: redis-headless
  replicas: 6
  selector:
    matchLabels:
      app: redis
  template:
    metadata:
      labels:
        app: redis
    spec:
      containers:
        - name: redis
          image: redis:7-alpine
          command:
            - redis-server
            - /etc/redis/redis.conf
          ports:
            - containerPort: 6379
              name: redis
            - containerPort: 16379
              name: cluster-bus
          resources:
            requests:
              cpu: "100m"
              memory: "128Mi"
            limits:
              cpu: "500m"
              memory: "512Mi"
          volumeMounts:
            - name: data
              mountPath: /data
            - name: config
              mountPath: /etc/redis
      volumes:
        - name: config
          configMap:
            name: redis-config
  volumeClaimTemplates:
    - metadata:
        name: data
      spec:
        accessModes: ["ReadWriteOnce"]
        storageClassName: local-path
        resources:
          requests:
            storage: 1Gi
```

---

## Gotchas

1. **`serviceName` must reference the headless Service** — this is what creates per-pod DNS records.
2. **PVCs are NOT deleted when you delete a StatefulSet** — you must delete PVCs manually to free storage.
3. **`OrderedReady` means pod N must be Running+Ready before pod N+1 starts** — if pod-0 is stuck, nothing else starts.
4. **Don't use `Recreate` strategy with StatefulSets** — rolling update is safer; Recreate causes full downtime.

---

## Practice

1. Deploy the PostgreSQL StatefulSet. Verify ordered pod startup and per-pod PVCs.
2. Write data to `postgres-0`. Scale down to 1 replica, scale back up to 3. Verify data persists.
3. Use partition-based updates to update only `postgres-2` first.
4. Exec into a pod and resolve `postgres-1.postgres-headless` via DNS.

---

## Key Takeaways

- StatefulSets give Pods stable names, DNS, and per-pod PVCs — essential for databases and clusters.
- Use a headless Service (`clusterIP: None`) so each Pod gets its own DNS record.
- PVCs survive pod deletion and StatefulSet deletion — always clean up manually.
- `partition` in the update strategy enables safe canary rollouts within a StatefulSet.
