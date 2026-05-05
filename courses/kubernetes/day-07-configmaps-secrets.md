# Day 07 — ConfigMaps & Secrets

## Learning Objectives
- Store configuration in ConfigMaps and inject them into Pods
- Store sensitive data in Secrets
- Mount config as environment variables or files
- Understand Secret types and base64 encoding

---

## ConfigMap

A ConfigMap stores non-sensitive key-value configuration data decoupled from the container image.

```yaml
# configmap.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: app-config
  namespace: default
data:
  # Simple key-value pairs
  APP_ENV: "production"
  LOG_LEVEL: "info"
  MAX_CONNECTIONS: "100"
  DB_HOST: "postgres.default.svc.cluster.local"
  DB_PORT: "5432"

  # Multi-line file content
  app.yaml: |
    server:
      port: 8080
      timeout: 30s
    logging:
      level: info
      format: json

  nginx.conf: |
    server {
        listen 80;
        location / {
            proxy_pass http://localhost:8080;
        }
    }
```

```bash
kubectl apply -f configmap.yaml
kubectl get configmaps
kubectl describe configmap app-config
kubectl get configmap app-config -o yaml
```

---

## Inject ConfigMap as Environment Variables

```yaml
# pod-configmap-env.yaml
apiVersion: v1
kind: Pod
metadata:
  name: app-env
spec:
  containers:
    - name: app
      image: busybox:1.36
      command: ["sh", "-c", "echo $APP_ENV $LOG_LEVEL && sleep 3600"]

      # Option 1: inject specific keys
      env:
        - name: APP_ENV
          valueFrom:
            configMapKeyRef:
              name: app-config
              key: APP_ENV
        - name: LOG_LEVEL
          valueFrom:
            configMapKeyRef:
              name: app-config
              key: LOG_LEVEL

      # Option 2: inject ALL keys as env vars
      envFrom:
        - configMapRef:
            name: app-config
            prefix: "CFG_"       # optional prefix — CFG_APP_ENV, CFG_LOG_LEVEL...
```

---

## Mount ConfigMap as Files

```yaml
# pod-configmap-volume.yaml
apiVersion: v1
kind: Pod
metadata:
  name: app-config-volume
spec:
  volumes:
    - name: config-vol
      configMap:
        name: app-config
        items:                       # mount only specific keys as files
          - key: app.yaml
            path: app.yaml           # filename in the mount
          - key: nginx.conf
            path: nginx.conf

  containers:
    - name: app
      image: nginx:alpine
      volumeMounts:
        - name: config-vol
          mountPath: /etc/config     # each key becomes a file here
          readOnly: true
```

```bash
kubectl apply -f pod-configmap-volume.yaml
kubectl exec app-config-volume -- cat /etc/config/app.yaml
```

**Live updates:** When a ConfigMap is updated, mounted files update automatically (within ~1 minute). Environment variables do NOT update — they require a Pod restart.

---

## Secret

Secrets store sensitive data. Values are base64-encoded (not encrypted by default — use encryption at rest in production).

```yaml
# secret.yaml
apiVersion: v1
kind: Secret
metadata:
  name: app-secrets
  namespace: default
type: Opaque                        # generic key-value secret

stringData:                         # plain text — Kubernetes base64-encodes it
  DB_PASSWORD: "supersecret123"
  API_KEY: "sk-abc123xyz789"
  JWT_SECRET: "my-jwt-signing-key"

# Alternatively, pre-encode values:
# data:
#   DB_PASSWORD: c3VwZXJzZWNyZXQxMjM=    # base64("supersecret123")
```

```bash
kubectl apply -f secret.yaml
kubectl get secrets
kubectl describe secret app-secrets    # values are hidden
kubectl get secret app-secrets -o jsonpath='{.data.DB_PASSWORD}' | base64 -d
```

---

## Inject Secret as Environment Variables

```yaml
# pod-secret-env.yaml
apiVersion: v1
kind: Pod
metadata:
  name: app-secret-env
spec:
  containers:
    - name: app
      image: busybox:1.36
      command: ["sh", "-c", "echo DB_PASSWORD is set && sleep 3600"]

      env:
        - name: DB_PASSWORD
          valueFrom:
            secretKeyRef:
              name: app-secrets
              key: DB_PASSWORD
              optional: false      # fail pod startup if secret/key is missing

      envFrom:
        - secretRef:
            name: app-secrets      # all keys as env vars
```

---

## Mount Secret as Files

```yaml
# pod-secret-volume.yaml
apiVersion: v1
kind: Pod
metadata:
  name: app-secret-volume
spec:
  volumes:
    - name: secrets-vol
      secret:
        secretName: app-secrets
        defaultMode: 0400          # read-only for owner (important for TLS keys)
        items:
          - key: API_KEY
            path: api-key          # mounted at /etc/secrets/api-key

  containers:
    - name: app
      image: nginx:alpine
      volumeMounts:
        - name: secrets-vol
          mountPath: /etc/secrets
          readOnly: true
```

```bash
kubectl exec app-secret-volume -- cat /etc/secrets/api-key
```

---

## TLS Secret

```yaml
# secret-tls.yaml
apiVersion: v1
kind: Secret
metadata:
  name: tls-cert
  namespace: default
type: kubernetes.io/tls             # special TLS type

data:
  tls.crt: <base64-encoded-cert>
  tls.key: <base64-encoded-key>
```

```bash
# Create from files
kubectl create secret tls tls-cert \
  --cert=./cert.pem \
  --key=./key.pem
```

---

## Docker Registry Secret

```yaml
# secret-registry.yaml
apiVersion: v1
kind: Secret
metadata:
  name: registry-creds
type: kubernetes.io/dockerconfigjson
data:
  .dockerconfigjson: <base64-encoded-docker-config>
```

```bash
# Create imperatively
kubectl create secret docker-registry registry-creds \
  --docker-server=myregistry.io \
  --docker-username=myuser \
  --docker-password=mypassword

# Reference in Pod
spec:
  imagePullSecrets:
    - name: registry-creds
```

---

## Full App: Deployment + ConfigMap + Secret

```yaml
# app-complete.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: app-config
data:
  APP_ENV: "production"
  LOG_LEVEL: "info"
  DB_HOST: "postgres"
  DB_PORT: "5432"
---
apiVersion: v1
kind: Secret
metadata:
  name: app-secrets
type: Opaque
stringData:
  DB_PASSWORD: "securepass"
  API_KEY: "sk-abc123"
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: myapp
spec:
  replicas: 2
  selector:
    matchLabels:
      app: myapp
  template:
    metadata:
      labels:
        app: myapp
    spec:
      containers:
        - name: app
          image: nginx:alpine
          envFrom:
            - configMapRef:
                name: app-config    # non-sensitive config
          env:
            - name: DB_PASSWORD     # sensitive — from secret
              valueFrom:
                secretKeyRef:
                  name: app-secrets
                  key: DB_PASSWORD
            - name: API_KEY
              valueFrom:
                secretKeyRef:
                  name: app-secrets
                  key: API_KEY
```

---

## Gotchas

1. **Secrets are base64, not encrypted** — anyone with RBAC access to get Secrets sees the values. Enable encryption at rest and use Sealed Secrets or Vault for real security.
2. **`envFrom` key names must be valid env var names** — keys with dots (`app.yaml`) can't be used with `envFrom`. Use volume mounts for file-like keys.
3. **ConfigMap volume updates are not immediate** — changes propagate in ~1 min (kubelet sync period). Don't expect instant hot reload.
4. **Missing secret causes Pod to fail to start** — use `optional: true` if you want the pod to start even without the secret.

---

## Practice

1. Create a ConfigMap with `DATABASE_URL`, `LOG_LEVEL`, and a multi-line `config.yaml`. Mount it both as env vars and as a file.
2. Create a Secret with a `PASSWORD` and inject it as an environment variable.
3. Update a ConfigMap and verify the mounted file updates inside the Pod.
4. Create a full app (Deployment + ConfigMap + Secret) for a fake database connection.

---

## Key Takeaways

- ConfigMaps for non-sensitive config; Secrets for passwords, tokens, keys.
- Env vars are set at Pod start — changes require Pod restart. Volume mounts update live.
- Never hardcode config in container images — use ConfigMaps and Secrets.
- Secrets are base64 encoded, not encrypted — use Sealed Secrets or Vault for production security.
