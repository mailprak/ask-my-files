import chromadb
import sys
import argparse
import re
import ollama

client = chromadb.PersistentClient(path="./chroma_db")

parser = argparse.ArgumentParser(description="Ask questions about your files or a course")
parser.add_argument("--course", type=str, help="Query a specific course (e.g., --course golang)")
parser.add_argument("--cross", action="store_true", help="Query all course collections comparatively")
parser.add_argument("--quiz", nargs="?", const="", default=None, metavar="DAY",
                    help="Generate a quiz. Optional day filter e.g. --quiz day-13")
parser.add_argument("query", nargs="*", help="Your question")
args = parser.parse_args()

# Mutual exclusion: --cross and --course cannot be used together
if args.cross and args.course:
    print("❌ --cross and --course are mutually exclusive.")
    print("   Use --cross to query all courses, or --course <name> for a single course.")
    sys.exit(1)

WIDTH = 72


def print_box_header(label: str, query_text: str):
    print()
    print("┌" + "─" * WIDTH + "┐")
    truncated = query_text[:WIDTH - len(label) - 2]
    print(f"│  {label}{truncated:<{WIDTH - len(label) - 2}}│")
    print("└" + "─" * WIDTH + "┘")


def print_answer(answer: str):
    print("\n  💬 Answer:\n")
    for line in answer.splitlines():
        while len(line) > WIDTH - 4:
            print(f"  {line[:WIDTH - 4]}")
            line = line[WIDTH - 4:]
        print(f"  {line}")


# ── Cross-course branch ────────────────────────────────────────────────────────
if args.cross:
    query = " ".join(args.query) if args.query else ""
    if not query:
        print("❌ Please provide a query. e.g. --cross 'how does Crossplane compare to KubeVela?'")
        sys.exit(1)

    all_collections = [c.name for c in client.list_collections() if c.name.startswith("course_")]
    if not all_collections:
        print("❌ No course collections found. Run: uv run injest.py --course <name>")
        sys.exit(1)

    all_results = []
    for coll_name in sorted(all_collections):
        coll = client.get_collection(name=coll_name)
        res = coll.query(query_texts=[query], n_results=3)
        all_results.append((coll_name, res["documents"][0], res["metadatas"][0]))

    # Build combined context labelled by course
    context_parts = []
    for coll_name, chunks, metas in all_results:
        tech = coll_name.removeprefix("course_").upper()
        section = f"=== {tech} ===\n" + "\n\n".join(
            f"[{meta['source']}]\n{doc}" for doc, meta in zip(chunks, metas)
        )
        context_parts.append(section)
    context = "\n\n".join(context_parts)

    system_prompt = (
        "You are a platform engineering expert with deep knowledge of cloud-native technologies. "
        "Synthesise across all course notes provided below. "
        "Highlight similarities, differences, and when to prefer each technology. "
        "Label each point with the relevant technology name."
    )

    prompt = (
        f"{system_prompt}\n\n"
        f"Context:\n{context}\n\n"
        f"Question: {query}\n"
        f"Answer:"
    )

    print_box_header("🔀 Cross-Course: ", query)
    print_answer(
        ollama.chat(model="llama3.2", messages=[{"role": "user", "content": prompt}])
        ["message"]["content"].strip()
    )

    print()
    print("  📂 Sources by course:")
    for coll_name, _, metas in all_results:
        tech = coll_name.removeprefix("course_").upper()
        print(f"     [{tech}]")
        for meta in metas:
            label = meta.get("folder", "")
            print(f"       • {meta['source']} [{label}]")
    print()
    sys.exit(0)


# ── Quiz branch ────────────────────────────────────────────────────────────────
if args.quiz is not None:
    if not args.course:
        print("❌ --quiz requires --course. e.g. --quiz --course golang")
        sys.exit(1)

    collection_name = f"course_{args.course}"
    try:
        collection = client.get_collection(name=collection_name)
    except Exception:
        print(f"❌ Course '{args.course}' not found.")
        print(f"   Run: uv run injest.py --course {args.course}")
        sys.exit(1)

    day_filter = args.quiz  # "" means no filter

    # Fetch a broader set of chunks
    res = collection.query(
        query_texts=[day_filter if day_filter else f"{args.course} concepts"],
        n_results=8,
    )
    chunks = res["documents"][0]
    metas = res["metadatas"][0]

    # Apply day filter if provided
    if day_filter:
        filtered = [(c, m) for c, m in zip(chunks, metas) if day_filter in m.get("source", "")]
        if filtered:
            chunks, metas = zip(*filtered)
        # else fall back to unfiltered (already set above)

    context = "\n\n".join(
        f"[{meta['source']}]\n{doc}" for doc, meta in zip(chunks, metas)
    )

    quiz_prompt = (
        f"You are a {args.course.upper()} tutor creating a short quiz.\n"
        "Generate exactly 5 question-and-answer pairs based ONLY on the notes below.\n"
        "Format strictly as:\nQ1:\nA1:\nQ2:\nA2:\nQ3:\nA3:\nQ4:\nA4:\nQ5:\nA5:\n\n"
        f"Notes:\n{context}\n\n"
        "Quiz:"
    )

    day_label = f" — {day_filter}" if day_filter else ""
    label = f"🎓 [{args.course.upper()}] Quiz{day_label}"
    print_box_header(label + "  ", "")

    response = ollama.chat(model="llama3.2", messages=[{"role": "user", "content": quiz_prompt}])
    raw = response["message"]["content"].strip()

    # Parse Q/A pairs
    pairs = re.findall(r'Q(\d+):\s*(.*?)\nA\1:\s*(.*?)(?=\nQ\d+:|\Z)', raw, re.DOTALL)

    if pairs:
        print()
        for num, question, answer in pairs:
            q_text = question.strip()
            a_text = answer.strip()
            print(f"  Q{num}: {q_text}")
            # wrap answer lines
            for line in a_text.splitlines():
                while len(line) > WIDTH - 8:
                    print(f"      {line[:WIDTH - 8]}")
                    line = line[WIDTH - 8:]
                print(f"      {line}")
            print()
    else:
        # Fallback: print raw output
        print_answer(raw)

    print("  📂 Sources:")
    for meta in metas:
        label_src = meta.get("folder", "")
        print(f"     • {meta['source']} [{label_src}]")
    print()
    sys.exit(0)


# ── Standard single-course / personal files branch ────────────────────────────
query = " ".join(args.query) if args.query else ""
if not query:
    print("❌ Please provide a query.")
    sys.exit(1)

if args.course:
    collection_name = f"course_{args.course}"
    try:
        collection = client.get_collection(name=collection_name)
    except Exception:
        print(f"❌ Course '{args.course}' not found.")
        print(f"   Run: uv run injest.py --course {args.course}")
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
