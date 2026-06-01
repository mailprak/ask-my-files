# Day 02 — Install KubeVela on k3d & First Application

## Learning Objectives
- Install KubeVela on a k3d cluster
- Install the `vela` CLI
- Access VelaUX (web dashboard)
- Deploy your first Application and inspect the resources it creates

---

## Prerequisites

```bash
# k3d cluster running
k3d cluster create vela-demo \
  --port "80:80@loadbalancer" \
  --port "443:443@loadbalancer" \
  --agents 2

kubectl get nodes
# NAME                      STATUS   ROLES
# k3d-vela-demo-server-0    Ready    control-plane,master
# k3d-vela-demo-agent-0     Ready    <none>
# k3d-vela-demo-agent-1     Ready    <none>
```

---

## Install the vela CLI

```bash
# macOS
brew install kubevela

# Linux
curl -fsSl https://kubevela.io/script/install.sh | bash

# Windows (PowerShell)
# Download from https://github.com/kubevela/kubevela/releases

# Verify
vela version
# CLI Version: v1.9.x
# Core Version: N/A (not installed yet)
```

---

## Install KubeVela on the Cluster

```bash
# Install KubeVela core (controller + CRDs)
vela install

# Watch components come up
kubectl get pods -n vela-system -w
# kubevela-vela-core-xxxx              1/1   Running
# kubevela-cluster-gateway-xxxx        1/1   Running

# Verify installation
vela system status
# [OK] KubeVela is running properly
```

---

## Install VelaUX (Web Dashboard)

```bash
# Enable the VelaUX addon
vela addon enable velaux

# Check it's running
kubectl get pods -n vela-system -l app=velaux

# Access the UI
vela port-forward addon-velaux -n vela-system 8080:80

# Open http://localhost:8080
# Default credentials: admin / VelaUX12345
```

---

## Explore Built-in Component Types

```bash
# List all available component types
vela components

# NAMESPACE   NAME          WORKLOAD-KIND   DESCRIPTION
# system      cron-task     CronJob         Run code periodically
# system      daemon        DaemonSet       Run as DaemonSet
# system      k8s-objects   ...             Raw K8s objects
# system      task          Job             Run code once to completion
# system      webservice    Deployment      Long-running web service
# system      worker        Deployment      Background worker (no ingress)

# Describe a component type (shows all properties)
vela show webservice
```

```bash
# List all available traits
vela traits

# NAME              APPLIES-TO                DESCRIPTION
# annotations       *                         Add annotations
# command           webservice,worker         Override container command
# env               webservice,worker         Add env variables
# gateway           webservice                Expose via Gateway API
# ingress           webservice                Expose via Ingress
# labels            *                         Add labels
# resource          *                         Set CPU/memory requests and limits
# scaler            webservice,worker         Attach HPA
# sidecar           webservice,worker         Inject a sidecar container

# Describe a trait (shows all properties)
vela show ingress
```

---

## Your First Application

```yaml
# first-app.yaml
apiVersion: core.oam.dev/v1beta1
kind: Application
metadata:
  name: first-app
  namespace: default
spec:
  components:
    - name: hello-web
      type: webservice
      properties:
        image: crccheck/hello-world   # simple HTTP server
        port: 8000
        replicas: 1
      traits:
        - type: ingress
          properties:
            domain: hello.local
            http:
              "/": 8000
```

```bash
# Apply the Application
kubectl apply -f first-app.yaml

# Check the Application status
vela status first-app

# NAME       COMPONENT    TYPE         PHASE     HEALTHY   STATUS
# first-app  hello-web    webservice   running   true      Ready:1/1
```

---

## Inspect What KubeVela Created

```bash
# KubeVela generated these Kubernetes resources automatically:
kubectl get deployment -n default
# NAME        READY   UP-TO-DATE   AVAILABLE
# hello-web   1/1     1            1

kubectl get service -n default
# NAME        TYPE        CLUSTER-IP    PORT(S)
# hello-web   ClusterIP   10.43.x.x    8000/TCP

kubectl get ingress -n default
# NAME        CLASS   HOSTS         ADDRESS
# hello-web   nginx   hello.local   <load-balancer-ip>

# The Application owns all these — deleting the Application deletes them all
kubectl delete application first-app
kubectl get deployment -n default   # all gone
```

---

## Application Lifecycle Commands

```bash
# Apply (create or update)
kubectl apply -f first-app.yaml
# or
vela up -f first-app.yaml

# Status overview
vela status first-app
vela status first-app --tree    # hierarchical view of all managed resources

# Detailed status with events
kubectl describe application first-app

# Logs from a component
vela logs first-app --component hello-web

# Exec into a component pod
vela exec first-app --component hello-web -- sh

# Port-forward to a component
vela port-forward first-app 8000:8000 --component hello-web

# Delete the application and all its resources
vela delete first-app
```

---

## VelaUX Walkthrough

After accessing `http://localhost:8080`:

1. **Applications** — list all Application CRs with health status
2. **Clusters** — register additional clusters for multi-cluster deployments
3. **Addons** — enable/disable KubeVela addons (observability, rollout, etc.)
4. **Definitions** — browse ComponentDefinitions, TraitDefinitions
5. **Pipelines** — manage multi-step deployment workflows visually

VelaUX lets you create Applications through the UI — it generates the YAML for you.

---

## Multi-Namespace Application

```yaml
# app-with-namespace.yaml
apiVersion: core.oam.dev/v1beta1
kind: Application
metadata:
  name: taskapp
  namespace: taskapp           # Application CR lives here
spec:
  components:
    - name: api
      type: webservice
      properties:
        image: myapi:1.0
        port: 8080
```

```bash
# Create namespace first
kubectl create namespace taskapp

# Apply
kubectl apply -f app-with-namespace.yaml

# All generated resources are in the same namespace as the Application
kubectl get all -n taskapp
```

---

## Gotchas

1. **`vela install` requires cluster-admin** — KubeVela installs CRDs and cluster-scoped resources. Run with sufficient permissions.
2. **VelaUX default password** — change it immediately: `vela addon enable velaux --set "adminPassword=password"`.
3. **`vela status` vs `kubectl get application`** — `vela status` is richer (shows component health). `kubectl get application` shows the raw CR status.
4. **Deleting an Application deletes all child resources** — including PVCs. Be careful in production. Use `--orphan` flag to detach without deleting: `vela delete myapp --orphan`.

---

## Practice

1. Create a k3d cluster and install KubeVela. Verify with `vela system status`.
2. Deploy `first-app.yaml`. Run `vela status first-app --tree` and identify every Kubernetes resource KubeVela created.
3. Access VelaUX and find your application in the dashboard.
4. Delete the Application and verify all child resources are cleaned up.

---

## Key Takeaways

- `vela install` installs KubeVela CRDs and the controller into `vela-system`.
- `vela components` and `vela traits` show what the platform provides — these are your building blocks.
- One `Application` CR generates multiple Kubernetes resources — Deployment, Service, Ingress, HPA.
- `vela status --tree` is your primary debug command — it shows the full resource hierarchy and health.
