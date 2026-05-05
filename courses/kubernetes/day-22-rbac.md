# Day 22 — RBAC (Roles, ClusterRoles & Bindings)

## Learning Objectives
- Understand Kubernetes RBAC model
- Create Roles, ClusterRoles and bind them to users and ServiceAccounts
- Follow the principle of least privilege
- Audit and debug RBAC permissions

---

## RBAC Concepts

| Resource | Scope | Purpose |
|---|---|---|
| `Role` | Namespace | Grants permissions within one namespace |
| `ClusterRole` | Cluster-wide | Grants permissions across all namespaces or for cluster-scoped resources |
| `RoleBinding` | Namespace | Binds a Role OR ClusterRole to a subject within a namespace |
| `ClusterRoleBinding` | Cluster-wide | Binds a ClusterRole to a subject across all namespaces |

Subjects: `User`, `Group`, `ServiceAccount`

---

## Role — Namespace-Scoped

```yaml
# role-dev.yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: developer
  namespace: staging
rules:
  - apiGroups: [""]                 # "" = core API group (pods, services, etc.)
    resources: ["pods", "pods/log", "pods/exec"]
    verbs: ["get", "list", "watch", "create", "delete"]

  - apiGroups: [""]
    resources: ["services", "endpoints"]
    verbs: ["get", "list", "watch"]

  - apiGroups: ["apps"]             # apps API group (deployments, replicasets)
    resources: ["deployments", "replicasets"]
    verbs: ["get", "list", "watch", "update", "patch"]

  - apiGroups: [""]
    resources: ["configmaps"]
    verbs: ["get", "list"]          # read-only — no create/update

  - apiGroups: [""]
    resources: ["secrets"]
    verbs: []                       # no access to secrets
```

---

## RoleBinding

```yaml
# rolebinding-dev.yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: developer-binding
  namespace: staging
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role                        # Role or ClusterRole
  name: developer
subjects:
  - kind: User
    name: alice                     # must match the username in the kubeconfig
    apiGroup: rbac.authorization.k8s.io

  - kind: User
    name: bob
    apiGroup: rbac.authorization.k8s.io

  - kind: Group
    name: backend-team              # all members of this group
    apiGroup: rbac.authorization.k8s.io

  - kind: ServiceAccount
    name: deploy-bot                # a service account in the same namespace
    namespace: staging
```

---

## ClusterRole — Cluster-Wide

```yaml
# clusterrole-readonly.yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: cluster-readonly
rules:
  - apiGroups: [""]
    resources: ["*"]               # all core resources
    verbs: ["get", "list", "watch"]

  - apiGroups: ["apps"]
    resources: ["*"]
    verbs: ["get", "list", "watch"]

  - apiGroups: ["batch"]
    resources: ["jobs", "cronjobs"]
    verbs: ["get", "list", "watch"]

  - apiGroups: ["networking.k8s.io"]
    resources: ["ingresses"]
    verbs: ["get", "list", "watch"]

  - apiGroups: ["storage.k8s.io"]
    resources: ["persistentvolumes", "storageclasses"]
    verbs: ["get", "list", "watch"]
```

---

## ClusterRoleBinding

```yaml
# clusterrolebinding-readonly.yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: cluster-readonly-binding
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: cluster-readonly
subjects:
  - kind: Group
    name: sre-team
    apiGroup: rbac.authorization.k8s.io
```

---

## ClusterRole Bound to a Single Namespace (via RoleBinding)

Reuse cluster-level roles within a namespace:

```yaml
# Bind a ClusterRole using a RoleBinding (limits scope to namespace)
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: use-cluster-role-in-ns
  namespace: production
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole                 # ← ClusterRole, not Role
  name: cluster-readonly
subjects:
  - kind: User
    name: carol
    apiGroup: rbac.authorization.k8s.io
```

Carol can now read all resources in `production` only — not cluster-wide.

---

## Service Account for CI/CD

```yaml
# ci-rbac.yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: ci-deploy
  namespace: production
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: deployer
  namespace: production
rules:
  - apiGroups: ["apps"]
    resources: ["deployments"]
    verbs: ["get", "list", "update", "patch"]

  - apiGroups: [""]
    resources: ["configmaps", "services"]
    verbs: ["get", "list", "update", "patch", "create"]

  - apiGroups: ["batch"]
    resources: ["jobs"]
    verbs: ["get", "list", "create", "delete"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: ci-deploy-binding
  namespace: production
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: deployer
subjects:
  - kind: ServiceAccount
    name: ci-deploy
    namespace: production
```

---

## Operator / Controller RBAC

```yaml
# operator-rbac.yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: myoperator
rules:
  - apiGroups: ["mygroup.example.com"]
    resources: ["mycrds"]
    verbs: ["*"]                   # full control of custom resources

  - apiGroups: ["apps"]
    resources: ["deployments", "statefulsets"]
    verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]

  - apiGroups: [""]
    resources: ["events"]
    verbs: ["create", "patch"]

  - apiGroups: [""]
    resources: ["pods"]
    verbs: ["get", "list", "watch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: myoperator
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: myoperator
subjects:
  - kind: ServiceAccount
    name: myoperator
    namespace: operators
```

---

## Auditing Permissions

```bash
# Can I do this?
kubectl auth can-i create pods
kubectl auth can-i delete deployments --namespace=production
kubectl auth can-i "*" "*"           # am I cluster-admin?

# Can this ServiceAccount do this?
kubectl auth can-i list secrets \
  --as=system:serviceaccount:staging:ci-deploy \
  --namespace=staging

# What can a user do?
kubectl auth can-i --list --as=alice --namespace=staging

# List all RBAC resources
kubectl get roles,rolebindings -n staging
kubectl get clusterroles,clusterrolebindings

# Describe a role
kubectl describe role developer -n staging
kubectl describe clusterrole cluster-admin
```

---

## Built-in ClusterRoles

```bash
kubectl get clusterroles | grep -v system

# Key built-in roles:
# cluster-admin  — full control of the entire cluster
# admin          — full control within a namespace
# edit           — read/write most resources in a namespace
# view           — read-only within a namespace
```

Using built-in roles:

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: view-binding
  namespace: staging
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: view               # built-in read-only role
subjects:
  - kind: Group
    name: interns
    apiGroup: rbac.authorization.k8s.io
```

---

## Gotchas

1. **RBAC is additive — no deny rules** — if multiple roles grant permissions, they all apply. You can't revoke a permission with another role.
2. **`*` on resources does not include subresources** — `pods` doesn't include `pods/log` or `pods/exec`. Specify subresources explicitly.
3. **ClusterRoleBinding gives cluster-wide permissions** — a RoleBinding scopes a ClusterRole to one namespace. Don't use ClusterRoleBinding when RoleBinding is sufficient.
4. **Deleting a ServiceAccount token secret** (k8s 1.24+ auto-generates tokens) — tokens are now auto-generated and injected. Don't create long-lived tokens unnecessarily.

---

## Practice

1. Create a `read-only` Role in namespace `staging`. Bind it to a user and verify with `kubectl auth can-i`.
2. Create a `ci-deploy` ServiceAccount with permission to update Deployments. Use it in a Job.
3. Use `kubectl auth can-i --list` to audit what a specific ServiceAccount can do.
4. Try the built-in `edit` ClusterRole with a RoleBinding — verify the user can create but not delete namespaces.

---

## Key Takeaways

- Role + RoleBinding = namespace-scoped. ClusterRole + ClusterRoleBinding = cluster-wide.
- A ClusterRole bound with a RoleBinding is scoped to the namespace — a useful pattern.
- RBAC is additive — no deny rules. Least privilege: start with nothing, add only what's needed.
- `kubectl auth can-i` is your debugging tool — check permissions before and after setting up RBAC.
