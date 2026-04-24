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

### 3. Install uv and sync dependencies

```bash
# macOS
brew install uv

# Or via pip
pip install uv
```

Then install all Python dependencies:

```bash
uv sync
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
```

Add to `~/.zshrc` or `~/.bashrc` to make it permanent.

### 5. Ask questions

```bash
ask "Did I pay school fees?"
ask "how do I deploy with KubeVela?"
ask "what was the PR validation workflow?"
```

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
