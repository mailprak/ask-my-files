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
| **Pillow** | Opens image files for OCR processing — and draws the animated GIF storyboards frame by frame |
| **say / espeak-ng / piper** | Offline text-to-speech — narrates a storyboard to a WAV that matches the GIF |

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

`.venv/` is built for one platform. If the same folder is also used from a Linux container,
rebuild it before running on the other side: `rm -rf .venv && uv sync`.

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
- 🎬 Visual Explanation — turn any answer into an animated storyboard GIF ([details](#-visual-explanation--animated-storyboards-from-any-answer))

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

### 🎬 Visual Explanation — Animated Storyboards from Any Answer

Turns a retrieved answer into a short animated GIF of the data flow: actors as labelled
stations across the stage, requests travelling between them on routed arrows, processing
states, and success or failure badges. Useful for anything with moving parts — a SCIM
provisioning round trip, Pod scheduling, a goroutine sending on a channel, a Crossplane
claim reconciling.

Nothing about it is topic-specific: it works on every collection, personal files included.

**How it works**

```text
Notes → ChromaDB → RAG → Ollama
                           ↓
                 ┌─────────┴─────────┐
                 ↓                   ↓
           Text answer        Storyboard JSON   ← second LLM pass, structured output
                                     ↓
                                  Pillow        ← deterministic frame-by-frame drawing
                                     ↓
                               Animated GIF
```

The LLM never draws anything. It emits a small JSON document — actors and scenes — and
`animate.py` renders it with Pillow. That split is deliberate: the same storyboard always
produces the same frames, the renderer needs no network, and a malformed model response
fails with a readable message instead of a broken picture.

**Storyboard schema**

```json
{
  "title": "SCIM user provisioning",
  "actors": [
    {"id": "idp",    "label": "Identity Provider", "kind": "person"},
    {"id": "scim",   "label": "SCIM Connect",      "kind": "service"},
    {"id": "target", "label": "Target App",        "kind": "cloud"}
  ],
  "scenes": [
    {"kind": "message", "from": "idp", "to": "scim", "label": "POST /Users",
     "detail": "The source IdP sends a SCIM user resource."},
    {"kind": "process", "at": "scim", "label": "Map attributes",
     "detail": "Attributes are mapped onto the target schema."},
    {"kind": "message", "from": "scim", "to": "target", "label": "POST /Users"},
    {"kind": "message", "from": "target", "to": "scim", "label": "201 Created",
     "status": "success"},
    {"kind": "result", "at": "target", "label": "User provisioned", "status": "success",
     "detail": "The account now exists downstream."}
  ]
}
```

| Field | Values |
|---|---|
| `actors[].kind` | `person`, `client`, `service`, `store`, `queue`, `cloud` — each drawn as a vector icon |
| `scenes[].kind` | `message` (A → B), `process` (work at one actor), `result` (outcome badge) |
| `scenes[].status` | `success` (green), `failure` (red), `info` (blue) |
| `scenes[].label` | Short chip drawn on the arrow — an HTTP call, a verb phrase |
| `scenes[].detail` | One sentence, drawn in the caption band, and the line spoken by narration |

Forward messages route above the row and responses below, so arrows never cross a station.

Caps: 5 actors, 8 scenes. Anything beyond is trimmed. Messy model output — wrong enum
values, ids referenced by label, `nodes`/`steps` instead of `actors`/`scenes` — is
repaired automatically; scenes pointing at actors that don't exist are dropped rather
than drawn wrong. If the first response is unusable the model gets one repair round.

**Web UI:** ask a question, then click **🎬 Visual Explanation** under the answer. The GIF
plays inline and is written to `out/<question-slug>-<timestamp>.gif` in the project root —
the path is shown under the animation. It is also cached on that message, so switching
collections or asking again won't rebuild it. **⬇️ Save GIF** downloads a copy through the
browser, **🔁 Regenerate** rerolls (keeping the earlier file), and **🧩 Storyboard JSON**
shows the data the drawing came from. Toggle the whole feature off in the sidebar under
**Visuals**, where there's also an animation speed slider.

**CLI:**

```bash
uv run ask.py --course kubernetes --visual "what happens when I create a Pod?"
uv run ask.py --course golang --visual --out out/channels.gif "how do goroutines use channels?"
uv run ask.py --cross --visual "how does a Crossplane claim become real infrastructure?"
```

The GIF lands in `out/<query>.gif` unless `--out` says otherwise, and `--speed 1.5` plays
it faster. `--visual` has no effect with `--quiz` — a quiz has no flow to animate.

### 🔊 Narration

GIF has no audio track — the format cannot carry sound. So there are two outputs, chosen
with the **Output** switch in the sidebar or `--mp4` on the CLI:

| Output | What you get |
|---|---|
| **GIF** | Silent animation, plus a `.wav` of the same length beside it. Autoplays inline anywhere — chat, wikis, README files |
| **MP4** | **One file** with the narration inside it. Full colour (no 256-entry palette), usually smaller, and it seeks and scrubs. Needs a player |

MP4 is encoded by **PyAV** (`uv sync` installs it), which loads FFmpeg as a library
in-process. That matters on a managed Mac: there is no downloaded executable for Gatekeeper
to block, which is what happens to pip-bundled ffmpeg binaries. A system `ffmpeg` is used
instead when one is present and actually runnable. The five-scene demo comes out around
110 KB silent, 455 KB narrated.

Speech is synthesised offline by whatever TTS engine is already on the machine; nothing is
downloaded and nothing leaves it.

| Platform | Engine | Install |
|---|---|---|
| macOS | `say` | already there |
| Linux | `espeak-ng` | `sudo apt install espeak-ng` |
| either | `piper` | set `PIPER_MODEL`, or drop a `.onnx` in `./voices/` |
| either | `flite` | `sudo apt install flite` |

**Voice.** On macOS the default is **Daniel**, falling back to the system voice when it is
not installed. Better ones are a free download — System Settings → Accessibility → Spoken
Content → System Voice → Manage Voices adds the Premium voices (**Ava**, **Zoe**, **Evan**)
and Enhanced versions of the built-ins, including Daniel — then pick one in the sidebar or
with `--voice`. On Linux, `piper` is the quality option: drop a `.onnx` model into
`./voices/` or point `PIPER_MODEL` at one.

```bash
uv run narrate.py --voices        # what this machine can speak with
```

**Captions are rewritten for the ear.** The on-screen text is untouched, but the spoken
copy gets fixed up first, because TTS engines mangle technical prose:

| Written | Spoken |
|---|---|
| `POST /Users` | "POST Users" — not "post slash users" |
| `201 Created` | "two oh one Created" — not "two hundred and one" |
| `userName`, `externalId` | "user Name", "external Id" |
| `SCIM`, `etcd`, `kubectl` | "skim", "et see dee", "cube control" |
| `SCIM Connect — user provisioning` | "skim Connect, user provisioning" |

Lines are then joined with positional connectives — *First… Then… Next… After that…
Finally…* — and topped and tailed with an intro and a closing line, so it plays as a
narration rather than a list of captions read aloud. Nothing here needs an LLM.

**Optional rewrite pass.** Tick **✍️ Rewrite captions for speech** (or `--rewrite`) to
spend one more LLM call turning the captions into spoken prose before the connectives are
applied. Better phrasing, but non-deterministic — a wrong-shaped answer is discarded and
the captions are used instead. The final script is shown under **📝 Narration script**.

**Timing.** The narration is generated *first*, and each spoken line's length sets a
minimum duration for its beat; the animation then holds that beat long enough to cover it.
So the GIF and the WAV come out the same length to the millisecond and loop together
instead of drifting apart. A narrated GIF therefore runs slower than a silent one, and the
speed slider is ignored while narrating — real time is what keeps them in step. Dead air
at the ends of each clip is trimmed so the pacing stays tight.

**Web UI:** turn on **🔊 Narrate** in the sidebar before clicking 🎬, then choose a voice
and speed. With **GIF** you get an audio player under the animation and a `.wav` beside the
GIF in `out/`; with **MP4** you get a single video with the sound already in it. The toggle
is disabled with a note when no engine is installed.

**CLI:**

```bash
uv run ask.py --course kubernetes --visual --narrate --mp4 "what happens when I create a Pod?"
uv run ask.py --course golang --visual --narrate --voice Ava --rate 150 "how do channels work?"
uv run ask.py --course kubevela --visual --narrate --rewrite "how does a workflow run?"

uv run narrate.py --demo out/demo.wav           # narrate the built-in board, no LLM
uv run narrate.py --demo --print                # see the script without synthesising
uv run animate.py --demo out/demo.mp4           # silent video
uv run animate.py --demo out/demo.mp4 --audio out/demo.wav   # video with sound
```

`--tts` picks the engine, `--voice` the voice within it, `--rate` the words per minute
(default 160). If synthesis fails, the animation is still produced — silently, with the
reason reported.

---

**Render without an LLM.** `animate.py` is a standalone renderer, handy for tuning the
look or checking the pipeline while Ollama is off:

```bash
uv run animate.py --demo out/demo.gif                 # built-in SCIM storyboard
uv run animate.py --json board.json out/board.gif     # your own storyboard JSON
uv run animate.py --demo out/demo.gif --png out/f.png # + one still per scene
uv run animate.py --demo out/demo.webp                # WebP: full colour, no 256-colour cap
```

Editing the storyboard JSON by hand and re-rendering is the reliable way to get a polished
result — the model gets you 90% there, and one edited label or reordered scene finishes it.

**A note on size.** Frames are drawn at 2× and downsampled for antialiasing, then encoded
with one palette shared across the whole animation and inter-frame deltas, which keeps the
five-scene demo near 160 KB. Pass a `.webp` path for a full-colour version.

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
