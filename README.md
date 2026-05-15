# ask-my-files

A local semantic search engine for your personal files — notes, PDFs, and scanned images. Powered by ChromaDB for vector search and Ollama for local LLM answers. No cloud, no API keys, no subscriptions.

```
ask "Did I pay school fees?"
```

```
┌────────────────────────────────────────────────────────────────────────┐
│  🔍 Query: Did I pay school fees?                                      │
└────────────────────────────────────────────────────────────────────────┘

  💬 Answer:

  Yes, the Q4 school fees of ₹1500 were paid for 2025-26.

  📂 Sources:
     • SchoolFees-2025-26-Q4.png [School]
     • receipt-2023.pdf [School]
```

## How It Works

Your files are converted to text (via OCR for images, extraction for PDFs), broken into chunks, and stored as **vector embeddings** in a local [ChromaDB](https://www.trychroma.com/) database. When you ask a question:

1. The query is converted into a vector and the closest matching chunks are retrieved
2. The matching chunks are passed as context to a local LLM running via [Ollama](https://ollama.com)
3. Ollama synthesises a direct answer based only on your files

No keyword matching. No cloud. Everything stays on your machine.

| Technology | Role |
|---|---|
| **ChromaDB** | Local vector database — stores and searches embeddings |
| **all-MiniLM-L6-v2** | Sentence embedding model — converts text to vectors (~79MB, auto-downloaded) |
| **Ollama (llama3.2)** | Local LLM — synthesises answers from retrieved chunks |
| **pdfplumber** | Extracts text from PDF files |
| **Tesseract + pytesseract** | OCR — extracts text from images (PNG, JPG, etc.) |
| **Pillow** | Opens image files for OCR processing |

## Supported File Types

- Markdown (`.md`) and plain text (`.txt`)
- PDFs (`.pdf`)
- Scanned images (`.png`, `.jpg`, `.jpeg`, `.tiff`, `.bmp`)
- Any other text-based file

## Requirements

### 1. Install Tesseract (for image OCR)

```bash
# macOS
brew install tesseract

# Linux
sudo apt install tesseract-ocr
```

### 2. Install Ollama (for local LLM answers)

```bash
# macOS
brew install ollama

# Or download from https://ollama.com
```

Pull the model:

```bash
ollama pull llama3.2
```

### 3. Install Python dependencies

**Option A — uv (recommended, faster):**

```bash
# macOS
brew install uv

# Or via pip
pip install uv
```

```bash
uv sync
```

**Option B — plain venv:**

```bash
python3 -m venv venv
source venv/bin/activate        # macOS/Linux
# venv\Scripts\activate         # Windows
pip install -r requirements.txt
```

## Setup

### 1. Configure your folders

A `config.json` is included in the repo. Edit it and replace `<username>` with your actual macOS/Linux username. If it doesn't exist, create it:

```json
{
  "folders": [
    "/Users/<username>/Documents/notes",
    "/Users/<username>/Personal/School"
  ]
}
```

**Example:**
```json
{
  "folders": [
    "/Users/john/Documents/notes",
    "/Users/john/Personal/School",
    "/Users/john/Documents/obsidian-vault"
  ]
}
```

Obsidian vaults work great — `[[links]]` and `#tags` are automatically stripped during indexing. You can add as many folders as you like.

### 2. Index your files

```bash
uv run injest.py
# or if using venv: python3 injest.py
```

```
✅ Indexed: SchoolFees-Q4.png (1 chunk)
✅ Indexed: receipt-2023.pdf (3 chunks)
✅ Indexed: PR Validation Workflow.md (32 chunks)
✅ All folders indexed into persistent memory
```

### 3. Start Ollama

```bash
ollama serve
```

### 4. Ask questions

**Option A — Web UI (recommended)**

```bash
uv run streamlit run app.py
# or with venv: streamlit run app.py
```

Opens at `http://localhost:8501`. Features:
- Collection picker — switch between personal files and any indexed course
- Streaming answers — response appears token by token
- Sources panel — collapsible list of files used for the answer
- Chat history — full conversation per session
- Model switcher — swap between llama3.2, mistral, gemma2

**Option B — CLI**

```bash
ask "Did I pay school fees?"
ask "how do I deploy with KubeVela?"
ask "what was the PR validation workflow?"
```

```bash
alias ask="uv run /path/to/ask.py"
# or if using venv: alias ask="python3 /path/to/ask.py"
```

Add to `~/.zshrc` or `~/.bashrc` to make it permanent.

## Courses — Structured Learning

You can index and query structured learning courses separately from your personal files. Courses live in `courses/<name>/` and get their own isolated ChromaDB collection.

### Available Courses

| Course | Days | Topics |
|---|---|---|
| **golang** | 34 | Variables → Concurrency → HTTP → Generics → Microservices → k3d |
| **kubernetes** | 30 | Architecture → Workloads → Storage → Networking → Security → Helm → Monitoring |
| **kubevela** | 12 | OAM concepts → Components → Traits → Policies → Workflows → Multi-cluster → GitOps |
| **crossplane** | 12 | Control plane pattern → Providers → Managed Resources → XRDs → Compositions → Claims → GitOps |

### Index a Course

```bash
uv run injest.py --course golang
uv run injest.py --course kubernetes
# or: python3 injest.py --course <name>
```

### Ask Questions from Course Notes

```bash
# GoLang course
ask --course golang "how does defer work?"
ask --course golang "what is the difference between value and pointer receivers?"
ask --course golang "show me how to use sync.WaitGroup"
ask --course golang "how do I deploy a Go microservice to k3d?"
ask --course golang "what HTTP status code should I return when a resource is not found?"

# Kubernetes course
ask --course kubernetes "what is the difference between a Role and a ClusterRole?"
ask --course kubernetes "how do I configure a rolling update with zero downtime?"
ask --course kubernetes "show me a NetworkPolicy that blocks all traffic by default"
ask --course kubernetes "how does HPA work with custom metrics?"
ask --course kubernetes "what is the difference between Helm and Kustomize?"

# Crossplane course
ask --course crossplane "what is the difference between an XRD and a Composition?"
ask --course crossplane "how do I write a Composition that maps size: small to an RDS instance class?"
ask --course crossplane "what is deletionPolicy: Orphan and when should I use it?"
ask --course crossplane "how do I use provider-kubernetes to sync a secret between namespaces?"
ask --course crossplane "how do I build and publish a Crossplane Configuration package?"

# KubeVela course
ask --course kubevela "what is the difference between a Component and a Trait?"
ask --course kubevela "how do I add a manual approval gate in a workflow?"
ask --course kubevela "show me how to write a custom ComponentDefinition in CUE"
ask --course kubevela "how do I deploy to multiple clusters with topology policies?"
ask --course kubevela "how does KubeVela integrate with ArgoCD for GitOps?"
```

Example output:
```
┌────────────────────────────────────────────────────────────────────────┐
│  📚 [GOLANG] how does defer work?                                      │
└────────────────────────────────────────────────────────────────────────┘

  💬 Answer:

  defer schedules a function call to run when the surrounding function
  returns — no matter how it returns (normal, error, or panic). Multiple
  defers run in LIFO order. Arguments are evaluated immediately at the
  defer call, not when it executes.

  📂 Sources:
     • day-13-defer-panic-recover.md [golang]
     • day-08-structs-methods.md [golang]
```

### GoLang 34-Day Curriculum

| Days | Topic Area |
|---|---|
| 1–7 | Foundations: variables, types, constants, functions, control flow, slices, maps |
| 8–14 | OOP: structs, pointers, interfaces, embedding, error handling, defer, modules |
| 15–21 | Concurrency: goroutines, channels, select, sync, context, patterns, file I/O |
| 22–30 | Production: JSON, HTTP client/server, testing, benchmarks, generics, reflection |
| 31–34 | Microservice: endpoints, middleware, file database, k3d deployment |

### Crossplane 12-Day Curriculum

| Days | Topic Area |
|---|---|
| 1 | Control plane pattern: why Crossplane, vs Terraform, core building blocks |
| 2 | Install on k3d, crossplane CLI, provider-nop for credential-free practice |
| 3 | Providers: AWS/GCP/Azure installation, ProviderConfig, IRSA/Workload Identity |
| 4 | Managed Resources: S3, RDS, VPC, GCS — forProvider, deletionPolicy, cross-refs |
| 5 | CompositeResourceDefinitions (XRDs): define the platform API with OpenAPI schema |
| 6 | Compositions: patches, transforms (map/convert/string/math), connection details |
| 7 | Claims: developer self-service, RBAC, connection secrets in app namespace |
| 8 | Composition Functions: function-kcl for conditionals, Go functions for custom logic |
| 9 | Packages: build Configuration packages as OCI images, version, distribute |
| 10 | provider-kubernetes + provider-helm: manage K8s resources and Helm releases as MRs |
| 11 | GitOps: ArgoCD sync waves, FluxCD dependsOn, drift detection, GitOps-safe secrets |
| 12 | Capstone: full internal developer platform — one Claim provisions everything |

### KubeVela 12-Day Curriculum

| Days | Topic Area |
|---|---|
| 1 | OAM concepts: Component, Trait, Policy, Workflow — the four primitives |
| 2 | Install on k3d, vela CLI, VelaUX dashboard, first Application |
| 3 | Built-in components: webservice, worker, task, cron-task, daemon |
| 4 | Built-in traits: ingress, scaler, resource, sidecar, labels, annotations |
| 5 | Policies: override (per-env config), topology (cluster/namespace targeting) |
| 6 | Workflow steps: deploy, suspend (approval gates), notification, step-group |
| 7 | Multi-cluster: hub-spoke model, cluster registration, cluster selectors |
| 8 | Custom definitions: ComponentDefinition in CUE, Helm wrapping, TraitDefinition |
| 9 | Addon ecosystem: FluxCD, Argo Rollouts (canary/blue-green), Prometheus, Terraform |
| 10 | GitOps: ApplicationRevision, ArgoCD integration, CI/CD pipeline patterns |
| 11 | Observability: prometheus-scrape trait, VelaUX, Loki, debug commands |
| 12 | Capstone: full multi-tier app with custom definitions, workflow, monitoring |

### Kubernetes 30-Day Curriculum

| Days | Topic Area |
|---|---|
| 1–2 | Architecture & kubectl: control plane, nodes, API server, core commands |
| 3–6 | Core workloads: Pods, Deployments, Services, Namespaces, ResourceQuota |
| 7–8 | Configuration: ConfigMaps, Secrets, Labels, Selectors, Annotations |
| 9–11 | Advanced workloads: ReplicaSets, DaemonSets, StatefulSets, Jobs, CronJobs |
| 12–14 | Storage: PersistentVolumes, PVCs, StorageClasses, resource limits, QoS |
| 15–17 | Networking: network model, health probes, Ingress with NGINX |
| 18–20 | Network policies: micro-segmentation, rolling updates, init containers, sidecars |
| 21–22 | DNS: CoreDNS, service discovery, ExternalDNS, RBAC roles and bindings |
| 23–25 | Security: ServiceAccounts, SecurityContexts, Pod Security Standards, Vault |
| 26–28 | Operations: HPA, KEDA, Helm charts, Kustomize overlays |
| 29–30 | Monitoring: Prometheus, Grafana, PromQL, capstone full-stack deployment |

---

## New Features

### Gap Detector — Audit Course Coverage

Audits your indexed course notes against a built-in topic checklist and shows which areas are well-covered, thin, or missing entirely.

```bash
uv run audit.py --course golang
uv run audit.py --course kubernetes
uv run audit.py --course kubevela
uv run audit.py --course crossplane
```

Example output:

```
┌────────────────────────────────────────────────────────────────────────┐
│  🔍 Gap Report: GOLANG                                                 │
├────────────────────────────────────────────────────────────────────────┤
│  ▸ Foundations                                                         │
│     ✅  variables types zero values                             0.412  │
│     ✅  functions multiple return values                        0.521  │
│     ⚠️   control flow if else switch                             0.934  │
│     ❌  pointers address dereferencing                          1.341  │
│                                                                        │
│  ▸ Concurrency                                                         │
│     ✅  goroutines go keyword                                   0.388  │
│     ✅  channels buffered unbuffered                            0.471  │
│     ⚠️   worker pool pattern                                     1.089  │
│                                                                        │
├────────────────────────────────────────────────────────────────────────┤
│  Total: 30  ✅ 22 covered  ⚠️  5 thin  ❌ 3 missing               │
└────────────────────────────────────────────────────────────────────────┘
```

**Distance thresholds** (ChromaDB cosine distance, 0 = identical, 2 = maximally dissimilar):

| Status | Distance | Meaning |
|---|---|---|
| ✅ Covered | < 0.80 | Strong match in your notes |
| ⚠️ Thin | 0.80 – 1.20 | Mentioned but not deeply covered |
| ❌ Missing | > 1.20 | No relevant content found |

For custom courses without a built-in checklist, the audit falls back to querying by source filename.

---

### Cross-Course Connections — Compare Technologies Side by Side

Queries all indexed course collections simultaneously and synthesises a comparative answer highlighting similarities, differences, and when to prefer each technology.

**CLI:**
```bash
uv run ask.py --cross "how does Crossplane compare to KubeVela for platform engineering?"
uv run ask.py --cross "what are the differences between goroutines and Kubernetes Jobs?"
uv run ask.py --cross "which tool would I use to manage secrets across clusters?"
```

Example output:
```
┌────────────────────────────────────────────────────────────────────────┐
│  🔀 Cross-Course: how does Crossplane compare to KubeVela?             │
└────────────────────────────────────────────────────────────────────────┘

  💬 Answer:

  CROSSPLANE: Focuses on provisioning and managing cloud infrastructure
  as Kubernetes resources. Uses XRDs and Compositions to build a
  platform API. Best when you need infrastructure-as-code with K8s.

  KUBEVELA: Focuses on application delivery using the OAM model.
  Defines Components, Traits, and Workflows. Best when you need
  multi-cluster app deployment with approval workflows.

  📂 Sources by course:
     [CROSSPLANE]
       • day-05-xrds.md [crossplane]
     [KUBEVELA]
       • day-01-oam-concepts.md [kubevela]
```

`--cross` and `--course` are mutually exclusive.

**Web UI:** Select **🔀 Cross-Course** from the collection dropdown (appears when 2+ courses are indexed).

---

### Teach Me Mode — Generate a Quiz from Course Notes

Generates a 5-question quiz from your indexed course notes. Optionally filter by day to focus on a specific topic.

**CLI:**
```bash
# Full-course quiz
uv run ask.py --course golang --quiz

# Day-specific quiz
uv run ask.py --course golang --quiz day-13
uv run ask.py --course kubernetes --quiz day-21
```

Example output:
```
┌────────────────────────────────────────────────────────────────────────┐
│  🎓 [GOLANG] Quiz — day-13                                             │
└────────────────────────────────────────────────────────────────────────┘

  Q1: What does the defer keyword do in Go?
      defer schedules a function call to run when the surrounding
      function returns. Multiple defers run in LIFO order.

  Q2: When would you use recover()?
      recover() stops a panic and returns the panic value. It must
      be called inside a deferred function to have any effect.

  Q3: What is the difference between panic and os.Exit?
      panic unwinds the stack and runs deferred functions. os.Exit
      terminates immediately without running defers.

  Q4: Can you defer a method call?
      Yes. defer works with any function or method call, including
      method calls on struct values.

  Q5: What happens if defer arguments reference a variable that
      changes after the defer statement?
      Arguments are evaluated immediately at the defer call site,
      not when the deferred function executes.
```

**Web UI:** Select a course, then use the **Teach Me** panel in the sidebar. Enter an optional day filter and click **🎓 Quiz Me**.

---

### Re-index After Adding Notes

Notes in any day file are yours to extend. After editing, just re-run ingest:

```bash
uv run injest.py --course golang
uv run injest.py --course kubernetes
```

### Add Your Own Course

You can create a course on any topic using the same structure as the GoLang course.

**Step 1 — Create the course folder**

```bash
mkdir -p courses/rust
```

**Step 2 — Name your files consistently**

Use the `day-NN-topic-name.md` convention so files sort correctly:

```
courses/rust/
├── day-01-hello-world-cargo.md
├── day-02-variables-mutability.md
├── day-03-ownership.md
...
```

**Step 3 — Use this template for each day's file**

```markdown
# Day NN — Topic Title

## Learning Objectives
- What you will be able to do after this day
- Keep to 3–5 bullet points

---

## Core Concept

Explain the concept in plain English first, then show code.

```go  ← replace with the language
// A working, runnable example
func example() {
    // ...
}
```

## Sub-topic

More concepts, more examples. Break each idea into its own section.

---

## Gotchas

1. **Common mistake** — explain why it trips people up and how to avoid it.
2. **Another pitfall** — with a before/after code comparison if helpful.

---

## Practice

1. Exercise that reinforces the first concept.
2. Exercise that combines today's topic with a previous day.
3. A stretch exercise for deeper understanding.

---

## Key Takeaways

- The 3–5 things to remember from today, in one line each.
```

**Step 4 — Index the course**

```bash
uv run injest.py --course rust
```

**Step 5 — Start asking**

```bash
ask --course rust "what is ownership?"
ask --course rust "how does the borrow checker work?"
```

**Tips for good course notes:**
- Keep each day focused on **one theme** — don't cram too many topics into a single file
- Always include **runnable code examples** — the LLM retrieves these verbatim when you ask for examples
- Write **Gotchas** — these are the highest-value sections when you're debugging real code
- Add your own notes as you learn — the more personal context, the better the answers

---

## Managing the Index

**Wipe and rebuild:**
```bash
rm -rf ./chroma_db && uv run injest.py
```

**Check docs indexed from a specific folder:**
```python
python3 -c "
import chromadb
client = chromadb.PersistentClient(path='./chroma_db')
col = client.get_collection('engineering_memory')
results = col.get(where={'folder': 'School'})
print(len(results['ids']), 'docs indexed from School')
"
```

**Remove a specific file from the index:**
```python
python3 -c "
import chromadb
client = chromadb.PersistentClient(path='./chroma_db')
col = client.get_collection('engineering_memory')
results = col.get(where={'source': 'filename.pdf'})
col.delete(ids=results['ids'])
print('Deleted', len(results['ids']), 'chunks')
"
```

## Notes

- The first run downloads the `all-MiniLM-L6-v2` embedding model (~79MB) to `~/.cache/chroma/`. This is a one-time download.
- Re-running `injest.py` is safe — hash-based IDs prevent duplicates.
- Ollama answers are grounded in your files only — if the answer isn't in your indexed documents, it will say so.
