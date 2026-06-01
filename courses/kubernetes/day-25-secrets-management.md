# Day 25 — Secrets Management (Advanced)

## Learning Objectives
- Understand native Kubernetes Secret limitations
- Use Sealed Secrets to encrypt secrets in Git
- Integrate HashiCorp Vault with Kubernetes
- Use External Secrets Operator to sync from cloud secret stores

---

## The Problem with Native Secrets

Kubernetes Secrets are base64-encoded — NOT encrypted at rest by default.

```bash
# Anyone with access to etcd or the Secret object can decode it
kubectl get secret my-secret -o jsonpath='{.data.password}' | base64 -d

# Risks:
# - Storing base64 in Git is equivalent to plaintext
# - etcd is not encrypted by default in many clusters
# - Broad RBAC access lets anyone read secrets
```

Enable encryption at rest (requires cluster admin):
```yaml
# /etc/kubernetes/manifests/kube-apiserver.yaml — add EncryptionConfiguration
# This encrypts secrets in etcd, but they're still decryptable by the API server
```

---

## Sealed Secrets — Encrypt for Git

Sealed Secrets uses asymmetric encryption. Only the cluster's private key can decrypt. Safe to commit to Git.

### Install Sealed Secrets

```bash
# Install controller in kube-system
kubectl apply -f https://github.com/bitnami-labs/sealed-secrets/releases/download/v0.24.5/controller.yaml

# Install kubeseal CLI
brew install kubeseal   # macOS
# or download from GitHub releases

# Get the public key (anyone can seal, only cluster can unseal)
kubeseal --fetch-cert > pub-cert.pem
```

### Create a Sealed Secret

```bash
# Step 1: Create a regular Secret (do NOT apply it to the cluster)
kubectl create secret generic db-password \
  --from-literal=password=password \
  --dry-run=client \
  -o yaml > secret-plain.yaml

# Step 2: Seal it
kubeseal --cert pub-cert.pem \
  --format yaml \
  < secret-plain.yaml \
  > secret-sealed.yaml

# Step 3: Delete the plaintext — commit only the sealed version
rm secret-plain.yaml
git add secret-sealed.yaml
git commit -m "add sealed db password"
```

```yaml
# secret-sealed.yaml — safe to commit to Git
apiVersion: bitnami.com/v1alpha1
kind: SealedSecret
metadata:
  name: db-password
  namespace: production
spec:
  encryptedData:
    password: AgBy3i4OJSWK+PiTySYZZA9rO43cGDEq...   # encrypted blob
  template:
    metadata:
      name: db-password
      namespace: production
    type: Opaque
```

```bash
# Apply the SealedSecret — controller decrypts and creates the Secret
kubectl apply -f secret-sealed.yaml

# Verify the Secret was created
kubectl get secret db-password
kubectl get secret db-password -o jsonpath='{.data.password}' | base64 -d
```

---

## HashiCorp Vault — External Secret Store

Vault stores secrets externally, rotates them, and audits access.

### Install Vault on k3d

```bash
# Add Vault Helm chart
helm repo add hashicorp https://helm.releases.hashicorp.com
helm repo update

# Install Vault in dev mode (for learning — not for production)
helm install vault hashicorp/vault \
  --namespace vault \
  --create-namespace \
  --set server.dev.enabled=true

# Verify
kubectl get pods -n vault
# vault-0   1/1   Running

# Access Vault UI
kubectl port-forward -n vault vault-0 8200:8200
# Open http://localhost:8200 — root token is "root" in dev mode
```

### Configure Vault Kubernetes Auth

```bash
# Exec into vault pod
kubectl exec -it -n vault vault-0 -- sh

# Enable kubernetes auth
vault auth enable kubernetes

# Configure Vault to talk to the Kubernetes API
vault write auth/kubernetes/config \
  kubernetes_host="https://kubernetes.default.svc:443" \
  kubernetes_ca_cert=@/var/run/secrets/kubernetes.io/serviceaccount/ca.crt \
  token_reviewer_jwt=@/var/run/secrets/kubernetes.io/serviceaccount/token

# Write a secret
vault secrets enable -path=secret kv-v2
vault kv put secret/production/db \
  password="password" \
  username="dbuser"

# Create a policy
vault policy write app-policy - <<EOF
path "secret/data/production/db" {
  capabilities = ["read"]
}
EOF

# Create a role — binds k8s SA to vault policy
vault write auth/kubernetes/role/app-role \
  bound_service_account_names=app-sa \
  bound_service_account_namespaces=production \
  policies=app-policy \
  ttl=1h
```

### Vault Agent Injector — Sidecar Pattern

The Vault Agent Injector intercepts pods with annotations and injects a sidecar that fetches secrets:

```yaml
# deployment-vault-injector.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
  namespace: production
spec:
  replicas: 2
  selector:
    matchLabels:
      app: api
  template:
    metadata:
      labels:
        app: api
      annotations:
        vault.hashicorp.com/agent-inject: "true"
        vault.hashicorp.com/role: "app-role"
        vault.hashicorp.com/agent-inject-secret-db.txt: "secret/data/production/db"
        # Template — format the secret into a file
        vault.hashicorp.com/agent-inject-template-db.txt: |
          {{- with secret "secret/data/production/db" -}}
          export DB_PASSWORD="{{ .Data.data.password }}"
          export DB_USERNAME="{{ .Data.data.username }}"
          {{- end }}

    spec:
      serviceAccountName: app-sa
      containers:
        - name: app
          image: myapp:2.0
          command:
            - sh
            - -c
            - |
              source /vault/secrets/db.txt    # source the injected secret
              exec ./myapp
```

Vault agent injects two init containers and a sidecar — the main container gets secrets in `/vault/secrets/`.

---

## External Secrets Operator — Sync from Cloud

ESO syncs secrets from AWS Secrets Manager, GCP Secret Manager, Azure Key Vault, etc.:

```bash
# Install ESO
helm repo add external-secrets https://charts.external-secrets.io
helm install external-secrets \
  external-secrets/external-secrets \
  -n external-secrets \
  --create-namespace
```

### SecretStore + ExternalSecret

```yaml
# secretstore-aws.yaml — connect to AWS Secrets Manager
apiVersion: external-secrets.io/v1beta1
kind: SecretStore
metadata:
  name: aws-secret-store
  namespace: production
spec:
  provider:
    aws:
      service: SecretsManager
      region: us-east-1
      auth:
        secretRef:
          accessKeyIDSecretRef:
            name: aws-credentials
            key: access-key-id
          secretAccessKeySecretRef:
            name: aws-credentials
            key: secret-access-key
```

```yaml
# externalsecret-db.yaml — pull from AWS, create k8s Secret
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: db-secret
  namespace: production
spec:
  refreshInterval: 1h            # re-sync every hour

  secretStoreRef:
    name: aws-secret-store
    kind: SecretStore

  target:
    name: db-password             # creates/updates this Secret
    creationPolicy: Owner         # ESO manages the lifecycle
    template:
      type: Opaque
      data:
        password: "{{ .password }}"     # transform the value
        dsn: "postgres://{{ .username }}:{{ .password }}@postgres:5432/mydb"

  data:
    - secretKey: password         # key in the k8s Secret
      remoteRef:
        key: production/db        # AWS secret path
        property: password        # JSON property

    - secretKey: username
      remoteRef:
        key: production/db
        property: username
```

```bash
# Verify ESO synced the secret
kubectl get externalsecret db-secret -n production
# NAME        STORE            REFRESH INTERVAL   STATUS    READY
# db-secret   aws-secret-store 1h                 SecretSynced True

kubectl get secret db-password -n production
```

---

## Comparing Approaches

| Approach | Encryption | Rotation | Git-Safe | Cloud Dep |
|---|---|---|---|---|
| Native Secret | No (base64) | Manual | No | No |
| Sealed Secrets | Yes (RSA) | Re-seal | Yes | No |
| Vault | Yes | Auto | N/A | No (self-hosted) |
| External Secrets | Cloud-managed | Auto | N/A | Yes |

---

## Secret Rotation — Zero Downtime

```yaml
# Use projected volumes — token is rotated without pod restart
volumes:
  - name: db-password
    projected:
      sources:
        - secret:
            name: db-password      # when Secret changes, the file updates

# In app: read password from file each time, not once at startup
# e.g., re-read /secrets/password before each DB connection attempt
```

---

## Gotchas

1. **Base64 is not encryption** — don't commit native Secrets to Git. Use Sealed Secrets or reference external stores.
2. **Sealed Secrets are cluster-tied** — if you rotate the cluster key (or the cluster is destroyed), existing SealedSecrets can't be decrypted. Export and back up the key.
3. **ESO refresh interval** — with `refreshInterval: 1h`, changes in AWS take up to 1 hour to appear. Set lower for critical secrets.
4. **Vault dev mode is not persistent** — in dev mode, Vault stores secrets in memory. Restart = all secrets lost. Use production mode with backend storage for real use.

---

## Practice

1. Install Sealed Secrets. Create and seal a Secret with a database password. Commit the SealedSecret, apply it, and verify the Secret is created.
2. Install Vault in dev mode. Write a secret to `secret/data/myapp/config`. Retrieve it using the Vault CLI.
3. Configure the Vault Kubernetes auth method. Create a Pod with the injector annotation and verify secrets appear in `/vault/secrets/`.
4. Install External Secrets Operator. Use a SecretStore pointing to Vault and create an ExternalSecret that pulls a value.

---

## Key Takeaways

- Native Secrets are base64 — safe on the cluster, but never commit to Git. Use Sealed Secrets if GitOps is required.
- Sealed Secrets = encrypt once, decrypt by the cluster only. Great for GitOps workflows.
- Vault = full-featured secret management with audit logs, dynamic secrets, and rotation.
- External Secrets Operator = bridge between Kubernetes and cloud secret stores (AWS, GCP, Azure).
