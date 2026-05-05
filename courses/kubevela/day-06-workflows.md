# Day 06 — Workflow Steps

## Learning Objectives
- Write multi-step deployment workflows
- Use suspend for manual approval gates
- Send notifications on success or failure
- Handle workflow failures and resumptions
- Run canary deployments via workflow

---

## What Is a Workflow?

A workflow defines the ordered sequence of steps executed when an Application is created or updated. Without a workflow, KubeVela deploys all components simultaneously.

```yaml
workflow:
  steps:
    - name: step-one
      type: deploy
      ...
    - name: step-two
      type: suspend        # waits here until manually approved
    - name: step-three
      type: deploy
      ...
```

If any step fails, the workflow stops. Subsequent steps do not run.

---

## Built-in Step Types

| Step Type | Purpose |
|---|---|
| `deploy` | Deploy components to target cluster/namespace |
| `suspend` | Pause and wait for human approval |
| `notification` | Send message to Slack, DingTalk, webhook |
| `apply-object` | Apply raw Kubernetes resource |
| `apply-terraform-config` | Provision cloud resources via Terraform |
| `share-cloud-resource` | Share a cloud resource between applications |
| `create-config` | Create a KubeVela config secret |
| `export-data` | Export data between steps |
| `step-group` | Run multiple steps in parallel |

---

## deploy Step

```yaml
workflow:
  steps:
    - name: deploy-to-staging
      type: deploy
      properties:
        policies:
          - staging-override    # which override policies to apply
          - staging-target      # which topology policy (namespace/cluster)

        # Parallel deploy to multiple targets
        # parallelism: 2        # deploy to N targets at a time (default: all)
```

---

## suspend Step — Manual Approval Gate

```yaml
workflow:
  steps:
    - name: deploy-staging
      type: deploy
      properties:
        policies: ["staging-target"]

    - name: wait-for-approval    # workflow pauses here
      type: suspend
      timeout: 24h               # auto-fail if not approved within 24 hours
                                 # omit for no timeout

    - name: deploy-production
      type: deploy
      properties:
        policies: ["production-target"]
```

```bash
# Check suspended workflows
vela workflow list
# APP       WORKFLOW     PHASE        AGE
# taskapp   taskapp      Suspending   5m

# Approve (resume the workflow)
vela workflow resume taskapp

# Reject (terminate the workflow without production deploy)
vela workflow terminate taskapp
```

---

## notification Step — Slack / Webhook

```yaml
workflow:
  steps:
    - name: deploy-production
      type: deploy
      properties:
        policies: ["production-target"]

    - name: notify-slack
      type: notification
      properties:
        slack:
          url:
            value: "https://hooks.slack.com/services/T00/B00/xxxx"
          message:
            text: |
              ✅ *{{ context.appName }}* deployed to production.
              Version: {{ context.appRevision }}
              Triggered by: {{ context.name }}
```

```yaml
# Send on failure using if condition
workflow:
  steps:
    - name: deploy-production
      type: deploy
      properties:
        policies: ["production-target"]

    - name: notify-on-failure
      type: notification
      if: status.deploy-production.failed    # only runs if previous step failed
      properties:
        slack:
          url:
            value: "https://hooks.slack.com/services/T00/B00/xxxx"
          message:
            text: "❌ *{{ context.appName }}* production deployment FAILED."
```

---

## Full Multi-Stage Workflow

```yaml
# app-full-workflow.yaml
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
        image: myapi:2.0
        port: 8080
        replicas: 3

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
      # Step 1: deploy to staging
      - name: deploy-staging
        type: deploy
        properties:
          policies: ["staging-override", "staging-target"]

      # Step 2: notify team that staging is ready for review
      - name: notify-staging-ready
        type: notification
        properties:
          slack:
            url:
              value: "https://hooks.slack.com/services/T00/B00/xxxx"
            message:
              text: "🚀 taskapp staging is ready. Review at https://api.staging.mycompany.com"

      # Step 3: manual approval gate
      - name: approve-production
        type: suspend
        timeout: 48h

      # Step 4: deploy to production
      - name: deploy-production
        type: deploy
        properties:
          policies: ["production-target"]

      # Step 5: notify success
      - name: notify-success
        type: notification
        properties:
          slack:
            url:
              value: "https://hooks.slack.com/services/T00/B00/xxxx"
            message:
              text: "✅ taskapp v2.0 deployed to production."

      # Step 6: notify failure (conditional)
      - name: notify-failure
        type: notification
        if: status.deploy-production.failed
        properties:
          slack:
            url:
              value: "https://hooks.slack.com/services/T00/B00/xxxx"
            message:
              text: "❌ taskapp production deploy FAILED — check VelaUX."
```

---

## step-group — Parallel Steps

Deploy to multiple regions simultaneously:

```yaml
workflow:
  steps:
    - name: deploy-staging
      type: deploy
      properties:
        policies: ["staging-target"]

    - name: approve
      type: suspend

    # Deploy to eu and us simultaneously
    - name: deploy-all-regions
      type: step-group
      subSteps:
        - name: deploy-eu
          type: deploy
          properties:
            policies: ["eu-target"]

        - name: deploy-us
          type: deploy
          properties:
            policies: ["us-target"]

    - name: notify-done
      type: notification
      properties:
        slack:
          url:
            value: "https://hooks.slack.com/services/T00/B00/xxxx"
          message:
            text: "Deployed to all regions."
```

---

## apply-object Step — Apply Raw Kubernetes Resource

Use when you need to create a resource KubeVela doesn't have a built-in abstraction for:

```yaml
workflow:
  steps:
    - name: create-namespace
      type: apply-object
      properties:
        value:
          apiVersion: v1
          kind: Namespace
          metadata:
            name: taskapp-production

    - name: deploy-app
      type: deploy
      properties:
        policies: ["production-target"]
```

---

## Workflow Commands

```bash
# List workflow status for all apps
vela workflow list

# Show detailed workflow steps
vela status taskapp

# Resume a suspended workflow (approve)
vela workflow resume taskapp

# Restart the workflow from the beginning
vela workflow restart taskapp

# Stop/terminate a workflow (no further steps)
vela workflow terminate taskapp

# Roll back to the previous ApplicationRevision
vela workflow rollback taskapp
```

---

## Workflow Context Variables

Use context variables in notification messages:

```
{{ context.appName }}          # Application name
{{ context.appRevision }}      # Current revision number
{{ context.namespace }}        # Application namespace
{{ context.name }}             # Workflow step name
{{ status.<step-name>.phase }} # Phase of a named step
{{ status.<step-name>.failed }}# Boolean: true if step failed
```

---

## Gotchas

1. **Workflow runs on every update** — every `kubectl apply` re-runs the workflow from the beginning. If you're in a `suspend` state, the update resets it. Use `--dry-run=server` to preview.
2. **`suspend` timeout** — if `timeout` is set and the workflow is not resumed, it auto-terminates. The Application remains deployed at the last successful step.
3. **`step-group` failure** — if one sub-step fails, the group fails and remaining sub-steps are cancelled.
4. **Notification secrets** — store Slack webhook URLs in Kubernetes Secrets and reference them instead of hardcoding: `url: { secretRef: { name: slack-secret, key: webhook } }`.

---

## Practice

1. Create a workflow with `deploy-staging` → `suspend` → `deploy-production`. Apply the Application, approve staging, then resume and watch production deploy.
2. Add a Slack notification after the production deploy step. Verify the message appears in your channel.
3. Add a conditional `notify-failure` step. Break the production deploy (bad image) and verify the failure notification fires.
4. Use `step-group` to deploy to two namespaces simultaneously. Verify both receive the Application components at the same time.

---

## Key Takeaways

- Workflows define the ordered deployment sequence — without one, all components deploy at once.
- `suspend` creates a human approval gate. `vela workflow resume` approves it, `terminate` rejects it.
- `notification` sends messages to Slack or webhooks — use `if: status.<step>.failed` for conditional alerts.
- `step-group` runs sub-steps in parallel — ideal for simultaneous multi-region or multi-namespace deployments.
