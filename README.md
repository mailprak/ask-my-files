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

### 4. Set up the `ask` alias

```bash
alias ask="uv run /path/to/ask.py"
# or if using venv: alias ask="python3 /path/to/ask.py"
```

Add to `~/.zshrc` or `~/.bashrc` to make it permanent.

### 5. Ask questions

```bash
ask "Did I pay school fees?"
ask "how do I deploy with KubeVela?"
ask "what was the PR validation workflow?"
```

## Courses — Structured Learning

You can index and query structured learning courses separately from your personal files. Courses live in `courses/<name>/` and get their own isolated ChromaDB collection.

### Available Courses

| Course | Days | Topics |
|---|---|---|
| **golang** | 34 | Variables → Concurrency → HTTP → Generics → Microservices → k3d |

### Index a Course

```bash
uv run injest.py --course golang
# or: python3 injest.py --course golang
```

### Ask Questions from Course Notes

```bash
# Ask anything covered in the course
ask --course golang "how does defer work?"
ask --course golang "what is the difference between value and pointer receivers?"
ask --course golang "show me how to use sync.WaitGroup"
ask --course golang "how do I deploy a Go microservice to k3d?"
ask --course golang "what HTTP status code should I return when a resource is not found?"
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

### Re-index After Adding Notes

Notes in any day file are yours to extend. After editing, just re-run ingest:

```bash
uv run injest.py --course golang
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
