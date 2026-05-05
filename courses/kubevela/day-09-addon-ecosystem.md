# Day 09 — Addon Ecosystem

## Learning Objectives
- Understand what KubeVela addons are and how to manage them
- Enable FluxCD, Argo Rollouts, Prometheus, and VelaD addons
- Use the rollout addon for canary and blue-green deployments
- Build a self-service platform with addons

---

## What Are Addons?

Addons extend KubeVela's capabilities. They install additional:
- ComponentDefinitions and TraitDefinitions
- Kubernetes controllers and operators
- Integrations with external systems

```bash
# List all available addons
vela addon list

# ADDON           STATUS     VERSION    DESCRIPTION
# fluxcd          disabled   1.0.0      FluxCD GitOps engine
# velaux          disabled   1.9.0      KubeVela UI dashboard
# rollout         disabled   1.9.0      Argo Rollouts integration
# prometheus      disabled   2.41.0     Prometheus monitoring
# loki            disabled   4.0.0      Log aggregation
# jaeger          disabled   1.35.0     Distributed tracing
# kruise-rollout  disabled   0.3.0      OpenKruise rollouts
# terraform       disabled   1.9.0      Terraform cloud provisioning
# ocm-hub-control-plane  disabled  0.9.0   Open Cluster Management
```

---

## Enable / Disable Addons

```bash
# Enable an addon
vela addon enable fluxcd
vela addon enable velaux --set "adminPassword=securepassword"
vela addon enable prometheus --set "grafana.adminPassword=admin123"

# Enable with specific version
vela addon enable rollout --version 1.9.0

# Disable an addon
vela addon disable fluxcd

# Check addon status
vela addon status fluxcd
```

---

## FluxCD Addon — GitOps & Helm

The FluxCD addon is required for:
- Helm chart-based ComponentDefinitions
- GitOps sync from Git repositories
- HelmRelease and HelmRepository resources

```bash
vela addon enable fluxcd
```

Once enabled, you can use `type: helm` in component definitions:

```yaml
# app-with-helm-component.yaml
apiVersion: core.oam.dev/v1beta1
kind: Application
metadata:
  name: infra
  namespace: production
spec:
  components:
    # Deploy Bitnami Redis directly as a component
    - name: redis
      type: helm
      properties:
        repoType: helm
        url: https://charts.bitnami.com/bitnami
        chart: redis
        version: "18.x.x"
        values:
          auth:
            password: myredispassword
          master:
            persistence:
              size: 5Gi
          replica:
            replicaCount: 0           # standalone mode

    # Deploy Bitnami PostgreSQL
    - name: postgres
      type: helm
      properties:
        repoType: helm
        url: https://charts.bitnami.com/bitnami
        chart: postgresql
        version: "13.x.x"
        values:
          auth:
            postgresPassword: mydbpassword
            database: taskapp
```

---

## Rollout Addon — Argo Rollouts Integration

The rollout addon gives you Argo Rollouts-powered canary and blue-green deployments as a KubeVela trait:

```bash
vela addon enable rollout
```

### Canary Rollout Trait

```yaml
# app-canary.yaml
apiVersion: core.oam.dev/v1beta1
kind: Application
metadata:
  name: api-canary
  namespace: production
spec:
  components:
    - name: api
      type: webservice
      properties:
        image: myapi:2.0           # new version being rolled out
        port: 8080
        replicas: 5
      traits:
        - type: rollout
          properties:
            targetRevision: latest
            rolloutBatches:
              - replicas: 1        # batch 1: promote 1 pod (20%)
              - replicas: 2        # batch 2: promote 2 more pods (60%)
              - replicas: 5        # batch 3: promote all (100%)
            batchPartition: 0      # start at batch 0 (pause between batches)
            canaryMetric:
              - name: error-rate
                templateRef:
                  name: success-rate
                  namespace: production
                successCondition: "result[0] >= 0.95"
                interval: 30s
```

```bash
# Check rollout status
vela status api-canary

# Advance to next batch
vela rollout api-canary --batch next

# Approve full rollout
vela rollout api-canary --all

# Rollback
vela rollout api-canary --revert
```

### Blue-Green Trait

```yaml
traits:
  - type: rollout
    properties:
      rolloutType: BlueGreen
      targetRevision: latest
      batchPartition: 0        # manual control between blue and green
```

---

## Prometheus Addon — Built-in Monitoring

```bash
vela addon enable prometheus --set "grafana.adminPassword=admin123"

# Access Grafana
vela port-forward addon-prometheus-server -n vela-system 9090:9090
vela port-forward addon-grafana -n vela-system 3000:80
```

Once enabled, add monitoring to your applications using the `prometheus-scrape` trait (provided by the addon):

```yaml
traits:
  - type: prometheus-scrape
    properties:
      port: 9090
      path: /metrics
```

---

## Loki Addon — Log Aggregation

```bash
vela addon enable loki
```

After enabling, view logs from VelaUX — it connects to Loki automatically.

---

## VelaD — All-in-One Dev Environment

VelaD bundles k3d + KubeVela into a single binary for local development:

```bash
# Install VelaD
curl -fsSl https://kubevela.io/script/install-velad.sh | bash

# Bootstrap a local cluster with KubeVela pre-installed
velad install

# Tear down
velad uninstall
```

VelaD is ideal for local development and CI environments — no separate k3d setup needed.

---

## Terraform Addon — Cloud Resource Provisioning

The Terraform addon lets you provision cloud infrastructure as KubeVela components:

```bash
vela addon enable terraform
vela addon enable terraform-aws    # AWS provider
```

```yaml
# app-with-cloud-db.yaml
apiVersion: core.oam.dev/v1beta1
kind: Application
metadata:
  name: taskapp-with-cloud-db
spec:
  components:
    # Provision an RDS instance on AWS
    - name: rds-db
      type: aws-rds              # provided by terraform-aws addon
      properties:
        instance_class: db.t3.micro
        db_name: taskapp
        username: taskapp
        password: mysecretpassword
        engine: postgres
        engine_version: "15"

    # Deploy the app, connecting to the RDS instance
    - name: api
      type: webservice
      properties:
        image: myapi:1.0
        port: 8080
        env:
          - name: DB_HOST
            # Reference the Terraform output from the rds-db component
            valueFrom:
              secretKeyRef:
                name: rds-db-conn
                key: endpoint
```

---

## Building a Self-Service Platform

With custom definitions + addons, you can build an internal developer platform:

```
Platform Team defines:
  ├── ComponentDefinitions
  │   ├── webservice (company standard: non-root, resource limits)
  │   ├── worker
  │   ├── postgresql (wraps Bitnami Helm)
  │   ├── redis (wraps Bitnami Helm)
  │   └── s3-bucket (wraps Terraform)
  │
  └── TraitDefinitions
      ├── ingress (company domains, TLS auto-provisioning)
      ├── pod-disruption-budget (standard min-available)
      ├── prometheus-scrape (standard metrics path)
      └── vault-secret (injects secrets from Vault)

Developer writes:
  Application:
    components:
      - type: webservice    # don't need to know about Deployments
      - type: postgresql    # don't need to know about StatefulSets
      - type: s3-bucket     # don't need to know about Terraform
```

---

## Addon Gotchas

1. **Addon order matters** — `rollout` addon requires `fluxcd`. Enable fluxcd first.
2. **Addon updates** — `vela addon enable <name>` upgrades an existing addon. No separate upgrade command.
3. **Addon resources go to `vela-system`** — addon controllers and CRDs are installed in `vela-system`. Don't manually delete resources there.
4. **`prometheus` addon vs kube-prometheus-stack** — the KubeVela prometheus addon is lightweight. For production-grade monitoring, use `kube-prometheus-stack` (from the Kubernetes course Day 29) and integrate via ServiceMonitor.

---

## Practice

1. Enable the `fluxcd` addon. Deploy a Bitnami Redis Helm chart as a component using `type: helm`.
2. Enable the `rollout` addon. Deploy an app and perform a canary rollout through 3 batches using `vela rollout`.
3. Enable the `prometheus` addon. Access Grafana and explore the pre-built Kubernetes dashboards.
4. Design a self-service platform: list 5 component types and 3 trait types your SRE team would define for developers.

---

## Key Takeaways

- Addons extend KubeVela with controllers, definitions, and integrations. Enable with `vela addon enable`.
- `fluxcd` addon is required for Helm chart-based component types.
- `rollout` addon adds Argo Rollouts-powered canary and blue-green as a simple trait.
- Building a self-service platform = custom definitions (what runs) + addons (how it runs) + VelaUX (self-service UI).
