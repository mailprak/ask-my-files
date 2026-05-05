# Day 23 — Service Accounts & Security Contexts

## Learning Objectives
- Understand Service Accounts and how Pods authenticate to the API server
- Configure Security Contexts to restrict container privileges
- Drop capabilities and run containers as non-root
- Use projected volumes for workload identity

---

## Service Accounts

Every Pod runs with a Service Account. The default Service Account has minimal permissions. Custom Service Accounts let you assign RBAC permissions to specific workloads.

```bash
# List service accounts
kubectl get serviceaccounts
kubectl get sa                    # shorthand

# The default SA is created automatically in every namespace
kubectl get sa default -o yaml
```

---

## Creating a Service Account

```yaml
# service-account.yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: app-sa
  namespace: production
  annotations:
    # AWS: link to an IAM role (IRSA)
    eks.amazonaws.com/role-arn: arn:aws:iam::123456789:role/my-app-role
    # GCP: link to a GCP service account (Workload Identity)
    iam.gke.io/gcp-service-account: my-app@my-project.iam.gserviceaccount.com
automountServiceAccountToken: false   # opt out of auto-mounting (safer)
```

---

## Assigning a Service Account to a Pod

```yaml
# pod-with-sa.yaml
apiVersion: v1
kind: Pod
metadata:
  name: api-pod
  namespace: production
spec:
  serviceAccountName: app-sa          # use our custom SA
  automountServiceAccountToken: true  # override SA-level setting if needed

  containers:
    - name: app
      image: myapp:2.0
      # The SA token is mounted at /var/run/secrets/kubernetes.io/serviceaccount/
      # token, ca.crt, namespace files
```

---

## Projected Volume — Short-Lived Token (k8s 1.20+)

Prefer projected volumes over legacy auto-mount tokens — the token has an expiry:

```yaml
# pod-projected-token.yaml
apiVersion: v1
kind: Pod
metadata:
  name: api-with-projected-token
spec:
  serviceAccountName: app-sa
  automountServiceAccountToken: false   # disable legacy mount

  volumes:
    - name: kube-api-access
      projected:
        sources:
          - serviceAccountToken:
              path: token
              expirationSeconds: 3600      # 1 hour — rotated automatically
              audience: "https://kubernetes.default.svc"
          - configMap:
              name: kube-root-ca.crt
              items:
                - key: ca.crt
                  path: ca.crt
          - downwardAPI:
              items:
                - path: namespace
                  fieldRef:
                    fieldPath: metadata.namespace

  containers:
    - name: app
      image: myapp:2.0
      volumeMounts:
        - name: kube-api-access
          mountPath: /var/run/secrets/kubernetes.io/serviceaccount
          readOnly: true
```

---

## Security Context — Pod Level

Pod-level security context applies to all containers:

```yaml
# pod-security-context.yaml
apiVersion: v1
kind: Pod
metadata:
  name: secure-pod
spec:
  securityContext:
    runAsNonRoot: true          # fail if container runs as root
    runAsUser: 1000             # UID for all containers
    runAsGroup: 3000            # GID for all containers
    fsGroup: 2000               # volume ownership — files written to volumes get this GID
    fsGroupChangePolicy: OnRootMismatch   # only chown if needed (faster for large volumes)

    seccompProfile:
      type: RuntimeDefault      # apply the runtime's default seccomp profile
                                # blocks ~100 dangerous syscalls (ptrace, mount, etc.)

    supplementalGroups: [4000]  # extra groups for all containers

  containers:
    - name: app
      image: myapp:2.0
      securityContext:
        allowPrivilegeEscalation: false   # cannot gain more privileges than parent
        readOnlyRootFilesystem: true       # container filesystem is read-only
        capabilities:
          drop:
            - ALL               # drop every Linux capability
          add:
            - NET_BIND_SERVICE  # add back only what's needed (bind port < 1024)
```

---

## Security Context — Minimally Privileged Container

A production-hardened container spec:

```yaml
# deployment-secure.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: secure-api
  namespace: production
spec:
  replicas: 3
  selector:
    matchLabels:
      app: secure-api
  template:
    metadata:
      labels:
        app: secure-api
    spec:
      serviceAccountName: app-sa
      automountServiceAccountToken: false

      securityContext:
        runAsNonRoot: true
        runAsUser: 10001
        runAsGroup: 10001
        fsGroup: 10001
        seccompProfile:
          type: RuntimeDefault

      containers:
        - name: api
          image: myapi:2.0
          ports:
            - containerPort: 8080
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities:
              drop: ["ALL"]

          # Must provide writable scratch space since root fs is read-only
          volumeMounts:
            - name: tmp
              mountPath: /tmp
            - name: cache
              mountPath: /app/cache

          resources:
            requests:
              cpu: "100m"
              memory: "128Mi"
            limits:
              cpu: "500m"
              memory: "256Mi"

      volumes:
        - name: tmp
          emptyDir: {}
        - name: cache
          emptyDir: {}
```

---

## Privileged Container (use sparingly)

Some system-level tools require elevated privileges:

```yaml
# daemonset-node-agent.yaml
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: node-agent
  namespace: kube-system
spec:
  selector:
    matchLabels:
      app: node-agent
  template:
    metadata:
      labels:
        app: node-agent
    spec:
      hostPID: true           # see host processes
      hostNetwork: true       # use host network namespace
      hostIPC: true           # use host IPC namespace

      tolerations:
        - operator: Exists    # run on all nodes including control-plane

      containers:
        - name: agent
          image: node-agent:latest
          securityContext:
            privileged: true  # full host access — required for eBPF, kernel modules
          volumeMounts:
            - name: host-root
              mountPath: /host
              readOnly: true
            - name: sys
              mountPath: /sys
              readOnly: true

      volumes:
        - name: host-root
          hostPath:
            path: /
        - name: sys
          hostPath:
            path: /sys
```

---

## Specific Capabilities

Instead of privileged, add only the capabilities you need:

```yaml
# Linux capabilities reference
securityContext:
  capabilities:
    drop: ["ALL"]
    add:
      # - NET_ADMIN       # manage networking, iptables
      # - NET_RAW         # raw sockets, ping
      # - SYS_PTRACE      # debug another process
      # - SYS_ADMIN       # broad — almost like privileged. Avoid.
      # - CHOWN           # change file ownership
      # - DAC_OVERRIDE    # bypass file permission checks
      # - SETUID          # change process UID
      # - KILL            # send signals to processes owned by other UIDs
      - NET_BIND_SERVICE  # bind to ports < 1024 as non-root
```

---

## Audit: What Security Context is a Pod Using?

```bash
# Check a running pod's security context
kubectl get pod my-pod -o jsonpath='{.spec.securityContext}'
kubectl get pod my-pod -o jsonpath='{.spec.containers[0].securityContext}'

# Check what UID the container is running as
kubectl exec my-pod -- id

# Check capabilities
kubectl exec my-pod -- cat /proc/1/status | grep Cap

# Verify read-only filesystem
kubectl exec my-pod -- touch /test-file  # should fail: Read-only file system

# Verify non-root
kubectl exec my-pod -- whoami           # should print non-root user
```

---

## Service Account Best Practices

```yaml
# Disable auto-mounting at the SA level
apiVersion: v1
kind: ServiceAccount
metadata:
  name: no-api-access
  namespace: production
automountServiceAccountToken: false    # pods using this SA don't get a token

---
# Re-enable per-pod when needed
apiVersion: v1
kind: Pod
spec:
  serviceAccountName: no-api-access
  automountServiceAccountToken: true   # override for this specific pod
```

---

## Gotchas

1. **`runAsNonRoot: true` without `runAsUser`** — Kubernetes checks the image's USER directive. If the image has `USER 0` (root) and you don't specify `runAsUser`, the pod fails to start.
2. **`readOnlyRootFilesystem: true`** — Apps that write to `/tmp`, `/var`, or `/app` at runtime will fail. Always provide `emptyDir` volumes for writable paths.
3. **`fsGroup` only applies to mounted volumes** — Not to the container filesystem. Files in the image are not chowned.
4. **Projected tokens vs legacy secrets** — Legacy `kubernetes.io/service-account-token` secrets are permanent. Projected tokens expire and rotate automatically. Prefer projected tokens.

---

## Practice

1. Create a ServiceAccount and bind it to a Role that can only read ConfigMaps. Mount it in a Pod and verify the token works.
2. Run a Pod with `runAsNonRoot: true`, `readOnlyRootFilesystem: true`, and `capabilities.drop: ALL`. Verify it starts and the root filesystem is not writable.
3. Use `kubectl exec` to verify the UID and capabilities of a running container.
4. Disable `automountServiceAccountToken` on the default SA. Verify new pods don't have a token mounted.

---

## Key Takeaways

- Every Pod has a Service Account — use a dedicated SA per workload for precise RBAC control.
- `runAsNonRoot`, `readOnlyRootFilesystem`, `allowPrivilegeEscalation: false`, and `capabilities.drop: ALL` are the four security essentials.
- Projected tokens rotate automatically — prefer them over legacy SA token secrets.
- `fsGroup` controls volume file ownership — needed when your app needs to write to a PVC.
