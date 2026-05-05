# Day 15 — Kubernetes Networking Model

## Learning Objectives
- Understand the Kubernetes networking model (flat network)
- Know how Pod-to-Pod, Pod-to-Service, and external traffic flows
- Understand CNI plugins and how they implement the network
- Use DNS for service discovery

---

## The Four Networking Problems Kubernetes Solves

1. **Container-to-container** within a Pod → via localhost (shared network namespace)
2. **Pod-to-Pod** across nodes → flat network, every Pod has a unique routable IP
3. **Pod-to-Service** → kube-proxy iptables/ipvs rules
4. **External-to-Service** → NodePort, LoadBalancer, Ingress

---

## The Flat Network Model

Every Pod gets a unique IP address. Any Pod can reach any other Pod directly — no NAT.

```
Node 1                          Node 2
┌──────────────────────┐        ┌──────────────────────┐
│  Pod A  172.16.0.1   │        │  Pod C  172.16.1.1   │
│  Pod B  172.16.0.2   │◄──────►│  Pod D  172.16.1.2   │
└──────────────────────┘        └──────────────────────┘
         Node IP: 10.0.0.1               Node IP: 10.0.0.2
```

Pod A (172.16.0.1) can talk to Pod C (172.16.1.1) directly. The CNI plugin makes this work.

---

## CNI Plugins

The Container Network Interface (CNI) plugin implements the flat network:

| CNI Plugin | Use Case |
|---|---|
| **Flannel** | Simple, overlay network, good for dev |
| **Calico** | Production, supports NetworkPolicy, BGP |
| **Cilium** | eBPF-based, best performance, advanced NetworkPolicy |
| **Weave** | Encrypted overlay |
| k3d uses **Flannel** by default |

---

## Pod Network Demo

```yaml
# pod-network-demo.yaml
apiVersion: v1
kind: Pod
metadata:
  name: pod-a
  labels:
    app: demo
spec:
  containers:
    - name: app
      image: curlimages/curl:latest
      command: ["sleep", "infinity"]
---
apiVersion: v1
kind: Pod
metadata:
  name: pod-b
  labels:
    app: demo
spec:
  containers:
    - name: nginx
      image: nginx:alpine
      ports:
        - containerPort: 80
```

```bash
kubectl apply -f pod-network-demo.yaml

# Get pod IPs
kubectl get pods -o wide
# NAME    IP            NODE
# pod-a   172.16.0.5    node-1
# pod-b   172.16.1.3    node-2

# Pod A directly reaches Pod B across nodes — no Service needed
kubectl exec pod-a -- curl -s http://172.16.1.3
```

---

## DNS in Kubernetes

CoreDNS runs as a Deployment in `kube-system` and provides DNS for all Pods.

### Pod DNS Config

```yaml
# pod-dns.yaml
apiVersion: v1
kind: Pod
metadata:
  name: dns-demo
spec:
  # Custom DNS configuration
  dnsPolicy: ClusterFirst        # ClusterFirst | Default | None | ClusterFirstWithHostNet
  dnsConfig:
    nameservers:
      - 8.8.8.8                  # add external resolver alongside CoreDNS
    searches:
      - myteam.svc.cluster.local # additional search domains
    options:
      - name: ndots
        value: "5"

  containers:
    - name: app
      image: curlimages/curl:latest
      command: ["sleep", "infinity"]
```

```bash
# DNS resolution from inside a pod
kubectl exec dns-demo -- nslookup kubernetes.default
# Server: 10.96.0.10  (CoreDNS ClusterIP)
# Address: 10.96.0.10#53
# Name: kubernetes.default.svc.cluster.local
# Address: 10.96.0.1

# Resolve a service
kubectl exec dns-demo -- nslookup taskservice.default.svc.cluster.local
kubectl exec dns-demo -- curl http://taskservice.default.svc.cluster.local
```

---

## DNS Record Patterns

```
# Service
<service-name>.<namespace>.svc.cluster.local

# StatefulSet Pod
<pod-name>.<service-name>.<namespace>.svc.cluster.local
# e.g.: postgres-0.postgres-headless.default.svc.cluster.local

# Pod (less common — requires enableServiceLinks or subdomain)
<pod-ip>.<namespace>.pod.cluster.local
# e.g.: 172-16-0-5.default.pod.cluster.local
```

---

## kube-proxy and Service Routing

kube-proxy watches Services and Endpoints and updates iptables rules on every node:

```bash
# See iptables rules created by kube-proxy (on a node)
iptables -t nat -L KUBE-SERVICES -n --line-numbers

# In k3d, kube-proxy runs as a Pod
kubectl get pods -n kube-system -l k8s-app=kube-proxy
kubectl logs -n kube-system -l k8s-app=kube-proxy
```

---

## Endpoints — The Bridge Between Service and Pods

```bash
kubectl get endpoints taskservice
# NAME          ENDPOINTS                           AGE
# taskservice   172.16.0.5:8080,172.16.1.3:8080   5m

# Watch endpoints update as pods come and go
kubectl get endpoints taskservice -w
```

When a Pod fails its readiness probe, it's removed from Endpoints — no traffic is sent to it.

---

## Debugging Network Issues

```bash
# Is the Service resolving?
kubectl exec my-pod -- nslookup taskservice

# Is the Service routing to any pods?
kubectl get endpoints taskservice

# Can we reach the Pod directly?
POD_IP=$(kubectl get pod taskservice-abc -o jsonpath='{.status.podIP}')
kubectl exec my-pod -- curl http://$POD_IP:8080/health

# Is kube-proxy updating iptables?
kubectl describe service taskservice
# Check "Endpoints:" field

# Check CoreDNS logs
kubectl logs -n kube-system -l k8s-app=kube-dns

# Run a debug pod
kubectl run debug --image=curlimages/curl --rm -it -- /bin/sh
# Inside: nslookup, curl, wget
```

---

## Network Topology Awareness

Route traffic to the closest Pod (same zone) to reduce latency:

```yaml
# service-topology.yaml
apiVersion: v1
kind: Service
metadata:
  name: taskservice
spec:
  selector:
    app: taskservice
  ports:
    - port: 80
      targetPort: 8080
  # Prefer local endpoints (same node or zone)
  trafficPolicy:
    local:
      enabled: true
---
# Or use topologyKeys (older approach):
apiVersion: v1
kind: Service
metadata:
  name: taskservice-local
spec:
  topologyKeys:
    - "kubernetes.io/hostname"           # prefer same node first
    - "topology.kubernetes.io/zone"      # then same zone
    - "*"                                # fallback to any
```

---

## Gotchas

1. **Pod IPs are not stable** — they change when pods restart. Always use Service DNS names.
2. **ClusterIP is not reachable from outside the cluster** — it only exists in the cluster's iptables.
3. **DNS caching** — some apps cache DNS responses. If a Service IP changes, apps may connect to stale IPs. Set short DNS TTLs or use service mesh.
4. **`dnsPolicy: Default`** uses the node's DNS (not CoreDNS) — you won't be able to resolve cluster services.

---

## Practice

1. Create two Pods on different nodes. Curl from Pod A to Pod B's IP directly.
2. Create a Service and resolve it by DNS from inside a Pod.
3. Break the selector (typo the label) and observe Endpoints showing `<none>`.
4. Use `kubectl exec` to nslookup a StatefulSet pod's stable DNS name.

---

## Key Takeaways

- Kubernetes networking is a flat, non-NAT network — every Pod has a unique routable IP.
- CoreDNS provides DNS for all Services and Pods — always use DNS names, never IPs.
- kube-proxy translates Service ClusterIPs to Pod IPs using iptables rules on every node.
- When a Service has no endpoints, check your label selector against the Pod labels.
