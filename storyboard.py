"""RAG answer → structured visual storyboard (LLM step).

The LLM only ever produces *data* — a small JSON document describing actors and
scenes. `animate.py` turns that data into frames. Keeping the two apart means the
renderer is deterministic and testable without Ollama, and a malformed model
response degrades to a clear error instead of a broken drawing.

Topic-agnostic: SCIM flows, Kubernetes scheduling, goroutines and channels,
KubeVela workflows — anything the notes describe as things talking to things.
"""

import json
import re

MAX_ACTORS = 5
MAX_SCENES = 8
MIN_SCENES = 2

ACTOR_KINDS = ("person", "client", "service", "store", "queue", "cloud")
SCENE_KINDS = ("message", "process", "result")
STATUSES = ("success", "failure", "info")

# Sloppy model output → our enums.
_KIND_HINTS = {
    "person": ("person", "user", "human", "admin", "employee", "actor", "developer", "operator"),
    "client": ("client", "cli", "browser", "terminal", "app", "frontend", "ui", "kubectl", "sdk"),
    "store":  ("store", "db", "database", "sql", "etcd", "storage", "cache", "registry", "volume",
               "bucket", "repo", "repository", "index"),
    "queue":  ("queue", "topic", "broker", "kafka", "channel", "stream", "bus", "buffer"),
    "cloud":  ("cloud", "aws", "gcp", "azure", "saas", "external", "internet", "third-party"),
    "service": ("service", "server", "api", "controller", "gateway", "proxy", "connector",
                "operator", "engine", "scheduler", "worker", "pod", "microservice"),
}

_SCENE_ALIASES = {
    "message": ("message", "request", "response", "call", "send", "post", "get", "arrow",
                "http", "reply", "return", "forward", "sync"),
    "process": ("process", "processing", "transform", "map", "validate", "compute", "work",
                "think", "internal", "step", "action"),
    "result":  ("result", "outcome", "success", "failure", "error", "done", "end", "final",
                "state", "complete"),
}

_STATUS_ALIASES = {
    "success": ("success", "ok", "created", "200", "201", "204", "pass", "green", "accepted"),
    "failure": ("failure", "fail", "error", "denied", "rejected", "409", "400", "401", "403",
                "404", "500", "red", "conflict"),
    "info":    ("info", "neutral", "pending", "in-progress", "note"),
}

# Whole-word matches that mean "this actor is a human", whatever kind the model said.
_PERSON_WORDS = frozenset({
    "user", "users", "person", "people", "human", "admin", "administrator",
    "employee", "developer", "operator", "customer", "engineer", "requester",
})

LABEL_MAX = 34      # arrow/badge chips — must stay readable at chip size
ACTOR_MAX = 26
SAYS_MAX = 52       # speech bubble — one short spoken line
DETAIL_MAX = 190
TITLE_MAX = 64


class StoryboardError(RuntimeError):
    """The model did not return a storyboard we can draw."""


SCHEMA_HELP = """Return ONE JSON object, nothing else. Shape:

{
  "title": "short title, max 8 words",
  "actors": [
    {"id": "short_snake_id", "label": "Display Name", "kind": "person|client|service|store|queue|cloud"}
  ],
  "scenes": [
    {"kind": "message", "from": "actor_id", "to": "actor_id", "label": "POST /Users",
     "status": "success|failure|info", "detail": "one sentence of narration"},
    {"kind": "process", "at": "actor_id", "label": "Validate schema",
     "detail": "one sentence"},
    {"kind": "result", "at": "actor_id", "label": "User created", "status": "success",
     "detail": "one sentence"}
  ]
}

Rules:
- 2 to %d actors, ordered left to right in the order they first act.
- %d to %d scenes, in chronological order. Every scene tells the next beat of the story.
- "message" moves between two DIFFERENT actors. "process" and "result" happen AT one actor.
- "label" is a short chip: an HTTP call, a verb phrase, a state. Max 6 words.
- "detail" is one plain sentence explaining that beat. It is drawn as the caption
  and read aloud by the narrator, so write it to be spoken.
- "status" is optional on message, expected on result.
- Every "from", "to" and "at" MUST be an id from the actors list.
- Base it only on the supplied notes and answer. No invented systems.
- The example below is from an unrelated domain and exists ONLY to show the JSON
  shape. Never reuse its actors, labels, wording or title.""" % (
    MAX_ACTORS, MIN_SCENES, MAX_SCENES
)

# Deliberately off-domain: a small local model will happily copy a worked example
# verbatim when it looks close to the question, so this one cannot be mistaken
# for an answer about anything in the notes.
EXAMPLE = """{"title": "Ordering a coffee", "actors": [{"id": "customer", "label": "Customer", "kind": "person"}, {"id": "barista", "label": "Barista", "kind": "service"}, {"id": "machine", "label": "Espresso Machine", "kind": "service"}], "scenes": [{"kind": "message", "from": "customer", "to": "barista", "label": "Order a flat white", "detail": "The customer places an order at the counter."}, {"kind": "process", "at": "barista", "label": "Grind and tamp", "detail": "The barista doses and tamps the ground coffee into the portafilter."}, {"kind": "message", "from": "barista", "to": "machine", "label": "Pull the shot", "detail": "The portafilter is locked in and extraction begins."}, {"kind": "result", "at": "machine", "label": "Coffee served", "status": "success", "detail": "The drink is finished with steamed milk and handed over."}]}"""


# ── Prompt ─────────────────────────────────────────────────────────────────────
def build_storyboard_prompt(question, answer, context="", topic=""):
    topic_line = f"Topic area: {topic}.\n" if topic else ""
    context_block = f"Source notes:\n{context.strip()[:6000]}\n\n" if context else ""
    return (
        "You are a technical illustrator. Turn the explanation below into a storyboard "
        "for a short animation that shows the flow step by step.\n"
        f"{topic_line}\n"
        f"{SCHEMA_HELP}\n\n"
        f"Worked example of the exact output format:\n{EXAMPLE}\n\n"
        f"{context_block}"
        f"Question: {question}\n\n"
        f"Explanation to visualise:\n{str(answer).strip()[:4000]}\n\n"
        "JSON:"
    )


def build_repair_prompt(raw, error):
    return (
        "The JSON below is invalid for the required storyboard schema.\n"
        f"Problem: {error}\n\n"
        f"{SCHEMA_HELP}\n\n"
        f"Invalid output:\n{str(raw)[:2000]}\n\n"
        "Return the corrected JSON object only:"
    )


# ── Parsing ────────────────────────────────────────────────────────────────────
def extract_json(raw):
    """Pull the first balanced JSON object out of a model response."""
    if raw is None:
        raise StoryboardError("empty model response")
    text = str(raw).strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()

    start = text.find("{")
    if start == -1:
        raise StoryboardError("no JSON object in model response")

    depth, in_str, escaped = 0, False, False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start:i + 1])
                except json.JSONDecodeError as exc:
                    raise StoryboardError(f"malformed JSON: {exc}") from exc
    raise StoryboardError("unterminated JSON object in model response")


def _slug(text, fallback="actor"):
    slug = re.sub(r"[^a-z0-9]+", "_", str(text).lower()).strip("_")
    return slug or fallback


def _match(value, table, default):
    """Best-effort enum coercion against a keyword table, by substring."""
    v = str(value or "").lower().strip()
    if v in table:
        return v
    for key, hints in table.items():
        if any(h in v for h in hints):
            return key
    return default


def _match_words(value, table, default):
    """Same, but whole words only — "userName mapper" is not a person."""
    words = set(re.findall(r"[a-z0-9]+", str(value or "").lower()))
    for key, hints in table.items():
        if words & set(hints):
            return key
    return default


def _clip(text, limit):
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _first(d, *keys, default=None):
    for k in keys:
        if isinstance(d, dict) and d.get(k) not in (None, ""):
            return d[k]
    return default


def normalize(data):
    """Coerce a raw parsed object into a storyboard `animate.py` can draw.

    Small local models are inconsistent — wrong enum values, ids that don't match
    the actor list, extra keys, one scene too many. Everything fixable is fixed
    here; only a storyboard with nothing left to draw raises.
    """
    if not isinstance(data, dict):
        raise StoryboardError("storyboard must be a JSON object")

    raw_actors = data.get("actors") or data.get("nodes") or []
    if isinstance(raw_actors, dict):                       # {"idp": {...}} form
        raw_actors = [{**v, "id": k} for k, v in raw_actors.items() if isinstance(v, dict)]
    if not isinstance(raw_actors, list) or not raw_actors:
        raise StoryboardError("storyboard has no actors")

    actors, by_id, alias = [], {}, {}
    for i, item in enumerate(raw_actors):
        if isinstance(item, str):
            item = {"label": item}
        if not isinstance(item, dict):
            continue
        label = _first(item, "label", "name", "title", "id", default=f"Actor {i + 1}")
        aid = _slug(_first(item, "id", "key", "name", default=label), f"actor_{i + 1}")
        if aid in by_id:
            aid = f"{aid}_{i + 1}"
        kind = _match(_first(item, "kind", "type", "role", default=""), _KIND_HINTS, "service")
        # A label like "Postgres database" should still look like a store.
        if kind == "service":
            kind = _match_words(label, _KIND_HINTS, "service")
        # Models routinely tag a human as a "client". Anyone actually named as a
        # person is drawn as one — it is the most legible role on the stage.
        if kind != "person" and _PERSON_WORDS & set(re.findall(r"[a-z]+", str(label).lower())):
            kind = "person"

        actor = {"id": aid, "label": _clip(label, ACTOR_MAX), "kind": kind}
        actors.append(actor)
        by_id[aid] = actor
        for key in (aid, _slug(label), str(label).lower().strip(), str(i), str(i + 1)):
            alias.setdefault(key, aid)
        if len(actors) == MAX_ACTORS:
            break

    def resolve(ref):
        if ref is None:
            return None
        key = str(ref).strip()
        return alias.get(key) or alias.get(key.lower()) or alias.get(_slug(key))

    raw_scenes = data.get("scenes") or data.get("steps") or data.get("frames") or []
    if not isinstance(raw_scenes, list):
        raise StoryboardError("storyboard has no scenes")

    scenes, dropped = [], []
    for i, item in enumerate(raw_scenes):
        if not isinstance(item, dict):
            dropped.append(f"scene {i + 1}: not an object")
            continue

        kind = _match(_first(item, "kind", "type", "action", default=""), _SCENE_ALIASES, "")
        src = resolve(_first(item, "from", "source", "from_id", "sender"))
        dst = resolve(_first(item, "to", "target", "to_id", "receiver"))
        at = resolve(_first(item, "at", "actor", "on", "node", "where"))
        if not kind:
            kind = "message" if (src and dst) else "process"

        label = _clip(_first(item, "label", "text", "title", "name", "summary", default=""), LABEL_MAX)
        detail = _clip(_first(item, "detail", "caption", "description", "note", default=""), DETAIL_MAX)
        says = _clip(_first(item, "says", "speech", "quote", "bubble", "line", default=""), SAYS_MAX)
        status = _first(item, "status", "outcome", "state")
        status = _match(status, _STATUS_ALIASES, None) if status is not None else None

        if kind == "message":
            if not src or not dst:
                dropped.append(f"scene {i + 1}: message with unknown actor")
                continue
            if src == dst:                                  # self-call is really a process
                kind, at = "process", src
            else:
                scenes.append({"kind": "message", "from": src, "to": dst,
                               "label": label or "message", "detail": detail,
                               **({"says": says} if says else {}),
                               **({"status": status} if status else {})})
                continue

        at = at or src or dst
        if not at:
            dropped.append(f"scene {i + 1}: {kind} with unknown actor")
            continue
        scenes.append({"kind": kind, "at": at,
                       "label": label or ("done" if kind == "result" else "processing"),
                       "detail": detail,
                       **({"says": says} if says else {}),
                       **({"status": status or ("success" if kind == "result" else None)}
                          if (status or kind == "result") else {})})

    scenes = scenes[:MAX_SCENES]
    if not scenes:
        raise StoryboardError(
            "no drawable scenes" + (f" ({dropped[0]})" if dropped else "")
        )

    # Drop actors nothing references, so the stage isn't padded with dead boxes.
    used = set()
    for scene in scenes:
        used.update([scene["from"], scene["to"]] if scene["kind"] == "message" else [scene["at"]])
    actors = [a for a in actors if a["id"] in used] or actors[:1]

    return {
        "title": _clip(data.get("title") or data.get("name") or "Visual explanation", TITLE_MAX),
        "actors": actors,
        "scenes": scenes,
        **({"warnings": dropped} if dropped else {}),
    }


# ── Generation ─────────────────────────────────────────────────────────────────
def _chat(model, prompt, client=None):
    import ollama

    chat = client.chat if client else ollama.chat
    kwargs = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "options": {"temperature": 0.2},
    }
    try:
        response = chat(format="json", **kwargs)
    except TypeError:                       # older ollama client without `format`
        response = chat(**kwargs)
    return response["message"]["content"]


def generate_storyboard(question, answer, context="", model="llama3.2",
                        topic="", client=None, repair=True):
    """Ask the LLM for a storyboard and return a validated, drawable dict.

    Raises StoryboardError if the model cannot produce something we can draw.
    """
    prompt = build_storyboard_prompt(question, answer, context, topic)
    raw = _chat(model, prompt, client)

    try:
        return normalize(extract_json(raw))
    except StoryboardError as first_error:
        if not repair:
            raise
        try:
            repaired = _chat(model, build_repair_prompt(raw, str(first_error)), client)
            return normalize(extract_json(repaired))
        except StoryboardError as second_error:
            raise StoryboardError(
                f"{first_error}; retry also failed: {second_error}"
            ) from second_error
