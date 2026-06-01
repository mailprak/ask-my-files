# Day 08 — Custom ComponentDefinitions & TraitDefinitions

## Learning Objectives
- Write a custom ComponentDefinition in CUE
- Wrap a Helm chart as a KubeVela component type
- Write a custom TraitDefinition
- Understand the CUE template language basics

---

## Why Custom Definitions?

Built-in types (`webservice`, `worker`) cover most cases. Custom definitions let you:
- Wrap your organisation's standard Deployment pattern as a reusable type
- Wrap a Helm chart so developers deploy it like any other component
- Create traits that enforce company policies (resource quotas, required labels, etc.)
- Abstract away infrastructure-specific details (cloud LBs, PVC storage classes)

---

## CUE — the Template Language

KubeVela definitions use [CUE](https://cuelang.org) to template Kubernetes resources. CUE is a data validation and templating language — it looks like JSON with variables.

```cue
// Basic CUE — a struct
name: string        // type declaration
age:  int & >=0     // constraint: integer >= 0

// Values
name: "Alice"
age:  30

// Computed values
greeting: "Hello, \(name)"   // string interpolation
```

In a ComponentDefinition, CUE templates receive `parameter` (user inputs) and output Kubernetes resource structs.

---

## ComponentDefinition Structure

```yaml
apiVersion: core.oam.dev/v1beta1
kind: ComponentDefinition
metadata:
  name: my-type               # the type name developers use
  namespace: vela-system
  annotations:
    definition.oam.dev/description: "My custom component type"
spec:
  workload:
    definition:
      apiVersion: apps/v1
      kind: Deployment         # what Kubernetes kind this type produces

  schematicDefinition:
    cue:
      template: |              # CUE template — the actual logic
        parameter: {           # inputs the developer provides
          image: string
          port: *8080 | int    # default 8080
          replicas: *1 | int
        }

        output: {              # the primary Kubernetes resource
          apiVersion: "apps/v1"
          kind: "Deployment"
          spec: {
            replicas: parameter.replicas
            template: spec: containers: [{
              image: parameter.image
              ports: [{containerPort: parameter.port}]
            }]
          }
        }
```

---

## Custom webservice with Required Labels

Extend the standard webservice to enforce required labels on every pod:

```yaml
# componentdef-secured-webservice.yaml
apiVersion: core.oam.dev/v1beta1
kind: ComponentDefinition
metadata:
  name: secured-webservice
  namespace: vela-system
  annotations:
    definition.oam.dev/description: "Standard web service with enforced security labels and non-root user"
spec:
  workload:
    definition:
      apiVersion: apps/v1
      kind: Deployment

  schematicDefinition:
    cue:
      template: |
        parameter: {
          image:     string
          port:      *8080 | int
          replicas:  *2 | int
          team:      string        // required — no default
          costCenter: string       // required
          cpu:       *"200m" | string
          memory:    *"256Mi" | string
        }

        output: {
          apiVersion: "apps/v1"
          kind: "Deployment"
          metadata: labels: {
            team:        parameter.team
            cost-center: parameter.costCenter
            managed-by:  "kubevela"
          }
          spec: {
            replicas: parameter.replicas
            selector: matchLabels: app: context.name
            template: {
              metadata: labels: {
                app:         context.name
                team:        parameter.team
                cost-center: parameter.costCenter
              }
              spec: {
                securityContext: {
                  runAsNonRoot: true
                  runAsUser:    10001
                  seccompProfile: type: "RuntimeDefault"
                }
                containers: [{
                  name:  context.name
                  image: parameter.image
                  ports: [{containerPort: parameter.port}]
                  securityContext: {
                    allowPrivilegeEscalation: false
                    readOnlyRootFilesystem: true
                    capabilities: drop: ["ALL"]
                  }
                  resources: {
                    requests: {cpu: parameter.cpu, memory: parameter.memory}
                    limits:   {cpu: parameter.cpu, memory: parameter.memory}
                  }
                }]
              }
            }
          }
        }

        // Expose as a Service (outputs[] for secondary resources)
        outputs: service: {
          apiVersion: "v1"
          kind: "Service"
          spec: {
            selector: app: context.name
            ports: [{port: 80, targetPort: parameter.port}]
          }
        }
```

```bash
kubectl apply -f componentdef-secured-webservice.yaml

# Developers use it like any other type
vela show secured-webservice
```

```yaml
# Developer's Application — clean and simple
components:
  - name: api
    type: secured-webservice    # uses our custom type
    properties:
      image: myapi:1.0
      port: 8080
      team: backend
      costCenter: cc-1234        # required fields enforced at template time
```

---

## Wrap a Helm Chart as a Component Type

This is one of the most powerful patterns — platform team wraps a Helm chart, developers use a simple interface:

```yaml
# componentdef-postgresql.yaml
apiVersion: core.oam.dev/v1beta1
kind: ComponentDefinition
metadata:
  name: postgresql
  namespace: vela-system
  annotations:
    definition.oam.dev/description: "PostgreSQL database via Bitnami Helm chart"
spec:
  workload:
    definition:
      apiVersion: apps/v1
      kind: StatefulSet

  schematicDefinition:
    helm:
      release:
        chart:
          spec:
            chart: postgresql
            version: "13.x.x"
            sourceRef:
              kind: HelmRepository
              name: bitnami
              namespace: vela-system

      # Map user-facing parameters to Helm values
      values:
        auth:
          postgresPassword: parameter.password
          username:         parameter.username
          database:         parameter.database
        primary:
          persistence:
            size: parameter.storageSize

  # The schema developers see
  schematicDefinition:
    cue:
      template: |
        parameter: {
          password:    string
          username:    *"postgres" | string
          database:    *"app" | string
          storageSize: *"10Gi" | string
        }
```

```yaml
# Developer deploys postgres like any other component
components:
  - name: db
    type: postgresql
    properties:
      password: password
      database: taskapp
      storageSize: "20Gi"
```

---

## Custom TraitDefinition

Create a trait that adds a PodDisruptionBudget to any component:

```yaml
# traitdef-pdb.yaml
apiVersion: core.oam.dev/v1beta1
kind: TraitDefinition
metadata:
  name: pod-disruption-budget
  namespace: vela-system
  annotations:
    definition.oam.dev/description: "Add a PodDisruptionBudget to maintain availability during node drains"
spec:
  appliesToWorkloads:
    - deployments.apps         # only applies to Deployment-based components

  schematicDefinition:
    cue:
      template: |
        parameter: {
          minAvailable: *1 | int | string   // int or percentage like "50%"
        }

        // patch modifies the existing component's resource (vs output which creates new)
        patch: {}

        // outputs creates a new resource alongside the component
        outputs: pdb: {
          apiVersion: "policy/v1"
          kind: "PodDisruptionBudget"
          spec: {
            minAvailable: parameter.minAvailable
            selector: matchLabels: context.outputs.workload.spec.selector.matchLabels
          }
        }
```

```bash
kubectl apply -f traitdef-pdb.yaml

vela show pod-disruption-budget
```

```yaml
# Developer attaches the PDB trait
components:
  - name: api
    type: webservice
    properties:
      image: myapi:1.0
      port: 8080
    traits:
      - type: pod-disruption-budget
        properties:
          minAvailable: 1        # always keep at least 1 pod running
```

---

## Patch Trait — Modify the Component's Resource

A trait can also patch the underlying Deployment rather than creating a new resource:

```yaml
# traitdef-node-selector.yaml
apiVersion: core.oam.dev/v1beta1
kind: TraitDefinition
metadata:
  name: node-selector
  namespace: vela-system
spec:
  appliesToWorkloads: ["deployments.apps"]

  schematicDefinition:
    cue:
      template: |
        parameter: {
          nodeType: *"standard" | "gpu" | "high-memory"
        }

        // patch modifies the main Deployment spec
        patch: spec: template: spec: nodeSelector: {
          "node.kubernetes.io/instance-type": parameter.nodeType
        }
```

---

## Test and Validate a Definition

```bash
# List all custom definitions
kubectl get componentdefinition -n vela-system
kubectl get traitdefinition -n vela-system

# Inspect what a definition produces (dry-run)
vela show my-type

# Render what the Application would generate without applying
vela dry-run -f app.yaml

# Debug CUE template
vela debug -f app.yaml

# Check for errors
kubectl describe componentdefinition my-type -n vela-system
```

---

## CUE Quick Reference for Definitions

```cue
// Access component name
context.name

// Access namespace
context.namespace

// Access application name
context.appName

// Access the rendered main resource from outputs
context.outputs.workload

// Conditionals
if parameter.tls != _|_ {     // _|_ = bottom/undefined
    // tls is set
}

// String interpolation
"\(parameter.name)-service"

// Default values
port: *8080 | int

// Optional field
logLevel?: *"info" | string    // ? = optional
```

---

## Gotchas

1. **CUE is strict about types** — `"2"` (string) and `2` (int) are different. If a Kubernetes field expects an int, don't pass a string.
2. **`output` vs `outputs`** — `output` is the primary resource (the Deployment). `outputs` is a map of additional resources (Service, PDB, etc.). Both are generated.
3. **`patch` in traits** — patch merges into the main component resource. Be careful with array fields — CUE patches replace arrays, not append.
4. **Helm-based definitions require FluxCD addon** — Helm chart component types need the `fluxcd` addon enabled: `vela addon enable fluxcd`.

---

## Practice

1. Write a `secured-webservice` ComponentDefinition that enforces `runAsNonRoot: true` on every pod. Deploy it and verify the security context.
2. Write a `pod-disruption-budget` TraitDefinition. Attach it to a webservice and verify the PDB is created with the correct selector.
3. Wrap the Bitnami Redis Helm chart as a `redis` ComponentDefinition. Deploy it from an Application using only `type: redis` with a `password` parameter.
4. Use `vela dry-run -f app.yaml` to preview what Kubernetes resources your custom definition generates before applying.

---

## Key Takeaways

- `ComponentDefinition` + CUE template = reusable, type-safe component abstraction for developers.
- `outputs` in the template creates secondary resources (Service, PDB) alongside the main workload.
- `patch` in a TraitDefinition modifies the existing component resource rather than creating a new one.
- Wrap Helm charts as component types — developers get a clean interface, the platform team controls the Helm values.
