# Day 13 — Storage Classes & Dynamic Provisioning

## Learning Objectives
- Create custom StorageClasses for different performance tiers
- Understand volume binding modes
- Use volume snapshots for backup
- Configure storage for different cloud providers

---

## StorageClass Deep Dive

```yaml
# storageclass-tiers.yaml

# Tier 1: Fast SSD for databases
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: premium-ssd
  annotations:
    storageclass.kubernetes.io/is-default-class: "false"
provisioner: ebs.csi.aws.com
parameters:
  type: gp3
  iops: "16000"
  throughput: "1000"
  encrypted: "true"
reclaimPolicy: Retain                    # keep data on PVC deletion
allowVolumeExpansion: true
volumeBindingMode: WaitForFirstConsumer  # wait until Pod is scheduled
mountOptions:
  - debug
---
# Tier 2: Standard for general workloads
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: standard
  annotations:
    storageclass.kubernetes.io/is-default-class: "true"   # make this the default
provisioner: ebs.csi.aws.com
parameters:
  type: gp2
  encrypted: "true"
reclaimPolicy: Delete
allowVolumeExpansion: true
volumeBindingMode: WaitForFirstConsumer
---
# Tier 3: Cheap bulk storage for logs/backups
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: bulk-hdd
provisioner: ebs.csi.aws.com
parameters:
  type: sc1                             # cold HDD — cheapest
reclaimPolicy: Delete
allowVolumeExpansion: false
volumeBindingMode: WaitForFirstConsumer
```

---

## k3d Local StorageClass (for development)

```yaml
# storageclass-local.yaml
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: fast-local
  annotations:
    storageclass.kubernetes.io/is-default-class: "false"
provisioner: rancher.io/local-path      # k3d built-in provisioner
reclaimPolicy: Delete
volumeBindingMode: WaitForFirstConsumer
```

---

## Volume Binding Modes

```yaml
volumeBindingMode: Immediate          # PV created when PVC is created
                                      # problem: PV may end up on a different
                                      # zone than the Pod

volumeBindingMode: WaitForFirstConsumer  # PV created only when a Pod is
                                         # scheduled — PV is on the same node/zone
                                         # always use this for cloud storage
```

---

## PVCs with Specific StorageClass

```yaml
# pvc-tiered.yaml

# Database PVC — premium SSD
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: postgres-data
spec:
  storageClassName: premium-ssd
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 100Gi
---
# App data PVC — standard
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: app-uploads
spec:
  storageClassName: standard
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 20Gi
---
# Log storage PVC — bulk HDD
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: log-archive
spec:
  storageClassName: bulk-hdd
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 500Gi
```

---

## Volume Snapshots (Backup)

Volume snapshots create point-in-time copies of PVCs. Requires a CSI driver with snapshot support.

```yaml
# volumesnapshotclass.yaml
apiVersion: snapshot.storage.k8s.io/v1
kind: VolumeSnapshotClass
metadata:
  name: csi-aws-vsc
driver: ebs.csi.aws.com
deletionPolicy: Delete             # Delete | Retain
parameters:
  tagSpecification_1: "key=backup,value=daily"
---
# volumesnapshot.yaml
apiVersion: snapshot.storage.k8s.io/v1
kind: VolumeSnapshot
metadata:
  name: postgres-snapshot-20240115
spec:
  volumeSnapshotClassName: csi-aws-vsc
  source:
    persistentVolumeClaimName: postgres-data   # PVC to snapshot
```

```bash
kubectl apply -f volumesnapshot.yaml
kubectl get volumesnapshots
# NAME                           READYTOUSE  SOURCEPVC        AGE
# postgres-snapshot-20240115     true        postgres-data    2m
```

---

## Restore from Snapshot

```yaml
# pvc-from-snapshot.yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: postgres-data-restored
spec:
  storageClassName: premium-ssd
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 100Gi
  dataSource:
    name: postgres-snapshot-20240115
    kind: VolumeSnapshot
    apiGroup: snapshot.storage.k8s.io
```

---

## NFS StorageClass (for ReadWriteMany)

When you need RWX (multiple pods reading and writing), use NFS:

```yaml
# storageclass-nfs.yaml
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: nfs-rwx
provisioner: nfs.csi.k8s.io
parameters:
  server: nfs-server.example.com
  share: /exports/k8s
reclaimPolicy: Delete
volumeBindingMode: Immediate
mountOptions:
  - noresvport
  - nfsvers=4.1
---
# pvc-rwx.yaml — for shared access by multiple pods
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: shared-uploads
spec:
  storageClassName: nfs-rwx
  accessModes:
    - ReadWriteMany             # multiple pods on multiple nodes
  resources:
    requests:
      storage: 50Gi
```

---

## Deployment Using Shared RWX Storage

```yaml
# deployment-shared-storage.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: web
spec:
  replicas: 3                   # multiple replicas sharing the same volume
  selector:
    matchLabels:
      app: web
  template:
    metadata:
      labels:
        app: web
    spec:
      containers:
        - name: nginx
          image: nginx:alpine
          volumeMounts:
            - name: uploads
              mountPath: /var/www/uploads
      volumes:
        - name: uploads
          persistentVolumeClaim:
            claimName: shared-uploads    # RWX PVC — all 3 pods access same data
```

---

## CronJob: Automated PVC Snapshots

```yaml
# cronjob-snapshot.yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: daily-snapshot
spec:
  schedule: "0 1 * * *"         # 1 AM daily
  concurrencyPolicy: Forbid
  jobTemplate:
    spec:
      template:
        spec:
          restartPolicy: OnFailure
          serviceAccountName: snapshot-sa   # needs RBAC to create VolumeSnapshots
          containers:
            - name: snapshotter
              image: bitnami/kubectl:latest
              command:
                - /bin/sh
                - -c
                - |
                  DATE=$(date +%Y%m%d)
                  kubectl apply -f - <<EOF
                  apiVersion: snapshot.storage.k8s.io/v1
                  kind: VolumeSnapshot
                  metadata:
                    name: postgres-snapshot-$DATE
                  spec:
                    volumeSnapshotClassName: csi-aws-vsc
                    source:
                      persistentVolumeClaimName: postgres-data
                  EOF
                  echo "Snapshot postgres-snapshot-$DATE created"
```

---

## Gotchas

1. **Default StorageClass** — if a PVC doesn't specify `storageClassName`, it uses the default. If no default is set, PVC stays Pending.
2. **`WaitForFirstConsumer` + topology** — PV is created in the zone where the Pod is scheduled. Cross-zone access doesn't work.
3. **Volume expansion requires a Pod restart** — on most CSI drivers, the filesystem resize happens when the pod mounts the volume again.
4. **Snapshot requires a CSI driver** — `hostPath` and `local-path` provisioners don't support snapshots.

---

## Practice

1. On k3d, create two StorageClasses: `fast` and `slow` (both using `local-path` provisioner but different labels). Create PVCs with each.
2. Create a Deployment with 3 replicas sharing a `ReadWriteMany` PVC. Write from one pod, read from another.
3. Write a CronJob that deletes PVC snapshots older than 7 days.
4. Verify that `WaitForFirstConsumer` delays PV creation until a Pod is deployed.

---

## Key Takeaways

- StorageClasses define storage tiers (speed, cost, reliability) — use the right class for the right workload.
- `WaitForFirstConsumer` binding mode prevents cross-zone storage placement issues.
- Volume snapshots = point-in-time backups — automate with a CronJob.
- RWX (ReadWriteMany) requires NFS, EFS, or similar — EBS/local-path are RWO only.
