"""Deterministic storyboard → animated GIF renderer (Pillow only).

Draws the flow as a diagram in motion: actors as labelled stations across the
stage, requests travelling between them on routed arrows, processing states, and
success or failure badges. No LLM, no network, no randomness — the same
storyboard always produces the same frames.

Frames are drawn at 2× and downsampled, which is where the crispness comes from.
`storyboard.py` builds the storyboard; this module draws it, and `narrate.py` can
time a spoken track to it.

Run standalone to sanity-check the renderer without Ollama:

    uv run animate.py --demo out/demo.gif
    uv run animate.py --json board.json out/board.gif --png out/frame.png
"""

import argparse
import io
import json
import math
import os
import shutil
import subprocess
import tempfile

from PIL import Image, ImageDraw, ImageFont

# ── Theme ──────────────────────────────────────────────────────────────────────
BG        = (17, 19, 27)
PANEL     = (27, 31, 43)
PANEL_LO  = (22, 25, 35)
STROKE    = (47, 54, 70)
TEXT      = (230, 233, 240)
MUTED     = (139, 147, 167)
ACCENT    = (77, 163, 255)
ACCENT_LO = (38, 74, 122)
SUCCESS   = (61, 220, 151)
FAILURE   = (255, 92, 122)
WARN      = (255, 200, 87)

STATUS_COLOR = {"success": SUCCESS, "failure": FAILURE, "info": ACCENT}

# ── Canvas ─────────────────────────────────────────────────────────────────────
SS = 2                                  # supersampling factor
OUT_W, OUT_H = 900, 540                 # delivered size
W, H = OUT_W * SS, OUT_H * SS

MARGIN_X    = 48 * SS
TITLE_H     = 70 * SS
BOX_H       = 122 * SS
BOX_MAX_W   = 172 * SS
BOX_GAP     = 44 * SS
ROW_CY      = 252 * SS     # vertical centre of the actor row
BUS_OFFSET  = 48 * SS      # how far above/below the boxes arrows are routed
DOTS_Y      = 418 * SS     # step progress dots
CAPTION_TOP = 434 * SS

# ── Timing ─────────────────────────────────────────────────────────────────────
FRAME_MS      = 70         # GIF delays are centiseconds — stay on the 10ms grid
MSG_FRAMES    = 16
MSG_HOLD      = 5
PROC_FRAMES   = 18
PROC_HOLD     = 3
RESULT_FRAMES = 11
RESULT_HOLD   = 7
FINAL_HOLD    = 20         # extra beats on the closing frame

FONT_DIRS = (
    "/usr/share/fonts/truetype/dejavu",
    "/usr/share/fonts/dejavu",
    "/Library/Fonts",
    "/System/Library/Fonts/Supplemental",
)


def _font(size, bold=False):
    """DejaVu when present, else Pillow's scalable default. Never raises."""
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    for d in FONT_DIRS:
        path = os.path.join(d, name)
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                pass
    try:
        return ImageFont.load_default(size=size)
    except TypeError:            # Pillow < 10.1 — bitmap default, fixed size
        return ImageFont.load_default()


class Fonts:
    """Built once per render, not once per frame."""

    def __init__(self):
        self.title   = _font(25 * SS, bold=True)
        self.actor   = _font(14 * SS, bold=True)
        self.chip    = _font(14 * SS, bold=True)
        self.caption = _font(16 * SS)
        self.small   = _font(12 * SS)
        self.badge   = _font(15 * SS, bold=True)


# ── Small drawing helpers ──────────────────────────────────────────────────────
def _smoothstep(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def _text_w(draw, text, font):
    return draw.textlength(text, font=font)


def _wrap(draw, text, font, max_w, max_lines=3):
    """Greedy word wrap; last line gets an ellipsis if it overflows."""
    words = str(text).split()
    lines, cur = [], ""
    for word in words:
        trial = f"{cur} {word}".strip()
        if _text_w(draw, trial, font) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
            if len(lines) == max_lines:
                break
    if cur and len(lines) < max_lines:
        lines.append(cur)
    if len(lines) == max_lines:
        if sum(len(line.split()) for line in lines) < len(words):
            last = lines[-1]
            while last and _text_w(draw, last + " …", font) > max_w:
                last = last.rsplit(" ", 1)[0] if " " in last else last[:-1]
            lines[-1] = last + " …"
    return lines


def _truncate(draw, text, font, max_w):
    text = str(text)
    if _text_w(draw, text, font) <= max_w:
        return text
    while text and _text_w(draw, text + "…", font) > max_w:
        text = text[:-1]
    return text + "…"


def _blend(c1, c2, t):
    t = max(0.0, min(1.0, t))
    return tuple(int(a + (b - a) * t) for a, b in zip(c1, c2))


def _polyline_point(points, t):
    """Point at fraction `t` along a polyline, plus the unit direction there."""
    segs = []
    total = 0.0
    for (x1, y1), (x2, y2) in zip(points, points[1:]):
        length = math.hypot(x2 - x1, y2 - y1)
        if length > 0:
            segs.append(((x1, y1), (x2, y2), length))
            total += length
    if not segs:
        return points[0], (1.0, 0.0)

    target = max(0.0, min(1.0, t)) * total
    walked = 0.0
    for (x1, y1), (x2, y2), length in segs:
        if walked + length >= target or (x2, y2) == segs[-1][1]:
            local = max(0.0, min(1.0, (target - walked) / length))
            return ((x1 + (x2 - x1) * local, y1 + (y2 - y1) * local),
                    ((x2 - x1) / length, (y2 - y1) / length))
        walked += length
    return segs[-1][1], (1.0, 0.0)


def _partial_polyline(points, t):
    """The first `t` fraction of a polyline, as a new point list."""
    if t <= 0:
        return [points[0]]
    lengths = [math.hypot(x2 - x1, y2 - y1) for (x1, y1), (x2, y2) in zip(points, points[1:])]
    total = sum(lengths)
    if total == 0:
        return [points[0]]

    target = t * total
    out = [points[0]]
    walked = 0.0
    for (start, end), length in zip(zip(points, points[1:]), lengths):
        if walked + length <= target:
            out.append(end)
            walked += length
        else:
            local = (target - walked) / length if length else 0
            out.append((start[0] + (end[0] - start[0]) * local,
                        start[1] + (end[1] - start[1]) * local))
            break
    return out


def _arrowhead(draw, point, direction, color, size=11):
    size *= SS
    dx, dy = direction
    norm = math.hypot(dx, dy) or 1.0
    dx, dy = dx / norm, dy / norm
    px, py = -dy, dx
    x, y = point
    draw.polygon(
        [
            (x, y),
            (x - dx * size + px * size * 0.55, y - dy * size + py * size * 0.55),
            (x - dx * size - px * size * 0.55, y - dy * size - py * size * 0.55),
        ],
        fill=color,
    )


# ── Actor icons (vector — no emoji fonts required) ─────────────────────────────
def _icon(draw, kind, cx, cy, s, color):
    """Draw a `kind` glyph centred on (cx, cy) inside a box of side `s`."""
    w = max(2, int(s * 0.06))
    if kind == "person":
        r = s * 0.19
        draw.ellipse([cx - r, cy - s * 0.42, cx + r, cy - s * 0.42 + 2 * r], fill=color)
        draw.pieslice([cx - s * 0.34, cy - s * 0.12, cx + s * 0.34, cy + s * 0.62],
                      180, 360, fill=color)
    elif kind == "client":
        draw.rounded_rectangle([cx - s * 0.40, cy - s * 0.38, cx + s * 0.40, cy + s * 0.18],
                               radius=s * 0.08, outline=color, width=w)
        draw.line([cx, cy + s * 0.18, cx, cy + s * 0.34], fill=color, width=w)
        draw.line([cx - s * 0.22, cy + s * 0.36, cx + s * 0.22, cy + s * 0.36],
                  fill=color, width=w)
    elif kind == "store":
        rx, ry = s * 0.34, s * 0.13
        top, bottom = cy - s * 0.34, cy + s * 0.26
        draw.line([cx - rx, top, cx - rx, bottom], fill=color, width=w)
        draw.line([cx + rx, top, cx + rx, bottom], fill=color, width=w)
        for oy in (0, s * 0.30, s * 0.60):
            draw.arc([cx - rx, top - ry + oy, cx + rx, top + ry + oy], 0, 180,
                     fill=color, width=w)
        draw.ellipse([cx - rx, top - ry, cx + rx, top + ry], outline=color, width=w)
    elif kind == "queue":
        for oy in (-s * 0.34, -s * 0.08, s * 0.18):
            draw.rounded_rectangle([cx - s * 0.36, cy + oy, cx + s * 0.36, cy + oy + s * 0.17],
                                   radius=s * 0.05, outline=color, width=w)
    elif kind == "cloud":
        draw.ellipse([cx - s * 0.42, cy - s * 0.10, cx - s * 0.02, cy + s * 0.30], fill=color)
        draw.ellipse([cx - s * 0.20, cy - s * 0.34, cx + s * 0.22, cy + s * 0.22], fill=color)
        draw.ellipse([cx + s * 0.02, cy - s * 0.08, cx + s * 0.42, cy + s * 0.30], fill=color)
        draw.rectangle([cx - s * 0.40, cy + s * 0.08, cx + s * 0.40, cy + s * 0.30], fill=color)
    else:  # "service" — a cog
        r = s * 0.28
        for i in range(8):
            a = math.radians(i * 45)
            draw.line([cx + math.cos(a) * r * 0.95, cy + math.sin(a) * r * 0.95,
                       cx + math.cos(a) * r * 1.42, cy + math.sin(a) * r * 1.42],
                      fill=color, width=w + 1)
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=color, width=w + 1)
        draw.ellipse([cx - r * 0.34, cy - r * 0.34, cx + r * 0.34, cy + r * 0.34], fill=color)


# ── Layout ─────────────────────────────────────────────────────────────────────
class Layout:
    def __init__(self, n_actors):
        usable = W - 2 * MARGIN_X
        gap = BOX_GAP if n_actors > 1 else 0
        box_w = min(BOX_MAX_W, (usable - gap * (n_actors - 1)) / max(n_actors, 1))
        self.box_w = box_w
        total = box_w * n_actors + gap * (n_actors - 1)
        start = (W - total) / 2
        self.boxes = [
            (start + i * (box_w + gap), ROW_CY - BOX_H / 2,
             start + i * (box_w + gap) + box_w, ROW_CY + BOX_H / 2)
            for i in range(n_actors)
        ]
        self.fwd_bus = ROW_CY - BOX_H / 2 - BUS_OFFSET
        self.ret_bus = ROW_CY + BOX_H / 2 + BUS_OFFSET

    def centre(self, i):
        x0, y0, x1, y1 = self.boxes[i]
        return ((x0 + x1) / 2, (y0 + y1) / 2)

    def route(self, i, j):
        """Polyline from actor i to actor j, routed clear of the boxes."""
        x0, y0, x1, y1 = self.boxes[i]
        tx0, ty0, tx1, ty1 = self.boxes[j]
        cx_from, cx_to = (x0 + x1) / 2, (tx0 + tx1) / 2
        if j > i:  # forward — route above the row
            bus = self.fwd_bus
            return [(cx_from, y0), (cx_from, bus), (cx_to, bus), (cx_to, ty0)]
        bus = self.ret_bus  # return — route below the row
        return [(cx_from, y1), (cx_from, bus), (cx_to, bus), (cx_to, ty1)]


# ── Frame painting ─────────────────────────────────────────────────────────────
def _chip(draw, cx, cy, text, font, fg, bg, border):
    w = _text_w(draw, text, font)
    pad_x, pad_y = 11 * SS, 7 * SS
    box = [cx - w / 2 - pad_x, cy - font.size / 2 - pad_y,
           cx + w / 2 + pad_x, cy + font.size / 2 + pad_y + 2 * SS]
    draw.rounded_rectangle(box, radius=9 * SS, fill=bg, outline=border, width=2 * SS)
    draw.text((cx - w / 2, cy - font.size / 2), text, font=font, fill=fg)


def _draw_actor(draw, layout, idx, actor, fonts, *, active, visited, badge, pulse=None):
    x0, y0, x1, y1 = layout.boxes[idx]
    if active:
        border, icon_col = ACCENT, ACCENT
        draw.rounded_rectangle([x0 - 4 * SS, y0 - 4 * SS, x1 + 4 * SS, y1 + 4 * SS],
                               radius=16 * SS, outline=ACCENT_LO, width=2 * SS)
    elif visited:
        border, icon_col = _blend(STROKE, ACCENT, 0.45), _blend(MUTED, ACCENT, 0.5)
    else:
        border, icon_col = STROKE, MUTED

    if badge in STATUS_COLOR:
        border = STATUS_COLOR[badge]

    draw.rounded_rectangle([x0, y0, x1, y1], radius=13 * SS,
                           fill=PANEL if (active or visited) else PANEL_LO,
                           outline=border, width=(3 if active else 2) * SS)

    cx = (x0 + x1) / 2
    _icon(draw, actor["kind"], cx, y0 + 40 * SS, 46 * SS, icon_col)

    label_font = fonts.actor
    lines = _wrap(draw, actor["label"], label_font, layout.box_w - 16 * SS, max_lines=2)
    ly = y1 - 14 * SS - len(lines) * (label_font.size + 3 * SS)
    for line in lines:
        draw.text((cx - _text_w(draw, line, label_font) / 2, ly), line,
                  font=label_font, fill=TEXT if (active or visited) else MUTED)
        ly += label_font.size + 3 * SS

    if pulse is not None:  # rotating arc — "working"
        r = layout.box_w * 0.5 + 6 * SS
        start = (pulse * 360) % 360
        draw.arc([cx - r, ROW_CY - r, cx + r, ROW_CY + r], start, start + 90,
                 fill=WARN, width=4 * SS)
        draw.arc([cx - r, ROW_CY - r, cx + r, ROW_CY + r], start + 180, start + 250,
                 fill=WARN, width=4 * SS)

    if badge in STATUS_COLOR:
        col = STATUS_COLOR[badge]
        bx, by, r = x1 - 15 * SS, y0 + 15 * SS, 13 * SS
        draw.ellipse([bx - r, by - r, bx + r, by + r], fill=col)
        if badge == "success":
            draw.line([bx - 6 * SS, by, bx - 1 * SS, by + 5 * SS], fill=BG, width=3 * SS)
            draw.line([bx - 1 * SS, by + 5 * SS, bx + 6 * SS, by - 5 * SS], fill=BG, width=3 * SS)
        elif badge == "failure":
            draw.line([bx - 5 * SS, by - 5 * SS, bx + 5 * SS, by + 5 * SS], fill=BG, width=3 * SS)
            draw.line([bx + 5 * SS, by - 5 * SS, bx - 5 * SS, by + 5 * SS], fill=BG, width=3 * SS)
        else:
            draw.text((bx - _text_w(draw, "i", fonts.badge) / 2, by - 9 * SS), "i",
                      font=fonts.badge, fill=BG)


def _draw_shell(draw, board, fonts, scene_idx, n_scenes):
    draw.rectangle([0, 0, W, H], fill=BG)

    title = _truncate(draw, board["title"], fonts.title, W - 2 * MARGIN_X - 120 * SS)
    draw.text((MARGIN_X, 24 * SS), title, font=fonts.title, fill=TEXT)
    step = f"{scene_idx + 1}/{n_scenes}"
    draw.text((W - MARGIN_X - _text_w(draw, step, fonts.small), 32 * SS), step,
              font=fonts.small, fill=MUTED)
    draw.line([MARGIN_X, TITLE_H, W - MARGIN_X, TITLE_H], fill=STROKE, width=1 * SS)

    dot_r, gap = 5 * SS, 20 * SS
    sx = (W - (n_scenes - 1) * gap) / 2
    for i in range(n_scenes):
        col = ACCENT if i == scene_idx else (
            _blend(STROKE, ACCENT, 0.4) if i < scene_idx else STROKE)
        cx = sx + i * gap
        draw.ellipse([cx - dot_r, DOTS_Y - dot_r, cx + dot_r, DOTS_Y + dot_r], fill=col)


def _draw_caption(draw, fonts, scene):
    box = [MARGIN_X, CAPTION_TOP, W - MARGIN_X, H - 26 * SS]
    draw.rounded_rectangle(box, radius=12 * SS, fill=PANEL_LO, outline=STROKE, width=2 * SS)

    accent = STATUS_COLOR.get(scene.get("status"), ACCENT)
    draw.rounded_rectangle([box[0] + 2 * SS, box[1] + 10 * SS, box[0] + 6 * SS, box[3] - 10 * SS],
                           radius=2 * SS, fill=accent)

    heading = _truncate(draw, scene.get("label", ""), fonts.chip, box[2] - box[0] - 40 * SS)
    draw.text((box[0] + 20 * SS, box[1] + 14 * SS), heading, font=fonts.chip, fill=accent)

    detail = scene.get("detail") or ""
    if detail:
        ty = box[1] + 40 * SS
        for line in _wrap(draw, detail, fonts.caption, box[2] - box[0] - 40 * SS, max_lines=2):
            draw.text((box[0] + 20 * SS, ty), line, font=fonts.caption, fill=TEXT)
            ty += fonts.caption.size + 5 * SS


def _actor_state(board, upto_scene):
    """Which actors are visited, and any status badge earned, before/at a scene."""
    visited, badges = set(), {}
    for scene in board["scenes"][:upto_scene + 1]:
        if scene["kind"] == "message":
            visited.add(scene["from"])
            visited.add(scene["to"])
        else:
            visited.add(scene["at"])
        if scene["kind"] == "result" and scene.get("status") in STATUS_COLOR:
            badges[scene["at"]] = scene["status"]
    return visited, badges


def render_frame(board, scene_idx, t, fonts=None):
    """One frame: scene `scene_idx` at progress `t` in [0, 1], at full size."""
    fonts = fonts or Fonts()
    actors = board["actors"]
    index = {a["id"]: i for i, a in enumerate(actors)}
    layout = Layout(len(actors))
    scene = board["scenes"][scene_idx]

    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)
    _draw_shell(draw, board, fonts, scene_idx, len(board["scenes"]))

    visited, badges = _actor_state(board, scene_idx - 1)
    if scene["kind"] == "result" and t > 0.35 and scene.get("status") in STATUS_COLOR:
        badges = {**badges, scene["at"]: scene["status"]}

    if scene["kind"] == "message":
        active = {scene["from"]} | ({scene["to"]} if t > 0.75 else set())
    else:
        active = {scene["at"]}
    visited |= active

    for i, actor in enumerate(actors):
        _draw_actor(
            draw, layout, i, actor, fonts,
            active=actor["id"] in active,
            visited=actor["id"] in visited,
            badge=badges.get(actor["id"]),
            pulse=t if (scene["kind"] == "process" and actor["id"] == scene["at"]) else None,
        )

    if scene["kind"] == "message":
        i, j = index[scene["from"]], index[scene["to"]]
        route = layout.route(i, j)
        colour = STATUS_COLOR.get(scene.get("status"), ACCENT)

        draw.line([p for pt in route for p in pt], fill=_blend(BG, STROKE, 0.9), width=3 * SS)
        eased = _smoothstep(t)
        if eased > 0.01:
            trail = _partial_polyline(route, eased)
            if len(trail) > 1:
                draw.line([p for pt in trail for p in pt], fill=colour, width=3 * SS)
            point, direction = _polyline_point(route, eased)
            _arrowhead(draw, point, direction, colour)

        chip_at, _ = _polyline_point(route, eased)
        bus_y = layout.fwd_bus if j > i else layout.ret_bus
        label = _truncate(draw, scene.get("label", ""), fonts.chip, W * 0.4)
        _chip(draw, chip_at[0], bus_y - 26 * SS if j > i else bus_y + 22 * SS,
              label, fonts.chip, TEXT, PANEL, colour)

    elif scene["kind"] == "process":
        cx, _ = layout.centre(index[scene["at"]])
        _chip(draw, cx, layout.fwd_bus - 6 * SS,
              _truncate(draw, scene.get("label", ""), fonts.chip, W * 0.4),
              fonts.chip, TEXT, PANEL, WARN)

    else:  # result
        cx, _ = layout.centre(index[scene["at"]])
        colour = STATUS_COLOR.get(scene.get("status"), ACCENT)
        _chip(draw, cx, layout.ret_bus + 6 * SS,
              _truncate(draw, scene.get("label", ""), fonts.chip, W * 0.4),
              fonts.chip, TEXT, PANEL, colour)

    _draw_caption(draw, fonts, scene)
    return img


def _downsample(img):
    return img.resize((OUT_W, OUT_H), Image.LANCZOS)


# ── Timing plan (shared with narrate.py) ───────────────────────────────────────
def shot_plan(board):
    """The animation as a list of (scene_index, run_frames, hold_ms)."""
    plan = []
    last = len(board["scenes"]) - 1
    for idx, scene in enumerate(board["scenes"]):
        if scene["kind"] == "message":
            run, hold = MSG_FRAMES, MSG_HOLD
        elif scene["kind"] == "process":
            run, hold = PROC_FRAMES, PROC_HOLD
        else:
            run, hold = RESULT_FRAMES, RESULT_HOLD
        if idx == last:
            hold += FINAL_HOLD
        plan.append((idx, run, hold * FRAME_MS))
    return plan


def shot_durations(board, min_shot_ms=None):
    """How long each scene runs, honouring per-scene minimums. {index: ms}."""
    minimums = min_shot_ms or {}
    out = {}
    for key, run, hold in shot_plan(board):
        wanted = max(run * FRAME_MS + hold, int(minimums.get(key, 0)))
        out[key] = -(-wanted // 10) * 10        # round up onto the 10ms grid
    return out


def iter_frames(board, fonts=None, min_shot_ms=None):
    """Every frame of the animation, in order, with its duration in ms.

    `min_shot_ms` maps a scene index to a minimum duration; that scene's final
    held frame stretches to reach it. That is how narration keeps in step — the
    picture waits for the voice rather than the other way round.
    """
    fonts = fonts or Fonts()
    durations = shot_durations(board, min_shot_ms)

    for idx, run, _hold in shot_plan(board):
        for f in range(run):
            yield _downsample(render_frame(board, idx, (f + 1) / run, fonts)), FRAME_MS
        yield (_downsample(render_frame(board, idx, 1.0, fonts)),
               max(FRAME_MS, durations[idx] - run * FRAME_MS))


def _master_palette(frames, colors=64, samples=10):
    """A palette covering the whole animation, not just one frame of it.

    Sampling evenly and quantising the montage means a colour that only appears
    in one scene — a red failure badge, say — still gets palette entries.
    """
    step = max(1, len(frames) // samples)
    picked = frames[::step][:samples] or frames[:1]
    thumb_w, thumb_h = OUT_W // 3, OUT_H // 3
    montage = Image.new("RGB", (thumb_w, thumb_h * len(picked)))
    for i, frame in enumerate(picked):
        montage.paste(frame.resize((thumb_w, thumb_h), Image.NEAREST), (0, i * thumb_h))
    return montage.quantize(colors=colors, method=Image.Quantize.MEDIANCUT,
                            dither=Image.Dither.NONE)


def render_gif(board, path=None, speed=1.0, fmt=None, min_shot_ms=None):
    """Render `board` to an animated GIF (or WebP). Returns the encoded bytes.

    `speed` > 1 plays faster. `min_shot_ms` stretches individual scenes so a
    narration track can line up with them. If `path` is given the bytes are also
    written there, and its extension picks the format unless `fmt` overrides it.
    """
    if not board.get("actors") or not board.get("scenes"):
        raise ValueError("storyboard needs at least one actor and one scene")

    fmt = (fmt or (os.path.splitext(path)[1].lstrip(".") if path else "gif") or "gif").lower()
    fmt = "WEBP" if fmt == "webp" else "GIF"

    fonts = Fonts()
    frames, durations, previous = [], [], None
    for img, ms in iter_frames(board, fonts, min_shot_ms):
        ms = max(20, int(round(ms / max(speed, 0.1) / 10)) * 10)
        signature = img.tobytes()
        if signature == previous:          # a hold — extend, don't duplicate
            durations[-1] += ms
            continue
        previous = signature
        frames.append(img)
        durations.append(ms)

    if fmt == "GIF":
        # One palette for the whole animation. Shared palettes let the encoder
        # store only what changed between frames — worth several times the file
        # size on a long GIF — and they remove palette flicker.
        frames = [f.quantize(palette=_master_palette(frames), dither=Image.Dither.NONE)
                  for f in frames]

    buf = io.BytesIO()
    extra = ({"optimize": True, "disposal": 1} if fmt == "GIF"
             else {"quality": 74, "method": 4})
    frames[0].save(buf, format=fmt, save_all=True, append_images=frames[1:],
                   duration=durations, loop=0, **extra)
    data = buf.getvalue()

    if path:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)
    return data


# ── MP4 (the only single-file option that carries sound) ──────────────────────
# Two encoders, in this order:
#   1. PyAV — FFmpeg as a *library*, loaded in-process. Nothing is executed, so
#      there is no binary for macOS Gatekeeper to quarantine.
#   2. An ffmpeg executable, if one is actually runnable.
def pyav_available():
    try:
        import av  # noqa: F401
        return True
    except Exception:
        return False


def ffmpeg_exe():
    """A runnable ffmpeg binary, or None.

    Existence is not enough: a downloaded binary can be present but blocked from
    executing, so the candidate has to answer `-version` before we trust it.
    """
    candidates = [shutil.which("ffmpeg")]
    try:
        import imageio_ffmpeg
        candidates.append(imageio_ffmpeg.get_ffmpeg_exe())
    except Exception:
        pass

    for exe in candidates:
        if not exe or not os.path.exists(exe):
            continue
        try:
            subprocess.run([exe, "-version"], stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=15, check=True)
            return exe
        except (OSError, subprocess.SubprocessError):
            continue        # present but not runnable — blocked, or wrong arch
    return None


def video_available():
    return pyav_available() or bool(ffmpeg_exe())


FFMPEG_HELP = (
    "no usable video encoder — `uv sync` installs PyAV, which needs no external "
    "binary. Failing that, install ffmpeg with `brew install ffmpeg` or "
    "`apt install ffmpeg`."
)


def _encode_with_pyav(entries, audio, fps, crf):
    """Encode in-process with PyAV. `entries` is [(PIL image, ms), …]."""
    import av
    from fractions import Fraction

    # Encoded to a real file rather than a buffer: +faststart rewrites the file
    # to put the index at the front, which needs something seekable with a name.
    tmp_dir = tempfile.TemporaryDirectory(prefix="animate-")
    out_path = os.path.join(tmp_dir.name, "out.mp4")
    # `options` would be handed to the codecs too, and AAC rejects a muxer flag
    # it does not recognise — container_options keeps it where it belongs.
    container = av.open(out_path, mode="w", format="mp4",
                        container_options={"movflags": "+faststart"})

    video = container.add_stream("libx264", rate=fps)
    video.width, video.height = OUT_W, OUT_H
    video.pix_fmt = "yuv420p"
    video.time_base = Fraction(1, fps)
    video.options = {"crf": str(crf), "preset": "medium"}

    # Every stream has to exist before the first packet is muxed — the container
    # writes its header then, and a stream added afterwards is rejected.
    ain = aout = resampler = stream_in = None
    if audio:
        source = io.BytesIO(audio) if isinstance(audio, (bytes, bytearray)) else str(audio)
        ain = av.open(source)
        stream_in = ain.streams.audio[0]
        # A WAV decodes with an *unspecified* layout ("1 channels"), and AAC
        # refuses to open without a concrete one — so name it from the channel
        # count. It also has to be set when the stream is created; assigning it
        # afterwards surfaces as a bare EINVAL from avcodec_open2.
        channels = getattr(stream_in.layout, "nb_channels", 0) or 1
        layout = {1: "mono", 2: "stereo"}.get(channels, "stereo")
        aout = container.add_stream("aac", rate=stream_in.rate, layout=layout)
        resampler = av.AudioResampler(format="fltp", layout=layout,
                                      rate=stream_in.rate)

    try:
        # Audio goes first. Muxing a packet makes the container open every codec
        # context it holds, and the AAC encoder cannot open until a frame has
        # given it a sample format — so it has to encode before the first video
        # packet is muxed. The muxer interleaves by timestamp regardless of the
        # order packets are handed to it.
        if ain is not None:
            for frame in ain.decode(stream_in):
                for resampled in resampler.resample(frame):
                    for packet in aout.encode(resampled):
                        container.mux(packet)
            for resampled in resampler.resample(None) or []:
                for packet in aout.encode(resampled):
                    container.mux(packet)
            for packet in aout.encode(None):
                container.mux(packet)

        # Constant frame rate: a beat lasting 900ms simply repeats. Duplicate
        # frames cost almost nothing once H.264 has seen the first one, and CFR
        # plays back everywhere, which variable frame timing does not.
        pts = 0
        for img, ms in entries:
            frame = av.VideoFrame.from_image(img)
            for _ in range(max(1, round(ms * fps / 1000))):
                frame.pts = pts
                pts += 1
                for packet in video.encode(frame):
                    container.mux(packet)
        for packet in video.encode(None):
            container.mux(packet)
    finally:
        if ain is not None:
            ain.close()
        container.close()

    try:
        with open(out_path, "rb") as f:
            return f.read()
    finally:
        tmp_dir.cleanup()


def _encode_with_ffmpeg(exe, entries, audio, fps, crf):
    """Encode by shelling out to an ffmpeg binary."""
    with tempfile.TemporaryDirectory(prefix="animate-") as tmp:
        files = []
        for i, (img, ms) in enumerate(entries):
            name = os.path.join(tmp, f"f{i:05d}.png")
            img.save(name)
            files.append((name, ms))

        listing = os.path.join(tmp, "frames.txt")
        with open(listing, "w") as f:
            for name, ms in files:
                f.write(f"file '{name}'\nduration {ms / 1000:.3f}\n")
            f.write(f"file '{files[-1][0]}'\n")   # concat needs the last one twice

        out_path = os.path.join(tmp, "out.mp4")
        cmd = [exe, "-y", "-f", "concat", "-safe", "0", "-i", listing]

        audio_path = None
        if audio:
            if isinstance(audio, (bytes, bytearray)):
                audio_path = os.path.join(tmp, "audio.wav")
                with open(audio_path, "wb") as f:
                    f.write(audio)
            else:
                audio_path = str(audio)
            cmd += ["-i", audio_path]

        cmd += ["-r", str(fps), "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-crf", str(crf), "-movflags", "+faststart"]
        if audio_path:
            cmd += ["-c:a", "aac", "-b:a", "128k", "-shortest"]
        cmd += [out_path]

        try:
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                           timeout=300, check=True)
        except subprocess.CalledProcessError as exc:
            detail = (exc.stderr or b"").decode(errors="replace").strip().splitlines()
            raise RuntimeError(f"ffmpeg failed: {detail[-1] if detail else exc}") from exc
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("ffmpeg timed out") from exc

        with open(out_path, "rb") as f:
            return f.read()


def render_video(board, path, speed=1.0, min_shot_ms=None, audio=None, crf=20,
                 fps=30, encoder=None):
    """Render `board` to an MP4 (H.264 + AAC). Returns the encoded bytes.

    `audio` is WAV bytes or a path to one; pass the narration track to get a
    single file with sound. Unlike the GIF this keeps full colour, since there is
    no 256-entry palette to squeeze the frames through.

    `encoder` forces "pyav" or "ffmpeg"; by default PyAV is preferred because it
    runs in-process and cannot be blocked the way a downloaded binary can.
    """
    if not board.get("actors") or not board.get("scenes"):
        raise ValueError("storyboard needs at least one actor and one scene")

    fonts = Fonts()
    entries, previous = [], None
    for img, ms in iter_frames(board, fonts, min_shot_ms):
        ms = max(20, int(round(ms / max(speed, 0.1))))
        signature = img.tobytes()
        if signature == previous:              # a hold — extend, don't re-encode
            entries[-1][1] += ms
            continue
        previous = signature
        entries.append([img, ms])

    if encoder in (None, "pyav") and pyav_available():
        try:
            data = _encode_with_pyav(entries, audio, fps, crf)
        except Exception as exc:
            exe = ffmpeg_exe() if encoder is None else None
            if not exe:
                raise RuntimeError(f"PyAV encode failed: {exc}") from exc
            data = _encode_with_ffmpeg(exe, entries, audio, fps, crf)
    else:
        exe = ffmpeg_exe()
        if not exe:
            raise RuntimeError(FFMPEG_HELP)
        data = _encode_with_ffmpeg(exe, entries, audio, fps, crf)

    if path:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)
    return data


DEMO_BOARD = {
    "title": "Kubernetes — creating a Pod",
    "actors": [
        {"id": "kubectl", "label": "kubectl",     "kind": "client"},
        {"id": "api",     "label": "API Server",  "kind": "service"},
        {"id": "etcd",    "label": "etcd",        "kind": "store"},
        {"id": "kubelet", "label": "Kubelet",     "kind": "service"},
    ],
    "scenes": [
        {"kind": "message", "from": "kubectl", "to": "api", "label": "apply pod.yaml",
         "detail": "The developer submits a Pod manifest to the API server."},
        {"kind": "process", "at": "api", "label": "Admit and validate",
         "detail": "The request is authenticated, authorised and checked against admission rules."},
        {"kind": "message", "from": "api", "to": "etcd", "label": "Persist desired state",
         "detail": "The accepted object is written to etcd as the single source of truth."},
        {"kind": "message", "from": "api", "to": "kubelet", "label": "Watch event",
         "status": "success",
         "detail": "The kubelet on the assigned node picks the Pod up through its watch."},
        {"kind": "result", "at": "kubelet", "label": "Containers running", "status": "success",
         "detail": "The kubelet pulls the image and starts the containers on the node."},
    ],
}


def main():
    parser = argparse.ArgumentParser(description="Render a storyboard JSON to an animated GIF")
    parser.add_argument("output", nargs="?", default="out/storyboard.gif", help="GIF path")
    parser.add_argument("--json", type=str, help="Storyboard JSON file (default: built-in demo)")
    parser.add_argument("--demo", action="store_true", help="Use the built-in demo storyboard")
    parser.add_argument("--png", type=str, help="Also write one still per scene")
    parser.add_argument("--speed", type=float, default=1.0, help="Playback speed multiplier")
    parser.add_argument("--audio", type=str, help="WAV to mux in (MP4 output only)")
    args = parser.parse_args()

    if args.json and not args.demo:
        with open(args.json) as f:
            board = json.load(f)
    else:
        board = DEMO_BOARD

    if args.output.lower().endswith((".mp4", ".m4v", ".mov")):
        data = render_video(board, args.output, speed=args.speed, audio=args.audio)
    else:
        data = render_gif(board, args.output, speed=args.speed)
    print(f"🎬 {args.output} — {len(data) / 1024:.0f} KB, {len(board['scenes'])} scenes")

    if args.png:
        stem, ext = os.path.splitext(args.png)
        ext = ext or ".png"
        os.makedirs(os.path.dirname(os.path.abspath(args.png)), exist_ok=True)
        fonts = Fonts()
        for i in range(len(board["scenes"])):
            out = f"{stem}-{i + 1}{ext}"
            _downsample(render_frame(board, i, 0.72, fonts)).save(out)
            print(f"🖼️  {out}")


if __name__ == "__main__":
    main()
