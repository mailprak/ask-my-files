# Day 01 — What is KubeVela & the Open Application Model (OAM)

## Learning Objectives
- Understand why KubeVela exists and the problem it solves
- Learn the four OAM primitives: Component, Trait, Policy, Workflow
- Understand the separation between developer and platform concerns
- Know how KubeVela relates to Kubernetes

---

## The Problem KubeVela Solves

Without KubeVela, deploying an app to Kubernetes means writing and managing many resources directly:

```
Developer must know about:
  Deployment → ReplicaSet → Pod
  Service → Ingress
  HPA → PodDisruptionBudget
  ConfigMap → Secret
  NetworkPolicy → ServiceAccount
  ... and all their interactions
```

KubeVela introduces the **Open Application Model (OAM)** — a standard for describing applications independent of the infrastructure that runs them.

```
Developer says:    "I need a web service with 2 replicas and an ingress"
Platform provides: All the Kubernetes primitives wired up correctly
```

---

## The Open Application Model (OAM)

OAM was co-authored by Microsoft and Alibaba. KubeVela is the Kubernetes implementation.

Four core primitives:

```
┌─────────────────────────────────────────────────────────────┐
│                      Application                            │
│                                                             │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐   │
│  │  Component   │   │    Trait     │   │   Policy     │   │
│  │              │   │              │   │              │   │
│  │  What runs   │   │  How it runs │   │  Where/how   │   │
│  │  (workload)  │   │  (behaviour) │   │  it deploys  │   │
│  └──────────────┘   └──────────────┘   └──────────────┘   │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │                    Workflow                          │  │
│  │           Steps that control the rollout             │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

---

## The Four Primitives

### 1. Component — What runs

A Component describes a deployable unit. It maps to a workload type (web service, worker, cron job, etc.). Components are written by developers.

```yaml
components:
  - name: api-server
    type: webservice          # built-in type: Deployment + Service
    properties:
      image: myapi:1.0
      port: 8080
      replicas: 2
```

### 2. Trait — How it runs

Traits attach operational behaviours to components. They are platform-provided capabilities that developers opt into.

```yaml
traits:
  - type: ingress             # expose the service via Ingress
    properties:
      domain: api.example.com
      http:
        "/": 8080

  - type: scaler              # attach an HPA
    properties:
      min: 2
      max: 10
      cpuPercent: 70
```

### 3. Policy — Where and how it deploys

Policies define deployment topology (which clusters) and per-environment overrides.

```yaml
policies:
  - name: staging-override
    type: override
    properties:
      components:
        - name: api-server
          properties:
            replicas: 1       # override replicas for staging only

  - name: target-clusters
    type: topology
    properties:
      clusters: ["staging", "production"]
```

### 4. Workflow — The rollout sequence

Workflow defines the ordered steps of a deployment. Steps can deploy, wait for approval, run checks, or send notifications.

```yaml
workflow:
  steps:
    - name: deploy-staging
      type: deploy
      properties:
        policies: ["staging-override"]

    - name: wait-for-approval
      type: suspend             # pause and wait for human approval

    - name: deploy-production
      type: deploy
      properties:
        policies: ["production-policy"]
```

---

## Who Owns What

This is the core SRE value proposition of KubeVela:

| Concern | Owner | Defined In |
|---|---|---|
| What image, what port, what env vars | Developer | Component properties |
| Ingress, HPA, resource limits, sidecars | Platform/SRE | Trait definitions |
| Which clusters, which namespaces | Platform/SRE | Policy definitions |
| Deployment sequence, approvals | Platform/SRE | Workflow steps |
| The ComponentDefinition itself | Platform/SRE | CUE-based definitions |

Developers write `Application` objects using types the platform team defines. They don't need to know about Deployments, Services, or Ingress resources.

---

## How KubeVela Relates to Kubernetes

KubeVela runs entirely on Kubernetes. It uses Custom Resource Definitions (CRDs) and controllers:

```
kubectl apply -f app.yaml (Application CR)
         ↓
KubeVela Controller (reads Application)
         ↓
Generates: Deployment + Service + Ingress + HPA
         ↓
Kubernetes reconciles these resources
```

KubeVela does NOT replace Kubernetes — it sits on top as an abstraction layer.

```bash
# You can always see the underlying resources KubeVela created
kubectl get deployment -n my-namespace
kubectl get ingress -n my-namespace
```

---

## A Complete Application (preview)

```yaml
# app.yaml — this is what a developer writes
apiVersion: core.oam.dev/v1beta1
kind: Application
metadata:
  name: taskapp
  namespace: production
spec:
  components:
    - name: api
      type: webservice
      properties:
        image: myapi:1.0
        port: 8080
      traits:
        - type: ingress
          properties:
            domain: api.example.com
            http:
              "/": 8080
        - type: scaler
          properties:
            min: 2
            max: 10

    - name: worker
      type: worker
      properties:
        image: myworker:1.0
        cmd: ["./worker", "--queue=tasks"]
```

One YAML file. The platform generates everything else.

---

## KubeVela vs Helm vs Kustomize

| | Helm | Kustomize | KubeVela |
|---|---|---|---|
| Abstraction | Templates | Overlays | Application model |
| Developer experience | Must know K8s YAML | Must know K8s YAML | Component types only |
| Multi-cluster | Manual | Manual | Built-in |
| Workflow/approvals | External (ArgoCD) | External | Built-in |
| Runtime reconciliation | No | No | Yes (continuous) |

KubeVela can also use Helm charts as component types — it's complementary, not a replacement.

---

## Gotchas

1. **OAM ≠ KubeVela** — OAM is the specification, KubeVela is the implementation. They're closely related but distinct.
2. **ComponentDefinitions are CUE-based** — the platform team writes definitions in CUE (a data validation language). Developers never touch CUE — they just use the types.
3. **KubeVela is a controller** — it continuously reconciles. If someone manually changes the underlying Deployment, KubeVela may revert it.
4. **Not a magic abstraction** — the platform team still needs to understand Kubernetes deeply to write good ComponentDefinitions and Traits.

---

## Key Takeaways

- OAM separates **what** runs (developer) from **how** it runs (platform). This is the core value.
- Four primitives: **Component** (workload), **Trait** (behaviour), **Policy** (topology), **Workflow** (rollout).
- KubeVela generates Kubernetes resources from the Application CR — the developer never writes a Deployment.
- SRE teams control the platform primitives; developers consume them. Clean boundary of responsibility.
