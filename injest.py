import os
import json
import hashlib
import chromadb
import re
import pdfplumber
from PIL import Image
import pytesseract

# Load config
with open("config.json") as f:
    config = json.load(f)

folders = config.get("folders", [])

if not folders:
    print("❌ No folders configured")
    exit(1)

# ✅ Persistent DB
client = chromadb.PersistentClient(path="./chroma_db")

collection = client.get_or_create_collection(name="engineering_memory")

def clean_text(text):
    text = re.sub(r"\[\[.*?\]\]", "", text)  # remove Obsidian links
    text = re.sub(r"#\w+", "", text)        # remove tags
    return text

def make_id(path, chunk):
    return hashlib.md5(f"{path}::{chunk}".encode()).hexdigest()

for base_path in folders:
    if not os.path.exists(base_path):
        print(f"⚠️ Skipping missing folder: {base_path}")
        continue

    for root, _, files in os.walk(base_path):
        for file in files:
            # Skip hidden and system files
            if file.startswith("."):
                continue

            full_path = os.path.join(root, file)
            ext = file.lower().rsplit(".", 1)[-1] if "." in file else ""

            try:
                if ext == "pdf":
                    content = ""
                    with pdfplumber.open(full_path) as pdf:
                        for page in pdf.pages:
                            content += (page.extract_text() or "") + "\n\n"
                elif ext in ("png", "jpg", "jpeg", "tiff", "bmp"):
                    content = pytesseract.image_to_string(Image.open(full_path))
                    # Store image OCR as a single chunk (no paragraph splitting)
                    content = clean_text(content)
                    if content.strip():
                        collection.upsert(
                            documents=[content],
                            metadatas=[{
                                "source": file,
                                "path": full_path,
                                "folder": os.path.basename(base_path)
                            }],
                            ids=[make_id(full_path, content)]
                        )
                        print(f"✅ Indexed: {file} (1 chunk)")
                    continue
                else:
                    with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()

                content = clean_text(content)
                chunks = content.split("\n\n")
                indexed = 0

                for chunk in chunks:
                    if chunk.strip():
                        collection.upsert(
                            documents=[chunk],
                            metadatas=[{
                                "source": file,
                                "path": full_path,
                                "folder": os.path.basename(base_path)
                            }],
                            ids=[make_id(full_path, chunk)]
                        )
                        indexed += 1

                if indexed:
                    print(f"✅ Indexed: {file} ({indexed} chunks)")

            except Exception as e:
                print(f"⚠️ Error reading {full_path}: {e}")

print("✅ All folders indexed into persistent memory")
