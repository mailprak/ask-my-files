# Day 11 — Observability with KubeVela

## Learning Objectives
- Enable the KubeVela observability addon stack
- Use VelaUX for application health monitoring
- Integrate with Prometheus and Grafana
- Set up log aggregation with Loki
- Debug application issues using KubeVela tools

---

## Observability Stack

KubeVela's observability addon installs a complete stack:

```
Applications → Metrics (Prometheus) → Visualise (Grafana)
            → Logs    (Loki)         → Query (Grafana)
            → Traces  (Jaeger)       → Trace (Jaeger UI)
            → Health  (VelaUX)       → Dashboard
```

---

## Enable the Observability Addon

```bash
# Enable the full observability stack
vela addon enable observability \
  --set grafana.adminPassword=password

# Or enable components separately
vela addon enable prometheus-server
vela addon enable grafana

# Verify
kubectl get pods -n vela-system | grep -E "prometheus|grafana|loki"

# Access Grafana
vela port-forward addon-grafana -n vela-system 3000:80
# http://localhost:3000  admin / password
```

---

## VelaUX — Application Health Dashboard

VelaUX shows real-time health of all Applications:

```bash
# Enable VelaUX (if not already)
vela addon enable velaux --set "adminPassword=password"

# Access
vela port-forward addon-velaux -n vela-system 8080:80
# http://localhost:8080
```

VelaUX shows:
- **Application list** with overall health (healthy / degraded / progressing)
- **Component tree** — each component and the Kubernetes resources it manages
- **Real-time pod status** — running, pending, crash-looping
- **Resource usage** — CPU and memory per component (if metrics-server is running)
- **Workflow history** — which step is running, which completed, which is suspended

---

## Instrument Your App for Prometheus

```yaml
# app-instrumented.yaml
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
        # Tell Prometheus to scrape this component
        - type: prometheus-scrape
          properties:
            port: 9090              # metrics port
            path: /metrics          # metrics path
            interval: 15s

        # Expose both app and metrics ports
        - type: expose
          properties:
            port: [8080, 9090]

        - type: ingress
          properties:
            domain: api.mycompany.com
            http:
              "/": 8080
```

The `prometheus-scrape` trait creates a `ServiceMonitor` automatically — no manual ServiceMonitor YAML needed.

---

## Custom Grafana Dashboard via Application

You can manage Grafana dashboards as KubeVela components:

```yaml
# app-dashboard.yaml
apiVersion: core.oam.dev/v1beta1
kind: Application
metadata:
  name: taskapp-dashboards
  namespace: production
spec:
  components:
    - name: api-dashboard
      type: grafana-dashboard
      properties:
        uid: taskapp-api
        title: "TaskApp API"
        datasource: prometheus
        panels:
          - title: "Request Rate"
            expr: "sum(rate(http_requests_total[5m])) by (path)"
          - title: "Error Rate %"
            expr: "sum(rate(http_requests_total{status=~'5..'}[5m])) / sum(rate(http_requests_total[5m])) * 100"
          - title: "P99 Latency"
            expr: "histogram_quantile(0.99, sum(rate(http_request_duration_seconds_bucket[5m])) by (le))"
```

---

## Alerting via PrometheusRule

```yaml
# app-alerts.yaml
apiVersion: core.oam.dev/v1beta1
kind: Application
metadata:
  name: taskapp-alerts
  namespace: production
spec:
  components:
    - name: api-alerts
      type: prometheus-rules         # provided by observability addon
      properties:
        groups:
          - name: taskapp.api
            rules:
              - alert: HighErrorRate
                expr: |
                  sum(rate(http_requests_total{status=~"5.."}[5m]))
                  / sum(rate(http_requests_total[5m])) > 0.05
                for: 2m
                labels:
                  severity: critical
                  app: taskapp
                annotations:
                  summary: "TaskApp API error rate > 5%"
                  description: "Error rate: {{ $value | humanizePercentage }}"
```

---

## Log Aggregation with Loki

```bash
# Enable Loki addon
vela addon enable loki
```

```yaml
# Add log shipping sidecar via trait
traits:
  - type: sidecar
    properties:
      name: log-shipper
      image: grafana/fluent-bit-plugin-loki:latest
      env:
        - name: LOKI_URL
          value: http://addon-loki.vela-system.svc.cluster.local:3100
      volumes:
        - name: logs
          path: /logs
```

In Grafana → Explore → select Loki datasource → query:
```
{app="taskapp", component="api"}
```

---

## Distributed Tracing with Jaeger

```bash
# Enable Jaeger addon
vela addon enable jaeger
```

```yaml
# Inject Jaeger agent as a sidecar
traits:
  - type: sidecar
    properties:
      name: jaeger-agent
      image: jaegertracing/jaeger-agent:latest
      cmd: ["--reporter.grpc.host-port=addon-jaeger-collector.vela-system:14250"]
      env:
        - name: JAEGER_AGENT_HOST
          value: localhost          # app sends traces to localhost:6831 (agent)
```

---

## KubeVela Debug Commands

```bash
# Full application health status
vela status taskapp -n production

# Resource tree with health indicators
vela status taskapp -n production --tree

# Component logs
vela logs taskapp -n production --component api

# Stream logs in real time
vela logs taskapp -n production --component api --follow

# Exec into a pod
vela exec taskapp -n production --component api -- sh

# Port-forward to a component for local testing
vela port-forward taskapp -n production 8080:8080 --component api

# Check events (for debugging failed deployments)
kubectl get events -n production --sort-by=lastTimestamp --field-selector involvedObject.name=taskapp

# Describe the Application CR (shows conditions and status)
kubectl describe application taskapp -n production
```

---

## Debugging Failed Applications

```bash
# Step 1: Check application status
vela status taskapp -n production
# Look for: PHASE = running | progressing | failed

# Step 2: Check which component is unhealthy
vela status taskapp -n production --tree
# Look for: HEALTHY = false | STATUS = Error

# Step 3: Check the component's pod status
kubectl get pods -n production -l app=api

# Step 4: If pod is CrashLoopBackOff
kubectl logs -n production -l app=api --previous    # previous container logs
kubectl describe pod -n production -l app=api       # events section

# Step 5: Check the Application controller logs
kubectl logs -n vela-system -l app.kubernetes.io/name=vela-core --tail=50

# Step 6: Check if there's a definition issue
kubectl describe componentdefinition webservice -n vela-system
```

---

## Application Status Conditions

```bash
kubectl describe application taskapp -n production
# Status:
#   Conditions:
#     Type:    Ready
#     Status:  True          ← healthy
#
#     Type:    Ready
#     Status:  False
#     Reason:  ComponentNotHealthy
#     Message: Deployment api is not ready: 0/3 replicas available
```

| Condition | Meaning |
|---|---|
| `Ready: True` | All components healthy |
| `Ready: False, Reason: ComponentNotHealthy` | At least one component is not ready |
| `Ready: False, Reason: WorkflowRunning` | Workflow is in progress |
| `Ready: False, Reason: WorkflowSuspending` | Workflow is paused at a suspend step |
| `Ready: False, Reason: WorkflowFailed` | A workflow step failed |

---

## Health Policy — Custom Health Checks

```yaml
# Custom health check for a component
apiVersion: core.oam.dev/v1beta1
kind: Application
metadata:
  name: taskapp
spec:
  components:
    - name: api
      type: webservice
      properties:
        image: myapi:1.0
        port: 8080
      # Custom health check — evaluated by KubeVela to determine component health
      # (advanced: uses CUE)
```

---

## SLO Monitoring via Grafana

After enabling the observability addon, create an SLO dashboard:

```
Panel 1: Availability SLO
  Query: 1 - (sum(rate(http_requests_total{status=~"5.."}[30d])) / sum(rate(http_requests_total[30d])))
  Target: 0.999 (99.9%)

Panel 2: Latency SLO (P99 < 500ms)
  Query: histogram_quantile(0.99, sum(rate(http_request_duration_seconds_bucket[5m])) by (le)) < 0.5
  Target: 1 (true = within SLO)

Panel 3: Error Budget Remaining
  Query: (1 - (sum(rate(http_requests_total{status=~"5.."}[30d])) / sum(rate(http_requests_total[30d])))) / (1 - 0.999)
  Alert when: Error budget < 10%
```

---

## Gotchas

1. **`prometheus-scrape` trait requires observability addon** — if the addon isn't enabled, the trait type doesn't exist and `kubectl apply` fails.
2. **VelaUX CPU/memory metrics require metrics-server** — without metrics-server running, the resource usage panels show "N/A". Install metrics-server separately if needed.
3. **Loki log retention** — the default Loki install retains logs for 24 hours. Configure `chunk_retain_period` in the Loki config for longer retention.
4. **Jaeger sampling** — by default, Jaeger samples 100% of traces (fine for dev). In production, configure a sampling rate (e.g., 1%) to reduce overhead.

---

## Practice

1. Enable the observability addon. Deploy an instrumented app with `prometheus-scrape` trait. Verify the scrape target appears in Prometheus.
2. Access VelaUX and explore the application health tree for a running app.
3. Write a PrometheusRule via a KubeVela Application that fires when pod restart count exceeds 3 in 10 minutes.
4. Use `vela logs --follow` and `vela exec` to debug a simulated issue (e.g., bad env var causing the app to crash).

---

## Key Takeaways

- `prometheus-scrape` trait creates a ServiceMonitor automatically — no manual Kubernetes YAML needed.
- VelaUX gives a real-time application health view: component status, resource tree, workflow progress.
- Debug in order: `vela status --tree` → component pod status → logs → controller logs.
- Manage observability config (dashboards, alert rules) as KubeVela Applications — GitOps all the way.
