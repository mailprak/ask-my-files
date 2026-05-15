import argparse
import sys
import chromadb

THRESHOLD_COVERED = 0.80   # distance < this → covered ✅
THRESHOLD_MISSING = 1.20   # distance > this → missing ❌  (between → thin ⚠️)

WIDTH = 72

CHECKLISTS = {
    "golang": {
        "Foundations": [
            "variables types zero values",
            "constants iota",
            "functions multiple return values",
            "control flow if else switch",
            "for loops range",
            "slices append copy",
            "maps iteration delete",
            "pointers address dereferencing",
        ],
        "OOP & Interfaces": [
            "structs fields methods",
            "value receivers pointer receivers",
            "interfaces implicit implementation",
            "embedding composition",
            "type assertion type switch",
            "error handling custom errors",
            "defer LIFO order",
            "panic recover",
        ],
        "Concurrency": [
            "goroutines go keyword",
            "channels buffered unbuffered",
            "select statement",
            "sync WaitGroup Mutex",
            "context cancellation timeout",
            "worker pool pattern",
        ],
        "Production": [
            "JSON marshal unmarshal struct tags",
            "HTTP client GET POST",
            "HTTP server handler routes",
            "testing unit tests table-driven",
            "benchmarks performance",
            "generics type parameters constraints",
            "modules go.mod go.sum",
            "reflection",
        ],
        "Deployment": [
            "microservice REST API",
            "middleware logging authentication",
            "k3d kubernetes local cluster",
            "Docker containerisation",
        ],
    },
    "kubernetes": {
        "Architecture": [
            "control plane API server etcd",
            "kubelet kube-proxy worker nodes",
            "kubectl commands context namespace",
        ],
        "Core Workloads": [
            "Pods containers spec",
            "Deployments replicas rolling update",
            "Services ClusterIP NodePort LoadBalancer",
            "Namespaces ResourceQuota LimitRange",
            "ReplicaSets DaemonSets",
            "StatefulSets persistent identity",
            "Jobs CronJobs batch",
        ],
        "Configuration": [
            "ConfigMaps environment variables",
            "Secrets base64 encoding",
            "Labels selectors annotations",
        ],
        "Storage": [
            "PersistentVolumes PersistentVolumeClaims",
            "StorageClasses dynamic provisioning",
            "resource limits requests QoS",
        ],
        "Networking": [
            "network model CNI",
            "liveness readiness startup probes",
            "Ingress NGINX TLS",
            "NetworkPolicy micro-segmentation",
            "CoreDNS service discovery",
        ],
        "Security": [
            "RBAC Roles ClusterRoles bindings",
            "ServiceAccounts tokens",
            "SecurityContext runAsUser capabilities",
            "Pod Security Standards",
            "Vault secrets management",
        ],
        "Operations": [
            "HPA horizontal pod autoscaler",
            "KEDA event-driven autoscaling",
            "Helm charts values templates",
            "Kustomize overlays patches",
            "init containers sidecars",
            "rolling updates zero downtime",
        ],
        "Monitoring": [
            "Prometheus metrics scraping",
            "Grafana dashboards",
            "PromQL queries",
        ],
    },
    "kubevela": {
        "OAM Concepts": [
            "Component Trait Policy Workflow primitives",
            "Application CRD spec",
            "OAM Open Application Model",
        ],
        "Components & Traits": [
            "webservice worker task cron-task daemon",
            "ingress scaler resource sidecar traits",
            "labels annotations built-in traits",
        ],
        "Policies & Workflows": [
            "override policy per-environment config",
            "topology policy cluster namespace targeting",
            "workflow steps deploy suspend notification",
            "approval gates manual step-group",
        ],
        "Multi-cluster": [
            "hub-spoke model cluster registration",
            "cluster selectors targeting",
        ],
        "Custom Definitions": [
            "ComponentDefinition CUE language",
            "TraitDefinition custom traits",
            "Helm wrapping components",
        ],
        "GitOps & Addons": [
            "ApplicationRevision ArgoCD integration",
            "FluxCD Argo Rollouts canary blue-green",
            "Prometheus observability prometheus-scrape",
            "VelaUX dashboard",
        ],
    },
    "crossplane": {
        "Core Concepts": [
            "control plane pattern vs Terraform",
            "providers AWS GCP Azure installation",
            "ProviderConfig credentials IRSA",
        ],
        "Managed Resources": [
            "S3 RDS VPC managed resource spec",
            "forProvider atProvider",
            "deletionPolicy Orphan Delete",
            "cross-resource references",
        ],
        "Compositions": [
            "CompositeResourceDefinition XRD schema",
            "Composition patches transforms",
            "map convert string math transforms",
            "connection details secrets",
        ],
        "Claims & RBAC": [
            "Claims developer self-service",
            "RBAC composite resource permissions",
            "connection secrets app namespace",
        ],
        "Functions & Packages": [
            "Composition Functions function-kcl",
            "Go functions custom logic",
            "Configuration packages OCI images",
            "version distribute packages",
        ],
        "Ecosystem": [
            "provider-kubernetes manage K8s resources",
            "provider-helm Helm releases managed resources",
            "ArgoCD sync waves GitOps",
            "FluxCD dependsOn drift detection",
        ],
    },
}


def classify_distance(d: float) -> tuple[str, str]:
    if d < THRESHOLD_COVERED:
        return ("✅", "covered")
    elif d > THRESHOLD_MISSING:
        return ("❌", "missing")
    else:
        return ("⚠️", "thin")


def print_report(course: str, results: list[tuple[str, str, str, float]]):
    """results: list of (category, topic, status_emoji, distance)"""
    print()
    print("┌" + "─" * WIDTH + "┐")
    title = f"  🔍 Gap Report: {course.upper()}"
    print(f"│{title:<{WIDTH}}│")
    print("├" + "─" * WIDTH + "┤")

    # Group by category
    categories: dict[str, list] = {}
    for cat, topic, emoji, dist in results:
        categories.setdefault(cat, []).append((topic, emoji, dist))

    for cat, items in categories.items():
        cat_line = f"  ▸ {cat}"
        print(f"│{cat_line:<{WIDTH}}│")
        for topic, emoji, dist in items:
            dist_str = f"{dist:.3f}"
            # emoji takes 2 display chars (some terminals vary), pad accordingly
            entry = f"     {emoji}  {topic}"
            dist_display = f"  {dist_str}"
            # fit within WIDTH
            max_topic = WIDTH - len(dist_display) - 2
            if len(entry) > max_topic:
                entry = entry[:max_topic - 1] + "…"
            line = f"{entry}{dist_display:>{WIDTH - len(entry)}} "
            # ensure exactly WIDTH chars
            print(f"│{line:<{WIDTH}}│")
        print("│" + " " * WIDTH + "│")

    # Summary
    covered = sum(1 for _, _, e, _ in results if e == "✅")
    thin = sum(1 for _, _, e, _ in results if e == "⚠️")
    missing = sum(1 for _, _, e, _ in results if e == "❌")
    total = len(results)
    print("├" + "─" * WIDTH + "┤")
    summary = f"  Total: {total}  ✅ {covered} covered  ⚠️  {thin} thin  ❌ {missing} missing"
    print(f"│{summary:<{WIDTH}}│")
    print("└" + "─" * WIDTH + "┘")
    print()


def run_audit(course: str):
    client = chromadb.PersistentClient(path="./chroma_db")

    try:
        collection = client.get_collection(name=f"course_{course}")
    except Exception:
        print(f"❌ Course '{course}' not found.")
        print(f"   Run: uv run injest.py --course {course}")
        sys.exit(1)

    if collection.count() == 0:
        print(f"❌ Course '{course}' is indexed but has no chunks.")
        sys.exit(1)

    checklist = CHECKLISTS.get(course)

    if checklist:
        # Known course — use structured checklist
        results = []
        for category, topics in checklist.items():
            for topic in topics:
                res = collection.query(query_texts=[topic], n_results=1)
                dist = res["distances"][0][0]
                emoji, _ = classify_distance(dist)
                results.append((category, topic, emoji, dist))
        print_report(course, results)
    else:
        # Unknown course — derive topics from source filenames
        print(f"\n  ℹ️  No checklist for '{course}'. Auditing by source files...\n")
        all_data = collection.get(include=["metadatas"])
        sources = sorted(set(
            m.get("source", "unknown") for m in all_data["metadatas"]
        ))
        results = []
        for source in sources:
            res = collection.query(query_texts=[source], n_results=1)
            dist = res["distances"][0][0]
            emoji, _ = classify_distance(dist)
            results.append(("Source Files", source, emoji, dist))
        print_report(course, results)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Audit course notes for topic coverage gaps")
    parser.add_argument("--course", required=True, type=str,
                        help="Course name to audit (e.g., golang, kubernetes)")
    args = parser.parse_args()
    run_audit(args.course)
