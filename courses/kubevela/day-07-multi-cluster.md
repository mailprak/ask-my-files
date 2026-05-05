# Day 07 — Multi-Cluster Deployment

## Learning Objectives
- Register additional clusters with KubeVela
- Deploy Applications across multiple clusters
- Use topology policies with cluster selectors
- Manage cluster-specific overrides
- Understand the hub-spoke architecture

---

## Hub-Spoke Architecture

KubeVela uses a hub-spoke model:

```
┌─────────────────────────────────────────────┐
│  Management Cluster (Hub)                    │
│                                             │
│  KubeVela Controller                        │
│  VelaUX                                     │
│  Application CRs                            │
│  ClusterGateway                             │
└────────────────┬────────────────────────────┘
                 │
     ┌───────────┼───────────┐
     ▼           ▼           ▼
┌─────────┐ ┌─────────┐ ┌─────────┐
│ staging │ │ eu-prod │ │ us-prod │
│ cluster │ │ cluster │ │ cluster │
└─────────┘ └─────────┘ └─────────┘
```

The KubeVela controller on the management cluster reads Application CRs and deploys to spoke clusters via the ClusterGateway.

---

## Create Multiple k3d Clusters (Local Lab)

```bash
# Management cluster (hub — KubeVela is installed here)
k3d cluster create hub \
  --port "8080:80@loadbalancer"

# Staging spoke
k3d cluster create staging \
  --port "8081:80@loadbalancer"

# Production spoke
k3d cluster create production \
  --port "8082:80@loadbalancer"

# List clusters
k3d cluster list
# NAME        SERVERS   AGENTS   LOADBALANCER
# hub         1/1       0/0      true
# staging     1/1       0/0      true
# production  1/1       0/0      true

# Switch to hub cluster
kubectl config use-context k3d-hub
```

---

## Register Spoke Clusters

```bash
# Export spoke kubeconfigs
k3d kubeconfig get staging > staging-kubeconfig.yaml
k3d kubeconfig get production > production-kubeconfig.yaml

# Register staging cluster (run on hub)
vela cluster join staging-kubeconfig.yaml \
  --name staging \
  --labels env=staging,region=local

# Register production cluster
vela cluster join production-kubeconfig.yaml \
  --name production \
  --labels env=production,region=local

# List registered clusters
vela cluster list
# CLUSTER       ALIAS   TYPE          ENDPOINT             LABELS
# local         -       Internal      -                    -
# staging       -       X509          https://...          env=staging
# production    -       X509          https://...          env=production

# Check cluster health
vela cluster probe staging
# cluster staging is accessible
```

---

## Deploy to a Specific Cluster

```yaml
# app-multi-cluster.yaml
apiVersion: core.oam.dev/v1beta1
kind: Application
metadata:
  name: taskapp
  namespace: default           # Application CR lives on the hub
spec:
  components:
    - name: api
      type: webservice
      properties:
        image: myapi:1.0
        port: 8080
        replicas: 2

  policies:
    - name: to-staging
      type: topology
      properties:
        clusters: ["staging"]   # deploy to the registered "staging" cluster
        namespace: taskapp      # namespace on the spoke cluster

    - name: to-production
      type: topology
      properties:
        clusters: ["production"]
        namespace: taskapp

  workflow:
    steps:
      - name: deploy-staging
        type: deploy
        properties:
          policies: ["to-staging"]

      - name: approve
        type: suspend

      - name: deploy-production
        type: deploy
        properties:
          policies: ["to-production"]
```

```bash
# Apply from the hub cluster
kubectl apply -f app-multi-cluster.yaml

# Status shows both clusters
vela status taskapp --tree
# APPLICATION  CLUSTER     NAMESPACE  COMPONENT  RESOURCE          STATUS
# taskapp      staging     taskapp    api        Deployment/api    Ready:2/2
# taskapp      production  taskapp    api        Deployment/api    Ready:2/2
```

---

## Cluster Selector — Dynamic Targeting

Instead of naming clusters explicitly, select by label:

```yaml
policies:
  - name: all-production-clusters
    type: topology
    properties:
      clusterSelector:
        labels:
          env: production        # all clusters labelled env=production
      namespace: taskapp

  - name: eu-only
    type: topology
    properties:
      clusterSelector:
        labels:
          env: production
          region: eu             # only EU production clusters
      namespace: taskapp
```

```bash
# Add/update labels on a registered cluster
vela cluster label production region=eu
vela cluster label staging env=staging

# Verify
vela cluster list
```

---

## Per-Cluster Overrides

Combine topology + override for cluster-specific configuration:

```yaml
policies:
  # Different replicas per cluster
  - name: staging-config
    type: override
    properties:
      components:
        - name: api
          properties:
            replicas: 1
            env:
              - name: APP_ENV
                value: staging

  - name: production-config
    type: override
    properties:
      components:
        - name: api
          properties:
            replicas: 5
            env:
              - name: APP_ENV
                value: production

  - name: to-staging
    type: topology
    properties:
      clusters: ["staging"]
      namespace: taskapp

  - name: to-production
    type: topology
    properties:
      clusters: ["production"]
      namespace: taskapp

workflow:
  steps:
    - name: deploy-staging
      type: deploy
      properties:
        policies: ["staging-config", "to-staging"]   # override + topology combined

    - name: approve
      type: suspend

    - name: deploy-production
      type: deploy
      properties:
        policies: ["production-config", "to-production"]
```

---

## Deploy to All Clusters at Once (No Workflow)

For cases where you want the same config on all clusters simultaneously:

```yaml
# app-broadcast.yaml
apiVersion: core.oam.dev/v1beta1
kind: Application
metadata:
  name: monitoring-agent
  namespace: default
spec:
  components:
    - name: node-exporter
      type: daemon
      properties:
        image: prom/node-exporter:latest
        cpu: "50m"
        memory: "64Mi"

  policies:
    - name: all-clusters
      type: topology
      properties:
        clusterSelector: {}       # empty selector = all registered clusters
        namespace: monitoring

  # No workflow = deploys to all clusters simultaneously
```

---

## Manage Resources on Spoke Clusters

```bash
# Run kubectl against a specific spoke cluster
vela exec taskapp --component api --cluster staging -- sh

# View logs from a spoke cluster component
vela logs taskapp --component api --cluster staging

# Port-forward from a spoke cluster
vela port-forward taskapp 8080:8080 --cluster staging

# Get resources on a spoke cluster directly
kubectl --context k3d-staging get pods -n taskapp
```

---

## Detach a Cluster

```bash
# Remove a cluster from KubeVela management
# Note: this does NOT delete resources deployed to the cluster
vela cluster detach staging

# To delete deployed resources, delete the Application first
vela delete taskapp
vela cluster detach staging
```

---

## Gotchas

1. **Namespace must exist on spoke clusters** — KubeVela does not create namespaces on spoke clusters automatically. Pre-create them or use an `apply-object` workflow step.
2. **Image registry accessibility** — if you push to a local k3d registry on the hub, spoke clusters can't pull it. Use a shared registry (Docker Hub, GHCR) for multi-cluster labs.
3. **`local` cluster is always available** — the hub cluster is always registered as `local`. You don't need to explicitly register it.
4. **ClusterRoleBinding on spokes** — KubeVela creates a ServiceAccount on each spoke for the cluster gateway. Ensure the hub has network access to spoke API servers.

---

## Practice

1. Create three k3d clusters (hub, staging, production). Install KubeVela on hub. Register staging and production.
2. Deploy an Application using topology policies targeting `staging` first, then `production` after a `suspend`.
3. Use a cluster label selector to target all clusters labelled `env=production`. Verify the same Application runs on all matching clusters.
4. Run `vela status taskapp --tree` and confirm the cluster column shows the correct cluster for each resource.

---

## Key Takeaways

- KubeVela uses hub-spoke: the management cluster hosts KubeVela, spoke clusters receive workloads.
- Register spokes with `vela cluster join <kubeconfig> --name <name> --labels <key=value>`.
- `topology` policy with `clusters: ["name"]` or `clusterSelector: { labels: {} }` controls which clusters receive the Application.
- Application CRs live on the hub — KubeVela pushes resources to spokes via the ClusterGateway.
