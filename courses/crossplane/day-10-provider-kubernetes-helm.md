# Day 10 — Provider-Kubernetes & Provider-Helm

## Learning Objectives
- Use provider-kubernetes to manage Kubernetes resources as Crossplane MRs
- Use provider-helm to deploy Helm releases as Crossplane MRs
- Compose cloud resources + Kubernetes resources in one XR
- Manage resources in remote clusters via provider-kubernetes

---

## Why These Providers?

`provider-kubernetes` and `provider-helm` extend Crossplane beyond cloud APIs:

| Provider | What It Manages | Use Case |
|---|---|---|
| `provider-kubernetes` | Any Kubernetes resource (Deployment, Secret, CRD...) | Manage K8s resources in the same or remote cluster |
| `provider-helm` | Helm releases | Install/upgrade Helm charts as managed resources |

This lets you compose a complete developer experience in one XR:
- Create an RDS instance (provider-aws)
- Create a Kubernetes Secret with the credentials (provider-kubernetes)
- Deploy the app via a Helm chart (provider-helm)

---

## Install the Providers

```yaml
# providers.yaml
apiVersion: pkg.crossplane.io/v1
kind: Provider
metadata:
  name: provider-kubernetes
spec:
  package: xpkg.upbound.io/crossplane-contrib/provider-kubernetes:v0.14.0
---
apiVersion: pkg.crossplane.io/v1
kind: Provider
metadata:
  name: provider-helm
spec:
  package: xpkg.upbound.io/crossplane-contrib/provider-helm:v0.19.0
```

```bash
kubectl apply -f providers.yaml

kubectl get providers
# NAME                  INSTALLED   HEALTHY
# provider-kubernetes   True        True
# provider-helm         True        True
```

---

## ProviderConfig for provider-kubernetes (Same Cluster)

```yaml
# providerconfig-kubernetes.yaml
apiVersion: kubernetes.crossplane.io/v1alpha1
kind: ProviderConfig
metadata:
  name: default
spec:
  credentials:
    source: InjectedIdentity     # use the controller's own service account
```

```bash
kubectl apply -f providerconfig-kubernetes.yaml

# Grant the provider's SA cluster-admin (for same-cluster management)
# In production, use a minimal ClusterRole instead
SA=$(kubectl -n crossplane-system get sa \
  -o name | grep provider-kubernetes | sed -e 's|serviceaccount/||')

kubectl create clusterrolebinding provider-kubernetes-admin \
  --clusterrole=cluster-admin \
  --serviceaccount="crossplane-system:${SA}"
```

---

## ProviderConfig for provider-kubernetes (Remote Cluster)

```yaml
# remote-cluster-secret.yaml
apiVersion: v1
kind: Secret
metadata:
  name: remote-cluster-kubeconfig
  namespace: crossplane-system
type: Opaque
stringData:
  kubeconfig: |
    apiVersion: v1
    kind: Config
    clusters:
      - name: remote
        cluster:
          server: https://remote-cluster-api:6443
          certificate-authority-data: <base64-ca>
    users:
      - name: crossplane
        user:
          token: <service-account-token>
    contexts:
      - name: remote
        context:
          cluster: remote
          user: crossplane
    current-context: remote
---
apiVersion: kubernetes.crossplane.io/v1alpha1
kind: ProviderConfig
metadata:
  name: remote-cluster
spec:
  credentials:
    source: Secret
    secretRef:
      namespace: crossplane-system
      name: remote-cluster-kubeconfig
      key: kubeconfig
```

---

## provider-kubernetes — Manage a Namespace

```yaml
# namespace-mr.yaml
apiVersion: kubernetes.crossplane.io/v1alpha2
kind: Object
metadata:
  name: team-backend-namespace
spec:
  forProvider:
    manifest:
      apiVersion: v1
      kind: Namespace
      metadata:
        name: team-backend
        labels:
          pod-security.kubernetes.io/enforce: restricted
          team: backend

  providerConfigRef:
    name: default            # same cluster

  # Or manage on a remote cluster:
  # providerConfigRef:
  #   name: remote-cluster
```

---

## provider-kubernetes — Manage a Secret

```yaml
# sync-db-secret.yaml
# Sync the connection secret from crossplane-system → team-backend namespace
apiVersion: kubernetes.crossplane.io/v1alpha2
kind: Object
metadata:
  name: sync-taskapp-db-secret
spec:
  forProvider:
    manifest:
      apiVersion: v1
      kind: Secret
      metadata:
        name: taskapp-db-conn
        namespace: team-backend          # target namespace
      type: Opaque
      data: {}                           # patched below from connection secret

  # Reference the connection secret as a patch source
  references:
    - patchesFrom:
        apiVersion: v1
        kind: Secret
        namespace: crossplane-system
        name: taskapp-db-conn-xr        # the XR-level connection secret
        fieldPath: data
      toFieldPath: spec.forProvider.manifest.data

  providerConfigRef:
    name: default
```

---

## provider-helm — Deploy a Helm Release

```yaml
# helm-release-nginx.yaml
apiVersion: helm.crossplane.io/v1beta1
kind: Release
metadata:
  name: nginx-ingress
spec:
  forProvider:
    chart:
      name: ingress-nginx
      repository: https://kubernetes.github.io/ingress-nginx
      version: 4.9.0

    namespace: ingress-nginx
    createNamespace: true

    values:                             # Helm values
      controller:
        replicaCount: 2
        service:
          type: LoadBalancer
        metrics:
          enabled: true

    # Or reference values from a ConfigMap
    # valuesFrom:
    #   - configMapKeyRef:
    #       name: nginx-values
    #       namespace: crossplane-system
    #       key: values.yaml

  providerConfigRef:
    name: default

  rollbackLimit: 3                      # keep 3 rollback revisions
```

```bash
kubectl apply -f helm-release-nginx.yaml

kubectl get release nginx-ingress -w
# NAME            CHART          VERSION   SYNCED   READY   AGE
# nginx-ingress   ingress-nginx  4.9.0     True     True    2m

# The Helm release is managed by Crossplane — updates via kubectl patch, not helm upgrade
kubectl patch release nginx-ingress --type=merge \
  -p '{"spec":{"forProvider":{"values":{"controller":{"replicaCount":3}}}}}'
```

---

## Compose Cloud + Kubernetes + Helm in One XR

This is the most powerful pattern — a single Claim provisions everything:

```yaml
# composition-full-app.yaml
apiVersion: apiextensions.crossplane.io/v1
kind: Composition
metadata:
  name: full-app-aws
spec:
  compositeTypeRef:
    apiVersion: platform.mycompany.com/v1alpha1
    kind: XApplication

  mode: Pipeline
  pipeline:
    - step: patch-and-transform
      functionRef:
        name: function-patch-and-transform

      input:
        apiVersion: pt.fn.crossplane.io/v1beta1
        kind: Resources
        resources:

          # 1. Create RDS database (cloud resource)
          - name: database
            base:
              apiVersion: rds.aws.upbound.io/v1beta1
              kind: Instance
              spec:
                forProvider:
                  region: us-east-1
                  engine: postgres
                  engineVersion: "15.4"
                  instanceClass: db.t3.micro
                  skipFinalSnapshot: true
                  publiclyAccessible: false
                providerConfigRef:
                  name: default
                deletionPolicy: Orphan
                writeConnectionSecretToRef:
                  namespace: crossplane-system
                  name: ""               # patched
            patches:
              - type: FromCompositeFieldPath
                fromFieldPath: metadata.name
                toFieldPath: spec.writeConnectionSecretToRef.name
                transforms:
                  - type: string
                    string:
                      type: Format
                      fmt: "%s-db-conn"
            connectionDetails:
              - type: FromFieldPath
                name: endpoint
                fromFieldPath: status.atProvider.endpoint

          # 2. Create namespace (Kubernetes resource)
          - name: namespace
            base:
              apiVersion: kubernetes.crossplane.io/v1alpha2
              kind: Object
              spec:
                forProvider:
                  manifest:
                    apiVersion: v1
                    kind: Namespace
                    metadata:
                      name: ""           # patched
                      labels:
                        managed-by: crossplane
                providerConfigRef:
                  name: default
            patches:
              - type: FromCompositeFieldPath
                fromFieldPath: spec.parameters.namespace
                toFieldPath: spec.forProvider.manifest.metadata.name

          # 3. Deploy the app via Helm (Kubernetes resource)
          - name: app-release
            base:
              apiVersion: helm.crossplane.io/v1beta1
              kind: Release
              spec:
                forProvider:
                  chart:
                    name: ""             # patched
                    repository: https://charts.mycompany.com
                    version: ""          # patched
                  namespace: ""          # patched
                  createNamespace: false
                  values:
                    replicaCount: 2
                providerConfigRef:
                  name: default
            patches:
              - type: FromCompositeFieldPath
                fromFieldPath: spec.parameters.chartName
                toFieldPath: spec.forProvider.chart.name
              - type: FromCompositeFieldPath
                fromFieldPath: spec.parameters.chartVersion
                toFieldPath: spec.forProvider.chart.version
              - type: FromCompositeFieldPath
                fromFieldPath: spec.parameters.namespace
                toFieldPath: spec.forProvider.namespace

    - step: auto-ready
      functionRef:
        name: function-auto-ready
```

---

## XRD for Full Application

```yaml
# xrd-application.yaml
apiVersion: apiextensions.crossplane.io/v1
kind: CompositeResourceDefinition
metadata:
  name: xapplications.platform.mycompany.com
spec:
  group: platform.mycompany.com
  names:
    kind: XApplication
    plural: xapplications
  claimNames:
    kind: Application
    plural: applications
  connectionSecretKeys:
    - db-endpoint
    - db-password
  versions:
    - name: v1alpha1
      served: true
      referenceable: true
      schema:
        openAPIV3Schema:
          type: object
          properties:
            spec:
              type: object
              properties:
                parameters:
                  type: object
                  required: [namespace, chartName, chartVersion]
                  properties:
                    namespace:
                      type: string
                    chartName:
                      type: string
                    chartVersion:
                      type: string
```

---

## Developer Claim — One Claim Provisions Everything

```yaml
# application-claim.yaml
apiVersion: platform.mycompany.com/v1alpha1
kind: Application
metadata:
  name: taskapp
  namespace: team-backend
spec:
  parameters:
    namespace: taskapp-prod
    chartName: taskapp
    chartVersion: "1.5.0"
  writeConnectionSecretToRef:
    name: taskapp-conn
```

```bash
kubectl apply -f application-claim.yaml

# One Claim creates:
# - RDS database in AWS
# - Kubernetes namespace
# - Helm release with the app

vela status taskapp -n team-backend   # if using KubeVela
# OR
kubectl get managed | grep taskapp    # see all MRs
```

---

## Gotchas

1. **provider-kubernetes needs RBAC on the target cluster** — the provider's service account must have permissions to create the objects you're managing. Use a least-privilege ClusterRole, not cluster-admin.
2. **provider-helm manages the Helm release state** — don't run `helm upgrade` manually on a release managed by Crossplane. Crossplane will revert it.
3. **Object provider uses `manifest` field** — the entire Kubernetes resource goes in `spec.forProvider.manifest`. Patches target fields within that manifest using full paths like `spec.forProvider.manifest.metadata.name`.
4. **Connection detail flow across providers** — only cloud provider MRs publish connection details by default. `provider-kubernetes` Object and `provider-helm` Release don't publish connection details unless explicitly configured.

---

## Practice

1. Install `provider-kubernetes` with same-cluster InjectedIdentity. Create an `Object` resource that manages a Namespace. Verify the namespace is created.
2. Install `provider-helm`. Deploy the Bitnami Redis chart as a `Release`. Update a Helm value via `kubectl patch` and verify Crossplane applies the change.
3. Create an XRD + Composition that combines an S3 bucket (provider-aws) with a Kubernetes Secret that stores the bucket name (provider-kubernetes).
4. Deploy a Helm release to a remote k3d cluster using a kubeconfig-based ProviderConfig. Verify the release appears in the remote cluster.

---

## Key Takeaways

- `provider-kubernetes` manages any Kubernetes resource (same or remote cluster) as a Crossplane managed resource.
- `provider-helm` manages Helm releases — updates via `kubectl patch`, not `helm upgrade`. Never mix the two.
- Combining cloud providers + provider-kubernetes + provider-helm in one Composition creates a complete "one Claim provisions everything" experience.
- Use `provider-kubernetes` to sync connection secrets from `crossplane-system` to developer namespaces — the Claim's connection secret.
