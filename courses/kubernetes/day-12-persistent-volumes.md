# Day 12 — Persistent Volumes & PersistentVolumeClaims

## Learning Objectives
- Understand the PV/PVC/StorageClass model
- Create static and dynamic PVs
- Mount storage into Pods and StatefulSets
- Understand access modes and reclaim policies

---

## The Storage Model

```
Pod → PersistentVolumeClaim (PVC) → PersistentVolume (PV) → Actual Storage
              (your request)            (cluster resource)      (disk/NFS/cloud)
```

- **PersistentVolume (PV)**: a piece of storage in the cluster, provisioned by an admin (static) or automatically (dynamic)
- **PersistentVolumeClaim (PVC)**: a request for storage by a user — specifies size and access mode
- **StorageClass**: defines how dynamic PVs are provisioned

---

## Access Modes

| Mode | Short | Meaning |
|---|---|---|
| `ReadWriteOnce` | RWO | One node can read/write |
| `ReadOnlyMany` | ROX | Many nodes can read |
| `ReadWriteMany` | RWX | Many nodes can read/write (NFS, EFS) |
| `ReadWriteOncePod` | RWOP | Only one Pod can read/write (k8s 1.22+) |

---

## Reclaim Policies

| Policy | Behaviour when PVC is deleted |
|---|---|
| `Retain` | PV kept, must manually reclaim (production default) |
| `Delete` | PV and underlying storage deleted automatically |
| `Recycle` | Data wiped, PV made available again (deprecated) |

---

## Static Provisioning — Admin Creates PV

```yaml
# pv-static.yaml
apiVersion: v1
kind: PersistentVolume
metadata:
  name: pv-data-01
  labels:
    type: local
    app: postgres
spec:
  storageClassName: manual        # must match PVC storageClassName

  capacity:
    storage: 10Gi

  accessModes:
    - ReadWriteOnce

  persistentVolumeReclaimPolicy: Retain

  # hostPath — for local development/k3d only
  hostPath:
    path: /data/pv-data-01
    type: DirectoryOrCreate

  # For NFS:
  # nfs:
  #   server: nfs-server.example.com
  #   path: /exports/data
```

---

## PersistentVolumeClaim — User Requests Storage

```yaml
# pvc.yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: app-data
  namespace: default
spec:
  storageClassName: manual        # must match a PV or StorageClass

  accessModes:
    - ReadWriteOnce

  resources:
    requests:
      storage: 5Gi               # Kubernetes finds a PV that satisfies this

  # Optional: bind to a specific PV
  # volumeName: pv-data-01
```

```bash
kubectl apply -f pv-static.yaml
kubectl apply -f pvc.yaml
kubectl get pv,pvc
# NAME           CAPACITY  ACCESS MODES  RECLAIM POLICY  STATUS  CLAIM
# pv/pv-data-01  10Gi      RWO           Retain          Bound   default/app-data
#
# NAME             STATUS  VOLUME        CAPACITY  ACCESS MODES
# pvc/app-data     Bound   pv-data-01    10Gi      RWO
```

---

## Mount PVC in a Pod

```yaml
# pod-with-pvc.yaml
apiVersion: v1
kind: Pod
metadata:
  name: db-pod
spec:
  volumes:
    - name: data-vol
      persistentVolumeClaim:
        claimName: app-data       # reference the PVC

  containers:
    - name: postgres
      image: postgres:16-alpine
      env:
        - name: POSTGRES_PASSWORD
          value: "password"
        - name: PGDATA
          value: /var/lib/postgresql/data/pgdata
      volumeMounts:
        - name: data-vol
          mountPath: /var/lib/postgresql/data
      resources:
        requests:
          cpu: "250m"
          memory: "256Mi"
        limits:
          cpu: "1"
          memory: "1Gi"
```

```bash
kubectl apply -f pod-with-pvc.yaml
kubectl exec -it db-pod -- psql -U postgres -c "CREATE TABLE test(id int);"
kubectl delete pod db-pod
kubectl apply -f pod-with-pvc.yaml    # data survives pod deletion!
kubectl exec -it db-pod -- psql -U postgres -c "\dt"   # table still exists
```

---

## Dynamic Provisioning — StorageClass

Dynamic provisioning automatically creates PVs on demand when a PVC is created.

```yaml
# storageclass.yaml
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: fast-ssd
  annotations:
    storageclass.kubernetes.io/is-default-class: "false"
provisioner: kubernetes.io/aws-ebs    # cloud-specific provisioner
parameters:
  type: gp3
  iops: "3000"
  throughput: "125"
  encrypted: "true"
  kmsKeyId: "arn:aws:kms:..."
reclaimPolicy: Delete                 # Delete or Retain
allowVolumeExpansion: true            # allow PVC resize
volumeBindingMode: WaitForFirstConsumer  # don't create PV until a pod needs it
```

```bash
# k3d ships with 'local-path' StorageClass
kubectl get storageclass
# NAME                   PROVISIONER             RECLAIMPOLICY
# local-path (default)   rancher.io/local-path   Delete
```

---

## Dynamic PVC with StorageClass

```yaml
# pvc-dynamic.yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: dynamic-data
  namespace: default
spec:
  storageClassName: local-path    # k3d default; use "fast-ssd" on AWS etc.
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 2Gi
```

No PV needed — the StorageClass provisioner creates it automatically.

---

## Full Deployment with Persistent Storage

```yaml
# deployment-with-storage.yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: taskservice-data
  namespace: default
spec:
  storageClassName: local-path
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 1Gi
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: taskservice
spec:
  replicas: 1                   # only 1 replica with RWO storage
  selector:
    matchLabels:
      app: taskservice
  template:
    metadata:
      labels:
        app: taskservice
    spec:
      containers:
        - name: app
          image: myapp:1.0
          env:
            - name: DATA_PATH
              value: /data/tasks.json
          volumeMounts:
            - name: app-data
              mountPath: /data
          resources:
            requests:
              cpu: "100m"
              memory: "64Mi"
            limits:
              cpu: "500m"
              memory: "256Mi"
      volumes:
        - name: app-data
          persistentVolumeClaim:
            claimName: taskservice-data
```

---

## Resize a PVC (if StorageClass supports it)

```yaml
# Edit the PVC and increase storage
kubectl edit pvc taskservice-data
# Change: storage: 1Gi → storage: 5Gi

kubectl get pvc taskservice-data
# STATUS shows "FileSystemResizePending" briefly, then "Bound" with new size
```

---

## Gotchas

1. **RWO PVC can only be mounted on one node at a time** — if a Pod moves to another node, the volume must detach and reattach (brief delay).
2. **Deleting a PVC with `Retain` policy leaves a Released PV** — the PV cannot be bound to a new PVC until manually cleaned up.
3. **`hostPath` volumes in k3d are node-local** — data is tied to the specific node. If the pod moves to another node, the data is gone. Use `local-path` StorageClass instead.
4. **PVCs in Pending state** — usually means no PV matches the requested size and access mode, or the StorageClass doesn't exist.

```bash
# Debug a pending PVC
kubectl describe pvc my-pvc
# Events will show why it's pending (no matching PV, etc.)
```

---

## Practice

1. Create a static PV and PVC. Mount the PVC in a Pod, write a file, delete and recreate the Pod, verify the file persists.
2. Create a dynamic PVC using the `local-path` StorageClass. Verify a PV is automatically created.
3. Deploy PostgreSQL with a PVC. Create a table, delete the Pod, verify the table survives.
4. Check what happens to a PVC when its Pod is deleted (PVC persists) vs when the PVC is deleted (data lost).

---

## Key Takeaways

- PV = cluster storage resource; PVC = user request for storage. They bind together.
- Dynamic provisioning via StorageClass creates PVs automatically — no admin intervention needed.
- `Retain` reclaim policy = data safe on PVC deletion; `Delete` = data gone.
- RWO (ReadWriteOnce) is the most common mode — only one node at a time.
