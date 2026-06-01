# Day 27 — Helm

## Learning Objectives
- Understand Helm charts, templates, and values
- Install and upgrade releases
- Write a Helm chart from scratch
- Use Helm hooks and tests

---

## What is Helm?

Helm is the package manager for Kubernetes. A **chart** is a collection of YAML templates + a values file. A **release** is a deployed instance of a chart.

```
Chart (template + defaults)  +  Values (overrides)  →  Release (running resources)
```

---

## Helm Basics

```bash
# Install Helm (macOS)
brew install helm

# Verify
helm version

# Add a chart repository
helm repo add bitnami https://charts.bitnami.com/bitnami
helm repo add stable https://charts.helm.sh/stable
helm repo update

# Search for charts
helm search repo nginx
helm search hub postgresql    # search artifacthub.io

# Install a chart
helm install my-postgres bitnami/postgresql \
  --namespace production \
  --create-namespace

# Install with custom values
helm install my-postgres bitnami/postgresql \
  --namespace production \
  --set auth.postgresPassword=password \
  --set primary.persistence.size=10Gi

# Install from a values file
helm install my-postgres bitnami/postgresql \
  --namespace production \
  --values postgres-values.yaml
```

---

## Managing Releases

```bash
# List releases
helm list -n production
helm list -A           # all namespaces

# Upgrade a release (apply changes)
helm upgrade my-postgres bitnami/postgresql \
  --namespace production \
  --values postgres-values.yaml

# Upgrade or install if not exists
helm upgrade --install my-postgres bitnami/postgresql \
  --namespace production \
  --values postgres-values.yaml

# Rollback to previous release revision
helm rollback my-postgres 1

# View release history
helm history my-postgres -n production

# Uninstall a release
helm uninstall my-postgres -n production

# Show computed values for a release
helm get values my-postgres -n production

# Show all manifests for a release
helm get manifest my-postgres -n production

# Template without installing (dry run)
helm template my-postgres bitnami/postgresql \
  --values postgres-values.yaml
```

---

## Chart Structure

```
mychart/
├── Chart.yaml          # chart metadata
├── values.yaml         # default values
├── templates/
│   ├── _helpers.tpl    # named templates (partials)
│   ├── deployment.yaml
│   ├── service.yaml
│   ├── configmap.yaml
│   ├── hpa.yaml
│   ├── NOTES.txt       # post-install instructions
│   └── tests/
│       └── test-connection.yaml
├── charts/             # chart dependencies
└── .helmignore
```

---

## Chart.yaml

```yaml
# Chart.yaml
apiVersion: v2
name: myapp
description: My application Helm chart
type: application          # application | library

version: 1.2.0             # chart version (SemVer)
appVersion: "2.5.1"        # version of the packaged app

keywords:
  - api
  - backend

maintainers:
  - name: Platform Team
    email: platform@example.com

dependencies:
  - name: postgresql
    version: "13.x.x"
    repository: https://charts.bitnami.com/bitnami
    condition: postgresql.enabled    # only if values.postgresql.enabled = true
```

```bash
# Download dependencies
helm dependency update ./mychart
```

---

## values.yaml

```yaml
# values.yaml
replicaCount: 2

image:
  repository: myapi
  tag: "2.5.1"
  pullPolicy: IfNotPresent

service:
  type: ClusterIP
  port: 80
  targetPort: 8080

ingress:
  enabled: false
  host: ""
  tls: false

resources:
  requests:
    cpu: "100m"
    memory: "128Mi"
  limits:
    cpu: "500m"
    memory: "256Mi"

autoscaling:
  enabled: false
  minReplicas: 2
  maxReplicas: 10
  targetCPUUtilizationPercentage: 70

postgresql:
  enabled: true
  auth:
    database: myapp
    username: myapp

env:
  LOG_LEVEL: info
  APP_ENV: production

podAnnotations: {}
nodeSelector: {}
tolerations: []
affinity: {}
```

---

## templates/deployment.yaml

```yaml
# templates/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ include "myapp.fullname" . }}       # from _helpers.tpl
  namespace: {{ .Release.Namespace }}
  labels:
    {{- include "myapp.labels" . | nindent 4 }}
    app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
  annotations:
    {{- toYaml .Values.podAnnotations | nindent 4 }}
spec:
  {{- if not .Values.autoscaling.enabled }}
  replicas: {{ .Values.replicaCount }}          # omit if HPA manages replicas
  {{- end }}
  selector:
    matchLabels:
      {{- include "myapp.selectorLabels" . | nindent 6 }}
  template:
    metadata:
      labels:
        {{- include "myapp.selectorLabels" . | nindent 8 }}
    spec:
      containers:
        - name: {{ .Chart.Name }}
          image: "{{ .Values.image.repository }}:{{ .Values.image.tag }}"
          imagePullPolicy: {{ .Values.image.pullPolicy }}
          ports:
            - containerPort: {{ .Values.service.targetPort }}
          env:
            {{- range $key, $value := .Values.env }}
            - name: {{ $key }}
              value: {{ $value | quote }}
            {{- end }}
          resources:
            {{- toYaml .Values.resources | nindent 12 }}
      nodeSelector:
        {{- toYaml .Values.nodeSelector | nindent 8 }}
      tolerations:
        {{- toYaml .Values.tolerations | nindent 8 }}
      affinity:
        {{- toYaml .Values.affinity | nindent 8 }}
```

---

## templates/_helpers.tpl

```yaml
{{/* _helpers.tpl — reusable named templates */}}

{{/* Full name: release-chart */}}
{{- define "myapp.fullname" -}}
{{- printf "%s-%s" .Release.Name .Chart.Name | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/* Standard labels */}}
{{- define "myapp.labels" -}}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version }}
{{ include "myapp.selectorLabels" . }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/* Selector labels */}}
{{- define "myapp.selectorLabels" -}}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}
```

---

## templates/service.yaml

```yaml
# templates/service.yaml
apiVersion: v1
kind: Service
metadata:
  name: {{ include "myapp.fullname" . }}
  namespace: {{ .Release.Namespace }}
  labels:
    {{- include "myapp.labels" . | nindent 4 }}
spec:
  type: {{ .Values.service.type }}
  ports:
    - port: {{ .Values.service.port }}
      targetPort: {{ .Values.service.targetPort }}
      protocol: TCP
  selector:
    {{- include "myapp.selectorLabels" . | nindent 4 }}
```

---

## Conditional Ingress

```yaml
# templates/ingress.yaml
{{- if .Values.ingress.enabled }}
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: {{ include "myapp.fullname" . }}
  namespace: {{ .Release.Namespace }}
  labels:
    {{- include "myapp.labels" . | nindent 4 }}
spec:
  rules:
    - host: {{ .Values.ingress.host | quote }}
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: {{ include "myapp.fullname" . }}
                port:
                  number: {{ .Values.service.port }}
  {{- if .Values.ingress.tls }}
  tls:
    - hosts:
        - {{ .Values.ingress.host | quote }}
      secretName: {{ include "myapp.fullname" . }}-tls
  {{- end }}
{{- end }}
```

---

## Helm Hooks

Hooks run at specific points in the release lifecycle:

```yaml
# templates/db-migrate.yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: {{ include "myapp.fullname" . }}-migrate
  annotations:
    "helm.sh/hook": pre-upgrade,pre-install     # run before installing/upgrading
    "helm.sh/hook-weight": "-5"                 # lower weight = runs first
    "helm.sh/hook-delete-policy": before-hook-creation,hook-succeeded
spec:
  template:
    spec:
      restartPolicy: Never
      containers:
        - name: migrate
          image: "{{ .Values.image.repository }}:{{ .Values.image.tag }}"
          command: ["./migrate", "--direction=up"]
          env:
            - name: DATABASE_URL
              valueFrom:
                secretKeyRef:
                  name: {{ include "myapp.fullname" . }}-db
                  key: url
```

Available hooks: `pre-install`, `post-install`, `pre-upgrade`, `post-upgrade`, `pre-delete`, `post-delete`, `pre-rollback`, `post-rollback`.

---

## Helm Test

```yaml
# templates/tests/test-connection.yaml
apiVersion: v1
kind: Pod
metadata:
  name: {{ include "myapp.fullname" . }}-test
  annotations:
    "helm.sh/hook": test              # runs only during 'helm test'
    "helm.sh/hook-delete-policy": hook-succeeded
spec:
  restartPolicy: Never
  containers:
    - name: test
      image: curlimages/curl:latest
      command:
        - sh
        - -c
        - |
          curl -f http://{{ include "myapp.fullname" . }}:{{ .Values.service.port }}/health
          echo "Health check passed!"
```

```bash
helm test my-release -n production
# Pod my-release-myapp-test pending
# Pod my-release-myapp-test running
# Pod my-release-myapp-test succeeded
# TEST SUITE:     my-release-myapp-test
# Last run status: Passed
```

---

## Deploy to k3d with Helm

```bash
# Create chart
helm create myapp

# Edit values and templates...

# Lint the chart
helm lint ./myapp

# Template and review output
helm template my-release ./myapp --values prod-values.yaml | less

# Install on k3d
helm upgrade --install my-release ./myapp \
  --namespace production \
  --create-namespace \
  --values prod-values.yaml \
  --wait \                    # wait until all pods are ready
  --timeout 5m

# Package and share
helm package ./myapp
# myapp-1.2.0.tgz

# Push to OCI registry (GitHub Container Registry, etc.)
helm push myapp-1.2.0.tgz oci://ghcr.io/myorg/charts
```

---

## Gotchas

1. **`helm upgrade` without `--install`** — fails if the release doesn't exist. Use `--install` for idempotent CI/CD.
2. **`replicaCount` and HPA conflict** — if HPA is enabled, don't set `replicas` in the Deployment template (it fights HPA). Wrap with `{{- if not .Values.autoscaling.enabled }}`.
3. **Helm stores release state in Secrets** — `helm list` reads Secrets in the release namespace. Don't delete these.
4. **Chart dependencies** — run `helm dependency update` after changing `Chart.yaml` dependencies, or the subchart won't be included.

---

## Practice

1. `helm create myapp` — explore the generated chart structure. Deploy it to your k3d cluster.
2. Add an HPA template controlled by `autoscaling.enabled`. Enable it via `--set autoscaling.enabled=true`.
3. Add a pre-upgrade hook that prints "Running migrations". Verify it runs before the Deployment is updated.
4. Run `helm test` against your release. Write a test pod that curls the `/health` endpoint.

---

## Key Takeaways

- Helm = Kubernetes package manager. Chart = templates + values. Release = deployed chart.
- `helm upgrade --install` is the idempotent CI/CD command — works on first install and subsequent updates.
- `_helpers.tpl` keeps labels and names DRY across all templates.
- Hooks let you run Jobs before/after install, upgrade, or delete — perfect for DB migrations and smoke tests.
