# Day 12 — Capstone: Full Application Deployment with KubeVela

## Learning Objectives
- Deploy a complete multi-tier application using KubeVela
- Apply all course concepts: custom definitions, traits, policies, workflows, GitOps, observability
- Implement multi-environment promotion with manual approval
- Practice failure recovery and rollback

---

## What We're Building

A production-grade task management platform deployed with KubeVela:

```
┌─────────────────────────────────────────────────────────────────┐
│  Git Repository (source of truth)                               │
│    apps/taskapp/staging/app.yaml                                │
│    apps/taskapp/production/app.yaml                             │
│    definitions/components/secured-webservice.yaml               │
└─────────────────┬───────────────────────────────────────────────┘
                  │  ArgoCD syncs
                  ▼
┌─────────────────────────────────────────────────────────────────┐
│  Hub Cluster (KubeVela + ArgoCD)                                │
│                                                                 │
│  Application CR                                                 │
│    ├── api (secured-webservice)    → ingress, scaler, pdb       │
│    ├── worker (worker)             → env, resource              │
│    ├── postgres (helm)             → PVC, headless service       │
│    └── cleanup (cron-task)         → scheduled backup           │
│                                                                 │
│  Workflow: staging → [approve] → production                     │
│  Policies: staging-override, production-override, topology      │
│  Monitoring: prometheus-scrape, PrometheusRules, Grafana        │
└─────────────────────────────────────────────────────────────────┘
```

---

## Step 1 — Cluster Setup

```bash
# Create hub cluster
k3d cluster create hub \
  --port "80:80@loadbalancer" \
  --port "443:443@loadbalancer" \
  --agents 2

# Install KubeVela
vela install

# Enable addons
vela addon enable velaux --set "adminPassword=admin123"
vela addon enable fluxcd
vela addon enable observability --set "grafana.adminPassword=admin123"
vela addon enable rollout

# Verify
vela system status
vela addon list | grep enabled
```

---

## Step 2 — Custom ComponentDefinition

```yaml
# definitions/components/secured-webservice.yaml
apiVersion: core.oam.dev/v1beta1
kind: ComponentDefinition
metadata:
  name: secured-webservice
  namespace: vela-system
  annotations:
    definition.oam.dev/description: "Company standard web service: non-root, read-only FS, resource limits required"
spec:
  workload:
    definition:
      apiVersion: apps/v1
      kind: Deployment
  schematicDefinition:
    cue:
      template: |
        parameter: {
          image:      string
          port:       *8080 | int
          replicas:   *2 | int
          team:       string
          cpu:        *"200m" | string
          memory:     *"256Mi" | string
          env:        *[] | [{name: string, value: string}]
        }

        output: {
          apiVersion: "apps/v1"
          kind:       "Deployment"
          metadata: labels: {
            team:       parameter.team
            managed-by: "kubevela"
          }
          spec: {
            replicas: parameter.replicas
            selector: matchLabels: app: context.name
            template: {
              metadata: labels: {
                app:  context.name
                team: parameter.team
              }
              spec: {
                securityContext: {
                  runAsNonRoot:  true
                  runAsUser:     10001
                  seccompProfile: type: "RuntimeDefault"
                }
                containers: [{
                  name:  context.name
                  image: parameter.image
                  ports: [{containerPort: parameter.port}]
                  securityContext: {
                    allowPrivilegeEscalation: false
                    readOnlyRootFilesystem:   true
                    capabilities: drop: ["ALL"]
                  }
                  resources: {
                    requests: {cpu: parameter.cpu, memory: parameter.memory}
                    limits:   {cpu: parameter.cpu, memory: parameter.memory}
                  }
                  env: parameter.env
                  volumeMounts: [{name: "tmp", mountPath: "/tmp"}]
                }]
                volumes: [{name: "tmp", emptyDir: {}}]
              }
            }
          }
        }

        outputs: service: {
          apiVersion: "v1"
          kind:       "Service"
          spec: {
            selector: app: context.name
            ports: [{port: 80, targetPort: parameter.port}]
          }
        }
```

```bash
kubectl apply -f definitions/components/secured-webservice.yaml
vela show secured-webservice
```

---

## Step 3 — The Application

```yaml
# apps/taskapp/app.yaml — the base Application used by both environments
apiVersion: core.oam.dev/v1beta1
kind: Application
metadata:
  name: taskapp
  namespace: default
  annotations:
    app.oam.dev/publishVersion: "v1.0.0"
spec:
  components:
    # API server
    - name: api
      type: secured-webservice
      properties:
        image: myapi:1.0.0
        port: 8080
        replicas: 3
        team: backend
        cpu: "500m"
        memory: "512Mi"
        env:
          - name: APP_ENV
            value: production
          - name: DB_HOST
            value: postgres
          - name: REDIS_URL
            value: redis://redis:6379
      traits:
        - type: ingress
          properties:
            domain: api.taskapp.mycompany.com
            http:
              "/": 8080
        - type: scaler
          properties:
            min: 3
            max: 20
            cpuPercent: 70
        - type: pod-disruption-budget
          properties:
            minAvailable: 2
        - type: prometheus-scrape
          properties:
            port: 9090
            path: /metrics

    # Background worker
    - name: worker
      type: worker
      properties:
        image: myworker:1.0.0
        replicas: 2
        env:
          - name: QUEUE_URL
            value: redis://redis:6379
      traits:
        - type: resource
          properties:
            requests:
              cpu: "200m"
              memory: "256Mi"
            limits:
              cpu: "500m"
              memory: "512Mi"

    # PostgreSQL via Helm
    - name: postgres
      type: helm
      properties:
        repoType: helm
        url: https://charts.bitnami.com/bitnami
        chart: postgresql
        version: "13.x.x"
        values:
          auth:
            postgresPassword: taskapppassword
            database: taskapp
          primary:
            persistence:
              size: 10Gi

    # Nightly backup job
    - name: backup
      type: cron-task
      properties:
        image: myapi:1.0.0
        cmd: ["./backup", "--target=s3://my-bucket/backups"]
        schedule: "0 2 * * *"
        cpu: "100m"
        memory: "128Mi"

  policies:
    # Staging overrides
    - name: staging-override
      type: override
      properties:
        components:
          - name: api
            properties:
              replicas: 1
              cpu: "100m"
              memory: "128Mi"
              env:
                - name: APP_ENV
                  value: staging
                - name: DB_HOST
                  value: postgres
                - name: REDIS_URL
                  value: redis://redis:6379
          - name: worker
            properties:
              replicas: 1

    # Staging target namespace
    - name: staging-target
      type: topology
      properties:
        clusters: ["local"]
        namespace: staging

    # Production target namespace
    - name: production-target
      type: topology
      properties:
        clusters: ["local"]
        namespace: production

  workflow:
    steps:
      # Deploy to staging
      - name: deploy-staging
        type: deploy
        properties:
          policies: ["staging-override", "staging-target"]

      # Notify staging is ready
      - name: notify-staging
        type: notification
        properties:
          slack:
            url:
              secretRef:
                name: slack-webhook
                key: url
            message:
              text: "🚀 taskapp staging ready for review: http://api.staging.taskapp.mycompany.com"

      # Human approval gate
      - name: approve-production
        type: suspend
        timeout: 48h

      # Deploy to production
      - name: deploy-production
        type: deploy
        properties:
          policies: ["production-target"]

      # Notify success
      - name: notify-success
        type: notification
        properties:
          slack:
            url:
              secretRef:
                name: slack-webhook
                key: url
            message:
              text: "✅ taskapp v{{ context.appRevision }} deployed to production."

      # Notify failure
      - name: notify-failure
        type: notification
        if: status.deploy-production.failed
        properties:
          slack:
            url:
              secretRef:
                name: slack-webhook
                key: url
            message:
              text: "❌ taskapp production deployment FAILED. Check VelaUX."
```

---

## Step 4 — Pre-requisites

```bash
# Create namespaces
kubectl create namespace staging
kubectl create namespace production

# Create Slack webhook secret
kubectl create secret generic slack-webhook \
  --from-literal=url="https://hooks.slack.com/services/T00/B00/xxxx" \
  --namespace=default
```

---

## Step 5 — Deploy

```bash
# Apply the Application
kubectl apply -f apps/taskapp/app.yaml

# Watch the workflow progress
vela status taskapp

# Step 1: deploy-staging completes
# Step 2: notify-staging fires
# Step 3: workflow suspends — waiting for approval

# Verify staging
vela status taskapp --tree
curl http://api.staging.taskapp.mycompany.com/health

# Approve production deploy
vela workflow resume taskapp

# Watch production deploy
vela status taskapp -w
```

---

## Step 6 — Monitoring

```bash
# Access Grafana
vela port-forward addon-grafana -n vela-system 3000:80

# Access VelaUX
vela port-forward addon-velaux -n vela-system 8080:80

# Access Prometheus
vela port-forward addon-prometheus-server -n vela-system 9090:9090
```

Import the API dashboard — query:
```promql
# Request rate
sum(rate(http_requests_total{namespace="production"}[5m])) by (path)

# Error rate
sum(rate(http_requests_total{namespace="production",status=~"5.."}[5m]))
/ sum(rate(http_requests_total{namespace="production"}[5m])) * 100

# P99 latency
histogram_quantile(0.99, sum(rate(http_request_duration_seconds_bucket{namespace="production"}[5m])) by (le))
```

---

## Step 7 — Update and Promote

```bash
# New version available — update the image tag
kubectl patch application taskapp --type=merge \
  -p '{"metadata":{"annotations":{"app.oam.dev/publishVersion":"v1.1.0"}},"spec":{"components":[{"name":"api","type":"secured-webservice","properties":{"image":"myapi:1.1.0"}}]}}'

# Or update the YAML and re-apply
# sed -i "s|myapi:1.0.0|myapi:1.1.0|g" apps/taskapp/app.yaml
# kubectl apply -f apps/taskapp/app.yaml

# Workflow restarts: staging → suspend → production
vela status taskapp

# Approve again
vela workflow resume taskapp
```

---

## Step 8 — Failure Scenarios

```bash
# Scenario 1: Bad image — workflow stalls at staging
kubectl patch application taskapp --type=merge \
  -p '{"spec":{"components":[{"name":"api","type":"secured-webservice","properties":{"image":"myapi:broken"}}]}}'

vela status taskapp
# deploy-staging: failed (api component not healthy)
# Production was NOT touched — safe!

# Rollback: revert the image
kubectl patch application taskapp --type=merge \
  -p '{"spec":{"components":[{"name":"api","type":"secured-webservice","properties":{"image":"myapi:1.0.0"}}]}}'

# Scenario 2: Workflow approved but production fails
# → use ApplicationRevision rollback
vela revision list taskapp
vela workflow rollback taskapp --revision taskapp-v1

# Scenario 3: Terminate an approved-but-not-started production deploy
vela workflow terminate taskapp
```

---

## Production Readiness Checklist

```
☐ Custom ComponentDefinition enforces:
    ☐ runAsNonRoot + non-root UID
    ☐ readOnlyRootFilesystem
    ☐ capabilities.drop: ALL
    ☐ Resource requests and limits required
    ☐ Team label required

☐ Traits applied:
    ☐ ingress with correct domain
    ☐ scaler with min/max replicas
    ☐ pod-disruption-budget (minAvailable ≥ 1)
    ☐ prometheus-scrape for metrics

☐ Workflow:
    ☐ staging deploy → notify → suspend → production deploy
    ☐ Success and failure notifications
    ☐ suspend timeout set (e.g., 48h)

☐ Policies:
    ☐ staging-override (fewer replicas, staging env vars)
    ☐ topology targets correct namespaces

☐ Observability:
    ☐ Prometheus scraping API metrics
    ☐ Grafana dashboard for request rate, error rate, latency
    ☐ Alert rule for error rate > 5%
    ☐ VelaUX accessible for health monitoring

☐ GitOps:
    ☐ Application YAML in Git
    ☐ ArgoCD syncing from Git
    ☐ publishVersion annotation updated on each release
    ☐ Rollback tested (git revert → auto sync)
```

---

## Key Takeaways

- KubeVela unifies the entire application delivery lifecycle: from component definition to multi-env rollout to monitoring.
- Custom ComponentDefinitions enforce platform standards without requiring developers to know Kubernetes internals.
- The workflow (staging → approve → production) is the SRE's change control mechanism — codified, auditable, repeatable.
- Combine with GitOps (ArgoCD) for a complete platform: Git is the source of truth, KubeVela is the delivery engine.

---

## Course Complete

Congratulations on completing the 12-day KubeVela course.

| Days | Topic |
|---|---|
| 01 | OAM concepts: Component, Trait, Policy, Workflow |
| 02 | Install KubeVela on k3d, VelaUX, first Application |
| 03 | Built-in components: webservice, worker, task, cron-task, daemon |
| 04 | Built-in traits: ingress, scaler, resource, sidecar, labels, annotations |
| 05 | Policies: override (per-env config) and topology (target clusters) |
| 06 | Workflow steps: deploy, suspend (approval), notification, step-group |
| 07 | Multi-cluster: hub-spoke, cluster registration, cluster selector |
| 08 | Custom definitions: ComponentDefinition in CUE, Helm wrapping, TraitDefinition |
| 09 | Addon ecosystem: FluxCD, Rollout (canary/blue-green), Prometheus, Terraform |
| 10 | GitOps: ApplicationRevision, ArgoCD integration, CI/CD pipeline |
| 11 | Observability: prometheus-scrape trait, VelaUX, Loki, debug commands |
| 12 | Capstone: full multi-tier app with custom definitions, workflow, monitoring |

**Next steps:** Explore Crossplane for infrastructure provisioning as KubeVela components, or contribute a ComponentDefinition to the KubeVela community catalog.
