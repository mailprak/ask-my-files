# Day 24 — Pod Security Standards (PSS) & Admission

## Learning Objectives
- Understand Pod Security Standards (Privileged, Baseline, Restricted)
- Apply PSS at the namespace level with labels
- Use OPA Gatekeeper or Kyverno for custom admission policies
- Validate manifests before deploying

---

## Pod Security Standards Overview

PSS replaced the deprecated PodSecurityPolicy (PSP) in k8s 1.25. Three built-in profiles:

| Profile | Description | Use For |
|---|---|---|
| `privileged` | No restrictions | System components, trusted workloads |
| `baseline` | Blocks known privilege escalations | General workloads |
| `restricted` | Follows security best practices | Security-sensitive workloads |

Three modes per profile:

| Mode | Behaviour |
|---|---|
| `enforce` | Reject pods that violate the policy |
| `audit` | Allow but log violations |
| `warn` | Allow but warn the user |

---

## Applying PSS to a Namespace

```yaml
# namespace-restricted.yaml
apiVersion: v1
kind: Namespace
metadata:
  name: production
  labels:
    # Enforce restricted — pods must comply or are rejected
    pod-security.kubernetes.io/enforce: restricted
    pod-security.kubernetes.io/enforce-version: v1.29

    # Audit restricted — log non-compliant pods
    pod-security.kubernetes.io/audit: restricted
    pod-security.kubernetes.io/audit-version: v1.29

    # Warn restricted — warn on kubectl apply
    pod-security.kubernetes.io/warn: restricted
    pod-security.kubernetes.io/warn-version: v1.29
```

```bash
# Apply PSS to existing namespace
kubectl label namespace production \
  pod-security.kubernetes.io/enforce=restricted \
  pod-security.kubernetes.io/enforce-version=v1.29

# Verify labels
kubectl get namespace production --show-labels

# Test: try to create a privileged pod — should be rejected
kubectl run privileged-test --image=nginx \
  --overrides='{"spec":{"containers":[{"name":"privileged-test","image":"nginx","securityContext":{"privileged":true}}]}}' \
  -n production
# Error: pods "privileged-test" is forbidden: violates PodSecurity "restricted:v1.29"
```

---

## PSS Profiles — What They Enforce

### Baseline Profile — what it blocks:
```yaml
# These will be REJECTED in a baseline namespace:

# ❌ Privileged containers
securityContext:
  privileged: true

# ❌ Host namespaces
hostPID: true
hostIPC: true
hostNetwork: true

# ❌ Host ports
ports:
  - containerPort: 80
    hostPort: 8080    # ❌

# ❌ Dangerous capabilities
securityContext:
  capabilities:
    add: ["SYS_ADMIN"]

# ❌ HostPath volumes (with exceptions)
volumes:
  - name: data
    hostPath:
      path: /etc
```

### Restricted Profile — additionally enforces:
```yaml
# These are REQUIRED in a restricted namespace:

# ✅ Run as non-root
securityContext:
  runAsNonRoot: true

# ✅ No privilege escalation
securityContext:
  allowPrivilegeEscalation: false

# ✅ Drop all capabilities
securityContext:
  capabilities:
    drop: ["ALL"]

# ✅ Seccomp profile
securityContext:
  seccompProfile:
    type: RuntimeDefault   # or Localhost

# ✅ Volume types: only configMap, emptyDir, projected, secret, downwardAPI, PVC
```

---

## Compliant Pod for Restricted Namespace

```yaml
# pod-restricted-compliant.yaml
apiVersion: v1
kind: Pod
metadata:
  name: compliant-app
  namespace: production
spec:
  securityContext:
    runAsNonRoot: true
    runAsUser: 10001
    runAsGroup: 10001
    seccompProfile:
      type: RuntimeDefault

  containers:
    - name: app
      image: myapp:2.0
      securityContext:
        allowPrivilegeEscalation: false
        readOnlyRootFilesystem: true
        capabilities:
          drop: ["ALL"]

      volumeMounts:
        - name: tmp
          mountPath: /tmp

  volumes:
    - name: tmp
      emptyDir: {}          # allowed volume type in restricted
```

---

## Kyverno — Policy Engine

Kyverno writes Kubernetes-native policies (no Rego). Install on k3d:

```bash
# Install Kyverno
kubectl create -f https://github.com/kyverno/kyverno/releases/download/v1.11.0/install.yaml

# Verify
kubectl get pods -n kyverno
```

### Kyverno Policies

```yaml
# kyverno-require-labels.yaml
apiVersion: kyverno.io/v1
kind: ClusterPolicy
metadata:
  name: require-app-label
spec:
  validationFailureAction: Enforce    # Audit | Enforce
  background: true                     # check existing resources too

  rules:
    - name: check-for-app-label
      match:
        any:
          - resources:
              kinds:
                - Deployment
      validate:
        message: "Deployment must have an 'app' label."
        pattern:
          metadata:
            labels:
              app: "?*"              # ?* = any non-empty string
```

```yaml
# kyverno-block-latest-tag.yaml
apiVersion: kyverno.io/v1
kind: ClusterPolicy
metadata:
  name: block-latest-tag
spec:
  validationFailureAction: Enforce
  rules:
    - name: check-image-tag
      match:
        any:
          - resources:
              kinds: [Pod]
      validate:
        message: "Image tag ':latest' is not allowed. Use a specific version."
        pattern:
          spec:
            containers:
              - image: "!*:latest"   # not ending in :latest
```

```yaml
# kyverno-mutate-add-labels.yaml — automatically add labels
apiVersion: kyverno.io/v1
kind: ClusterPolicy
metadata:
  name: add-managed-by-label
spec:
  rules:
    - name: add-label
      match:
        any:
          - resources:
              kinds: [Deployment, StatefulSet]
      mutate:
        patchStrategicMerge:
          metadata:
            labels:
              managed-by: kyverno        # added automatically on create/update
```

```yaml
# kyverno-generate-networkpolicy.yaml — auto-create deny-all when namespace is created
apiVersion: kyverno.io/v1
kind: ClusterPolicy
metadata:
  name: default-deny-all-on-ns-create
spec:
  rules:
    - name: generate-deny-all
      match:
        any:
          - resources:
              kinds: [Namespace]
      generate:
        apiVersion: networking.k8s.io/v1
        kind: NetworkPolicy
        name: deny-all
        namespace: "{{request.object.metadata.name}}"
        data:
          spec:
            podSelector: {}
            policyTypes: [Ingress, Egress]
```

---

## OPA Gatekeeper — Policy Engine (Rego-based)

Gatekeeper uses OPA Rego policies. Install:

```bash
kubectl apply -f https://raw.githubusercontent.com/open-policy-agent/gatekeeper/v3.14.0/deploy/gatekeeper.yaml
```

### ConstraintTemplate + Constraint

```yaml
# gatekeeper-require-labels.yaml
# Step 1: Define the template (the policy logic in Rego)
apiVersion: templates.gatekeeper.sh/v1
kind: ConstraintTemplate
metadata:
  name: k8srequiredlabels
spec:
  crd:
    spec:
      names:
        kind: K8sRequiredLabels
      validation:
        openAPIV3Schema:
          properties:
            labels:
              type: array
              items:
                type: string
  targets:
    - target: admission.k8s.gatekeeper.sh
      rego: |
        package k8srequiredlabels

        violation[{"msg": msg}] {
          provided := {label | input.review.object.metadata.labels[label]}
          required := {label | label := input.parameters.labels[_]}
          missing := required - provided
          count(missing) > 0
          msg := sprintf("Missing required labels: %v", [missing])
        }
---
# Step 2: Apply the constraint to Deployments
apiVersion: constraints.gatekeeper.sh/v1beta1
kind: K8sRequiredLabels
metadata:
  name: deployment-must-have-app-label
spec:
  match:
    kinds:
      - apiGroups: ["apps"]
        kinds: ["Deployment"]
  parameters:
    labels: ["app", "version"]   # both labels required
```

---

## Validation with kubectl

```bash
# Dry-run before applying — catches API validation errors
kubectl apply -f my-deployment.yaml --dry-run=server

# Validate a file without a cluster (static)
kubectl apply -f my-deployment.yaml --dry-run=client

# Check if a pod would be admitted in a namespace
kubectl run test --image=nginx -n production --dry-run=server

# Kyverno test — validate policies offline
kyverno apply kyverno-require-labels.yaml --resource pod.yaml
```

---

## Admission Webhook Chain

```
kubectl apply →  API Server  →  Mutating Webhooks  →  Validating Webhooks  →  etcd
                               (Kyverno mutate)        (Kyverno validate,
                                                        Gatekeeper,
                                                        PSA enforcer)
```

---

## Gotchas

1. **PSA applies at the namespace level, not cluster level** — you must label each namespace. Unlabeled namespaces default to `privileged` mode.
2. **`warn` mode does not block** — use `enforce` in production to actually reject non-compliant pods.
3. **System namespaces should be `privileged`** — `kube-system` needs privilege for system pods. Never apply `restricted` to it.
4. **Kyverno `background: true`** — audits existing resources. Without it, only new/updated resources are checked.

---

## Practice

1. Label the `default` namespace with `baseline` enforce. Try to run a privileged pod — verify it's blocked.
2. Label a new namespace `secure-ns` with `restricted` enforce. Write a compliant Deployment and verify it runs.
3. Install Kyverno and apply the `block-latest-tag` policy. Verify that applying a Deployment with `:latest` fails.
4. Use `--dry-run=server` to check if your manifests comply with PSS before applying to production.

---

## Key Takeaways

- Pod Security Standards: `privileged` (anything goes) → `baseline` (no host access/privesc) → `restricted` (explicit security context required).
- Apply via namespace labels: `pod-security.kubernetes.io/enforce: restricted`.
- Use `warn` + `audit` first to see violations before switching to `enforce`.
- Kyverno (YAML-based) is simpler than Gatekeeper (Rego-based) for most teams — start with Kyverno.
