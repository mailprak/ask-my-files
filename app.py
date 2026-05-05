import streamlit as st
import chromadb
import ollama

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Ask My Files",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── ChromaDB client (cached — one connection for the whole session) ────────────
@st.cache_resource
def get_client():
    return chromadb.PersistentClient(path="./chroma_db")

client = get_client()

# ── Discover available collections ─────────────────────────────────────────────
@st.cache_data(ttl=30)
def list_collections():
    try:
        names = [c.name for c in client.list_collections()]
    except Exception:
        return [], []

    courses = sorted([n.removeprefix("course_") for n in names if n.startswith("course_")])
    has_personal = "engineering_memory" in names
    return courses, has_personal

courses, has_personal = list_collections()

# ── Sidebar ─────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("🧠 Ask My Files")
    st.markdown("---")

    # Collection selector
    options = []
    if has_personal:
        options.append("📂 Personal Files")
    for c in courses:
        icon = {
            "golang":     "🐹",
            "kubernetes": "☸️",
            "kubevela":   "🚀",
            "crossplane": "🔧",
        }.get(c, "📚")
        options.append(f"{icon} {c.title()}")

    if not options:
        st.warning("No indexed collections found.\n\nRun:\n```\npython injest.py\n```\nor\n```\npython injest.py --course golang\n```")
        st.stop()

    selected = st.selectbox("Collection", options, index=0)

    st.markdown("---")
    st.caption("Model")
    model = st.selectbox("Ollama model", ["llama3.2", "llama3.1", "mistral", "gemma2"], index=0)

    st.markdown("---")
    st.caption("Search")
    n_results = st.slider("Chunks to retrieve", min_value=1, max_value=10, value=5)

    st.markdown("---")
    if st.button("🗑️ Clear chat"):
        st.session_state.messages = []
        st.rerun()

    st.markdown("---")
    st.caption("Indexed collections")
    if has_personal:
        st.markdown("- 📂 Personal Files")
    for c in courses:
        st.markdown(f"- 📚 {c}")

# ── Resolve selected collection ─────────────────────────────────────────────────
if selected.startswith("📂"):
    collection_name = "engineering_memory"
    collection_label = "Personal Files"
    is_course = False
    course_name = None
else:
    course_name = selected.split(" ", 1)[1].lower()
    collection_name = f"course_{course_name}"
    collection_label = course_name.upper()
    is_course = True

try:
    collection = client.get_collection(name=collection_name)
except Exception:
    st.error(f"Collection **{collection_name}** not found. Please index it first.")
    st.stop()

# ── System prompts ──────────────────────────────────────────────────────────────
if is_course:
    system_prompt = (
        f"You are a {collection_label} expert and tutor. "
        "Answer the question using only the learning notes provided in the context. "
        "Include code examples from the notes where relevant. "
        "Be concise and precise."
    )
    not_found_msg = f"I could not find an answer to that in the {collection_label} course notes."
else:
    system_prompt = (
        "You are a helpful personal assistant. "
        "Answer the question using only the context provided from the user's files. "
        "Be concise and factual."
    )
    not_found_msg = "I could not find an answer to that in your files."

# ── Chat history ────────────────────────────────────────────────────────────────
if "messages" not in st.session_state:
    st.session_state.messages = []

# Track which collection the history belongs to — reset on switch
if st.session_state.get("active_collection") != collection_name:
    st.session_state.messages = []
    st.session_state.active_collection = collection_name

# ── Header ──────────────────────────────────────────────────────────────────────
col1, col2 = st.columns([3, 1])
with col1:
    if is_course:
        st.title(f"📚 {collection_label}")
    else:
        st.title("📂 Personal Files")
with col2:
    st.markdown(f"<br><span style='color:gray'>model: `{model}`</span>", unsafe_allow_html=True)

st.markdown("---")

# ── Render existing chat messages ───────────────────────────────────────────────
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg["role"] == "assistant" and msg.get("sources"):
            with st.expander("📂 Sources", expanded=False):
                for src in msg["sources"]:
                    folder = src.get("folder", "")
                    source = src.get("source", "")
                    label = f"[{folder}]" if folder else ""
                    st.markdown(f"- `{source}` {label}")

# ── Chat input ──────────────────────────────────────────────────────────────────
query = st.chat_input(f"Ask anything about {collection_label}…")

if query:
    # Show user message
    st.session_state.messages.append({"role": "user", "content": query})
    with st.chat_message("user"):
        st.markdown(query)

    # Query ChromaDB
    with st.chat_message("assistant"):
        with st.spinner("Searching…"):
            try:
                results = collection.query(
                    query_texts=[query],
                    n_results=n_results,
                )
                chunks = results["documents"][0]
                metas = results["metadatas"][0]
            except Exception as e:
                st.error(f"ChromaDB error: {e}")
                st.stop()

        context = "\n\n".join(
            f"[{meta.get('source', '')}]\n{doc}"
            for doc, meta in zip(chunks, metas)
        )

        prompt = (
            f"{system_prompt}\n"
            f'If the answer is not in the context, say "{not_found_msg}"\n\n'
            f"Context:\n{context}\n\n"
            f"Question: {query}\n"
            f"Answer:"
        )

        # Stream response from Ollama
        answer_placeholder = st.empty()
        answer = ""

        try:
            stream = ollama.chat(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                stream=True,
            )
            for chunk in stream:
                token = chunk["message"]["content"]
                answer += token
                answer_placeholder.markdown(answer + "▌")
            answer_placeholder.markdown(answer)

        except Exception as e:
            answer = f"❌ Ollama error: {e}\n\nMake sure `ollama serve` is running."
            answer_placeholder.error(answer)

        # Show sources
        with st.expander("📂 Sources", expanded=False):
            for meta in metas:
                folder = meta.get("folder", "")
                source = meta.get("source", "")
                label = f"[{folder}]" if folder else ""
                st.markdown(f"- `{source}` {label}")

    # Save to history
    st.session_state.messages.append({
        "role": "assistant",
        "content": answer,
        "sources": metas,
    })
