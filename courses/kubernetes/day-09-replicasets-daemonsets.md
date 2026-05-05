# Day 09 — ReplicaSets & DaemonSets

## Learning Objectives
- Understand how ReplicaSets manage Pod replicas
- Know when to interact with ReplicaSets directly
- Use DaemonSets to run one Pod per node
- Apply node selectors and tolerations to DaemonSets

---

## ReplicaSet

A ReplicaSet ensures a specified number of Pod replicas are running at all times. In practice you never create ReplicaSets directly — Deployments manage them. But understanding them is important for debugging.

```yaml
# replicaset.yaml
apiVersion: apps/v1
kind: ReplicaSet
metadata:
  name: myapp-rs
  labels:
    app: myapp
spec:
  replicas: 3

  selector:
    matchLabels:
      app: myapp        # manages any pod with this label

  template:
    metadata:
      labels:
        app: myapp      # must match selector
    spec:
      containers:
        - name: app
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
```

```bash
kubectl apply -f replicaset.yaml
kubectl get rs
kubectl describe rs myapp-rs

# Delete a pod — RS immediately creates a replacement
kubectl delete pod myapp-rs-<hash>
kubectl get pods -w    # watch replacement appear
```

---

## How a Deployment Uses ReplicaSets

When you update a Deployment, it creates a NEW ReplicaSet and scales down the old one:

```bash
# Before update
kubectl get rs
# NAME                DESIRED  CURRENT  READY
# myapp-7d9f5b-abc   3        3        3

# After updating image
kubectl set image deployment/myapp app=myapp:2.0
kubectl get rs
# NAME                DESIRED  CURRENT  READY
# myapp-7d9f5b-abc   0        0        0    ← old RS kept for rollback
# myapp-6c8e4d-xyz   3        3        3    ← new RS
```

---

## DaemonSet

A DaemonSet ensures exactly **one Pod runs on every node** (or every node matching a selector). When new nodes join, the DaemonSet automatically adds a Pod there.

Use cases:
- Log collectors (Fluentd, Filebeat)
- Node monitoring agents (Prometheus node-exporter)
- Network plugins (Calico, Cilium)
- Storage drivers

```yaml
# daemonset-log-collector.yaml
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: fluentd
  namespace: kube-system
  labels:
    app: fluentd
    component: logging
spec:
  selector:
    matchLabels:
      app: fluentd

  updateStrategy:
    type: RollingUpdate           # RollingUpdate | OnDelete
    rollingUpdate:
      maxUnavailable: 1           # update one node at a time

  template:
    metadata:
      labels:
        app: fluentd
    spec:
      # DaemonSets often need host-level access
      hostNetwork: false
      hostPID: false

      tolerations:
        # Run on control-plane nodes too (normally tainted)
        - key: node-role.kubernetes.io/control-plane
          operator: Exists
          effect: NoSchedule

      containers:
        - name: fluentd
          image: fluent/fluentd-kubernetes-daemonset:v1.16-debian-elasticsearch8
          env:
            - name: FLUENT_ELASTICSEARCH_HOST
              value: "elasticsearch.logging.svc.cluster.local"
            - name: FLUENT_ELASTICSEARCH_PORT
              value: "9200"

          resources:
            requests:
              cpu: "100m"
              memory: "200Mi"
            limits:
              cpu: "500m"
              memory: "500Mi"

          volumeMounts:
            - name: varlog
              mountPath: /var/log
            - name: varlibdockercontainers
              mountPath: /var/lib/docker/containers
              readOnly: true

      volumes:
        - name: varlog
          hostPath:
            path: /var/log         # mount host directory

        - name: varlibdockercontainers
          hostPath:
            path: /var/lib/docker/containers
```

---

## DaemonSet on Specific Nodes Only

```yaml
# daemonset-gpu.yaml
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: nvidia-gpu-driver
  namespace: kube-system
spec:
  selector:
    matchLabels:
      app: nvidia-gpu-driver
  template:
    metadata:
      labels:
        app: nvidia-gpu-driver
    spec:
      nodeSelector:
        hardware: gpu             # only run on nodes with this label

      # OR use affinity for more expressive rules:
      affinity:
        nodeAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
            nodeSelectorTerms:
              - matchExpressions:
                  - key: nvidia.com/gpu
                    operator: Exists

      containers:
        - name: nvidia-driver
          image: nvidia/k8s-device-plugin:v0.14.0
          securityContext:
            privileged: true
          volumeMounts:
            - name: device-plugin
              mountPath: /var/lib/kubelet/device-plugins

      volumes:
        - name: device-plugin
          hostPath:
            path: /var/lib/kubelet/device-plugins
```

---

## Node Monitoring DaemonSet Example

```yaml
# daemonset-node-exporter.yaml
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: node-exporter
  namespace: monitoring
  labels:
    app: node-exporter
spec:
  selector:
    matchLabels:
      app: node-exporter
  template:
    metadata:
      labels:
        app: node-exporter
      annotations:
        prometheus.io/scrape: "true"
        prometheus.io/port: "9100"
    spec:
      hostNetwork: true          # use host networking for accurate metrics
      hostPID: true

      tolerations:
        - operator: Exists       # tolerate all taints — run on every node

      containers:
        - name: node-exporter
          image: prom/node-exporter:v1.7.0
          args:
            - --path.rootfs=/host
          ports:
            - name: metrics
              containerPort: 9100
              hostPort: 9100     # expose on host port
          resources:
            requests:
              cpu: "50m"
              memory: "50Mi"
            limits:
              cpu: "200m"
              memory: "200Mi"
          volumeMounts:
            - name: root
              mountPath: /host
              readOnly: true
              mountPropagation: HostToContainer

      volumes:
        - name: root
          hostPath:
            path: /
```

---

## Inspecting DaemonSets

```bash
kubectl get daemonsets -n kube-system
# NAME         DESIRED  CURRENT  READY  UP-TO-DATE  AVAILABLE  NODE SELECTOR
# fluentd      3        3        3      3           3          <none>

kubectl describe daemonset fluentd -n kube-system
kubectl get pods -n kube-system -l app=fluentd -o wide   # shows which node each pod is on
kubectl rollout status daemonset/fluentd -n kube-system
kubectl rollout history daemonset/fluentd -n kube-system
```

---

## Gotchas

1. **Never manage a Deployment's ReplicaSet directly** — scaling or deleting a RS that's owned by a Deployment will be immediately reconciled back.
2. **DaemonSet pods don't count against quota in some contexts** — but resource requests still count toward node capacity.
3. **`hostPath` volumes are a security risk** — the container can read/write the host filesystem. Only use for trusted system daemons.
4. **DaemonSet pods on control-plane nodes** — control-plane nodes have a taint by default. Add a toleration for `node-role.kubernetes.io/control-plane` to schedule there.

---

## Practice

1. Create a DaemonSet that runs `busybox` on every node and prints the node name.
2. Label one node with `role=logging`. Create a DaemonSet that only runs on labeled nodes.
3. Update a DaemonSet image and use `kubectl rollout status` to track the update.
4. Run `kubectl get pods -o wide` and verify exactly one pod per node.

---

## Key Takeaways

- ReplicaSet manages Pod count — Deployment manages ReplicaSets. Always work at the Deployment level.
- DaemonSet = one Pod per node — perfect for cluster-wide agents (logging, monitoring, networking).
- DaemonSets update with `RollingUpdate` strategy — one node at a time.
- Use `tolerations` to run DaemonSet pods on tainted nodes (like control-plane nodes).
