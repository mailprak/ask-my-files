# Day 01 — What is Crossplane & the Control Plane Pattern

## Learning Objectives
- Understand why Crossplane exists and the problem it solves
- Learn the control plane pattern for infrastructure management
- Know how Crossplane differs from Terraform and Helm
- Understand the core building blocks at a high level

---

## The Problem: Infrastructure Is Not Kubernetes-Native

Traditional infrastructure tooling lives outside Kubernetes:

```
Terraform    → state files, CLI, plan/apply cycle, separate pipeline
CloudFormation → AWS-only, stack drift, YAML/JSON templates
Pulumi       → code-based, separate runtime, state backend
Ansible      → procedural, not declarative, not self-healing
```

None of these tools integrate with Kubernetes RBAC, are continuously reconciled, or work with `kubectl`.

Crossplane brings infrastructure management **into** Kubernetes — as Custom Resource Definitions and controllers.

---

## The Control Plane Pattern

Crossplane implements the Kubernetes controller pattern for cloud resources:

```
Developer applies:    kubectl apply -f database-claim.yaml
                              ↓
Crossplane controller reads the claim
                              ↓
Creates cloud resource (AWS RDS, GCP CloudSQL, Azure Database)
                              ↓
Continuously reconciles — detects drift, heals automatically
                              ↓
Writes connection details back as a Kubernetes Secret
```

This is the same reconciliation loop that makes Deployments self-healing — applied to cloud infrastructure.

---

## Crossplane Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  Kubernetes Cluster                                             │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Crossplane Core                                         │  │
│  │  - Manages providers, compositions, XRDs                 │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐ │
│  │ provider-aws │  │ provider-gcp │  │ provider-kubernetes  │ │
│  │ (watches MRs)│  │ (watches MRs)│  │ (watches K8s objs)   │ │
│  └──────┬───────┘  └──────┬───────┘  └──────────┬───────────┘ │
└─────────┼─────────────────┼────────────────────-─┼─────────────┘
          │                 │                       │
          ▼                 ▼                       ▼
       AWS API           GCP API             Kubernetes API
     (RDS, S3, VPC)   (GCS, GKE, SQL)     (remote cluster)
```

---

## Core Building Blocks

### Managed Resource (MR)
A direct 1:1 representation of a cloud resource. Written by developers or platform teams.

```yaml
# This YAML creates a real S3 bucket in AWS
apiVersion: s3.aws.upbound.io/v1beta1
kind: Bucket
metadata:
  name: my-app-assets
spec:
  forProvider:
    region: us-east-1
  providerConfigRef:
    name: aws-config
```

### Composite Resource (XR)
A custom API resource composed of multiple managed resources. Defined by the platform team.

```yaml
# A developer files this — they don't know what it creates underneath
apiVersion: platform.mycompany.com/v1alpha1
kind: Database
metadata:
  name: taskapp-db
spec:
  parameters:
    size: small
    engine: postgres
```

### CompositeResourceDefinition (XRD)
Defines the schema for a Composite Resource — what fields a developer can set.

### Composition
Maps a Composite Resource to the actual managed resources it creates. Contains the "recipe".

### Claim
Namespace-scoped access to a Composite Resource. Developers file Claims; the platform creates XRs.

### Provider
A Kubernetes controller + CRDs for a specific cloud platform. `provider-aws` adds 1000+ AWS resource types.

### ProviderConfig
Credentials and configuration for a Provider (AWS credentials, GCP service account, etc.).

---

## Crossplane vs Terraform

| Aspect | Terraform | Crossplane |
|---|---|---|
| Runtime | CLI tool, separate pipeline | Kubernetes controller (always running) |
| State | State files (local/S3/Terraform Cloud) | Kubernetes etcd (the cluster IS the state) |
| Drift detection | `terraform plan` (manual) | Continuous reconciliation (automatic) |
| Self-healing | No — drift stays until next apply | Yes — controller reverts unauthorised changes |
| RBAC | Terraform Cloud / external | Kubernetes RBAC (native) |
| Secret handling | Terraform outputs, state contains secrets | Kubernetes Secrets (written back automatically) |
| Developer self-service | Difficult (full Terraform access needed) | Easy (file a Claim, get a database) |
| Multi-team isolation | Workspaces, modules | Namespaces, Claims |
| Learning curve | Moderate | Higher (K8s + CUE/composition) |

**When to use Terraform:** You're not already on Kubernetes, you need multi-cloud with complex module reuse, or your team knows Terraform deeply.

**When to use Crossplane:** You're on Kubernetes, you want self-healing infrastructure, you want developers to provision resources via `kubectl`, or you're building an internal developer platform.

---

## Crossplane vs Helm

Helm deploys Kubernetes resources from templates. Crossplane manages **cloud resources** that live outside the cluster.

They complement each other:
- `provider-helm`: Crossplane can deploy Helm releases as managed resources
- `provider-kubernetes`: Crossplane can manage Kubernetes resources in any cluster
- KubeVela + Crossplane: KubeVela handles app deployment, Crossplane provisions the cloud infrastructure the app needs

---

## The Developer Experience Goal

Without Crossplane — a developer needing a PostgreSQL database:
1. Opens a ticket to the DBA team
2. Waits 2–5 days
3. Gets credentials over Slack
4. Hard-codes credentials in the app
5. No automated rotation, no audit trail

With Crossplane — same developer:
```yaml
# Developer applies this YAML
apiVersion: platform.mycompany.com/v1alpha1
kind: DatabaseClaim
metadata:
  name: taskapp-db
  namespace: my-team
spec:
  parameters:
    engine: postgres
    size: small
```

```bash
kubectl apply -f database-claim.yaml
# Wait ~3 minutes
kubectl get secret taskapp-db-conn -n my-team
# Connection string is ready — no tickets, no waiting, no manual secrets
```

The platform team defines what `DatabaseClaim` creates (RDS, Aurora, Cloud SQL — whatever). Developers just file Claims.

---

## Key Concepts Diagram

```
Platform Team defines:
  XRD (the API schema)
  +
  Composition (the implementation)
        ↓
  creates a new Kubernetes API

Developer uses:
  Claim (namespace-scoped request)
        ↓
  Crossplane creates XR (cluster-scoped)
        ↓
  Composition renders Managed Resources
        ↓
  Provider controller calls cloud API
        ↓
  Cloud resource created
        ↓
  Connection secret written to developer's namespace
```

---

## Gotchas

1. **Crossplane does not replace Terraform for everything** — Terraform modules for complex networking (Transit Gateway, VPC peering) may be better expressed in HCL. Use Crossplane where the self-service and self-healing model adds value.
2. **Deleting a MR deletes the cloud resource** — unlike Terraform's `terraform destroy`, `kubectl delete` on a managed resource immediately starts deleting the cloud resource. Add `deletionPolicy: Orphan` to protect critical resources.
3. **Crossplane requires a running cluster** — if the cluster goes down, Crossplane can't reconcile. For production, Crossplane itself needs to run on a highly-available cluster.
4. **Cloud costs are immediate** — applying a managed resource to the cluster starts incurring cloud costs. There is no "plan" step. Be intentional about what you apply.

---

## Key Takeaways

- Crossplane brings cloud infrastructure into Kubernetes as Custom Resources — managed via `kubectl`, RBAC, and GitOps.
- The control plane pattern: controllers continuously reconcile desired state (YAML) against actual state (cloud API). Drift is automatically corrected.
- XRD + Composition = internal developer platform API. Claim = developer's self-service request.
- Crossplane and Terraform are complementary — Crossplane excels at self-service, self-healing, and developer workflows within Kubernetes.
