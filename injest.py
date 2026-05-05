import os
import json
import hashlib
import argparse
import chromadb
import re
import pdfplumber
from PIL import Image
import pytesseract

parser = argparse.ArgumentParser(description="Index files into ChromaDB")
parser.add_argument("--course", type=str, help="Index a course (e.g., --course golang)")
args = parser.parse_args()

client = chromadb.PersistentClient(path="./chroma_db")

if args.course:
    course_path = os.path.join(".", "courses", args.course)
    if not os.path.exists(course_path):
        print(f"❌ Course folder not found: {course_path}")
        exit(1)
    folders = [course_path]
    collection_name = f"course_{args.course}"
    print(f"📚 Indexing course '{args.course}' from {course_path}")
else:
    with open("config.json") as f:
        config = json.load(f)
    folders = config.get("folders", [])
    collection_name = "engineering_memory"
    if not folders:
        print("❌ No folders configured")
        exit(1)

collection = client.get_or_create_collection(name=collection_name)


def clean_text(text):
    text = re.sub(r"\[\[.*?\]\]", "", text)  # remove Obsidian links
    text = re.sub(r"#\w+", "", text)         # remove tags
    return text


def make_id(path, chunk):
    return hashlib.md5(f"{path}::{chunk}".encode()).hexdigest()


indexed_ids = set()
successfully_indexed = 0

for base_path in folders:
    if not os.path.exists(base_path):
        print(f"⚠️ Skipping missing folder: {base_path}")
        continue

    for root, _, files in os.walk(base_path):
        for file in files:
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
                    content = clean_text(content)
                    if content.strip():
                        chunk_id = make_id(full_path, content)
                        collection.upsert(
                            documents=[content],
                            metadatas=[{
                                "source": file,
                                "path": full_path,
                                "folder": os.path.basename(base_path)
                            }],
                            ids=[chunk_id]
                        )
                        indexed_ids.add(chunk_id)
                        successfully_indexed += 1
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
                        chunk_id = make_id(full_path, chunk)
                        collection.upsert(
                            documents=[chunk],
                            metadatas=[{
                                "source": file,
                                "path": full_path,
                                "folder": os.path.basename(base_path)
                            }],
                            ids=[chunk_id]
                        )
                        indexed_ids.add(chunk_id)
                        indexed += 1

                successfully_indexed += indexed
                if indexed:
                    print(f"✅ Indexed: {file} ({indexed} chunks)")

            except Exception as e:
                print(f"⚠️ Error reading {full_path}: {e}")
                existing = collection.get(where={"path": full_path})
                indexed_ids.update(existing["ids"])

if args.course:
    print(f"✅ Course '{args.course}' indexed into collection '{collection_name}'")
else:
    print("✅ All folders indexed into persistent memory")

if successfully_indexed > 0:
    all_stored = collection.get()
    orphan_ids = set(all_stored["ids"]) - indexed_ids
    if orphan_ids:
        collection.delete(ids=list(orphan_ids))
        print(f"🗑️  Pruned {len(orphan_ids)} stale chunk(s) from deleted or shortened files")
    else:
        print("✅ No stale chunks found")
