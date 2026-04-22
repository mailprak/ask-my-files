import chromadb
import sys
import ollama

# Same DB path as ingestion
client = chromadb.PersistentClient(path="./chroma_db")

collection = client.get_collection(name="engineering_memory")

query = " ".join(sys.argv[1:])

if not query:
    print("❌ Please provide a question")
    print('Example: ask "why is my pod restarting?"')
    sys.exit(1)

results = collection.query(
    query_texts=[query],
    n_results=3
)

WIDTH = 72

# Build context from retrieved chunks
chunks = results["documents"][0]
metas = results["metadatas"][0]

context = "\n\n".join(
    f"[{meta['source']}]\n{doc}"
    for doc, meta in zip(chunks, metas)
)

# Ask Ollama to answer based on context
prompt = f"""You are a helpful assistant. Answer the question using only the context provided below.
If the answer is not in the context, say "I could not find this in your files."

Context:
{context}

Question: {query}
Answer:"""

print()
print("┌" + "─" * WIDTH + "┐")
print(f"│  🔍 Query: {query:<{WIDTH - 12}}│")
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
    print(f"     • {meta['source']} [{meta['folder']}]")
print()
