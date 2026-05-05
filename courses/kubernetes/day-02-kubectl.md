# Day 02 — kubectl: The Kubernetes CLI

## Learning Objectives
- Use kubectl to create, inspect, edit, and delete resources
- Read and interpret kubectl output
- Use contexts to switch between clusters
- Master the most useful day-to-day kubectl commands

---

## kubectl Basics

kubectl is an HTTP client that talks to the kube-apiserver. Every command is a REST call.

```bash
# Syntax
kubectl <verb> <resource> [name] [flags]

# Verbs: get, describe, apply, delete, edit, logs, exec, port-forward, rollout...
```

---

## Creating Resources

```bash
# From a file (preferred — version-controllable)
kubectl apply -f pod.yaml
kubectl apply -f ./k8s/           # apply entire directory
kubectl apply -f ./k8s/ -R        # apply recursively

# Imperatively (quick testing only)
kubectl run nginx --image=nginx:alpine
kubectl create deployment myapp --image=myapp:1.0 --replicas=3
kubectl create namespace staging
```

---

## Getting Resources

```bash
# List resources
kubectl get pods
kubectl get pods -n kube-system              # specific namespace
kubectl get pods -A                          # all namespaces
kubectl get pods,services,deployments        # multiple resource types

# Wide output — shows node, IP
kubectl get pods -o wide

# YAML output — full object definition
kubectl get pod nginx -o yaml

# JSON output
kubectl get pod nginx -o json

# Custom columns
kubectl get pods -o custom-columns="NAME:.metadata.name,STATUS:.status.phase,IP:.status.podIP"

# Watch mode — refreshes automatically
kubectl get pods -w

# Labels
kubectl get pods -l app=nginx                # filter by label
kubectl get pods --show-labels               # show all labels
```

---

## Describing Resources

```bash
# Full detail — events, conditions, resource usage
kubectl describe pod my-pod
kubectl describe node k3d-devcluster-agent-0
kubectl describe deployment my-app

# Events are key for debugging — always check describe first
```

---

## Logs

```bash
kubectl logs my-pod                          # current logs
kubectl logs my-pod -c sidecar              # specific container in a pod
kubectl logs my-pod --previous              # logs from crashed container
kubectl logs my-pod -f                      # follow (tail -f)
kubectl logs my-pod --tail=100              # last 100 lines
kubectl logs my-pod --since=1h              # logs from last hour

# Logs from all pods matching a label
kubectl logs -l app=my-app --all-containers
```

---

## Exec into a Container

```bash
# Interactive shell
kubectl exec -it my-pod -- /bin/sh
kubectl exec -it my-pod -c sidecar -- /bin/bash

# One-off command
kubectl exec my-pod -- env
kubectl exec my-pod -- cat /etc/config/app.yaml
kubectl exec my-pod -- wget -qO- http://localhost:8080/health
```

---

## Port Forwarding

```bash
# Forward local port 9090 → pod port 8080
kubectl port-forward pod/my-pod 9090:8080

# Forward to a deployment (picks a healthy pod)
kubectl port-forward deployment/my-app 9090:8080

# Forward to a service
kubectl port-forward svc/my-service 9090:80

# Then in another terminal:
curl http://localhost:9090/health
```

---

## Editing Resources

```bash
# Opens YAML in your editor — save to apply
kubectl edit deployment my-app

# Patch a specific field
kubectl patch deployment my-app -p '{"spec":{"replicas":5}}'

# Set image
kubectl set image deployment/my-app app=myapp:2.0
```

---

## Deleting Resources

```bash
kubectl delete -f pod.yaml                  # from file
kubectl delete pod my-pod                   # by name
kubectl delete pods -l app=my-app           # by label
kubectl delete namespace staging            # deletes everything in it
kubectl delete all --all -n staging         # delete all resources in namespace
```

---

## Contexts — Switching Between Clusters

A context is a (cluster + user + namespace) combination stored in `~/.kube/config`.

```bash
# List all contexts
kubectl config get-contexts

# Current context
kubectl config current-context

# Switch context
kubectl config use-context k3d-devcluster

# Switch namespace in current context
kubectl config set-context --current --namespace=staging

# View kubeconfig
kubectl config view
```

---

## Useful Aliases

Add to `~/.zshrc` or `~/.bashrc`:

```bash
alias k=kubectl
alias kgp="kubectl get pods"
alias kgs="kubectl get services"
alias kgd="kubectl get deployments"
alias kdp="kubectl describe pod"
alias klo="kubectl logs -f"
alias kex="kubectl exec -it"

# Switch namespace quickly
kns() { kubectl config set-context --current --namespace="$1"; }
```

---

## Dry Run — Preview Without Applying

```bash
# See what would be applied
kubectl apply -f deployment.yaml --dry-run=client
kubectl apply -f deployment.yaml --dry-run=server   # validated by API server

# Generate YAML from imperative command
kubectl create deployment nginx --image=nginx --dry-run=client -o yaml > nginx-deployment.yaml
```

---

## kubectl explain — Built-in Docs

```bash
kubectl explain pod
kubectl explain pod.spec
kubectl explain pod.spec.containers
kubectl explain deployment.spec.strategy
```

---

## Gotchas

1. **`kubectl apply` vs `kubectl create`** — `apply` is idempotent (create or update); `create` fails if the resource exists. Always use `apply`.
2. **Namespace matters** — forgetting `-n myns` means you're looking in `default` and wondering why nothing shows up.
3. **`kubectl delete pod` in a Deployment** — the pod gets recreated immediately by the ReplicaSet controller. Delete the Deployment to permanently remove it.
4. **`-o yaml` is your debugging superpower** — always dump the full object when something behaves unexpectedly.

---

## Key Takeaways

- `kubectl apply -f` for everything in production — idempotent and version-controllable.
- `kubectl describe` + `kubectl logs` are your first debugging tools.
- `kubectl port-forward` lets you test any pod/service without exposing it publicly.
- `kubectl explain` is built-in documentation — use it instead of Googling field names.
