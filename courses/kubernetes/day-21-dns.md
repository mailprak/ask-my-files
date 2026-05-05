# Day 21 — DNS in Kubernetes

## Learning Objectives
- Understand how CoreDNS works in Kubernetes
- Know all DNS record patterns for Services and Pods
- Customize DNS configuration for Pods
- Debug DNS resolution issues

---

## CoreDNS

CoreDNS is the cluster DNS server — deployed as a Deployment in `kube-system`:

```bash
kubectl get deployment -n kube-system coredns
kubectl get svc -n kube-system kube-dns
# NAME       TYPE        CLUSTER-IP   PORT(S)
# kube-dns   ClusterIP   10.96.0.10   53/UDP,53/TCP

kubectl get configmap -n kube-system coredns -o yaml
```

Every Pod's `/etc/resolv.conf` is configured to use the `kube-dns` ClusterIP.

---

## CoreDNS ConfigMap

```yaml
# coredns-configmap.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: coredns
  namespace: kube-system
data:
  Corefile: |
    .:53 {
        errors
        health {
            lameduck 5s
        }
        ready
        kubernetes cluster.local in-addr.arpa ip6.arpa {
            pods insecure
            fallthrough in-addr.arpa ip6.arpa
            ttl 30
        }
        prometheus :9153
        forward . /etc/resolv.conf {
            max_concurrent 1000
        }
        cache 30
        loop
        reload
        loadbalance
    }
```

---

## DNS Records: Services

```bash
# Full FQDN
<service-name>.<namespace>.svc.cluster.local

# Examples
kubectl run test --image=curlimages/curl --rm -it -- sh

# From same namespace (default)
nslookup myapp
nslookup myapp.default
nslookup myapp.default.svc
nslookup myapp.default.svc.cluster.local
# All four resolve to the same ClusterIP

# From different namespace
nslookup myapp.production.svc.cluster.local

# Kubernetes API server itself
nslookup kubernetes.default.svc.cluster.local
```

---

## DNS Records: StatefulSet Pods (via Headless Service)

```bash
# <pod-name>.<headless-service>.<namespace>.svc.cluster.local
nslookup postgres-0.postgres-headless.default.svc.cluster.local
nslookup postgres-1.postgres-headless.default.svc.cluster.local

# SRV records (for port discovery)
nslookup -type=SRV _postgres._tcp.postgres-headless.default.svc.cluster.local
```

---

## Pod DNS Configuration

```yaml
# pod-dns-config.yaml
apiVersion: v1
kind: Pod
metadata:
  name: dns-custom
spec:
  dnsPolicy: ClusterFirst      # default: use CoreDNS first, fall back to node DNS

  dnsConfig:
    nameservers:
      - 1.1.1.1                # add additional DNS servers
    searches:
      - myteam.svc.cluster.local        # extra search domains
      - svc.cluster.local
      - cluster.local
    options:
      - name: ndots
        value: "5"             # try as relative name for queries with < 5 dots
      - name: timeout
        value: "2"
      - name: attempts
        value: "3"

  containers:
    - name: app
      image: busybox:1.36
      command: ["sleep", "infinity"]
```

```bash
kubectl exec dns-custom -- cat /etc/resolv.conf
# nameserver 10.96.0.10
# nameserver 1.1.1.1
# search default.svc.cluster.local svc.cluster.local cluster.local myteam.svc.cluster.local
# options ndots:5
```

---

## DNS Policies

```yaml
dnsPolicy: ClusterFirst           # (default) CoreDNS first, then node resolver
dnsPolicy: ClusterFirstWithHostNet  # use with hostNetwork: true
dnsPolicy: Default                # use node's DNS resolver (NOT CoreDNS)
                                  # pods cannot resolve cluster services
dnsPolicy: None                   # fully custom — must provide dnsConfig
```

---

## Customizing CoreDNS

Add a stub zone to forward a specific domain to an external DNS server:

```yaml
# coredns-custom.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: coredns
  namespace: kube-system
data:
  Corefile: |
    .:53 {
        errors
        health
        ready
        kubernetes cluster.local in-addr.arpa ip6.arpa {
            pods insecure
            fallthrough in-addr.arpa ip6.arpa
            ttl 30
        }
        prometheus :9153
        forward . /etc/resolv.conf
        cache 30
        loop
        reload
        loadbalance
    }

    # Forward internal corporate domain to internal DNS server
    corp.example.com:53 {
        errors
        cache 30
        forward . 10.100.0.1
    }

    # Rewrite: alias old service name to new one
    rewrite name old-service.default.svc.cluster.local new-service.default.svc.cluster.local
```

```bash
kubectl apply -f coredns-custom.yaml
# CoreDNS reloads automatically (reload plugin)
```

---

## ExternalDNS — Automatic DNS for Services

ExternalDNS syncs Service and Ingress hostnames to cloud DNS (Route53, Cloudflare, etc.):

```yaml
# externaldns-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: external-dns
  namespace: kube-system
spec:
  replicas: 1
  selector:
    matchLabels:
      app: external-dns
  template:
    metadata:
      labels:
        app: external-dns
    spec:
      serviceAccountName: external-dns
      containers:
        - name: external-dns
          image: registry.k8s.io/external-dns/external-dns:v0.14.0
          args:
            - --source=service
            - --source=ingress
            - --domain-filter=example.com    # only manage records in this zone
            - --provider=aws
            - --aws-zone-type=public
            - --registry=txt
            - --txt-owner-id=my-cluster
```

When you annotate a Service with the right hostname, ExternalDNS creates a DNS record:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: myapp
  annotations:
    external-dns.alpha.kubernetes.io/hostname: myapp.example.com
spec:
  type: LoadBalancer
  selector:
    app: myapp
  ports:
    - port: 80
```

---

## Debugging DNS

```bash
# Run a debug pod
kubectl run dnsutils --image=busybox:1.36 --rm -it -- sh

# Inside the pod:
nslookup kubernetes                                    # should resolve
nslookup kubernetes.default.svc.cluster.local         # FQDN
nslookup myservice.myns.svc.cluster.local             # specific service
cat /etc/resolv.conf                                   # check config

# Check CoreDNS pods
kubectl get pods -n kube-system -l k8s-app=kube-dns
kubectl logs -n kube-system -l k8s-app=kube-dns

# Check CoreDNS config
kubectl get configmap coredns -n kube-system -o yaml

# Check if a service has endpoints
kubectl get endpoints myservice
```

---

## Common DNS Issues

| Symptom | Likely Cause | Fix |
|---|---|---|
| `nslookup: can't resolve myservice` | Wrong namespace or service doesn't exist | Use FQDN `myservice.ns.svc.cluster.local` |
| DNS resolves but no traffic | Service has no endpoints | Check `kubectl get endpoints myservice` |
| `SERVFAIL` from CoreDNS | CoreDNS pod crashed | `kubectl restart pod coredns` |
| External DNS not resolving | `dnsPolicy: Default` used | Change to `ClusterFirst` |
| Intermittent DNS failures | DNS cache too aggressive | Reduce `cache` TTL in CoreDNS config |

---

## Practice

1. Create two Services in different namespaces. Resolve each from a Pod using short and FQDN names.
2. Customize a Pod's `dnsConfig` to add an extra search domain. Verify it's in `/etc/resolv.conf`.
3. Add a stub zone to CoreDNS forwarding `test.local` to `8.8.8.8`.
4. Debug a DNS failure scenario: create a Service with a wrong selector (no endpoints) and trace why DNS resolves but connections fail.

---

## Key Takeaways

- CoreDNS runs as a Deployment in `kube-system` — it's the DNS server for all Pods.
- Services: `<name>.<ns>.svc.cluster.local`. StatefulSet pods: `<pod>.<headless-svc>.<ns>.svc.cluster.local`.
- `ndots:5` means queries with fewer than 5 dots are tried with all search domains first — this causes extra DNS queries.
- Always debug DNS with `nslookup` inside a Pod, not from your laptop.
