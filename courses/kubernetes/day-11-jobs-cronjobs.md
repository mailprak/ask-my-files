# Day 11 — Jobs & CronJobs

## Learning Objectives
- Run one-off tasks with Jobs
- Handle retries and parallelism in Jobs
- Schedule recurring tasks with CronJobs
- Use Jobs for database migrations and batch processing

---

## Job — Run to Completion

A Job creates Pods that run until they complete successfully. Unlike Deployments, completed Pods are kept for log inspection.

```yaml
# job-simple.yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: db-seed
  namespace: default
  labels:
    app: db-seed
spec:
  completions: 1              # number of successful completions required
  parallelism: 1              # pods running simultaneously
  backoffLimit: 4             # retry up to 4 times on failure
  activeDeadlineSeconds: 300  # kill job after 5 minutes (even if not done)
  ttlSecondsAfterFinished: 3600  # delete job + pods 1h after completion

  template:
    metadata:
      labels:
        job: db-seed
    spec:
      restartPolicy: OnFailure    # OnFailure | Never (NOT Always)

      containers:
        - name: seed
          image: postgres:16-alpine
          command:
            - /bin/sh
            - -c
            - |
              echo "Connecting to database..."
              psql $DATABASE_URL -c "INSERT INTO users(name) VALUES('admin') ON CONFLICT DO NOTHING;"
              echo "Seed complete"
          env:
            - name: DATABASE_URL
              valueFrom:
                secretKeyRef:
                  name: app-secrets
                  key: DATABASE_URL
          resources:
            requests:
              cpu: "100m"
              memory: "64Mi"
            limits:
              cpu: "200m"
              memory: "128Mi"
```

```bash
kubectl apply -f job-simple.yaml
kubectl get jobs
kubectl get pods -l job=db-seed
kubectl logs job/db-seed
kubectl describe job db-seed
```

---

## Parallel Jobs — Process Many Items

```yaml
# job-parallel.yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: image-processor
spec:
  completions: 10         # process 10 items total
  parallelism: 3          # run 3 pods simultaneously
  backoffLimit: 6
  completionMode: Indexed # each pod gets a unique index (0-9) via JOB_COMPLETION_INDEX env

  template:
    spec:
      restartPolicy: OnFailure
      containers:
        - name: processor
          image: busybox:1.36
          command:
            - sh
            - -c
            - |
              echo "Processing item $JOB_COMPLETION_INDEX"
              sleep $((RANDOM % 10))
              echo "Done with item $JOB_COMPLETION_INDEX"
          env:
            - name: JOB_COMPLETION_INDEX
              valueFrom:
                fieldRef:
                  fieldPath: metadata.annotations['batch.kubernetes.io/job-completion-index']
```

---

## Database Migration Job

```yaml
# job-migrate.yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: db-migrate
  annotations:
    argocd.argoproj.io/hook: PreSync           # run before deployment (ArgoCD)
    argocd.argoproj.io/hook-delete-policy: HookSucceeded
spec:
  backoffLimit: 3
  activeDeadlineSeconds: 600
  ttlSecondsAfterFinished: 86400    # keep logs for 24h

  template:
    spec:
      restartPolicy: OnFailure
      initContainers:
        - name: wait-for-db
          image: busybox:1.36
          command: ['sh', '-c', 'until nc -z postgres 5432; do echo waiting; sleep 2; done']

      containers:
        - name: migrate
          image: myapp:2.0
          command: ["./migrate", "--direction=up", "--all"]
          env:
            - name: DATABASE_URL
              valueFrom:
                secretKeyRef:
                  name: db-secret
                  key: url
          resources:
            requests:
              cpu: "100m"
              memory: "128Mi"
            limits:
              cpu: "500m"
              memory: "512Mi"
```

---

## CronJob — Scheduled Recurring Tasks

```yaml
# cronjob.yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: backup-db
  namespace: default
spec:
  schedule: "0 2 * * *"            # every day at 2:00 AM (UTC)
                                    # min hour day month weekday
  timeZone: "America/New_York"      # k8s 1.27+ supports timezone
  concurrencyPolicy: Forbid         # Allow | Forbid | Replace
  successfulJobsHistoryLimit: 3     # keep last 3 successful jobs
  failedJobsHistoryLimit: 5         # keep last 5 failed jobs
  startingDeadlineSeconds: 300      # if missed, skip if not started within 5 min
  suspend: false                    # set true to pause the CronJob

  jobTemplate:
    spec:
      backoffLimit: 2
      activeDeadlineSeconds: 1800   # 30 min max

      template:
        metadata:
          labels:
            app: backup-db
        spec:
          restartPolicy: OnFailure

          containers:
            - name: backup
              image: postgres:16-alpine
              command:
                - /bin/sh
                - -c
                - |
                  TIMESTAMP=$(date +%Y%m%d_%H%M%S)
                  echo "Starting backup at $TIMESTAMP"
                  pg_dump $DATABASE_URL | gzip > /backups/backup_$TIMESTAMP.sql.gz
                  echo "Backup complete: /backups/backup_$TIMESTAMP.sql.gz"
              env:
                - name: DATABASE_URL
                  valueFrom:
                    secretKeyRef:
                      name: db-secret
                      key: url
              volumeMounts:
                - name: backup-storage
                  mountPath: /backups
              resources:
                requests:
                  cpu: "200m"
                  memory: "256Mi"
                limits:
                  cpu: "500m"
                  memory: "512Mi"

          volumes:
            - name: backup-storage
              persistentVolumeClaim:
                claimName: backup-pvc
```

---

## Common CronJob Schedules

```yaml
schedule: "*/5 * * * *"     # every 5 minutes
schedule: "0 * * * *"       # every hour
schedule: "0 9 * * 1-5"     # 9 AM Monday–Friday
schedule: "0 0 1 * *"       # midnight on the 1st of every month
schedule: "0 0 * * 0"       # midnight every Sunday
schedule: "@hourly"          # same as "0 * * * *"
schedule: "@daily"           # same as "0 0 * * *"
schedule: "@weekly"          # same as "0 0 * * 0"
```

---

## Concurrency Policies

```yaml
concurrencyPolicy: Allow     # (default) allow multiple jobs to run simultaneously
concurrencyPolicy: Forbid    # skip new job if previous is still running
concurrencyPolicy: Replace   # kill previous job and start new one
```

Use `Forbid` for backups and migrations. Use `Allow` for stateless processing jobs.

---

## Manually Trigger a CronJob

```bash
# Create a one-off job from a CronJob spec (useful for testing)
kubectl create job backup-manual --from=cronjob/backup-db

kubectl get jobs
kubectl logs job/backup-manual
```

---

## Monitoring Jobs and CronJobs

```bash
kubectl get jobs
# NAME          COMPLETIONS   DURATION   AGE
# db-seed       1/1           8s         2m
# db-migrate    0/1           30s        45s

kubectl get cronjobs
# NAME        SCHEDULE      SUSPEND   ACTIVE   LAST SCHEDULE   AGE
# backup-db   0 2 * * *     False     0        12h             7d

kubectl describe cronjob backup-db
kubectl get jobs --selector=app=backup-db --sort-by=.metadata.creationTimestamp
```

---

## Gotchas

1. **`restartPolicy: Always` is not allowed in Jobs** — use `OnFailure` or `Never`.
2. **`backoffLimit` counts pod failures, not job failures** — if `parallelism=3` and all 3 fail simultaneously, that's 3 failures counted.
3. **CronJob times are UTC by default** — use `timeZone` (k8s 1.27+) or document the UTC time clearly.
4. **`ttlSecondsAfterFinished`** — without this, completed Job pods accumulate forever and clutter the namespace.
5. **CronJob doesn't guarantee exact timing** — jobs may start late if the cluster is under load.

---

## Practice

1. Create a Job that counts words in a string. Run it, inspect logs, then check it completed.
2. Create a parallel Job that processes 5 items with 2 workers simultaneously.
3. Create a CronJob that runs every minute and prints the current timestamp.
4. Manually trigger the CronJob and verify it runs immediately.

---

## Key Takeaways

- Jobs run Pods to completion — use `restartPolicy: OnFailure` and set `backoffLimit`.
- `ttlSecondsAfterFinished` prevents completed Jobs from accumulating forever.
- CronJobs schedule Jobs — use `concurrencyPolicy: Forbid` for migrations and backups.
- `kubectl create job --from=cronjob/name` lets you trigger a CronJob on demand for testing.
