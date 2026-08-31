import streamlit as st
import chromadb
import ollama
import os
import re
from datetime import datetime

import animate
import narrate
import storyboard

CROSS_COURSE_OPTION = "🔀 Cross-Course"

# Every generated GIF is written here — next to app.py, not the shell's cwd.
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")


def build_cross_context(all_results):
    """all_results: list of (coll_name, chunks, metas)"""
    parts = []
    for coll_name, chunks, metas in all_results:
        tech = coll_name.removeprefix("course_").upper()
        section = f"=== {tech} ===\n" + "\n\n".join(
            f"[{meta.get('source', '')}]\n{doc}"
            for doc, meta in zip(chunks, metas)
        )
        parts.append(section)
    return "\n\n".join(parts)


def media_filename(question, ext="gif"):
    slug = re.sub(r"[^a-z0-9]+", "-", question.lower()).strip("-")[:48] or "storyboard"
    return f"{slug}.{ext}"


def media_path(question, ext="gif"):
    """out/<question-slug>-<timestamp>.<ext> — timestamped so a regenerate keeps both."""
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return os.path.join(OUT_DIR, f"{media_filename(question, ext)[:-len(ext) - 1]}-{stamp}.{ext}")


@st.cache_data(ttl=300)
def tts_engines():
    return narrate.available_engines()


@st.cache_data(ttl=300)
def tts_voices():
    return narrate.list_voices()


def render_visual_block(msg, idx, model, speed, narration=False, voice_opts=None):
    """The optional 🎬 Visual Explanation panel under one assistant answer.

    The GIF is cached on the message itself — Streamlit reruns the whole script
    on every interaction, and regenerating would mean a second LLM round trip
    plus a re-render each time.
    """
    voice_opts = voice_opts or {}

    if msg.get("video"):
        st.video(msg["video"])
    elif msg.get("gif"):
        st.image(msg["gif"])
        if msg.get("wav"):
            st.audio(msg["wav"], format="audio/wav")
    if msg.get("video") or msg.get("gif"):
        if msg.get("narration_error"):
            st.caption(f"⚠️ Narration unavailable: {msg['narration_error']}")
        col_a, col_b = st.columns([1, 4])
        with col_a:
            is_video = bool(msg.get("video"))
            st.download_button(
                "⬇️ Save MP4" if is_video else "⬇️ Save GIF",
                data=msg["video"] if is_video else msg["gif"],
                file_name=media_filename(msg.get("question", "storyboard"),
                                         "mp4" if is_video else "gif"),
                mime="video/mp4" if is_video else "image/gif",
                key=f"dl_{idx}",
            )
        with col_b:
            if st.button("🔁 Regenerate", key=f"regen_{idx}"):
                for key in ("gif", "board", "viz_error", "gif_path", "save_error",
                            "wav", "wav_path", "narration_error", "script",
                            "video", "video_path"):
                    msg.pop(key, None)
                st.rerun()
        if msg.get("video_path") or msg.get("gif_path"):
            saved = f"💾 Saved to `{msg.get('video_path') or msg['gif_path']}`"
            if msg.get("wav_path"):
                saved += f" and `{msg['wav_path']}`"
            st.caption(saved)
        elif msg.get("save_error"):
            st.caption(f"⚠️ Not saved to disk: {msg['save_error']}")
        if msg.get("script"):
            with st.expander("📝 Narration script", expanded=False):
                for line in msg["script"]:
                    st.markdown(f"- {line}")
        with st.expander("🧩 Storyboard JSON", expanded=False):
            st.json(msg.get("board", {}))
        return

    if msg.get("viz_error"):
        st.warning(f"Could not build a visual: {msg['viz_error']}")
        if st.button("🔁 Try again", key=f"retry_{idx}"):
            msg.pop("viz_error", None)
            st.rerun()
        return

    if not st.button("🎬 Visual Explanation", key=f"viz_{idx}"):
        return

    try:
        with st.spinner("Storyboarding…"):
            board = storyboard.generate_storyboard(
                question=msg.get("question", ""),
                answer=msg.get("content", ""),
                context=msg.get("context", ""),
                model=model,
                topic=msg.get("topic", ""),
            )
        want_mp4 = voice_opts.get("fmt") == "MP4"
        path = media_path(msg.get("question", "storyboard"),
                          "mp4" if want_mp4 else "gif")

        # Narration first: it decides how long each beat has to be held, so the
        # animation can be rendered to match instead of drifting against it.
        min_shot_ms = None
        if narration:
            wav_path = None if want_mp4 else os.path.splitext(path)[0] + ".wav"
            try:
                override = None
                if voice_opts.get("rewrite"):
                    with st.spinner("Rewriting captions for speech…"):
                        override = narrate.rewrite_script(board, model=model)
                script = narrate.script_for(board, lines_override=override)
                with st.spinner("Recording narration…"):
                    wav, min_shot_ms, _engine = narrate.build_narration(
                        board, wav_path, script=script,
                        voice=voice_opts.get("voice"),
                        rate=voice_opts.get("rate", narrate.DEFAULT_RATE))
                msg["wav"] = wav
                if wav_path:
                    msg["wav_path"] = os.path.relpath(wav_path, os.path.dirname(OUT_DIR))
                msg["script"] = [text for _key, text in script]
            except (narrate.NarrationError, OSError) as exc:
                msg["narration_error"] = str(exc)   # carry on, silently
                min_shot_ms = None

        with st.spinner("Encoding video…" if want_mp4 else "Drawing frames…"):
            play_speed = 1.0 if min_shot_ms else speed   # narration needs real time
            key = "video" if want_mp4 else "gif"
            def _render(dest):
                if want_mp4:
                    return animate.render_video(board, dest, speed=play_speed,
                                                min_shot_ms=min_shot_ms,
                                                audio=msg.get("wav"))
                return animate.render_gif(board, dest, speed=play_speed,
                                          min_shot_ms=min_shot_ms)
            try:
                msg[key] = _render(path)
                msg[f"{key}_path"] = os.path.relpath(path, os.path.dirname(OUT_DIR))
            except OSError as exc:
                # Rendering worked, only the write failed — keep it in memory.
                msg[key] = _render(None)
                msg["save_error"] = str(exc)
            msg["board"] = board
    except storyboard.StoryboardError as exc:
        msg["viz_error"] = str(exc)
    except Exception as exc:
        msg["viz_error"] = f"{exc} — is `ollama serve` running?"
    st.rerun()


def build_quiz_prompt(course_name, context, day_filter):
    day_label = f" (focus on {day_filter})" if day_filter else ""
    return (
        f"You are a {course_name.upper()} tutor creating a short quiz{day_label}.\n"
        "Generate exactly 5 question-and-answer pairs based ONLY on the notes below.\n"
        "Format strictly as:\nQ1:\nA1:\nQ2:\nA2:\nQ3:\nA3:\nQ4:\nA4:\nQ5:\nA5:\n\n"
        f"Notes:\n{context}\n\n"
        "Quiz:"
    )


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

    # Append Cross-Course option when multiple courses are available
    if len(courses) > 1:
        options.append(CROSS_COURSE_OPTION)

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
    st.caption("Visuals")
    visuals_on = st.toggle("🎬 Visual explanations", value=True,
                           help="Offer an animated storyboard under each answer")
    gif_speed = st.slider("Animation speed", 0.5, 2.0, 1.0, 0.25, disabled=not visuals_on)

    engines = tts_engines()
    narration_on = st.toggle(
        "🔊 Narrate", value=False, disabled=not (visuals_on and engines),
        help=("Speak each step with " + engines[0] + "; beats are held long enough "
              "for the line, so the GIF runs slower" if engines else narrate.ENGINE_HELP),
    )
    can_encode = animate.video_available()
    out_fmt = st.radio(
        "Output", ["GIF", "MP4"], horizontal=True, disabled=not visuals_on,
        help="MP4 is one file with the narration inside it; GIF is silent and "
             "autoplays anywhere" if can_encode else animate.FFMPEG_HELP,
        index=0,
    )
    if out_fmt == "MP4" and not can_encode:
        st.caption("🎞️ No video encoder — falling back to GIF")
        out_fmt = "GIF"

    voice, voice_rate, rewrite_on = None, narrate.DEFAULT_RATE, False
    if not engines:
        st.caption("🔇 No TTS engine — `apt install espeak-ng`, or use macOS `say`")
    elif narration_on:
        voices = tts_voices()
        if voices:
            default = narrate.resolve_voice(engines[0])
            voice = st.selectbox("Voice", voices,
                                 index=voices.index(default) if default in voices else 0)
            if engines[0] == "say" and not any("Premium" in v or "Enhanced" in v
                                               for v in voices):
                st.caption("💡 Better voices: System Settings → Accessibility → "
                           "Spoken Content → Manage Voices")
        voice_rate = st.slider("Words per minute", 120, 220, narrate.DEFAULT_RATE, 5)
        rewrite_on = st.checkbox(
            "✍️ Rewrite captions for speech", value=False,
            help="An extra LLM pass turns the captions into spoken prose. "
                 "Better narration, one more round trip.")

    st.markdown("---")
    if st.button("🗑️ Clear chat"):
        st.session_state.messages = []
        st.rerun()

    # Quiz Me widget — only shown when a course collection is active
    if st.session_state.get("active_collection", "").startswith("course_"):
        st.markdown("---")
        st.caption("Teach Me")
        quiz_day = st.text_input("Day filter (optional)", placeholder="e.g. day-13", key="quiz_day")
        quiz_triggered = st.button("🎓 Quiz Me", key="quiz_btn")
    else:
        quiz_triggered = False
        quiz_day = None

    st.markdown("---")
    st.caption("Indexed collections")
    if has_personal:
        st.markdown("- 📂 Personal Files")
    for c in courses:
        st.markdown(f"- 📚 {c}")

# ── Resolve selected collection ─────────────────────────────────────────────────
is_cross_course = (selected == CROSS_COURSE_OPTION)

if selected.startswith("📂"):
    collection_name = "engineering_memory"
    collection_label = "Personal Files"
    is_course = False
    course_name = None
    collection = None
elif is_cross_course:
    collection_name = "__cross__"
    collection_label = "Cross-Course"
    is_course = False
    course_name = None
    collection = None
else:
    course_name = selected.split(" ", 1)[1].lower()
    collection_name = f"course_{course_name}"
    collection_label = course_name.upper()
    is_course = True
    collection = None

if not is_cross_course:
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
elif is_cross_course:
    system_prompt = (
        "You are a platform engineering expert with deep knowledge of cloud-native technologies. "
        "Synthesise across all course notes provided below. "
        "Highlight similarities, differences, and when to prefer each technology. "
        "Label each point with the relevant technology name."
    )
    not_found_msg = "I could not find a relevant answer across the course notes."
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
    if is_cross_course:
        st.title("🔀 Cross-Course")
    elif is_course:
        st.title(f"📚 {collection_label}")
    else:
        st.title("📂 Personal Files")
with col2:
    st.markdown(f"<br><span style='color:gray'>model: `{model}`</span>", unsafe_allow_html=True)

st.markdown("---")

# ── Render existing chat messages ───────────────────────────────────────────────
for idx, msg in enumerate(st.session_state.messages):
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg["role"] == "assistant" and msg.get("sources"):
            with st.expander("📂 Sources", expanded=False):
                for src in msg["sources"]:
                    folder = src.get("folder", "")
                    source = src.get("source", "")
                    label = f"[{folder}]" if folder else ""
                    st.markdown(f"- `{source}` {label}")
        if msg["role"] == "assistant" and visuals_on and msg.get("visualisable"):
            render_visual_block(msg, idx, model, gif_speed, narration_on,
                                {"voice": voice, "rate": voice_rate,
                                 "rewrite": rewrite_on, "fmt": out_fmt})

# ── Chat input ──────────────────────────────────────────────────────────────────
chat_placeholder = (
    "Ask anything across all courses…" if is_cross_course
    else f"Ask anything about {collection_label}…"
)
query = st.chat_input(chat_placeholder)

if query:
    # Show user message
    st.session_state.messages.append({"role": "user", "content": query})
    with st.chat_message("user"):
        st.markdown(query)

    with st.chat_message("assistant"):
        with st.spinner("Searching…"):
            if is_cross_course:
                # Query all course collections
                all_course_names = sorted([
                    c.name for c in client.list_collections()
                    if c.name.startswith("course_")
                ])
                all_results = []
                for coll_name in all_course_names:
                    coll = client.get_collection(name=coll_name)
                    res = coll.query(query_texts=[query], n_results=3)
                    all_results.append((coll_name, res["documents"][0], res["metadatas"][0]))
                context = build_cross_context(all_results)
                metas = [m for _, _, ml in all_results for m in ml]
            else:
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
            if is_cross_course:
                for coll_name, _, coll_metas in all_results:
                    tech = coll_name.removeprefix("course_").upper()
                    st.markdown(f"**{tech}**")
                    for meta in coll_metas:
                        folder = meta.get("folder", "")
                        source = meta.get("source", "")
                        label = f"[{folder}]" if folder else ""
                        st.markdown(f"- `{source}` {label}")
            else:
                for meta in metas:
                    folder = meta.get("folder", "")
                    source = meta.get("source", "")
                    label = f"[{folder}]" if folder else ""
                    st.markdown(f"- `{source}` {label}")

    # Save to history — question/context ride along so a visual can be built later
    st.session_state.messages.append({
        "role": "assistant",
        "content": answer,
        "sources": metas,
        "question": query,
        "context": context,
        "topic": collection_label,
        "visualisable": not answer.startswith("❌"),
    })
    st.rerun()

# ── Quiz trigger ────────────────────────────────────────────────────────────────
if quiz_triggered and is_course and collection:
    with st.chat_message("assistant"):
        with st.spinner("Generating quiz…"):
            # Fetch chunks — use day filter as query seed if provided
            quiz_query = quiz_day if quiz_day else f"{course_name} concepts"
            res = collection.query(query_texts=[quiz_query], n_results=8)
            q_chunks = res["documents"][0]
            q_metas = res["metadatas"][0]

            # Apply day filter
            if quiz_day:
                filtered = [
                    (c, m) for c, m in zip(q_chunks, q_metas)
                    if quiz_day in m.get("source", "")
                ]
                if filtered:
                    q_chunks, q_metas = zip(*filtered)

            context = "\n\n".join(
                f"[{meta.get('source', '')}]\n{doc}"
                for doc, meta in zip(q_chunks, q_metas)
            )

        quiz_prompt = build_quiz_prompt(course_name, context, quiz_day)

        day_label = f" — {quiz_day}" if quiz_day else ""
        quiz_header = f"🎓 **Quiz: {collection_label}{day_label}**\n\n"

        answer_placeholder = st.empty()
        raw_answer = ""

        try:
            stream = ollama.chat(
                model=model,
                messages=[{"role": "user", "content": quiz_prompt}],
                stream=True,
            )
            for chunk in stream:
                token = chunk["message"]["content"]
                raw_answer += token
                answer_placeholder.markdown(quiz_header + raw_answer + "▌")
            answer_placeholder.markdown(quiz_header + raw_answer)

        except Exception as e:
            raw_answer = f"❌ Ollama error: {e}"
            answer_placeholder.error(raw_answer)

        # Parse and render Q/A pairs neatly
        pairs = re.findall(
            r'Q(\d+):\s*(.*?)\nA\1:\s*(.*?)(?=\nQ\d+:|\Z)',
            raw_answer, re.DOTALL
        )
        if pairs:
            formatted = quiz_header
            for num, question, answer_text in pairs:
                formatted += f"**Q{num}:** {question.strip()}\n\n"
                formatted += f"> {answer_text.strip()}\n\n"
            answer_placeholder.markdown(formatted)
            raw_answer = formatted

        with st.expander("📂 Sources", expanded=False):
            for meta in q_metas:
                folder = meta.get("folder", "")
                source = meta.get("source", "")
                label = f"[{folder}]" if folder else ""
                st.markdown(f"- `{source}` {label}")

    st.session_state.messages.append({
        "role": "assistant",
        "content": raw_answer,
        "sources": list(q_metas),
    })
