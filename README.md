# ask-my-files

A local semantic search engine for your personal files — notes, PDFs, and scanned images. No cloud, no API keys, no subscriptions.

```
ask "Did I pay school fees?"
```

```
┌────────────────────────────────────────────────────────────────────────┐
│  🔍 Query: Did I pay school fees?                                      │
└────────────────────────────────────────────────────────────────────────┘

  ┌─ Result 1 ──────────────────────────────────────────────────────────┐
  │  📄 SchoolFees-2025-26-Q4.png  [School]
  │  📁 /Users/john/Personal/School/SchoolFees-2025-26-Q4.png
  ├─────────────────────────────────────────────────────────────────────┤
  │  FEE RECEIPT [2025-26]
  │  Student: John  Amount: ₹12,500  Status: PAID
  └─────────────────────────────────────────────────────────────────────┘
```

## Supported File Types

- Markdown (`.md`) and plain text (`.txt`)
- PDFs (`.pdf`)
- Scanned images (`.png`, `.jpg`, `.jpeg`, `.tiff`, `.bmp`)
- Any other text-based file

## Requirements

### System dependency (for image OCR)

```bash
# macOS
brew install tesseract

# Linux
sudo apt install tesseract-ocr
```

### Python dependencies

```bash
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

Obsidian vaults work great — Obsidian `[[links]]` and `#tags` are automatically stripped during indexing.

You can add as many folders as you like.

### 2. Index your files

```bash
python3 injest.py
```

### 3. Set up the `ask` alias

```bash
alias ask="python3 /path/to/ask.py"
```

Add to `~/.zshrc` or `~/.bashrc` to make it permanent.

### 4. Ask questions

```bash
ask "Did I pay school fees?"
ask "how do I deploy with KubeVela?"
ask "what was the PR validation workflow?"
```

## Managing the Index

**Wipe and rebuild:**
```bash
rm -rf ./chroma_db && python3 injest.py
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
- ChromaDB always returns the top 3 results even if none are relevant. If results look unrelated, the answer likely isn't in your indexed files.
