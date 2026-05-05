# Day 12 — Capstone: Full Internal Developer Platform

## Learning Objectives
- Build a complete internal developer platform with Crossplane
- Combine XRDs, Compositions, Claims, provider-kubernetes, and provider-helm
- Integrate with GitOps via ArgoCD
- Enable developer self-service with proper RBAC
- Handle the full lifecycle: provision → use → deprovision

---

## What We're Building

A platform where a developer files one Claim and gets:

```
ApplicationClaim (filed by developer)
      │
      ├── RDS PostgreSQL (provider-aws-rds)
      │     └── Connection Secret in developer namespace
      │
      ├── S3 Assets Bucket (provider-aws-s3)
      │     └── IAM credentials Secret in developer namespace
      │
      ├── Kubernetes Namespace (provider-kubernetes)
      │     └── With PSS labels + resource quota
      │
      └── Helm Release — the app itself (provider-helm)
            └── Configured with DB + S3 secrets automatically
```

All from a 10-line YAML file. Zero tickets. Three minutes.

---

## Step 1 — Cluster Setup

```bash
k3d cluster create platform \
  --agents 2 \
  --port "80:80@loadbalancer"

# Install Crossplane
helm repo add crossplane-stable https://charts.crossplane.io/stable
helm install crossplane crossplane-stable/crossplane \
  --namespace crossplane-system \
  --create-namespace \
  --wait

# Install ArgoCD
kubectl create namespace argocd
kubectl apply -n argocd \
  -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml

kubectl port-forward svc/argocd-server -n argocd 8443:443 &
```

---

## Step 2 — Providers

```yaml
# platform/crossplane/providers/providers.yaml
apiVersion: pkg.crossplane.io/v1
kind: Provider
metadata:
  name: provider-aws-rds
  annotations:
    argocd.argoproj.io/sync-wave: "0"
spec:
  package: xpkg.upbound.io/upbound/provider-aws-rds:v1.1.0
---
apiVersion: pkg.crossplane.io/v1
kind: Provider
metadata:
  name: provider-aws-s3
  annotations:
    argocd.argoproj.io/sync-wave: "0"
spec:
  package: xpkg.upbound.io/upbound/provider-aws-s3:v1.1.0
---
apiVersion: pkg.crossplane.io/v1
kind: Provider
metadata:
  name: provider-kubernetes
  annotations:
    argocd.argoproj.io/sync-wave: "0"
spec:
  package: xpkg.upbound.io/crossplane-contrib/provider-kubernetes:v0.14.0
---
apiVersion: pkg.crossplane.io/v1
kind: Provider
metadata:
  name: provider-helm
  annotations:
    argocd.argoproj.io/sync-wave: "0"
spec:
  package: xpkg.upbound.io/crossplane-contrib/provider-helm:v0.19.0
---
apiVersion: pkg.crossplane.io/v1beta1
kind: Function
metadata:
  name: function-patch-and-transform
  annotations:
    argocd.argoproj.io/sync-wave: "0"
spec:
  package: xpkg.upbound.io/crossplane-contrib/function-patch-and-transform:v0.6.0
---
apiVersion: pkg.crossplane.io/v1beta1
kind: Function
metadata:
  name: function-auto-ready
  annotations:
    argocd.argoproj.io/sync-wave: "0"
spec:
  package: xpkg.upbound.io/crossplane-contrib/function-auto-ready:v0.2.0
```

---

## Step 3 — ProviderConfigs

```yaml
# platform/crossplane/providerconfigs/providerconfigs.yaml
# AWS (using IRSA on EKS, or access keys locally)
apiVersion: aws.upbound.io/v1beta1
kind: ProviderConfig
metadata:
  name: default
  annotations:
    argocd.argoproj.io/sync-wave: "1"
spec:
  credentials:
    source: Secret
    secretRef:
      namespace: crossplane-system
      name: aws-credentials          # created by Sealed Secrets
      key: credentials
---
# Kubernetes (same cluster)
apiVersion: kubernetes.crossplane.io/v1alpha1
kind: ProviderConfig
metadata:
  name: default
  annotations:
    argocd.argoproj.io/sync-wave: "1"
spec:
  credentials:
    source: InjectedIdentity
---
# Helm (same cluster)
apiVersion: helm.crossplane.io/v1beta1
kind: ProviderConfig
metadata:
  name: default
  annotations:
    argocd.argoproj.io/sync-wave: "1"
spec:
  credentials:
    source: InjectedIdentity
```

---

## Step 4 — XRD: Application

```yaml
# platform/platform-apis/application/xrd.yaml
apiVersion: apiextensions.crossplane.io/v1
kind: CompositeResourceDefinition
metadata:
  name: xapplications.platform.mycompany.com
  annotations:
    argocd.argoproj.io/sync-wave: "2"
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
    - bucket-name
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
                  required:
                    - appName
                    - dbSize
                    - region
                    - chartVersion
                  properties:
                    appName:
                      type: string
                      description: "Application name (used to name all resources)"
                    dbSize:
                      type: string
                      enum: [small, medium, large]
                    dbEngine:
                      type: string
                      enum: [postgres, mysql]
                      default: postgres
                    region:
                      type: string
                      default: us-east-1
                    chartVersion:
                      type: string
                      description: "Helm chart version to deploy"
                    team:
                      type: string
                      description: "Owning team name (for labels)"
```

---

## Step 5 — Composition: Application

```yaml
# platform/platform-apis/application/composition.yaml
apiVersion: apiextensions.crossplane.io/v1
kind: Composition
metadata:
  name: application-aws
  annotations:
    argocd.argoproj.io/sync-wave: "3"
spec:
  compositeTypeRef:
    apiVersion: platform.mycompany.com/v1alpha1
    kind: XApplication

  mode: Pipeline

  pipeline:
    - step: resources
      functionRef:
        name: function-patch-and-transform

      input:
        apiVersion: pt.fn.crossplane.io/v1beta1
        kind: Resources
        resources:

          # 1. RDS Database
          - name: database
            base:
              apiVersion: rds.aws.upbound.io/v1beta1
              kind: Instance
              spec:
                forProvider:
                  engine: postgres
                  engineVersion: "15.4"
                  instanceClass: db.t3.micro
                  allocatedStorage: 20
                  skipFinalSnapshot: true
                  publiclyAccessible: false
                  autoMinorVersionUpgrade: true
                  backupRetentionPeriod: 7
                providerConfigRef:
                  name: default
                deletionPolicy: Orphan
                writeConnectionSecretToRef:
                  namespace: crossplane-system
                  name: placeholder
            patches:
              - type: FromCompositeFieldPath
                fromFieldPath: spec.parameters.region
                toFieldPath: spec.forProvider.region
              - type: FromCompositeFieldPath
                fromFieldPath: spec.parameters.dbEngine
                toFieldPath: spec.forProvider.engine
              - type: FromCompositeFieldPath
                fromFieldPath: spec.parameters.dbSize
                toFieldPath: spec.forProvider.instanceClass
                transforms:
                  - type: map
                    map:
                      small:  db.t3.micro
                      medium: db.m5.large
                      large:  db.r5.xlarge
              - type: FromCompositeFieldPath
                fromFieldPath: spec.parameters.dbSize
                toFieldPath: spec.forProvider.allocatedStorage
                transforms:
                  - type: map
                    map:
                      small:  20
                      medium: 100
                      large:  500
              - type: FromCompositeFieldPath
                fromFieldPath: spec.parameters.appName
                toFieldPath: spec.writeConnectionSecretToRef.name
                transforms:
                  - type: string
                    string:
                      type: Format
                      fmt: "%s-db-conn"
            connectionDetails:
              - type: FromFieldPath
                name: db-endpoint
                fromFieldPath: status.atProvider.endpoint
              - type: FromConnectionSecretKey
                name: db-password
                fromConnectionSecretKey: password

          # 2. S3 Assets Bucket
          - name: assets-bucket
            base:
              apiVersion: s3.aws.upbound.io/v1beta1
              kind: Bucket
              spec:
                forProvider: {}
                providerConfigRef:
                  name: default
                deletionPolicy: Retain
                writeConnectionSecretToRef:
                  namespace: crossplane-system
                  name: placeholder
            patches:
              - type: FromCompositeFieldPath
                fromFieldPath: spec.parameters.region
                toFieldPath: spec.forProvider.region
              - type: FromCompositeFieldPath
                fromFieldPath: spec.parameters.appName
                toFieldPath: metadata.annotations["crossplane.io/external-name"]
                transforms:
                  - type: string
                    string:
                      type: Format
                      fmt: "%s-assets"
              - type: FromCompositeFieldPath
                fromFieldPath: spec.parameters.appName
                toFieldPath: spec.writeConnectionSecretToRef.name
                transforms:
                  - type: string
                    string:
                      type: Format
                      fmt: "%s-s3-conn"
            connectionDetails:
              - type: FromFieldPath
                name: bucket-name
                fromFieldPath: metadata.annotations["crossplane.io/external-name"]

          # 3. Namespace with labels and quota
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
                      labels:
                        pod-security.kubernetes.io/enforce: restricted
                        managed-by: crossplane
                    # ResourceQuota created alongside
                providerConfigRef:
                  name: default
            patches:
              - type: FromCompositeFieldPath
                fromFieldPath: spec.parameters.appName
                toFieldPath: spec.forProvider.manifest.metadata.name
              - type: FromCompositeFieldPath
                fromFieldPath: spec.parameters.team
                toFieldPath: spec.forProvider.manifest.metadata.labels.team

          # 4. Helm release — deploy the app
          - name: app-release
            base:
              apiVersion: helm.crossplane.io/v1beta1
              kind: Release
              spec:
                forProvider:
                  chart:
                    name: myapp
                    repository: https://charts.mycompany.com
                  values:
                    replicaCount: 2
                providerConfigRef:
                  name: default
            patches:
              - type: FromCompositeFieldPath
                fromFieldPath: spec.parameters.chartVersion
                toFieldPath: spec.forProvider.chart.version
              - type: FromCompositeFieldPath
                fromFieldPath: spec.parameters.appName
                toFieldPath: spec.forProvider.namespace

    - step: auto-ready
      functionRef:
        name: function-auto-ready
```

---

## Step 6 — RBAC for Claims

```yaml
# platform/platform-apis/rbac/developer-role.yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: platform-developer
rules:
  - apiGroups: ["platform.mycompany.com"]
    resources: ["applications", "applications/status"]
    verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]
---
# Bind to team namespaces via RoleBinding (not ClusterRoleBinding)
```

---

## Step 7 — Developer Files a Claim

```yaml
# claims/team-backend/taskapp.yaml
apiVersion: platform.mycompany.com/v1alpha1
kind: Application
metadata:
  name: taskapp
  namespace: team-backend
spec:
  parameters:
    appName: taskapp-prod
    dbSize: small
    region: us-east-1
    chartVersion: "1.5.0"
    team: backend
  writeConnectionSecretToRef:
    name: taskapp-conn
```

```bash
kubectl apply -f claims/team-backend/taskapp.yaml

# Watch everything provision
kubectl get application taskapp -n team-backend -w
# NAME      READY   CONNECTION-SECRET   AGE
# taskapp   False   taskapp-conn        5s
# taskapp   False   taskapp-conn        2m   (namespace + S3 ready, DB provisioning)
# taskapp   True    taskapp-conn        8m   (all ready)

# Check all managed resources created
kubectl get managed | grep taskapp-prod

# Verify connection secret in developer namespace
kubectl get secret taskapp-conn -n team-backend
kubectl get secret taskapp-conn -n team-backend \
  -o jsonpath='{.data.db-endpoint}' | base64 -d
```

---

## Step 8 — Failure Scenarios

```bash
# Scenario 1: Wrong parameter — caught by schema validation
kubectl apply -f - <<EOF
apiVersion: platform.mycompany.com/v1alpha1
kind: Application
metadata:
  name: bad-app
  namespace: team-backend
spec:
  parameters:
    appName: bad
    dbSize: xlarge     # not in enum: [small, medium, large]
    region: us-east-1
    chartVersion: "1.0"
EOF
# Error: spec.parameters.dbSize: Unsupported value "xlarge"

# Scenario 2: Drift detection
# Manually change the RDS instance class in AWS Console
# Crossplane detects and reverts within 1 minute

# Scenario 3: Deprovision the app
kubectl delete application taskapp -n team-backend
# RDS: stays (deletionPolicy: Orphan — protect data)
# S3:  stays (deletionPolicy: Retain — protect objects)
# Namespace + Helm release: deleted
```

---

## Platform Runbook: Adding a New Team

```bash
# 1. Create the team namespace
kubectl create namespace team-data

# 2. Bind the developer ClusterRole in their namespace
kubectl create rolebinding team-data-developers \
  --clusterrole=platform-developer \
  --group=team-data-engineers \
  --namespace=team-data

# 3. Developer can now file Claims
kubectl apply -f - <<EOF
apiVersion: platform.mycompany.com/v1alpha1
kind: Application
metadata:
  name: dataplatform
  namespace: team-data
spec:
  parameters:
    appName: dataplatform-prod
    dbSize: large
    region: us-east-1
    chartVersion: "2.0.0"
    team: data
  writeConnectionSecretToRef:
    name: dataplatform-conn
EOF
```

---

## Platform Checklist

```
☐ Providers installed (aws-rds, aws-s3, kubernetes, helm)
☐ ProviderConfigs created (no credentials in Git — IRSA or Sealed Secrets)
☐ Functions installed (function-patch-and-transform, function-auto-ready)
☐ XRDs applied with proper schema validation
☐ Compositions tested with `crossplane render` before applying
☐ RBAC: ClusterRole for Claim creation, RoleBinding per namespace
☐ deletionPolicy: Orphan on all database and storage MRs
☐ ArgoCD sync waves: providers(0) → providerconfigs(1) → xrds(2) → compositions(3) → claims(don't prune)
☐ Drift detection tested: manual cloud change reverts within 1 min
☐ Developer self-service tested end-to-end: Claim → Ready → App running
```

---

## Key Takeaways

- One `Application` Claim provisions an entire stack: cloud resources, Kubernetes namespace, and the app itself.
- Crossplane continuously reconciles — infrastructure drift is automatically corrected without manual intervention.
- RBAC on Claims + namespace isolation gives teams self-service within guardrails. No cloud console access required.
- GitOps + Crossplane = auditable, version-controlled, self-healing infrastructure as Kubernetes resources.

---

## Course Complete

Congratulations on completing the 12-day Crossplane course.

| Days | Topic |
|---|---|
| 01 | Control plane pattern, Crossplane vs Terraform, core concepts |
| 02 | Install on k3d, crossplane CLI, provider-nop for local practice |
| 03 | Providers: AWS, GCP, Azure — installation, ProviderConfig, IRSA |
| 04 | Managed Resources: S3, RDS, VPC, GCS — forProvider, deletionPolicy, cross-refs |
| 05 | XRDs: define the platform API schema with OpenAPI v3 validation |
| 06 | Compositions: patch-based mapping from XR to managed resources, transforms |
| 07 | Claims: developer self-service, RBAC, connection secrets in app namespace |
| 08 | Composition Functions: KCL for conditionals and loops, Go for custom logic |
| 09 | Packages: build, push, and install Configuration packages as OCI images |
| 10 | provider-kubernetes + provider-helm: manage K8s resources and Helm releases |
| 11 | GitOps: ArgoCD sync waves, FluxCD dependsOn, drift detection, secret safety |
| 12 | Capstone: full internal developer platform — one Claim provisions everything |

**Next steps:** Explore Upbound's marketplace for community Compositions, or contribute your own XRD/Composition package to the Crossplane community.
