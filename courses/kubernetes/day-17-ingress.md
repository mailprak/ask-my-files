# Day 17 — Ingress & Ingress Controllers

## Learning Objectives
- Understand what Ingress is and why it replaces NodePort/LoadBalancer
- Configure path and host-based routing
- Set up TLS termination
- Use annotations for controller-specific features

---

## Why Ingress?

Without Ingress, each Service needs its own cloud LoadBalancer — expensive and unscalable.

```
Without Ingress:
  app-service    → LoadBalancer (IP: 1.2.3.4, port 80)   ← $$$
  api-service    → LoadBalancer (IP: 5.6.7.8, port 80)   ← $$$
  admin-service  → LoadBalancer (IP: 9.10.11.12, port 80) ← $$$

With Ingress:
  single LoadBalancer → Ingress Controller → app-service      ← $
                                           → api-service
                                           → admin-service
```

---

## Ingress Controller

The Ingress resource is just a routing config. The **Ingress Controller** is the actual reverse proxy (Nginx, Traefik, HAProxy, etc.) that reads the config and routes traffic.

k3d ships with **Traefik** as the default Ingress Controller.

```bash
kubectl get pods -n kube-system -l app.kubernetes.io/name=traefik
kubectl get svc -n kube-system traefik
```

---

## Simple Ingress — Path-Based Routing

```yaml
# ingress-simple.yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: app-ingress
  namespace: default
  annotations:
    # Traefik-specific (used in k3d)
    traefik.ingress.kubernetes.io/router.entrypoints: web

spec:
  rules:
    - host: myapp.local              # HTTP Host header matching
      http:
        paths:
          - path: /
            pathType: Prefix         # Prefix | Exact | ImplementationSpecific
            backend:
              service:
                name: frontend-svc
                port:
                  number: 80

          - path: /api
            pathType: Prefix
            backend:
              service:
                name: api-svc
                port:
                  number: 80

          - path: /api/v2
            pathType: Prefix
            backend:
              service:
                name: api-v2-svc
                port:
                  number: 80
```

---

## Multi-Host Ingress

```yaml
# ingress-multi-host.yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: multi-host-ingress
  namespace: default
spec:
  rules:
    # Production app
    - host: myapp.example.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: frontend-svc
                port:
                  number: 80

    # API
    - host: api.example.com
      http:
        paths:
          - path: /v1
            pathType: Prefix
            backend:
              service:
                name: api-v1-svc
                port:
                  number: 8080
          - path: /v2
            pathType: Prefix
            backend:
              service:
                name: api-v2-svc
                port:
                  number: 8080

    # Admin panel
    - host: admin.example.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: admin-svc
                port:
                  number: 3000
```

---

## TLS Ingress

```yaml
# ingress-tls.yaml
apiVersion: v1
kind: Secret
metadata:
  name: tls-secret
  namespace: default
type: kubernetes.io/tls
data:
  tls.crt: <base64-encoded-certificate>
  tls.key: <base64-encoded-private-key>
---
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: tls-ingress
  namespace: default
  annotations:
    nginx.ingress.kubernetes.io/ssl-redirect: "true"
    nginx.ingress.kubernetes.io/force-ssl-redirect: "true"
spec:
  tls:
    - hosts:
        - myapp.example.com
        - api.example.com
      secretName: tls-secret      # one secret can cover multiple hosts

  rules:
    - host: myapp.example.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: frontend-svc
                port:
                  number: 80
```

---

## Nginx Ingress Controller Annotations

```yaml
# ingress-nginx-annotated.yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: api-ingress
  annotations:
    # Rate limiting
    nginx.ingress.kubernetes.io/limit-rps: "100"
    nginx.ingress.kubernetes.io/limit-connections: "20"

    # Timeouts
    nginx.ingress.kubernetes.io/proxy-connect-timeout: "10"
    nginx.ingress.kubernetes.io/proxy-send-timeout: "60"
    nginx.ingress.kubernetes.io/proxy-read-timeout: "60"

    # Body size
    nginx.ingress.kubernetes.io/proxy-body-size: "10m"

    # CORS
    nginx.ingress.kubernetes.io/enable-cors: "true"
    nginx.ingress.kubernetes.io/cors-allow-origin: "https://myapp.example.com"

    # Auth
    nginx.ingress.kubernetes.io/auth-type: basic
    nginx.ingress.kubernetes.io/auth-secret: basic-auth-secret
    nginx.ingress.kubernetes.io/auth-realm: "Authentication Required"

    # Rewrite path: /api/v1/users → /users
    nginx.ingress.kubernetes.io/rewrite-target: /$2

spec:
  ingressClassName: nginx
  rules:
    - host: api.example.com
      http:
        paths:
          - path: /api/v1(/|$)(.*)
            pathType: Prefix
            backend:
              service:
                name: api-svc
                port:
                  number: 8080
```

---

## IngressClass — Multiple Controllers

```yaml
# ingressclass.yaml
apiVersion: networking.k8s.io/v1
kind: IngressClass
metadata:
  name: nginx
  annotations:
    ingressclass.kubernetes.io/is-default-class: "true"
spec:
  controller: k8s.io/ingress-nginx
---
apiVersion: networking.k8s.io/v1
kind: IngressClass
metadata:
  name: traefik
spec:
  controller: traefik.io/ingress-controller
```

```yaml
# reference in Ingress:
spec:
  ingressClassName: nginx    # or traefik
```

---

## Full Stack: Deployment + Service + Ingress

```yaml
# full-stack.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: frontend
  namespace: default
spec:
  replicas: 2
  selector:
    matchLabels:
      app: frontend
  template:
    metadata:
      labels:
        app: frontend
    spec:
      containers:
        - name: nginx
          image: nginx:alpine
          ports:
            - containerPort: 80
          resources:
            requests:
              cpu: "100m"
              memory: "64Mi"
            limits:
              cpu: "200m"
              memory: "128Mi"
---
apiVersion: v1
kind: Service
metadata:
  name: frontend-svc
  namespace: default
spec:
  selector:
    app: frontend
  ports:
    - port: 80
      targetPort: 80
---
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: frontend-ingress
  namespace: default
  annotations:
    traefik.ingress.kubernetes.io/router.entrypoints: web
spec:
  rules:
    - http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: frontend-svc
                port:
                  number: 80
```

```bash
kubectl apply -f full-stack.yaml
# Access via k3d mapped port
curl http://localhost:8080
```

---

## Testing Ingress on k3d

```bash
# k3d maps host port 8080 to the load balancer
# Add hostname to /etc/hosts for host-based routing
echo "127.0.0.1 myapp.local" >> /etc/hosts

curl http://myapp.local:8080
curl http://myapp.local:8080/api
```

---

## Gotchas

1. **Ingress without an Ingress Controller does nothing** — the resource is just config. The controller must be installed separately.
2. **Path ordering matters** — more specific paths should come before general ones. `/api/v2` before `/api`.
3. **`pathType: Prefix`** matches the path and any sub-path. `Exact` matches only that exact path.
4. **TLS secret must be in the same namespace as the Ingress** — a secret in `kube-system` isn't accessible.

---

## Practice

1. Deploy two apps (nginx and httpd). Create an Ingress that routes `/app1` to nginx and `/app2` to httpd.
2. Configure host-based routing: `app.local` → frontend, `api.local` → backend.
3. Add a rate limit annotation (500 req/s) and test it with `curl` in a loop.
4. Create TLS Ingress using a self-signed cert generated with `openssl`.

---

## Key Takeaways

- Ingress = one LoadBalancer, many services — far more cost-effective than per-service LoadBalancers.
- The Ingress resource is config; the Ingress Controller (Nginx, Traefik) does the actual routing.
- Annotations are controller-specific — check the docs for your specific controller.
- Always specify `ingressClassName` when multiple controllers are installed.
