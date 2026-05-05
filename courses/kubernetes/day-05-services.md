# Day 05 — Services

## Learning Objectives
- Understand why Services exist and how they route traffic
- Create ClusterIP, NodePort, and LoadBalancer Services
- Use label selectors to target Pods
- Understand headless Services for StatefulSets

---

## Why Services?

Pods are ephemeral — they die and get new IPs. A Service provides a **stable virtual IP** (ClusterIP) and DNS name that always routes to healthy Pods.

```
Client → Service (stable IP: 10.96.0.10) → Pod (172.17.0.5)
                                          → Pod (172.17.0.6)
                                          → Pod (172.17.0.7)
```

kube-proxy watches Services and Pods, updating iptables/ipvs rules on every node.

---

## ClusterIP — Internal Only (Default)

```yaml
# service-clusterip.yaml
apiVersion: v1
kind: Service
metadata:
  name: taskservice
  namespace: default
  labels:
    app: taskservice
spec:
  type: ClusterIP              # default — only reachable inside the cluster

  selector:
    app: taskservice           # routes to Pods with this label

  ports:
    - name: http
      port: 80                 # port the Service listens on
      targetPort: 8080         # port on the Pod (or named port)
      protocol: TCP
```

```bash
kubectl apply -f service-clusterip.yaml
kubectl get services
# NAME          TYPE        CLUSTER-IP     PORT(S)   AGE
# taskservice   ClusterIP   10.96.45.123   80/TCP    5s

# Access from inside the cluster
kubectl run curl-test --image=curlimages/curl --rm -it -- curl http://taskservice/health
```

---

## Named Port Reference

Define named ports in your Deployment and reference them in the Service:

```yaml
# In the Deployment:
containers:
  - name: app
    ports:
      - name: http          # named port
        containerPort: 8080

# In the Service:
ports:
  - port: 80
    targetPort: http        # reference by name — survives port number changes
```

---

## NodePort — Expose on Every Node's IP

```yaml
# service-nodeport.yaml
apiVersion: v1
kind: Service
metadata:
  name: taskservice-nodeport
spec:
  type: NodePort

  selector:
    app: taskservice

  ports:
    - name: http
      port: 80              # ClusterIP port (internal)
      targetPort: 8080      # Pod port
      nodePort: 30080       # port on every Node's IP (30000–32767)
                            # omit to get a random port assigned
```

```bash
kubectl apply -f service-nodeport.yaml
kubectl get svc taskservice-nodeport
# NAME                    TYPE       CLUSTER-IP    EXTERNAL-IP   PORT(S)
# taskservice-nodeport    NodePort   10.96.1.200   <none>        80:30080/TCP

# Access via any node IP
curl http://<node-ip>:30080/health

# On k3d:
curl http://localhost:30080/health
```

---

## LoadBalancer — Cloud Load Balancer

```yaml
# service-loadbalancer.yaml
apiVersion: v1
kind: Service
metadata:
  name: taskservice-lb
  annotations:
    service.beta.kubernetes.io/aws-load-balancer-type: "nlb"   # AWS-specific
spec:
  type: LoadBalancer

  selector:
    app: taskservice

  ports:
    - name: http
      port: 80
      targetPort: 8080
```

```bash
kubectl get svc taskservice-lb
# NAME             TYPE           CLUSTER-IP    EXTERNAL-IP       PORT(S)
# taskservice-lb   LoadBalancer   10.96.2.100   a1b2c3.elb.aws..  80:31234/TCP
```

On k3d, LoadBalancer type is handled by k3d's built-in load balancer (the port mapping you set with `--port`).

---

## ExternalName — DNS Alias to External Service

```yaml
# service-externalname.yaml
apiVersion: v1
kind: Service
metadata:
  name: postgres
  namespace: default
spec:
  type: ExternalName
  externalName: mydb.us-east-1.rds.amazonaws.com   # CNAME alias
```

Pods can now connect to `postgres.default.svc.cluster.local` and it resolves to the RDS endpoint. Useful for migrating services out of the cluster without changing connection strings.

---

## Headless Service — No ClusterIP

Used with StatefulSets — each Pod gets its own DNS entry:

```yaml
# service-headless.yaml
apiVersion: v1
kind: Service
metadata:
  name: postgres-headless
spec:
  clusterIP: None            # headless — no VIP assigned

  selector:
    app: postgres

  ports:
    - port: 5432
      targetPort: 5432
```

DNS entries created:
```
postgres-0.postgres-headless.default.svc.cluster.local → Pod IP
postgres-1.postgres-headless.default.svc.cluster.local → Pod IP
postgres-2.postgres-headless.default.svc.cluster.local → Pod IP
```

---

## Service Discovery via DNS

Every Service gets a DNS name:

```
<service-name>.<namespace>.svc.cluster.local
```

From within the same namespace, short name works:
```bash
# From same namespace
curl http://taskservice/health
curl http://taskservice.default/health
curl http://taskservice.default.svc.cluster.local/health

# From different namespace
curl http://taskservice.production.svc.cluster.local/health
```

---

## Deployment + Service Together

```yaml
# app-full.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: myapp
spec:
  replicas: 3
  selector:
    matchLabels:
      app: myapp
  template:
    metadata:
      labels:
        app: myapp          # Service selector must match this
    spec:
      containers:
        - name: app
          image: nginx:alpine
          ports:
            - name: http
              containerPort: 80
---
apiVersion: v1
kind: Service
metadata:
  name: myapp
spec:
  selector:
    app: myapp              # routes to pods with label app=myapp
  ports:
    - port: 80
      targetPort: http
```

```bash
kubectl apply -f app-full.yaml
kubectl get pods,svc -l app=myapp
```

---

## Gotchas

1. **Selector must match Pod labels exactly** — a typo means the Service has no endpoints and traffic goes nowhere.
2. **`targetPort` is the Pod port, `port` is the Service port** — easy to mix up.
3. **NodePort range is 30000–32767** — specifying a port outside this range is rejected.
4. **ClusterIP is not reachable from your host machine** — use `kubectl port-forward` or a NodePort/LoadBalancer for local access.

```bash
# Debug: check if Service has endpoints
kubectl get endpoints taskservice
# NAME          ENDPOINTS                     AGE
# taskservice   172.17.0.5:8080,172.17.0.6:8080   5m
# If ENDPOINTS shows <none> — selector doesn't match any pod labels
```

---

## Practice

1. Create a Deployment with 3 nginx replicas and a ClusterIP Service. Verify traffic reaches all 3.
2. Change the Service to NodePort and access it via your machine's browser.
3. Delete one Pod — verify the Service still routes traffic to the remaining two.
4. Test DNS resolution: exec into a Pod and `curl http://myapp`.

---

## Key Takeaways

- Services provide stable virtual IPs and DNS names for ephemeral Pods.
- ClusterIP = internal only; NodePort = via node IP; LoadBalancer = cloud LB.
- `kubectl get endpoints <svc>` — if it shows `<none>`, your selector doesn't match any Pod.
- DNS: `<service>.<namespace>.svc.cluster.local` — from same namespace, just `<service>` works.
