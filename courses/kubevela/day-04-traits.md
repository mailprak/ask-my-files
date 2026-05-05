# Day 04 — Built-in Traits

## Learning Objectives
- Apply traits to control how components run
- Use ingress, scaler, resource, sidecar, env, labels, and annotations traits
- Combine multiple traits on a single component
- Understand which traits apply to which component types

---

## Traits Overview

Traits are operational capabilities attached to components. The platform team defines them; developers opt in.

```yaml
components:
  - name: api
    type: webservice
    properties:
      image: myapi:1.0
      port: 8080
    traits:               # ← traits attach here, under the component
      - type: ingress
        properties:
          domain: api.example.com
          http:
            "/": 8080
      - type: scaler
        properties:
          min: 2
          max: 10
```

---

## ingress Trait — Expose via Ingress

```yaml
traits:
  - type: ingress
    properties:
      domain: api.example.com      # hostname for the Ingress rule

      http:
        "/api": 8080               # path → container port
        "/docs": 8080

      # TLS — references a Secret with tls.crt and tls.key
      # tls: api.example.com       # uncomment to enable TLS

      # Ingress class (default: nginx)
      # ingressClassName: nginx

      # Pass-through custom annotations
      annotations:
        nginx.ingress.kubernetes.io/proxy-body-size: "50m"
        nginx.ingress.kubernetes.io/proxy-read-timeout: "60"
```

```bash
# Verify the Ingress was created
kubectl get ingress -n production

# Test
curl http://api.example.com/api/health
```

---

## gateway Trait — Expose via Gateway API

For clusters using the Gateway API (the Ingress successor):

```yaml
traits:
  - type: gateway
    properties:
      domain: api.example.com
      http:
        "/": 8080
      gatewayRef:
        name: my-gateway            # references a Gateway resource
        namespace: kube-system
```

---

## scaler Trait — Horizontal Pod Autoscaler

```yaml
traits:
  - type: scaler
    properties:
      min: 2                        # minimum replicas
      max: 20                       # maximum replicas
      cpuPercent: 70                # scale up when avg CPU > 70%

      # Memory-based scaling (alternative)
      # memoryPercent: 80
```

```bash
# Verify HPA was created
kubectl get hpa -n production

# Watch scaling
kubectl get hpa -n production -w
```

---

## resource Trait — CPU & Memory Limits

```yaml
traits:
  - type: resource
    properties:
      cpu: "500m"                   # request AND limit set to the same value by default
      memory: "512Mi"

      # Separate requests and limits
      requests:
        cpu: "200m"
        memory: "256Mi"
      limits:
        cpu: "1"
        memory: "1Gi"
```

This overrides any `cpu`/`memory` set in the component `properties` — use one or the other.

---

## env Trait — Add Environment Variables

```yaml
traits:
  - type: env
    properties:
      env:
        - name: FEATURE_FLAG_X
          value: "true"
        - name: DB_PASSWORD
          valueFrom:
            secretKeyRef:
              name: db-secret
              key: password
        - name: POD_NAME
          valueFrom:
            fieldRef:
              fieldPath: metadata.name    # downward API
```

Useful when you want to inject env vars without changing the component definition — e.g., platform-managed secrets.

---

## sidecar Trait — Inject a Sidecar Container

```yaml
traits:
  - type: sidecar
    properties:
      name: log-shipper
      image: fluent/fluent-bit:2.2

      # Mount the same volume as the main container
      volumes:
        - name: logs
          path: /logs

      # Environment variables for the sidecar
      env:
        - name: LOG_LEVEL
          value: info

      # Resource limits for the sidecar
      cpu: "50m"
      memory: "64Mi"
```

```yaml
# The main component needs to share the volume
components:
  - name: api
    type: webservice
    properties:
      image: myapi:1.0
      port: 8080
      volumeMounts:
        - name: logs
          mountPath: /app/logs
          emptyDir: {}
    traits:
      - type: sidecar
        properties:
          name: log-shipper
          image: fluent/fluent-bit:2.2
          volumes:
            - name: logs
              path: /logs            # mounted at /logs in the sidecar
```

---

## labels Trait — Add Labels

```yaml
traits:
  - type: labels
    properties:
      labels:
        team: backend
        cost-center: "cc-1234"
        environment: production
```

Labels are added to the Pod template — useful for cost attribution and Prometheus selectors.

---

## annotations Trait — Add Annotations

```yaml
traits:
  - type: annotations
    properties:
      annotations:
        prometheus.io/scrape: "true"
        prometheus.io/port: "9090"
        prometheus.io/path: "/metrics"
        vault.hashicorp.com/agent-inject: "true"
        vault.hashicorp.com/role: "app-role"
```

---

## command Trait — Override Container Command

```yaml
traits:
  - type: command
    properties:
      command:
        - ./server
        - --mode=debug
        - --log-level=trace
      args:
        - --extra-flag
```

---

## Combining Multiple Traits

```yaml
# app-all-traits.yaml
apiVersion: core.oam.dev/v1beta1
kind: Application
metadata:
  name: production-api
  namespace: production
spec:
  components:
    - name: api
      type: webservice
      properties:
        image: myapi:2.0
        port: 8080
        replicas: 2

      traits:
        # Expose via Ingress
        - type: ingress
          properties:
            domain: api.mycompany.com
            http:
              "/": 8080
            annotations:
              nginx.ingress.kubernetes.io/proxy-read-timeout: "60"

        # Auto-scale
        - type: scaler
          properties:
            min: 2
            max: 15
            cpuPercent: 70

        # Resource limits
        - type: resource
          properties:
            requests:
              cpu: "200m"
              memory: "256Mi"
            limits:
              cpu: "1"
              memory: "512Mi"

        # Platform-managed env vars
        - type: env
          properties:
            env:
              - name: DB_PASSWORD
                valueFrom:
                  secretKeyRef:
                    name: db-secret
                    key: password

        # Log shipping sidecar
        - type: sidecar
          properties:
            name: log-agent
            image: fluent/fluent-bit:2.2
            cpu: "50m"
            memory: "64Mi"

        # Cost attribution labels
        - type: labels
          properties:
            labels:
              team: backend
              cost-center: cc-1234

        # Prometheus scraping
        - type: annotations
          properties:
            annotations:
              prometheus.io/scrape: "true"
              prometheus.io/port: "9090"
```

---

## Trait Applicability

Not all traits apply to all component types:

```bash
# Check which traits apply to which component types
vela show scaler
# APPLIES-TO: webservice, worker

vela show ingress
# APPLIES-TO: webservice

vela show sidecar
# APPLIES-TO: webservice, worker

vela show labels
# APPLIES-TO: * (all)
```

Applying a trait to an incompatible component type will produce a validation error on `kubectl apply`.

---

## Verify Traits Were Applied

```bash
# Status shows which traits are active
vela status production-api

# Tree view shows all generated resources including HPA, Ingress
vela status production-api --tree
# APPLICATION     COMPONENT  RESOURCE              STATUS
# production-api  api        Deployment/api        Ready:2/2
# production-api  api        Service/api           -
# production-api  api        Ingress/api           -
# production-api  api        HorizontalPodAutoscaler/api  -

# Check the generated Deployment has sidecar injected
kubectl get deployment api -n production -o jsonpath='{.spec.template.spec.containers[*].name}'
# api log-agent
```

---

## Gotchas

1. **`resource` trait vs component `cpu`/`memory` properties** — if both are set, the trait takes precedence. Pick one approach and stick with it.
2. **`scaler` trait overrides `replicas` in component properties** — once an HPA is created, manual `replicas` changes are overridden. Remove `replicas` from the component when using `scaler`.
3. **`sidecar` volumes must exist** — the volume referenced by the sidecar must be declared in the component's `volumeMounts`. If the main container doesn't mount it, the Pod won't start.
4. **`ingress` requires an Ingress controller** — on k3d, the NGINX ingress controller is built in. On other clusters, verify the IngressClass exists.

---

## Practice

1. Add a `scaler` trait to a webservice. Generate load and verify the HPA scales up replicas.
2. Add a `sidecar` trait with a `busybox` sidecar that tails a log file. Verify both containers are in the Pod.
3. Add `labels` and `annotations` traits. Verify the labels appear on the Pod with `kubectl get pod --show-labels`.
4. Combine `ingress`, `scaler`, and `resource` traits on one component. Run `vela status --tree` to see all generated resources.

---

## Key Takeaways

- Traits attach operational behaviour to components — ingress, autoscaling, resource limits, sidecars, labels.
- Multiple traits can be combined on a single component — they all apply independently.
- Use `vela show <trait>` to see what properties a trait accepts and which component types it applies to.
- `vela status --tree` shows every Kubernetes resource generated by KubeVela — including those from traits.
