import chromadb
import sys
import argparse
import ollama

client = chromadb.PersistentClient(path="./chroma_db")

parser = argparse.ArgumentParser(description="Ask questions about your files or a course")
parser.add_argument("--course", type=str, help="Query a specific course (e.g., --course golang)")
parser.add_argument("query", nargs="+", help="Your question")
args = parser.parse_args()

query = " ".join(args.query)

if args.course:
    collection_name = f"course_{args.course}"
    try:
        collection = client.get_collection(name=collection_name)
    except Exception:
        print(f"❌ Course '{args.course}' not found.")
        print(f"   Run: python injest.py --course {args.course}")
        sys.exit(1)
    system_prompt = (
        f"You are a {args.course.upper()} programming tutor. "
        "Answer the question using only the learning notes provided below. "
        "Include code examples from the notes where relevant."
    )
    not_found_msg = "I could not find this in your course notes."
else:
    collection = client.get_collection(name="engineering_memory")
    system_prompt = (
        "You are a helpful assistant. "
        "Answer the question using only the context provided below."
    )
    not_found_msg = "I could not find this in your files."

results = collection.query(
    query_texts=[query],
    n_results=5
)

WIDTH = 72

chunks = results["documents"][0]
metas = results["metadatas"][0]

context = "\n\n".join(
    f"[{meta['source']}]\n{doc}"
    for doc, meta in zip(chunks, metas)
)

prompt = f"""{system_prompt}
If the answer is not in the context, say "{not_found_msg}"

Context:
{context}

Question: {query}
Answer:"""

print()
print("┌" + "─" * WIDTH + "┐")
if args.course:
    label = f"📚 [{args.course.upper()}] "
    truncated = query[:WIDTH - len(label) - 2]
    print(f"│  {label}{truncated:<{WIDTH - len(label) - 2}}│")
else:
    truncated = query[:WIDTH - 12]
    print(f"│  🔍 Query: {truncated:<{WIDTH - 12}}│")
print("└" + "─" * WIDTH + "┘")

print("\n  💬 Answer:\n")
response = ollama.chat(
    model="llama3.2",
    messages=[{"role": "user", "content": prompt}]
)
answer = response["message"]["content"].strip()
for line in answer.splitlines():
    while len(line) > WIDTH - 4:
        print(f"  {line[:WIDTH - 4]}")
        line = line[WIDTH - 4:]
    print(f"  {line}")

print()
print("  📂 Sources:")
for meta in metas:
    label = meta.get("folder", "")
    print(f"     • {meta['source']} [{label}]")
print()
