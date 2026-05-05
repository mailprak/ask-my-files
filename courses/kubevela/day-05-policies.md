# Day 05 — Policies: Override & Topology

## Learning Objectives
- Use `override` policy to customise per-environment configuration
- Use `topology` policy to target specific clusters or namespaces
- Combine policies for multi-environment deployments
- Understand how policies interact with workflow steps

---

## What Are Policies?

Policies control **where** an Application deploys and **how** it is customised per environment. They don't change what the component does — they change the deployment target and properties at render time.

Two built-in policy types:

| Policy | Purpose |
|---|---|
| `override` | Change component properties per environment (replicas, image tag, env vars) |
| `topology` | Select which clusters and namespaces to deploy to |

---

## override Policy

The `override` policy patches component properties before rendering. You can change any property that the component type supports.

```yaml
# app-with-override.yaml
apiVersion: core.oam.dev/v1beta1
kind: Application
metadata:
  name: taskapp
  namespace: taskapp
spec:
  components:
    - name: api
      type: webservice
      properties:
        image: myapi:1.0
        port: 8080
        replicas: 3            # production default
        cpu: "500m"
        memory: "512Mi"
        env:
          - name: APP_ENV
            value: production
          - name: LOG_LEVEL
            value: info

  policies:
    # Override for staging environment
    - name: staging-override
      type: override
      properties:
        components:
          - name: api           # match by component name
            properties:
              replicas: 1       # staging: fewer replicas
              cpu: "100m"       # staging: smaller resources
              memory: "128Mi"
              env:
                - name: APP_ENV
                  value: staging
                - name: LOG_LEVEL
                  value: debug    # more verbose in staging

    # Override for production environment
    - name: production-override
      type: override
      properties:
        components:
          - name: api
            properties:
              replicas: 5
              cpu: "1"
              memory: "1Gi"
```

Policies are only applied when referenced in a Workflow step — by themselves they do nothing.

---

## topology Policy — Single Cluster, Different Namespaces

```yaml
policies:
  # Deploy to staging namespace on the local cluster
  - name: staging-target
    type: topology
    properties:
      clusters: ["local"]       # "local" = the management cluster
      namespace: staging        # override the namespace

  # Deploy to production namespace
  - name: production-target
    type: topology
    properties:
      clusters: ["local"]
      namespace: production
```

---

## topology Policy — Multi-Cluster

```yaml
policies:
  # Deploy to eu-west-1 cluster
  - name: eu-target
    type: topology
    properties:
      clusters: ["eu-west-1"]   # must be registered in KubeVela
      namespace: production

  # Deploy to us-east-1 cluster
  - name: us-target
    type: topology
    properties:
      clusters: ["us-east-1"]
      namespace: production

  # Deploy to all clusters matching a label
  - name: all-production-clusters
    type: topology
    properties:
      clusterSelector:
        labels:
          env: production       # selects clusters labelled env=production
      namespace: production
```

---

## Combining Override + Topology

Policies are combined in the Workflow — each step references which policies to apply:

```yaml
# app-multi-env.yaml
apiVersion: core.oam.dev/v1beta1
kind: Application
metadata:
  name: taskapp
  namespace: default
spec:
  components:
    - name: api
      type: webservice
      properties:
        image: myapi:1.5
        port: 8080
        replicas: 3
        env:
          - name: APP_ENV
            value: production

  policies:
    - name: staging-override
      type: override
      properties:
        components:
          - name: api
            properties:
              replicas: 1
              env:
                - name: APP_ENV
                  value: staging

    - name: staging-target
      type: topology
      properties:
        clusters: ["local"]
        namespace: staging

    - name: production-target
      type: topology
      properties:
        clusters: ["local"]
        namespace: production

  workflow:
    steps:
      # Step 1: deploy to staging with overridden replicas + staging namespace
      - name: deploy-staging
        type: deploy
        properties:
          policies:
            - staging-override    # apply replica/env override
            - staging-target      # deploy to staging namespace

      # Step 2: human approves before production
      - name: approve
        type: suspend

      # Step 3: deploy to production with full replicas
      - name: deploy-production
        type: deploy
        properties:
          policies:
            - production-target   # no override = use base properties
```

```bash
# Apply
kubectl apply -f app-multi-env.yaml

# Check status
vela status taskapp
# STEP           PHASE       AGE
# deploy-staging Succeeded   2m
# approve        Suspending  2m   ← waiting for human approval

# Resume (approve)
vela workflow resume taskapp

# After approval, production deploys
vela status taskapp
# STEP                PHASE      AGE
# deploy-staging      Succeeded  5m
# approve             Succeeded  3m
# deploy-production   Succeeded  1m
```

---

## Override with Trait Changes

You can also override traits in an override policy:

```yaml
policies:
  - name: staging-override
    type: override
    properties:
      components:
        - name: api
          properties:
            replicas: 1
          traits:
            - type: ingress
              properties:
                domain: api.staging.mycompany.com   # different domain in staging
                http:
                  "/": 8080
            - type: scaler
              disable: true                          # disable HPA in staging
```

---

## Image Tag Override Per Environment

A very common use case — different image tags per environment:

```yaml
policies:
  - name: staging-image
    type: override
    properties:
      components:
        - name: api
          properties:
            image: myapi:1.5-rc1      # release candidate in staging

  - name: production-image
    type: override
    properties:
      components:
        - name: api
          properties:
            image: myapi:1.4          # last stable in production (not yet promoted)
```

---

## Replication Policy — Deploy Same Config to Multiple Namespaces

```yaml
policies:
  - name: spread-to-namespaces
    type: topology
    properties:
      clusters: ["local"]
      namespace: ["ns-a", "ns-b", "ns-c"]   # deploy to all three namespaces
```

---

## Checking Policy Status

```bash
# Show which policies are active per environment
vela status taskapp

# Show which namespaces/clusters the app was deployed to
vela status taskapp --tree

# APPLICATION  CLUSTER  NAMESPACE    COMPONENT  RESOURCE
# taskapp      local    staging      api        Deployment/api   Ready:1/1
# taskapp      local    production   api        Deployment/api   Ready:3/3
```

---

## Gotchas

1. **Policies do nothing without a Workflow** — a policy only takes effect when referenced in a `workflow.steps[].properties.policies[]` list. Defining a policy and not using it in a workflow has zero effect.
2. **`override` is a full replace for arrays** — overriding `env` replaces the entire array, not just the changed entry. Repeat all env vars in the override, not just the ones you want to change.
3. **`topology` namespace must exist** — KubeVela does not create the target namespace automatically. Create it before applying.
4. **Multi-cluster requires cluster registration** — before you can use a cluster name in `topology`, you must register it: `vela cluster join <kubeconfig> --name eu-west-1`.

---

## Practice

1. Create an Application with one component. Add a `staging-override` that sets `replicas: 1`. Add a `production-override` that sets `replicas: 5`. Use a workflow to deploy staging first, then production.
2. Add a `topology` policy that deploys to a different namespace than the Application's own namespace. Verify resources appear in the target namespace.
3. Override the image tag per environment using two `override` policies — one for staging (RC tag), one for production (stable tag).
4. Use `vela status --tree` and confirm that the correct number of replicas appear in each namespace.

---

## Key Takeaways

- `override` policy patches component properties per environment — replicas, image, env vars, traits.
- `topology` policy controls *where* to deploy — which cluster, which namespace.
- Policies only activate when referenced in a workflow step's `policies` list.
- Overriding array fields (like `env`) replaces the entire array — include all values, not just the changed ones.
