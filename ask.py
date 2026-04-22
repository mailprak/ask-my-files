import chromadb
import sys

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

print()
print("┌" + "─" * WIDTH + "┐")
print(f"│  🔍 Query: {query:<{WIDTH - 12}}│")
print("└" + "─" * WIDTH + "┘")

for i, (doc, meta) in enumerate(zip(results["documents"][0], results["metadatas"][0]), 1):
    print()
    print(f"  ┌─ Result {i} " + "─" * (WIDTH - 12) + "┐")
    print(f"  │  📄 {meta['source']}  [{meta['folder']}]")
    print(f"  │  📁 {meta['path']}")
    print(f"  ├" + "─" * WIDTH + "┤")
    for line in doc.strip().splitlines():
        line = line.strip()
        if line:
            # wrap long lines
            while len(line) > WIDTH - 4:
                print(f"  │  {line[:WIDTH - 4]}")
                line = line[WIDTH - 4:]
            print(f"  │  {line}")
    print(f"  └" + "─" * WIDTH + "┘")

print()
