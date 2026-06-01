# Day 29 — Monitoring with Prometheus & Grafana

## Learning Objectives
- Install Prometheus and Grafana on k3d with Helm
- Instrument a Go/Python app with Prometheus metrics
- Write PromQL queries for common scenarios
- Create Grafana dashboards and alerts

---

## Architecture Overview

```
App Pods  →  /metrics endpoint  →  Prometheus (scrapes)  →  Grafana (visualise)
                                         ↓
                                  Alertmanager (alert)
                                         ↓
                                  PagerDuty / Slack
```

---

## Install kube-prometheus-stack on k3d

The `kube-prometheus-stack` Helm chart installs Prometheus, Alertmanager, Grafana, and a set of pre-built dashboards and recording rules:

```bash
# Add Helm repo
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

# Install
helm upgrade --install monitoring prometheus-community/kube-prometheus-stack \
  --namespace monitoring \
  --create-namespace \
  --set grafana.adminPassword=password \
  --set prometheus.prometheusSpec.retention=7d \
  --set prometheus.prometheusSpec.storageSpec.volumeClaimTemplate.spec.resources.requests.storage=10Gi

# Verify
kubectl get pods -n monitoring
# alertmanager-monitoring-kube-prometheus-alertmanager-0   Running
# monitoring-grafana-xxxx                                   Running
# monitoring-kube-prometheus-operator-xxxx                  Running
# prometheus-monitoring-kube-prometheus-prometheus-0        Running

# Access Grafana
kubectl port-forward -n monitoring svc/monitoring-grafana 3000:80
# Open http://localhost:3000 — admin / admin123

# Access Prometheus
kubectl port-forward -n monitoring svc/monitoring-kube-prometheus-prometheus 9090:9090
```

---

## Exposing Metrics from Your App

### ServiceMonitor — Tell Prometheus What to Scrape

```yaml
# servicemonitor.yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: api-service-monitor
  namespace: production
  labels:
    release: monitoring           # must match the Prometheus operator's label selector
spec:
  selector:
    matchLabels:
      app: api-service            # selects Services with this label

  namespaceSelector:
    matchNames:
      - production

  endpoints:
    - port: metrics               # the port name on the Service
      path: /metrics              # the metrics path
      interval: 15s               # scrape every 15 seconds
      scrapeTimeout: 10s
```

```yaml
# service.yaml — expose the metrics port
apiVersion: v1
kind: Service
metadata:
  name: api-service
  namespace: production
  labels:
    app: api-service
spec:
  selector:
    app: api-service
  ports:
    - name: http
      port: 80
      targetPort: 8080
    - name: metrics               # port name referenced in ServiceMonitor
      port: 9090
      targetPort: 9090
```

---

## Instrumenting a Go App

```go
// main.go
package main

import (
    "net/http"
    "time"
    "github.com/prometheus/client_golang/prometheus"
    "github.com/prometheus/client_golang/prometheus/promauto"
    "github.com/prometheus/client_golang/prometheus/promhttp"
)

var (
    httpRequestsTotal = promauto.NewCounterVec(
        prometheus.CounterOpts{
            Name: "http_requests_total",
            Help: "Total number of HTTP requests",
        },
        []string{"method", "path", "status"},
    )

    httpRequestDuration = promauto.NewHistogramVec(
        prometheus.HistogramOpts{
            Name:    "http_request_duration_seconds",
            Help:    "HTTP request duration in seconds",
            Buckets: prometheus.DefBuckets,   // .005, .01, .025, .05, .1, .25, .5, 1, 2.5, 5, 10
        },
        []string{"method", "path"},
    )

    activeConnections = promauto.NewGauge(prometheus.GaugeOpts{
        Name: "active_connections",
        Help: "Number of active connections",
    })
)

func metricsMiddleware(next http.Handler) http.Handler {
    return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        start := time.Now()
        activeConnections.Inc()
        defer activeConnections.Dec()

        rw := &responseWriter{ResponseWriter: w, statusCode: http.StatusOK}
        next.ServeHTTP(rw, r)

        duration := time.Since(start).Seconds()
        status := fmt.Sprintf("%d", rw.statusCode)

        httpRequestsTotal.WithLabelValues(r.Method, r.URL.Path, status).Inc()
        httpRequestDuration.WithLabelValues(r.Method, r.URL.Path).Observe(duration)
    })
}

func main() {
    mux := http.NewServeMux()
    mux.Handle("/metrics", promhttp.Handler())   // Prometheus scrapes this
    mux.Handle("/api/", metricsMiddleware(apiHandler()))

    http.ListenAndServe(":8080", mux)
}
```

---

## PromQL — Prometheus Query Language

### Core Concepts

```promql
# Instant vector — current value
http_requests_total

# Range vector — values over time
http_requests_total[5m]

# Rate — per-second rate over the last 5 minutes
rate(http_requests_total[5m])

# irate — instant rate based on the last two samples (more responsive)
irate(http_requests_total[5m])
```

### Common Queries

```promql
# Request rate per second across all pods
rate(http_requests_total[5m])

# Request rate by HTTP method and path
sum(rate(http_requests_total[5m])) by (method, path)

# Error rate (5xx responses)
sum(rate(http_requests_total{status=~"5.."}[5m]))

# Error rate as a percentage
sum(rate(http_requests_total{status=~"5.."}[5m]))
/
sum(rate(http_requests_total[5m])) * 100

# P50, P95, P99 latency
histogram_quantile(0.50, sum(rate(http_request_duration_seconds_bucket[5m])) by (le))
histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket[5m])) by (le))
histogram_quantile(0.99, sum(rate(http_request_duration_seconds_bucket[5m])) by (le))

# CPU usage per pod
rate(container_cpu_usage_seconds_total{namespace="production"}[5m])

# Memory usage per pod
container_memory_working_set_bytes{namespace="production"}

# Pod restarts in the last hour
increase(kube_pod_container_status_restarts_total{namespace="production"}[1h])

# Pods not running
kube_pod_status_phase{phase!="Running", namespace="production"}

# HPA current vs desired replicas
kube_horizontalpodautoscaler_status_current_replicas
kube_horizontalpodautoscaler_spec_max_replicas
```

---

## PrometheusRule — Alerting Rules

```yaml
# prometheusrule.yaml
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: api-alerts
  namespace: production
  labels:
    release: monitoring           # must match Prometheus operator selector
spec:
  groups:
    - name: api.rules
      interval: 30s               # evaluation interval

      rules:
        # Recording rule — precompute expensive queries
        - record: job:http_requests_total:rate5m
          expr: sum(rate(http_requests_total[5m])) by (job)

        # Alert: high error rate
        - alert: HighErrorRate
          expr: |
            sum(rate(http_requests_total{status=~"5.."}[5m]))
            /
            sum(rate(http_requests_total[5m])) > 0.05
          for: 2m                 # must be true for 2 min before firing
          labels:
            severity: critical
            team: backend
          annotations:
            summary: "High error rate on API"
            description: "Error rate is {{ humanizePercentage $value }} — above 5% threshold."
            runbook: "https://runbooks.example.com/api-error-rate"

        # Alert: high latency
        - alert: HighLatencyP99
          expr: |
            histogram_quantile(0.99,
              sum(rate(http_request_duration_seconds_bucket[5m])) by (le)
            ) > 2
          for: 5m
          labels:
            severity: warning
          annotations:
            summary: "P99 latency above 2s"
            description: "P99 latency is {{ $value | humanizeDuration }}"

        # Alert: pod OOMKilled
        - alert: PodOOMKilled
          expr: |
            increase(kube_pod_container_status_restarts_total[15m]) > 2
            and on(namespace, pod, container)
            kube_pod_container_status_last_terminated_reason{reason="OOMKilled"} == 1
          labels:
            severity: warning
          annotations:
            summary: "Pod {{ $labels.pod }} OOMKilled"
            description: "Container {{ $labels.container }} in {{ $labels.namespace }} was OOMKilled"

        # Alert: deployment not available
        - alert: DeploymentNotAvailable
          expr: kube_deployment_status_replicas_available == 0
          for: 1m
          labels:
            severity: critical
          annotations:
            summary: "Deployment {{ $labels.deployment }} has 0 available replicas"
```

---

## Alertmanager Configuration

```yaml
# alertmanager-config.yaml (via Helm values)
alertmanager:
  config:
    global:
      resolve_timeout: 5m
      slack_api_url: 'https://hooks.slack.com/services/T00/B00/xxxx'

    route:
      group_by: ['alertname', 'namespace']
      group_wait: 30s
      group_interval: 5m
      repeat_interval: 12h
      receiver: slack-critical

      routes:
        - match:
            severity: critical
          receiver: slack-critical
          continue: true           # also send to default receiver

        - match:
            severity: warning
          receiver: slack-warning

    receivers:
      - name: slack-critical
        slack_configs:
          - channel: '#alerts-critical'
            title: '{{ template "slack.title" . }}'
            text: '{{ template "slack.text" . }}'
            send_resolved: true

      - name: slack-warning
        slack_configs:
          - channel: '#alerts-warning'
            text: '{{ .CommonAnnotations.summary }}'
            send_resolved: true
```

---

## Grafana Dashboard as Code

```yaml
# grafana-dashboard-configmap.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: api-dashboard
  namespace: monitoring
  labels:
    grafana_dashboard: "1"        # Grafana sidecar auto-imports dashboards with this label
data:
  api-dashboard.json: |
    {
      "title": "API Service Dashboard",
      "uid": "api-service",
      "panels": [
        {
          "title": "Request Rate",
          "type": "timeseries",
          "targets": [
            {
              "expr": "sum(rate(http_requests_total[5m])) by (path)",
              "legendFormat": "{{ path }}"
            }
          ]
        },
        {
          "title": "Error Rate %",
          "type": "stat",
          "targets": [
            {
              "expr": "sum(rate(http_requests_total{status=~\"5..\"}[5m])) / sum(rate(http_requests_total[5m])) * 100"
            }
          ],
          "thresholds": {
            "steps": [
              {"value": 0, "color": "green"},
              {"value": 1, "color": "yellow"},
              {"value": 5, "color": "red"}
            ]
          }
        }
      ]
    }
```

---

## Useful kubectl Commands for Monitoring

```bash
# Check pod metrics
kubectl top pods -n production --sort-by=memory
kubectl top nodes

# Check events (pod OOMKilled, eviction, etc.)
kubectl get events -n production --sort-by=lastTimestamp

# Describe HPA — shows current CPU and scale events
kubectl describe hpa -n production

# Check Prometheus targets
kubectl port-forward -n monitoring svc/monitoring-kube-prometheus-prometheus 9090:9090
# Open http://localhost:9090/targets — see all scrape targets and their status
```

---

## Gotchas

1. **`release: monitoring` label on ServiceMonitor/PrometheusRule** — the Prometheus operator only watches resources with a label that matches its selector. The default is `release: monitoring` for the kube-prometheus-stack chart.
2. **`for: 2m` prevents flapping** — without `for`, alerts fire on the first bad data point. Add `for` to require sustained violation.
3. **Histogram quantiles require `_bucket` metrics** — `histogram_quantile` operates on `_bucket` time series. Only histograms provide these, not summaries.
4. **Prometheus high cardinality** — never use high-cardinality labels (user IDs, request IDs) in metrics. Each unique label combination is a separate time series.

---

## Practice

1. Install kube-prometheus-stack. Access Grafana and explore the built-in Kubernetes cluster dashboard.
2. Deploy an app that exposes `/metrics`. Create a ServiceMonitor and verify it appears in Prometheus targets.
3. Write a PrometheusRule that alerts when pod restart count exceeds 3 in 10 minutes.
4. Use `histogram_quantile` in Prometheus to query P95 latency of your app's requests.

---

## Key Takeaways

- `kube-prometheus-stack` deploys the full monitoring stack in one Helm command.
- ServiceMonitor tells Prometheus what to scrape — labels must match the Prometheus operator's selector.
- `rate()` for counters, direct value for gauges, `histogram_quantile()` for latency percentiles.
- Always add `for: 2m+` to alert rules to prevent alerts from flapping on single bad data points.
