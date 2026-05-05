# Day 18 — Network Policies

## Learning Objectives
- Understand the default allow-all networking model
- Write ingress and egress NetworkPolicy rules
- Implement namespace isolation and micro-segmentation
- Test NetworkPolicy behaviour

---

## Default Behaviour: Allow All

By default, all Pods can talk to all other Pods — even across namespaces. NetworkPolicy adds firewall rules at the Pod level.

NetworkPolicy requires a CNI plugin that supports it (Calico, Cilium, Weave). **Flannel (k3d default) does NOT enforce NetworkPolicy.** Use Calico or Cilium for enforcement.

---

## NetworkPolicy Structure

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: my-policy
  namespace: default
spec:
  podSelector:        # which pods this policy applies to
    matchLabels:
      app: my-app

  policyTypes:        # which directions to control
    - Ingress         # incoming traffic to selected pods
    - Egress          # outgoing traffic from selected pods

  ingress:            # rules for incoming traffic
    - from: [...]
      ports: [...]

  egress:             # rules for outgoing traffic
    - to: [...]
      ports: [...]
```

---

## Deny All Traffic (Default Deny)

Best practice: start by denying everything, then explicitly allow what's needed.

```yaml
# deny-all.yaml — apply to a namespace first
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: deny-all
  namespace: production
spec:
  podSelector: {}        # {} matches ALL pods in the namespace
  policyTypes:
    - Ingress
    - Egress
  # no ingress/egress rules = deny everything
```

---

## Allow Specific Ingress

```yaml
# allow-frontend-to-api.yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-frontend-to-api
  namespace: production
spec:
  podSelector:
    matchLabels:
      app: api-service          # this policy applies to the API pods

  policyTypes:
    - Ingress

  ingress:
    - from:
        - podSelector:
            matchLabels:
              app: frontend     # only frontend pods can reach api

      ports:
        - protocol: TCP
          port: 8080
```

---

## Allow from Specific Namespace

```yaml
# allow-monitoring.yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-prometheus-scrape
  namespace: production
spec:
  podSelector:
    matchLabels:
      app: api-service

  policyTypes:
    - Ingress

  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: monitoring   # from the monitoring namespace
          podSelector:
            matchLabels:
              app: prometheus    # AND from the prometheus pod specifically
                                 # namespaceSelector AND podSelector = AND condition
      ports:
        - protocol: TCP
          port: 9090

    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: monitoring
        # no podSelector = allow from ALL pods in the monitoring namespace
      ports:
        - protocol: TCP
          port: 9090
```

**Important:** When both `namespaceSelector` and `podSelector` are in the same `from` item, it's an AND. When they're in separate `from` items, it's an OR.

---

## Allow DNS Egress (Always Needed with Deny-All)

```yaml
# allow-dns.yaml — must add this with deny-all
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-dns-egress
  namespace: production
spec:
  podSelector: {}          # all pods
  policyTypes:
    - Egress
  egress:
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: kube-system
          podSelector:
            matchLabels:
              k8s-app: kube-dns
      ports:
        - protocol: UDP
          port: 53
        - protocol: TCP
          port: 53
```

---

## Complete Micro-Segmentation Example

A 3-tier app: frontend → api → database

```yaml
# network-policies-3tier.yaml

# ── Database: only accept from API ───────────────────────────────────────
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: db-ingress
  namespace: production
spec:
  podSelector:
    matchLabels:
      tier: database
  policyTypes:
    - Ingress
    - Egress
  ingress:
    - from:
        - podSelector:
            matchLabels:
              tier: api
      ports:
        - port: 5432
  egress: []    # database has no allowed egress
---
# ── API: accept from frontend, reach database ─────────────────────────────
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: api-policy
  namespace: production
spec:
  podSelector:
    matchLabels:
      tier: api
  policyTypes:
    - Ingress
    - Egress
  ingress:
    - from:
        - podSelector:
            matchLabels:
              tier: frontend
      ports:
        - port: 8080
  egress:
    - to:
        - podSelector:
            matchLabels:
              tier: database
      ports:
        - port: 5432
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: kube-system
      ports:
        - port: 53
          protocol: UDP
---
# ── Frontend: accept from internet (ingress controller), reach API ────────
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: frontend-policy
  namespace: production
spec:
  podSelector:
    matchLabels:
      tier: frontend
  policyTypes:
    - Ingress
    - Egress
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: kube-system   # from ingress controller
  egress:
    - to:
        - podSelector:
            matchLabels:
              tier: api
      ports:
        - port: 8080
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: kube-system
      ports:
        - port: 53
          protocol: UDP
```

---

## Allow External Egress (to Internet)

```yaml
# allow-external-egress.yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-external-api
  namespace: production
spec:
  podSelector:
    matchLabels:
      app: payment-service
  policyTypes:
    - Egress
  egress:
    # Allow DNS
    - ports:
        - port: 53
          protocol: UDP

    # Allow HTTPS to Stripe API (by IP block — Stripe's range)
    - to:
        - ipBlock:
            cidr: 54.187.174.169/32
      ports:
        - port: 443
          protocol: TCP

    # Allow HTTPS to all external IPs (broad — prefer specific)
    - to:
        - ipBlock:
            cidr: 0.0.0.0/0
            except:
              - 10.0.0.0/8       # exclude cluster-internal
              - 172.16.0.0/12
              - 192.168.0.0/16
      ports:
        - port: 443
          protocol: TCP
```

---

## Testing Network Policies

```bash
# From a pod, try to reach the database directly (should be blocked)
kubectl exec -it frontend-pod -n production -- nc -zv postgres.production.svc 5432

# From the API pod (should succeed)
kubectl exec -it api-pod -n production -- nc -zv postgres.production.svc 5432

# List all network policies
kubectl get networkpolicies -A

# Describe a policy
kubectl describe networkpolicy db-ingress -n production
```

---

## Gotchas

1. **Flannel doesn't enforce NetworkPolicies** — you need Calico, Cilium, or Weave. On k3d, install Calico manually.
2. **AND vs OR in `from`** — `namespaceSelector` + `podSelector` in the SAME from item = AND. Separate items = OR.
3. **Always allow DNS egress** when using deny-all — without it, DNS breaks and everything stops working.
4. **NetworkPolicies are additive** — multiple policies on the same pod are OR'd together. There's no "deny" rule; you restrict by not allowing.

---

## Practice

1. Apply `deny-all` to a namespace. Verify two pods can no longer communicate.
2. Add a policy allowing pod A to reach pod B on port 8080. Verify A can reach B but not vice versa.
3. Implement the 3-tier micro-segmentation example and verify each tier can only talk to its allowed peer.
4. Add a policy allowing the monitoring namespace to scrape metrics from all pods on port 9090.

---

## Key Takeaways

- NetworkPolicy is a whitelist model — if no policy selects a pod, all traffic is allowed.
- Apply `deny-all` first, then add specific allow rules for each communication path.
- AND vs OR in selectors: same `from` item = AND, separate items = OR.
- Always allow DNS (port 53 UDP) when using egress policies — everything breaks without it.
