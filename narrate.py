"""Storyboard → spoken narration track (offline TTS).

The storyboard already contains the script, so narration is a matter of speaking
one line per scene and padding each clip out to the length of the beat it belongs
to. Because `animate.py` can stretch a beat to fit (`min_shot_ms`), the picture
waits for the voice instead of drifting away from it: the GIF and the WAV end up
exactly the same length and loop together.

Two things separate this from reading the captions aloud:

* Captions are written to be *read*. `spoken_form` rewrites them to be *heard* —
  "GET /pods" becomes "get pods", "409" becomes "four oh nine", "kubectl" becomes
  "cube control" — leaving the on-screen text untouched.
* Positional connectives ("First… Then… Finally…") turn a list of captions into
  something that sounds like a narration.

Engines are whatever is already on the machine — macOS `say` needs no install at
all, Linux usually means `espeak-ng` or `piper`. Nothing is downloaded and nothing
leaves the machine. Audio is never resampled (Python 3.13 dropped `audioop`); one
engine produces every clip in a run, so the format is consistent by construction.

Standalone:

    uv run narrate.py --demo out/demo.wav
    uv run narrate.py --demo out/demo.wav --voice Ava --rate 155  # default: Daniel
    uv run narrate.py --voices                 # what this machine can speak with
"""

import argparse
import array
import io
import json
import os
import re
import shutil
import subprocess
import tempfile
import wave
from functools import lru_cache

import animate

GAP_MS = 420           # breathing room after each spoken line
SYNTH_TIMEOUT = 60     # per line — a stuck engine should not hang the app
DEFAULT_RATE = 160     # words per minute; slower than the engine defaults
DEFAULT_VOICE = "Daniel"   # macOS `say`; ignored when it is not installed
TRIM_FLOOR = 0.012     # amplitude below this counts as silence
TRIM_KEEP_MS = 60      # silence left in place at each end


class NarrationError(RuntimeError):
    """No usable TTS engine, or the engine failed."""


# ── Engines ────────────────────────────────────────────────────────────────────
# Ordered by preference: the built-in macOS voice first (best quality, zero
# install), then the usual Linux options.
ENGINES = ("say", "piper", "espeak-ng", "espeak", "flite")

ENGINE_HELP = (
    "no offline TTS engine found — install one of: espeak-ng (Linux: "
    "`sudo apt install espeak-ng`), piper, or flite. macOS has `say` built in."
)

VOICE_HELP = (
    f"'{DEFAULT_VOICE}' is used by default when installed. macOS ships better "
    "voices than its own default too: System Settings → Accessibility → Spoken "
    "Content → System Voice → Manage Voices adds Premium ones (Ava, Zoe, Evan), "
    "and Enhanced versions of the built-ins. `say -v '?'` lists what is installed."
)


def available_engines():
    return [e for e in ENGINES if shutil.which(e)]


def pick_engine(preferred=None):
    """The engine to use, or None. A named preference must actually exist."""
    if preferred:
        return preferred if shutil.which(preferred) else None
    found = available_engines()
    return found[0] if found else None


@lru_cache(maxsize=8)
def list_voices(engine=None):
    """Voice names this machine can speak with. Empty list if none/unknown."""
    engine = pick_engine(engine)
    if not engine:
        return []
    try:
        if engine == "say":
            out = subprocess.run(["say", "-v", "?"], capture_output=True, text=True,
                                 timeout=10).stdout
            # "Ava (Premium)        en_US    # Hello, my name is Ava."
            return [m.group(1).strip() for m in
                    re.finditer(r"^(.+?)\s{2,}(en[_-]\w+)", out, re.MULTILINE)]
        if engine in ("espeak-ng", "espeak"):
            out = subprocess.run([engine, "--voices=en"], capture_output=True,
                                 text=True, timeout=10).stdout
            return [line.split()[3] for line in out.splitlines()[1:] if len(line.split()) > 3]
        if engine == "piper":
            return [os.path.basename(m) for m in _piper_models()]
    except (OSError, subprocess.SubprocessError, IndexError):
        return []
    return []


def resolve_voice(engine, voice=None):
    """The voice to speak with: the caller's, else DEFAULT_VOICE if installed.

    Falls back to the engine's own default rather than passing a name that is not
    there, which `say` rejects outright.
    """
    if voice:
        return voice
    if engine != "say":
        return None
    for installed in list_voices("say"):
        # `say -v '?'` prints names like "Daniel (Enhanced)".
        if installed == DEFAULT_VOICE or installed.startswith(DEFAULT_VOICE + " "):
            return installed
    return None


def _piper_models():
    found = []
    model = os.environ.get("PIPER_MODEL")
    if model and os.path.exists(model):
        found.append(model)
    for folder in ("voices", os.path.expanduser("~/.local/share/piper")):
        if os.path.isdir(folder):
            found += [os.path.join(folder, n) for n in sorted(os.listdir(folder))
                      if n.endswith(".onnx")]
    return found


def _piper_model(voice=None):
    models = _piper_models()
    if voice:
        for m in models:
            if os.path.basename(m) == voice or m == voice:
                return m
    return models[0] if models else None


def _command(engine, text, path, rate, voice):
    if engine == "say":                     # macOS, built in
        cmd = ["say", "-r", str(rate), "-o", path, "--data-format=LEI16@22050"]
        if voice:
            cmd += ["-v", voice]
        return cmd + [text]
    if engine == "piper":
        model = _piper_model(voice)
        if not model:
            raise NarrationError(
                "piper needs a voice model — set PIPER_MODEL or put a .onnx in ./voices")
        return ["piper", "--model", model, "--output_file", path]
    if engine in ("espeak-ng", "espeak"):
        cmd = [engine, "-s", str(rate), "-w", path]
        if voice:
            cmd += ["-v", voice]
        return cmd + [text]
    if engine == "flite":
        return ["flite", "-t", text, "-o", path]
    raise NarrationError(f"unsupported TTS engine: {engine}")


def speak_to_file(text, path, engine=None, rate=DEFAULT_RATE, voice=None):
    """Synthesise one line to a WAV file. Returns the engine that produced it."""
    engine = pick_engine(engine)
    if not engine:
        raise NarrationError(ENGINE_HELP)

    text = " ".join(str(text).split())[:400] or "…"
    voice = resolve_voice(engine, voice)
    cmd = _command(engine, text, path, rate, voice)
    try:
        subprocess.run(
            cmd,
            input=text.encode() if engine == "piper" else None,
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            timeout=SYNTH_TIMEOUT, check=True,
        )
    except subprocess.TimeoutExpired as exc:
        raise NarrationError(f"{engine} timed out after {SYNTH_TIMEOUT}s") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or b"").decode(errors="replace").strip()[:200]
        hint = f" (is '{voice}' installed? `say -v '?'`)" if voice and engine == "say" else ""
        raise NarrationError(f"{engine} failed: {detail or exc}{hint}") from exc
    except OSError as exc:
        raise NarrationError(f"could not run {engine}: {exc}") from exc

    if not os.path.exists(path) or os.path.getsize(path) < 64:
        raise NarrationError(f"{engine} produced no audio")
    return engine


# ── Spoken form: captions are written to be read, not heard ────────────────────
# Read as words rather than numbers: "two oh one", not "two hundred and one".
STATUS_WORDS = {
    "200": "two hundred", "201": "two oh one", "202": "two oh two",
    "204": "two oh four", "301": "three oh one", "302": "three oh two",
    "304": "three oh four", "400": "four hundred", "401": "four oh one",
    "403": "four oh three", "404": "four oh four", "409": "four oh nine",
    "412": "four twelve", "422": "four twenty two", "429": "four twenty nine",
    "500": "five hundred", "502": "five oh two", "503": "five oh three",
    "504": "five oh four",
}

# Terms TTS engines reliably mangle. Keys are matched whole-word, case-insensitively.
PRONUNCIATION = {
    "etcd": "et see dee", "kubectl": "cube control",
    "k8s": "kubernetes", "yaml": "yammel", "json": "jason", "sql": "sequel",
    "nginx": "engine ex", "oauth": "oh-auth", "jwt": "J W T", "idp": "I D P",
    "oidc": "O I D C", "crd": "C R D", "crds": "C R Ds", "xrd": "X R D",
    "xrds": "X R Ds", "oam": "O A M", "rbac": "R back", "pvc": "P V C",
    "cli": "C L I", "uri": "U R I", "url": "U R L", "api": "A P I",
    "apis": "A P Is", "http": "H T T P", "https": "H T T P S", "grpc": "G R P C",
    "cidr": "cider", "iam": "I A M", "vpc": "V P C", "tls": "T L S",
    "ssh": "S S H", "uuid": "U U I D", "cron": "cron", "regex": "reg ex",
    "stdout": "standard out", "stderr": "standard error", "env": "environment",
    "repo": "repository", "config": "config", "auth": "auth", "async": "a-sync",
    "goroutine": "go routine", "goroutines": "go routines", "mutex": "mew tex",
    "kubelet": "cube let", "kubevela": "cube vela", "helm": "helm",
}

_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


def spoken_form(text):
    """Rewrite display text into something a TTS engine reads well.

    Only ever applied to the narration script — the on-screen caption keeps its
    original wording.
    """
    text = str(text or "")

    # Paths and URLs: "/Users" reads as "slash users" otherwise.
    text = re.sub(r"(?<![\w])/([\w./-]+)", lambda m: " " + m.group(1).replace("/", " "), text)
    # Arrows and operators that appear in notes.
    text = text.replace("->", " to ").replace("=>", " to ").replace("&&", " and ")
    # Dashes are a visual pause; spoken, they need to become real punctuation.
    text = re.sub(r"\s*[—–]\s*", ", ", text)
    text = re.sub(r"[`*_#|]", " ", text)

    def word(match):
        raw = match.group(0)
        low = raw.lower()
        if low in PRONUNCIATION:
            return PRONUNCIATION[low]
        if raw in STATUS_WORDS:
            return STATUS_WORDS[raw]
        if _CAMEL.search(raw):          # userName → user Name
            return _CAMEL.sub(" ", raw)
        return raw

    text = re.sub(r"[A-Za-z0-9]+", word, text)
    return " ".join(text.split())


# ── Script ─────────────────────────────────────────────────────────────────────
def _count_word(n):
    words = {1: "one", 2: "two", 3: "three", 4: "four",
             5: "five", 6: "six", 7: "seven", 8: "eight"}
    return words.get(n, str(n))


def _connective(idx, total):
    if total == 1:
        return ""
    if idx == 0:
        return "First, "
    if idx == total - 1:
        return "Finally, "
    return ("Then, ", "Next, ", "After that, ")[(idx - 1) % 3]


def _lower_first(text):
    """Join a connective onto a sentence without a capital in the middle."""
    if not text:
        return text
    head, rest = text[0], text[1:]
    # Leave acronyms and proper-looking tokens alone: "API Server accepts…"
    first_word = text.split(" ", 1)[0]
    if first_word.isupper() or (len(first_word) > 1 and first_word[1].isupper()):
        return text
    return head.lower() + rest


def script_for(board, intro=True, outro=True, lines_override=None):
    """One spoken line per scene: [(scene_index, text), …] in playback order."""
    scenes = board["scenes"]
    total = len(scenes)
    out = []

    for idx, scene in enumerate(scenes):
        if lines_override and idx < len(lines_override) and lines_override[idx]:
            body = str(lines_override[idx]).strip()
        else:
            detail = (scene.get("detail") or "").strip()
            says = (scene.get("says") or "").strip()
            label = (scene.get("label") or "").strip()
            # The caption sentence is the teaching content. The label is already
            # on screen, so speaking it too just stutters — use it only when
            # there is no sentence to read.
            body = detail or says or label or f"step {idx + 1}"

        spoken = spoken_form(body)
        connective = _connective(idx, total)
        if connective:
            spoken = connective + _lower_first(spoken)
        if not spoken.rstrip().endswith((".", "!", "?")):
            spoken += "."

        if idx == 0 and intro:      # no title card, so the voice opens the piece
            title = spoken_form(board.get("title") or "This flow").rstrip(". ")
            steps = "one step" if total == 1 else f"{_count_word(total)} steps"
            spoken = f"{title}. Here is how it works, in {steps}. {spoken}"
        if idx == total - 1 and outro:
            spoken += " And that is the whole flow."

        out.append((idx, spoken))
    return out


REWRITE_PROMPT = """Rewrite these {n} caption sentences as a spoken narration for a
short explainer animation. Return exactly {n} numbered lines, one per caption, in
the same order — no preamble, no extra lines.

Rules:
- One or two short sentences per line. Say it the way a person would out loud.
- Keep every technical fact and name exactly as given. Invent nothing.
- Do not add step numbers or words like "First" or "Finally" — those are added later.

Captions:
{captions}

Numbered narration:"""


def rewrite_script(board, model="llama3.2", client=None):
    """Ask the LLM to turn the captions into spoken lines. Returns a list or None.

    Optional and opt-in: it reads better but costs a round trip and is not
    deterministic, so a wrong-shaped answer is discarded rather than patched.
    """
    scenes = board["scenes"]
    captions = "\n".join(
        f"{i + 1}. {(s.get('detail') or s.get('label') or '').strip()}"
        for i, s in enumerate(scenes)
    )
    prompt = REWRITE_PROMPT.format(n=len(scenes), captions=captions)

    try:
        import ollama
        chat = client.chat if client else ollama.chat
        raw = chat(model=model, messages=[{"role": "user", "content": prompt}],
                   options={"temperature": 0.3})["message"]["content"]
    except Exception:
        return None

    lines = re.findall(r"^\s*(\d+)[.)]\s*(.+?)\s*$", raw, re.MULTILINE)
    if len(lines) != len(scenes):
        return None
    ordered = {int(n): text for n, text in lines}
    if set(ordered) != set(range(1, len(scenes) + 1)):
        return None
    return [ordered[i + 1] for i in range(len(scenes))]


# ── WAV assembly ───────────────────────────────────────────────────────────────
def _read_wav(path):
    with wave.open(path, "rb") as w:
        params = (w.getnchannels(), w.getsampwidth(), w.getframerate())
        return params, w.readframes(w.getnframes())


def _duration_ms(params, frames):
    channels, width, rate = params
    return int(len(frames) / (channels * width) / rate * 1000)


def _silence(params, ms):
    channels, width, rate = params
    return b"\x00" * (int(rate * ms / 1000) * channels * width)


def trim_silence(params, frames, floor=TRIM_FLOOR, keep_ms=TRIM_KEEP_MS):
    """Drop the dead air engines pad onto each clip, keeping a short lead-in.

    16-bit only — anything else is returned untouched rather than mangled.
    """
    channels, width, rate = params
    if width != 2 or not frames:
        return frames

    samples = array.array("h")
    samples.frombytes(frames[:len(frames) - len(frames) % 2])
    if not samples:
        return frames
    limit = int(32767 * floor)

    first, last = 0, len(samples) - 1
    while first < len(samples) and abs(samples[first]) < limit:
        first += 1
    if first >= len(samples):
        return frames                       # all silence — leave it alone
    while last > first and abs(samples[last]) < limit:
        last -= 1

    keep = int(rate * keep_ms / 1000) * channels
    first = max(0, first - keep)
    last = min(len(samples) - 1, last + keep)
    first -= first % channels               # never split a frame
    return samples[first:last + 1].tobytes()


def build_narration(board, path=None, engine=None, rate=DEFAULT_RATE, voice=None,
                    gap_ms=GAP_MS, speak=None, script=None, trim=True):
    """Narrate `board`. Returns (wav_bytes, min_shot_ms, engine_name).

    Feed `min_shot_ms` straight to `animate.render_gif` so the animation holds
    each beat long enough for its line. `script` accepts a pre-built line list
    (see `script_for`); `speak` overrides the synthesiser and is only for tests.
    """
    speak = speak or speak_to_file
    lines = script if script is not None else script_for(board)
    base = animate.shot_durations(board)

    clips, params, used_engine = [], None, engine
    with tempfile.TemporaryDirectory(prefix="narrate-") as tmp:
        for i, (key, text) in enumerate(lines):
            clip_path = os.path.join(tmp, f"{i:02d}.wav")
            used_engine = speak(text, clip_path, engine=engine, rate=rate,
                                voice=voice) or used_engine
            clip_params, frames = _read_wav(clip_path)
            if params is None:
                params = clip_params
            elif clip_params != params:
                # One engine per run, so this should not happen; if it somehow
                # does, refuse rather than emit a garbled track.
                raise NarrationError(
                    f"inconsistent audio format from {used_engine}: "
                    f"{clip_params} after {params}")
            clips.append((key, trim_silence(params, frames) if trim else frames))

    min_shot_ms, track = {}, bytearray()
    for key, frames in clips:
        spoken = _duration_ms(params, frames)
        shot = max(base[key], spoken + gap_ms)
        min_shot_ms[key] = shot
        track += frames + _silence(params, shot - spoken)

    buf = io.BytesIO()
    with wave.open(buf, "wb") as out:
        out.setnchannels(params[0])
        out.setsampwidth(params[1])
        out.setframerate(params[2])
        out.writeframes(bytes(track))
    data = buf.getvalue()

    if path:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)
    return data, min_shot_ms, used_engine


def main():
    parser = argparse.ArgumentParser(description="Narrate a storyboard to a WAV track")
    parser.add_argument("output", nargs="?", default="out/narration.wav")
    parser.add_argument("--json", type=str, help="Storyboard JSON file")
    parser.add_argument("--demo", action="store_true", help="Use the built-in demo board")
    parser.add_argument("--tts", type=str, help=f"Engine: {', '.join(ENGINES)}")
    parser.add_argument("--voice", type=str, help="Voice name (see --voices)")
    parser.add_argument("--voices", action="store_true", help="List installed voices and exit")
    parser.add_argument("--rate", type=int, default=DEFAULT_RATE, help="Words per minute")
    parser.add_argument("--rewrite", action="store_true",
                        help="Let the LLM rewrite the captions as spoken lines")
    parser.add_argument("--model", type=str, default="llama3.2", help="Model for --rewrite")
    parser.add_argument("--print", dest="show", action="store_true",
                        help="Print the script without synthesising")
    args = parser.parse_args()

    if args.json and not args.demo:
        with open(args.json) as f:
            board = json.load(f)
    else:
        board = animate.DEMO_BOARD

    if args.voices:
        engine = pick_engine(args.tts)
        if not engine:
            print(f"❌ {ENGINE_HELP}")
            raise SystemExit(1)
        voices = list_voices(engine)
        print(f"🗣  {engine}: {len(voices)} voice(s)")
        for v in voices:
            print(f"   • {v}")
        if engine == "say":
            print(f"\n💡 {VOICE_HELP}")
        return

    override = rewrite_script(board, args.model) if args.rewrite else None
    if args.rewrite and override is None:
        print("⚠️  LLM rewrite unusable — falling back to the captions")
    lines = script_for(board, lines_override=override)

    if args.show:
        for key, text in lines:
            print(f"  [{key}] {text}")
        return

    if not available_engines() and not args.tts:
        print(f"❌ {ENGINE_HELP}")
        raise SystemExit(1)

    data, min_shot_ms, engine = build_narration(
        board, args.output, engine=args.tts, rate=args.rate, voice=args.voice,
        script=lines)
    total = sum(min_shot_ms.values()) / 1000
    print(f"🔊 {args.output} — {len(data) / 1024:.0f} KB, {total:.1f}s, "
          f"voice: {resolve_voice(engine, args.voice) or 'engine default'} ({engine})")


if __name__ == "__main__":
    main()
