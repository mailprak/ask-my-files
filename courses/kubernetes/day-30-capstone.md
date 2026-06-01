# Day 30 — Capstone: Full Stack Deployment on k3d

## Learning Objectives
- Deploy a complete production-grade application on k3d
- Apply every concept from the course: RBAC, NetworkPolicy, HPA, Ingress, Secrets, Monitoring
- Use Helm + Kustomize together
- Simulate failure scenarios and recover

---

## What We're Building

A full-stack task management app:

```
Internet → Ingress (NGINX) → Frontend (React, 2 replicas)
                           → API (Go, HPA 2-10 replicas)
                                   ↓
                             PostgreSQL (StatefulSet, PVC)
                                   ↓
                             Redis (StatefulSet, cache)

Monitoring: Prometheus + Grafana (kube-prometheus-stack)
Secrets: Sealed Secrets (Git-safe)
RBAC: Least-privilege service accounts per workload
Network: Deny-all + explicit allow rules
```

---

## Step 1 — Create k3d Cluster

```bash
# Create a cluster with a local registry and port mappings
k3d cluster create taskapp \
  --registry-create taskapp-registry:localhost:5000 \
  --port "80:80@loadbalancer" \
  --port "443:443@loadbalancer" \
  --agents 2

# Verify
kubectl get nodes
# NAME                    STATUS   ROLES
# k3d-taskapp-server-0    Ready    control-plane,master
# k3d-taskapp-agent-0     Ready    <none>
# k3d-taskapp-agent-1     Ready    <none>
```

---

## Step 2 — Namespaces & RBAC

```yaml
# namespaces.yaml
apiVersion: v1
kind: Namespace
metadata:
  name: taskapp
  labels:
    pod-security.kubernetes.io/enforce: restricted
    pod-security.kubernetes.io/enforce-version: v1.29
---
apiVersion: v1
kind: Namespace
metadata:
  name: monitoring
```

```yaml
# rbac.yaml
# API service account — can only read ConfigMaps and Secrets in taskapp ns
apiVersion: v1
kind: ServiceAccount
metadata:
  name: api-sa
  namespace: taskapp
automountServiceAccountToken: false
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: api-role
  namespace: taskapp
rules:
  - apiGroups: [""]
    resources: ["configmaps", "secrets"]
    verbs: ["get", "list"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: api-role-binding
  namespace: taskapp
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: api-role
subjects:
  - kind: ServiceAccount
    name: api-sa
    namespace: taskapp
---
# Frontend SA — no API access needed
apiVersion: v1
kind: ServiceAccount
metadata:
  name: frontend-sa
  namespace: taskapp
automountServiceAccountToken: false
```

---

## Step 3 — Secrets

```bash
# Install Sealed Secrets
kubectl apply -f https://github.com/bitnami-labs/sealed-secrets/releases/download/v0.24.5/controller.yaml

# Create and seal DB secret
kubectl create secret generic db-secret \
  --from-literal=POSTGRES_PASSWORD=password \
  --from-literal=POSTGRES_USER=taskapp \
  --from-literal=POSTGRES_DB=tasks \
  --namespace=taskapp \
  --dry-run=client -o yaml | \
  kubeseal --format yaml > db-secret-sealed.yaml

kubectl apply -f db-secret-sealed.yaml
```

---

## Step 4 — PostgreSQL StatefulSet

```yaml
# postgres.yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: postgres
  namespace: taskapp
spec:
  serviceName: postgres-headless
  replicas: 1
  selector:
    matchLabels:
      app: postgres
  template:
    metadata:
      labels:
        app: postgres
        tier: database
    spec:
      serviceAccountName: api-sa
      securityContext:
        runAsNonRoot: true
        runAsUser: 999          # postgres UID
        fsGroup: 999
        seccompProfile:
          type: RuntimeDefault

      containers:
        - name: postgres
          image: postgres:15-alpine
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: false  # postgres needs to write to /var/lib/postgresql
            capabilities:
              drop: ["ALL"]

          ports:
            - containerPort: 5432

          envFrom:
            - secretRef:
                name: db-secret

          volumeMounts:
            - name: data
              mountPath: /var/lib/postgresql/data
              subPath: postgres        # avoid storing data at root of PVC

          resources:
            requests:
              cpu: "250m"
              memory: "256Mi"
            limits:
              cpu: "1"
              memory: "512Mi"

          readinessProbe:
            exec:
              command:
                - pg_isready
                - -U
                - taskapp
            initialDelaySeconds: 10
            periodSeconds: 5

  volumeClaimTemplates:
    - metadata:
        name: data
      spec:
        accessModes: [ReadWriteOnce]
        resources:
          requests:
            storage: 5Gi
---
# Headless service for StatefulSet
apiVersion: v1
kind: Service
metadata:
  name: postgres-headless
  namespace: taskapp
spec:
  clusterIP: None
  selector:
    app: postgres
  ports:
    - port: 5432
---
# ClusterIP for normal access
apiVersion: v1
kind: Service
metadata:
  name: postgres
  namespace: taskapp
spec:
  selector:
    app: postgres
  ports:
    - port: 5432
```

---

## Step 5 — API Deployment

```yaml
# api-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
  namespace: taskapp
  annotations:
    kubernetes.io/change-cause: "v1.0.0: initial deployment"
spec:
  replicas: 2
  selector:
    matchLabels:
      app: api
      tier: api
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  minReadySeconds: 10

  template:
    metadata:
      labels:
        app: api
        tier: api
      annotations:
        prometheus.io/scrape: "true"
        prometheus.io/port: "9090"
        prometheus.io/path: "/metrics"

    spec:
      serviceAccountName: api-sa
      automountServiceAccountToken: false

      securityContext:
        runAsNonRoot: true
        runAsUser: 10001
        runAsGroup: 10001
        fsGroup: 10001
        seccompProfile:
          type: RuntimeDefault

      initContainers:
        - name: wait-for-postgres
          image: busybox:1.36
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities:
              drop: ["ALL"]
          command:
            - sh
            - -c
            - until nc -z postgres.taskapp.svc.cluster.local 5432; do sleep 2; done

      containers:
        - name: api
          image: localhost:5000/taskapp-api:1.0.0
          ports:
            - name: http
              containerPort: 8080
            - name: metrics
              containerPort: 9090
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities:
              drop: ["ALL"]

          envFrom:
            - secretRef:
                name: db-secret
          env:
            - name: DB_HOST
              value: postgres.taskapp.svc.cluster.local
            - name: DB_PORT
              value: "5432"

          volumeMounts:
            - name: tmp
              mountPath: /tmp

          resources:
            requests:
              cpu: "100m"
              memory: "128Mi"
            limits:
              cpu: "500m"
              memory: "256Mi"

          readinessProbe:
            httpGet:
              path: /health/ready
              port: 8080
            initialDelaySeconds: 5
            periodSeconds: 5
            successThreshold: 2

          livenessProbe:
            httpGet:
              path: /health/live
              port: 8080
            initialDelaySeconds: 30
            periodSeconds: 10
            failureThreshold: 3

          lifecycle:
            preStop:
              exec:
                command: ["/bin/sh", "-c", "sleep 5"]

      terminationGracePeriodSeconds: 30

      volumes:
        - name: tmp
          emptyDir: {}
---
apiVersion: v1
kind: Service
metadata:
  name: api
  namespace: taskapp
  labels:
    app: api
spec:
  selector:
    app: api
  ports:
    - name: http
      port: 80
      targetPort: 8080
    - name: metrics
      port: 9090
      targetPort: 9090
---
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: api-hpa
  namespace: taskapp
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: api
  minReplicas: 2
  maxReplicas: 10
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
  behavior:
    scaleDown:
      stabilizationWindowSeconds: 300
```

---

## Step 6 — Network Policies

```yaml
# networkpolicies.yaml
# Default deny all in taskapp
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: deny-all
  namespace: taskapp
spec:
  podSelector: {}
  policyTypes: [Ingress, Egress]
---
# Allow DNS for all pods
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-dns
  namespace: taskapp
spec:
  podSelector: {}
  policyTypes: [Egress]
  egress:
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: kube-system
      ports:
        - port: 53
          protocol: UDP
---
# Allow ingress → frontend
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-ingress-to-frontend
  namespace: taskapp
spec:
  podSelector:
    matchLabels:
      tier: frontend
  policyTypes: [Ingress]
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: kube-system   # ingress controller
---
# Allow frontend → API
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-frontend-to-api
  namespace: taskapp
spec:
  podSelector:
    matchLabels:
      tier: api
  policyTypes: [Ingress]
  ingress:
    - from:
        - podSelector:
            matchLabels:
              tier: frontend
      ports:
        - port: 8080
---
# Allow API → Postgres
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-api-to-postgres
  namespace: taskapp
spec:
  podSelector:
    matchLabels:
      app: postgres
  policyTypes: [Ingress]
  ingress:
    - from:
        - podSelector:
            matchLabels:
              tier: api
      ports:
        - port: 5432
---
# Allow Prometheus to scrape metrics
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-prometheus-scrape
  namespace: taskapp
spec:
  podSelector:
    matchLabels:
      tier: api
  policyTypes: [Ingress]
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: monitoring
      ports:
        - port: 9090
```

---

## Step 7 — Ingress

```yaml
# ingress.yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: taskapp-ingress
  namespace: taskapp
  annotations:
    nginx.ingress.kubernetes.io/rewrite-target: /$2
    nginx.ingress.kubernetes.io/proxy-read-timeout: "60"
    nginx.ingress.kubernetes.io/proxy-body-size: "10m"
spec:
  ingressClassName: nginx
  rules:
    - host: taskapp.local
      http:
        paths:
          - path: /api(/|$)(.*)
            pathType: Prefix
            backend:
              service:
                name: api
                port:
                  number: 80
          - path: /
            pathType: Prefix
            backend:
              service:
                name: frontend
                port:
                  number: 80
```

```bash
# Add to /etc/hosts for local access
echo "127.0.0.1 taskapp.local" | sudo tee -a /etc/hosts
```

---

## Step 8 — Monitoring

```bash
# Install kube-prometheus-stack
helm upgrade --install monitoring prometheus-community/kube-prometheus-stack \
  --namespace monitoring \
  --create-namespace \
  --set grafana.adminPassword=password
```

```yaml
# servicemonitor.yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: api-monitor
  namespace: taskapp
  labels:
    release: monitoring
spec:
  selector:
    matchLabels:
      app: api
  endpoints:
    - port: metrics
      path: /metrics
      interval: 15s
---
# prometheusrule.yaml
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: taskapp-alerts
  namespace: taskapp
  labels:
    release: monitoring
spec:
  groups:
    - name: taskapp.rules
      rules:
        - alert: APIHighErrorRate
          expr: |
            sum(rate(http_requests_total{status=~"5.."}[5m]))
            / sum(rate(http_requests_total[5m])) > 0.05
          for: 2m
          labels:
            severity: critical
          annotations:
            summary: "TaskApp API error rate > 5%"

        - alert: PostgresDown
          expr: kube_pod_status_ready{pod=~"postgres-.*", namespace="taskapp"} == 0
          for: 1m
          labels:
            severity: critical
          annotations:
            summary: "PostgreSQL pod is not ready"
```

---

## Step 9 — Deploy Everything

```bash
# Apply in order (namespace first)
kubectl apply -f namespaces.yaml
kubectl apply -f rbac.yaml
kubectl apply -f db-secret-sealed.yaml
kubectl apply -f postgres.yaml
kubectl apply -f api-deployment.yaml
kubectl apply -f networkpolicies.yaml
kubectl apply -f ingress.yaml
kubectl apply -f servicemonitor.yaml
kubectl apply -f prometheusrule.yaml

# Watch everything come up
kubectl get pods -n taskapp -w

# Verify the API is accessible
curl http://taskapp.local/api/health

# Check HPA
kubectl get hpa -n taskapp

# Access Grafana
kubectl port-forward -n monitoring svc/monitoring-grafana 3000:80
```

---

## Step 10 — Failure Scenarios

```bash
# Scenario 1: Delete a pod — verify it restarts
kubectl delete pod -n taskapp -l app=api

# Scenario 2: Scale API to 0 — verify Ingress returns 503
kubectl scale deployment api -n taskapp --replicas=0
curl http://taskapp.local/api/tasks    # 503 Service Unavailable
kubectl scale deployment api -n taskapp --replicas=2

# Scenario 3: Bad rollout — deploy broken image
kubectl set image deployment/api api=localhost:5000/taskapp-api:broken -n taskapp
kubectl rollout status deployment/api -n taskapp   # should stall on readiness
kubectl rollout undo deployment/api -n taskapp     # rollback

# Scenario 4: Test network policy
kubectl run test-pod --image=busybox --rm -it -n taskapp -- sh
# wget postgres.taskapp.svc.cluster.local:5432   # should timeout (blocked by network policy)

# Scenario 5: Simulate load
kubectl run load-gen --image=busybox --rm -it -n taskapp -- \
  sh -c "while true; do wget -q -O- http://api.taskapp.svc.cluster.local/api/tasks; done"
# Watch HPA scale up
kubectl get hpa -n taskapp -w
```

---

## Checklist — Production Readiness

```
☐ Namespaces with PSS labels (restricted)
☐ Dedicated ServiceAccounts (no auto-mount of default SA token)
☐ RBAC with least privilege
☐ Secrets via Sealed Secrets (not plain base64 in Git)
☐ ReadinessProbe and LivenessProbe on all containers
☐ Resource requests and limits on all containers
☐ HPA for stateless workloads
☐ PodDisruptionBudget for StatefulSets
☐ NetworkPolicy: deny-all + explicit allow rules
☐ Ingress with TLS termination
☐ Monitoring: ServiceMonitor + PrometheusRule alerts
☐ Rollout strategy: maxUnavailable=0, minReadySeconds > 0
☐ PreStop hook + terminationGracePeriodSeconds
☐ revisionHistoryLimit >= 5 (rollback capability)
☐ All images pinned to specific tags (not :latest)
```

---

## Key Takeaways

- A production-ready app on Kubernetes touches every topic in this course — they're all connected.
- Start with least privilege: deny-all network, restricted PSS, minimal RBAC, no root.
- Readiness probes gate rollouts and traffic. Liveness probes restart stuck containers. Both are essential.
- HPA + pre-configured monitoring = self-healing, self-scaling infrastructure.
- Practice failure scenarios: delete pods, roll back deployments, test network policies. Know what breaks before production does.

---

## Course Complete

Congratulations on completing the 30-day Kubernetes course. Here is what you covered:

| Days | Topic |
|---|---|
| 01-02 | Architecture, kubectl |
| 03-06 | Pods, Deployments, Services, Namespaces |
| 07-08 | ConfigMaps, Secrets, Labels |
| 09-11 | ReplicaSets, DaemonSets, StatefulSets, Jobs |
| 12-14 | Storage, ResourceQuota, Limits |
| 15-17 | Networking, Probes, Ingress |
| 18-20 | NetworkPolicy, Rolling Updates, Init/Sidecars |
| 21-22 | DNS, RBAC |
| 23-25 | Security Contexts, PSS, Secrets Management |
| 26-28 | HPA, Helm, Kustomize |
| 29-30 | Monitoring, Capstone |

Next steps: CKA (Certified Kubernetes Administrator) exam, or explore GitOps with ArgoCD.
