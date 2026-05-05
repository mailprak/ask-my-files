# Day 01 — Kubernetes Architecture & Core Concepts

## Learning Objectives
- Understand what Kubernetes is and why it exists
- Know the control plane vs data plane components
- Understand the Kubernetes object model (spec vs status)
- Set up a local k3d cluster for all exercises

---

## What Is Kubernetes?

Kubernetes (k8s) is a container orchestration platform. It answers: "I have containers — how do I run them reliably at scale?"

It handles scheduling, self-healing, scaling, rolling updates, service discovery, and config management.

---

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│                     Control Plane                         │
│  ┌────────────┐  ┌──────┐  ┌───────────┐  ┌──────────┐  │
│  │ API Server │  │ etcd │  │ Scheduler │  │Controller│  │
│  └────────────┘  └──────┘  └───────────┘  │ Manager  │  │
│                                            └──────────┘  │
└──────────────────────────────────────────────────────────┘
                  │  instructs
┌──────────────────────────────────────────────────────────┐
│                  Data Plane (Nodes)                       │
│  ┌──────────────────────┐   ┌──────────────────────┐     │
│  │ Node 1               │   │ Node 2               │     │
│  │  kubelet  kube-proxy │   │  kubelet  kube-proxy │     │
│  │  [Pod] [Pod] [Pod]   │   │  [Pod] [Pod]         │     │
│  └──────────────────────┘   └──────────────────────┘     │
└──────────────────────────────────────────────────────────┘
```

### Control Plane Components

| Component | Role |
|---|---|
| **kube-apiserver** | Single entry point — validates and stores all objects |
| **etcd** | Distributed key-value store — single source of truth |
| **kube-scheduler** | Picks which node runs each Pod |
| **kube-controller-manager** | Runs reconciliation loops (Deployment, ReplicaSet controllers, etc.) |

### Node Components

| Component | Role |
|---|---|
| **kubelet** | Agent on every node — starts/stops containers per API server instructions |
| **kube-proxy** | Maintains iptables/ipvs rules for Service routing |
| **Container runtime** | Actually runs containers (containerd) |

---

## The Object Model

Every Kubernetes resource is a YAML object with four top-level fields:

```yaml
apiVersion: apps/v1        # API group and version
kind: Deployment           # resource type
metadata:                  # identity
  name: my-app
  namespace: default
  labels:
    app: my-app
spec:                      # desired state — YOU declare this
  replicas: 3
# status:                  # actual state — Kubernetes fills this in
#   readyReplicas: 3
```

The **reconciliation loop**: controllers constantly compare `spec` (what you want) with `status` (what exists) and act to close the gap.

---

## Setting Up k3d

k3d runs k3s (lightweight Kubernetes) inside Docker containers — a full cluster on your laptop.

```bash
# Install k3d
curl -s https://raw.githubusercontent.com/k3d-io/k3d/main/install.sh | bash

# Create a cluster with a local image registry
k3d cluster create devcluster \
  --servers 1 \
  --agents 2 \
  --port "8080:80@loadbalancer" \
  --registry-create devregistry:5000

# Verify
kubectl get nodes
# NAME                      STATUS   ROLES                AGE
# k3d-devcluster-server-0  Ready    control-plane,master  30s
# k3d-devcluster-agent-0   Ready    <none>                25s
# k3d-devcluster-agent-1   Ready    <none>                25s

# View control plane pods
kubectl get pods -n kube-system
```

---

## Your First Manifest

```yaml
# hello.yaml
apiVersion: v1
kind: Pod
metadata:
  name: hello
  labels:
    app: hello
spec:
  containers:
    - name: hello
      image: nginx:alpine
      ports:
        - containerPort: 80
```

```bash
kubectl apply -f hello.yaml
kubectl get pods
kubectl describe pod hello
kubectl delete -f hello.yaml
```

---

## Gotchas

1. **`spec` is yours, `status` is Kubernetes'** — never try to set `status` in your YAML.
2. **etcd is the source of truth** — never modify it directly, always go through the API server.
3. **Namespaces are not security boundaries** — they organise resources but don't isolate network traffic by default.
4. **k3d uses `k3d-<registry-name>:5000`** inside the cluster but `localhost:5000` from your host machine.

---

## Key Takeaways

- Control plane = brain (API server, etcd, scheduler, controllers). Data plane = workers (nodes + kubelet).
- Every object has `spec` (desired) and `status` (actual) — controllers reconcile the gap.
- k3d gives you a full local cluster in Docker — use it for every exercise in this course.
