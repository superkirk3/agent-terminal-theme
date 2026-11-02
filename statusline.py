#!/usr/bin/env python3
"""Portable Claude Code status line for macOS and WSL."""

import base64
import fcntl
import json
import os
from pathlib import Path
import random
import re
import subprocess
import sys
import tempfile
import time
import unicodedata
import zlib

from theme_config import STYLES, effective_preferences, session_key
import theme_sessions


RESET = "\x1b[0m"
BOLD = "\x1b[1m"
ITALIC = "\x1b[3m"
# Mecha HUD palette: steel frame, cyan telemetry, amber caution, red alert.
PALETTE = {
    "text": (226, 234, 252),
    "muted": (118, 132, 168),
    "label": (104, 146, 214),
    "frame": (58, 78, 116),
    "dark": (38, 48, 70),
    "ink": (14, 16, 26),
    "cyan": (0, 229, 255),
    "blue": (64, 156, 255),
    "green": (72, 245, 160),
    "amber": (255, 190, 40),
    "orange": (255, 132, 32),
    "red": (255, 64, 96),
    "accent": (255, 132, 32),  # replaced by the cast character's colour
    "accent_dim": (137, 75, 31),
}
QUOTE_PAIRS = (
    ("Believe it!", "说到做到，这就是我的忍道！"),
    ("I'll become Hokage!", "总有一天，我要成为火影！"),
    ("Never give up!", "别想让我放弃！"),
    ("I won't leave you alone!", "我不会让你独自一人！"),
)
TALK_FRAMES = {
    "happy": tuple(f"happy-talk-{frame:02d}" for frame in range(17)),
    "calm": tuple(f"calm-talk-{frame:02d}" for frame in range(16)),
    "urgent": tuple(f"urgent-talk-{frame:02d}" for frame in range(8)),
    "frenzy": tuple(f"frenzy-{frame:02d}" for frame in range(8)),
    "rage": tuple(f"rage-talk-{frame:02d}" for frame in range(9)),
}
THOUGHT_STORY = (
    [("HAPPY", f"thought-natural-{frame:02d}") for frame in (0, 1, 4, 7)]
    + [("LAUGH", f"thought-joy-{frame:02d}") for frame in range(0, 9)]
    + [("RASENGAN", f"rasengan-{frame:02d}") for frame in range(7)]
    + [("HAPPY", f"thought-natural-{frame:02d}") for frame in (9, 10, 12, 15, 20)]
    + [("LAUGH", f"thought-joy-{frame:02d}") for frame in range(9)]
    + [("HAPPY", f"thought-natural-{frame:02d}") for frame in (23, 24)]
)
# Frame stems per animation. Kitty-protocol terminals loop them natively;
# the iTerm/ANSI paths step one frame per refresh.
ANIMATIONS = {
    "happy-talk": TALK_FRAMES["happy"],
    "frenzy": TALK_FRAMES["frenzy"],
    "rage-talk": TALK_FRAMES["rage"],
    "thinking": tuple(source for _, source in THOUGHT_STORY),
    **{f"{mood}-idle": (f"{mood}-idle",) for mood in ("happy", "calm", "frenzy", "rage")},
}
ESCAPE = re.compile(r"\x1b\[[0-9;]*m")
HEAT = ("cyan", "cyan", "green", "amber", "red")
SCAN = (0, 1, 2, 3, 4, 3, 2, 1)
MARKER = "UZUMAKI·NARUTO"
# Portrait size in terminal cells (columns, rows).
AVATAR = (10, 5)
PENDING_IMAGE = []
PENDING_UPLOADS = []
PORTRAIT = []
# Kitty graphics via Unicode placeholders (Ghostty, kitty): upload once, then
# print placeholder text; tmux moves it like any other text.
KITTY_PLACEHOLDER = "\U0010EEEE"
KITTY_DIACRITICS = (0x0305, 0x030D, 0x030E, 0x0310, 0x0312)  # values 0-4
# Claude Code drops to 256 colours inside tmux, so an image id is a 256-colour
# index plus a most-significant byte carried by a third diacritic.
KITTY_MSB, KITTY_MSB_DIACRITIC = 7, 0x033F
KITTY_GAP_MS = 120
KITTY_TTL = 600  # re-upload now and then in case the terminal dropped the image

# Cast: one anime character per Claude session (cast.json + tools/build_cast.py).
CAST_DIR = Path(__file__).parent / "assets" / "cast"
CAST_STATES = ("done", "idle", "sleep", "think", "talk", "tool", "wait", "error", "power")
# Missing animation -> try these in order.
CAST_FALLBACK = {"done": ("idle",), "sleep": ("idle",), "wait": ("talk", "idle"),
                 "error": ("think", "idle"), "power": ("tool", "idle"),
                 "think": ("idle",), "talk": ("idle",), "tool": ("idle",)}
CAST_LABELS = {"done": "DONE", "idle": "CHILL", "sleep": "ZZZ", "think": "THINKING",
               "talk": "TALK", "tool": "ACTION", "wait": "NEEDS YOU", "error": "OOPS",
               "power": "LIMIT"}
CAST_TONES = {"done": "green", "idle": "blue", "sleep": "muted", "think": "amber",
              "talk": "cyan", "tool": "accent", "wait": "red", "error": "red", "power": "red"}
CAST_ACTIVE = 300  # sessions seen this recently keep their character to themselves
# Same heuristic as tmux-agents: a permission prompt or question at the bottom.
WAIT_RE = re.compile(r"❯\s*1\.\s*Yes|\bDo you (want|trust)\b|enter to select", re.I)
_CAST, _KEYS = [], []
_GIT_CACHE = {}


def width(text):
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1
               for c in ESCAPE.sub("", text))


def clip(text, limit):
    if limit < 1:
        return ""
    if width(text) <= limit:
        return text
    out = ""
    used = 0
    for part in re.split(r"(\x1b\[[0-9;]*m)", text):
        if ESCAPE.fullmatch(part):
            out += part
            continue
        for c in part:
            cell_width = 2 if unicodedata.east_asian_width(c) in "WF" else 1
            if used + cell_width > limit - 1:
                return out + "…" + RESET
            out += c
            used += cell_width
    return out


def number(value):
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def token_count(value):
    n = number(value)
    if n is None:
        return "—"
    if n >= 1_000_000:
        return f"{n / 1_000_000:g}M"
    if n >= 1000:
        return f"{n / 1000:.0f}k"
    return str(int(n))


def countdown(reset_at, now):
    seconds = number(reset_at)
    if seconds is None:
        return ""
    left = max(0, int(seconds - now))
    if left >= 86400:
        return f"T-{left // 86400}D{left % 86400 // 3600:02d}H"
    return f"T-{left // 3600:02d}:{left % 3600 // 60:02d}"


def rgb(text, value, enabled, bg=None, bold=False):
    if not enabled:
        return text
    code = "\x1b[38;2;%d;%d;%dm" % value
    if bg:
        code += "\x1b[48;2;%d;%d;%dm" % bg
    return (BOLD if bold else "") + code + text + RESET


def chip(text, tone, enabled):
    """Slanted badge drawn with Powerline wedges."""
    if not enabled:
        return f"[{text}]"
    bg = PALETTE[tone]
    return (rgb("\ue0ba", bg, enabled) + rgb(f" {text} ", PALETTE["ink"], enabled, bg, True) +
            rgb("\ue0bc", bg, enabled))


def level_color(pct):
    if pct is None:
        return "muted"
    return "cyan" if pct < 50 else "amber" if pct < 80 else "red"


def heat(position):
    # Blend across HEAT so a fuller gauge reaches warmer colors.
    scaled = min(1, max(0, position)) * (len(HEAT) - 1)
    low = int(scaled)
    high = min(low + 1, len(HEAT) - 1)
    a, b = PALETTE[HEAT[low]], PALETTE[HEAT[high]]
    return tuple(round(a[j] + (b[j] - a[j]) * (scaled - low)) for j in range(3))


def segment_glyph():
    """Gauge segment: Meslo's ▮ has side gaps; Maple Mono (WezTerm) lacks ▮,
    and its fallback fills the cell, so use ▪ there."""
    glyph = os.environ.get("CLAUDE_STATUSLINE_SEGMENT")
    if glyph:
        return glyph
    return "▪" if outer_terminal() == "wezterm" else "▮"


def gauge(pct, enabled, cells=24, pace=None, tone=None):
    filled = 0 if pct is None else min(cells, max(0, round(pct * cells / 100)))
    if pct:
        filled = max(1, filled)
    if not enabled:
        return "[" + "#" * filled + "-" * (cells - filled) + "]"
    pace_cell = None if pace is None else min(cells - 1, max(0, int(pace * cells / 100)))
    glyph = segment_glyph()
    parts = [rgb("▕", PALETTE["frame"], enabled)]
    for i in range(cells):
        if pct is not None and i == pace_cell:
            color = PALETTE["text"]
        elif i < filled:
            color = PALETTE[tone] if tone else heat(i / max(1, cells - 1))
        else:
            color = PALETTE["dark"]
        parts.append(rgb(glyph, color, enabled))
    parts.append(rgb("▏", PALETTE["frame"], enabled))
    return "".join(parts)


def quota_data(data, window, now):
    """Return (percent, countdown, pace percent, ahead of pace)."""
    if not isinstance(data, dict):
        data = {}
    pct = number(data.get("used_percentage"))
    if pct is None:
        return None, "", None, False
    pct = min(100, max(0, pct))
    reset_at = number(data.get("resets_at"))
    if reset_at is None:
        return pct, "", None, False
    pace = min(100, max(0, 100 * (1 - (reset_at - now) / window)))
    return pct, countdown(reset_at, now), pace, pct > pace + 10


def mood_from_usage(*percentages):
    valid = [value for value in percentages if value is not None]
    if valid and max(valid) >= 100:
        return "rage"
    if valid and max(valid) >= 80:
        return "urgent"
    if valid and max(valid) >= 50:
        return "calm"
    return "happy"


def portrait_selection(mood, state, now, native=False):
    """Return (animation key, frame stem for this second, label).

    native: the terminal plays the animation itself, so the thought story's
    per-frame labels cannot stay in sync and collapse to THINKING.
    """
    tick = int(now)
    if state == "IDLE":
        key = f"{'frenzy' if mood == 'urgent' else mood}-idle"
        return key, f"naruto-{key}", "FRENZY" if mood == "urgent" else ""
    if mood == "rage":
        key, label = "rage-talk", "RAGE"
    elif mood == "urgent":
        key, label = "frenzy", "FRENZY"
    elif state == "SPEAKING":
        key, label = "happy-talk", "TALK"
    else:
        expression, source = THOUGHT_STORY[tick % len(THOUGHT_STORY)]
        return "thinking", f"naruto-{source}", "THINKING" if native else expression
    frames = ANIMATIONS[key]
    return key, f"naruto-{frames[tick % len(frames)]}", label


def quote(now, pairs=QUOTE_PAIRS):
    slot = int(now // 12)
    pair = pairs[(slot // 2) % len(pairs)]
    return pair[slot % 2]


def load_cast():
    if not _CAST:
        try:
            cast = json.loads((Path(__file__).parent / "cast.json").read_text(encoding="utf-8"))
            cast = {name: spec for name, spec in cast.items() if (CAST_DIR / name).is_dir()}
        except (OSError, ValueError):
            cast = {}
        _CAST.append(cast)
    return _CAST[0]


def choose_character(cast, session, cwd, now, pinned=None):
    """Stable character per session, avoiding ones other open sessions show."""
    pinned = os.environ.get("CLAUDE_STATUSLINE_CAST", "").lower() if pinned is None else pinned
    if pinned in cast:
        return pinned
    names = list(cast)
    key = session or cwd or "default"
    registry = Path(tempfile.gettempdir()) / f"claude-cast-{os.getuid()}.json"
    try:
        with open(registry, "a+", encoding="utf-8") as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            stream.seek(0)
            try:
                seen = json.loads(stream.read() or "{}")
            except ValueError:
                seen = {}
            seen = {k: v for k, v in seen.items()
                    if isinstance(v, list) and v[0] in cast and now - v[1] < 86400}
            if key in seen:
                name = seen[key][0]
            else:
                busy = {v[0] for k, v in seen.items() if now - v[1] < CAST_ACTIVE}
                name = random.choice([n for n in names if n not in busy] or names)
            seen[key] = [name, now]
            stream.seek(0)
            stream.truncate()
            stream.write(json.dumps(seen))
        return name
    except OSError:
        return names[zlib.crc32(key.encode()) % len(names)]


def rex_status():
    """Root OSC 7501 record of this Rex terminal; None outside Rex or on failure.

    Claude Code reports its own state (blocked on a permission, error, ...)
    when the terminal answers the 7501 probe, and Rex stores it per block.
    """
    if not os.environ.get("REX_BLOCK"):
        return None
    try:
        out = subprocess.run(["rex", "block", "call", "program_status"], capture_output=True,
                             text=True, timeout=0.5, check=True).stdout
        records = json.loads(out).get("records") or []
    except (OSError, subprocess.SubprocessError, ValueError, AttributeError):
        return None
    root = [r for r in records if isinstance(r, dict) and not r.get("id")]
    return root[0] if root else None


def waiting_for_user():
    pane = os.environ.get("TMUX_PANE")
    if not pane:
        return False
    lines = [line for line in tmux("capture-pane", "-p", "-t", pane).split("\n") if line.strip()]
    return bool(WAIT_RE.search("\n".join(lines[-20:])))


def errored(records, age):
    """Last message is a failed tool result or an interrupt, and it is recent."""
    messages = [r for r in records if r.get("type") in ("user", "assistant")]
    if age > 30 or not messages or messages[-1]["type"] != "user":
        return False
    content = (messages[-1].get("message") or {}).get("content") or ""
    if isinstance(content, str):
        return content.startswith("[Request interrupted")
    return any(isinstance(part, dict) and (
        (part.get("type") == "tool_result" and part.get("is_error")) or
        (part.get("type") == "text" and str(part.get("text", "")).startswith("[Request interrupted")))
        for part in content)


def cast_state(state, records, age, levels):
    reported = rex_status()
    if reported:
        # Exact state from the agent itself; no screen scraping needed.
        if reported.get("state") == "blocked":
            return "wait"
        if reported.get("state") == "error":
            return "error"
    elif state in ("USING TOOL", "IDLE") and waiting_for_user():
        return "wait"
    if errored(records, age):
        return "error"
    if state != "IDLE" and max([v for v in levels if v is not None] or [0]) >= 80:
        return "power"
    if state != "IDLE":
        return {"THINKING": "think", "SPEAKING": "talk", "USING TOOL": "tool"}.get(state, "think")
    messages = [r for r in records if r.get("type") in ("user", "assistant")]
    if messages and messages[-1]["type"] == "assistant" and age < 60:
        return "done"
    return "sleep" if age > 600 else "idle"


def cast_animation(character, wanted):
    """First state with built frames, following CAST_FALLBACK."""
    for state in (wanted, *CAST_FALLBACK.get(wanted, ())):
        if any((CAST_DIR / character / state).glob("*.png")):
            return state
    return None


def tail_records(path, count=40):
    if not path:
        return [], 0
    try:
        p = Path(path)
        age = time.time() - p.stat().st_mtime
        with p.open("rb") as stream:
            stream.seek(0, os.SEEK_END)
            end = stream.tell()
            stream.seek(max(0, end - 128 * 1024))
            lines = stream.read().splitlines()
        if end > 128 * 1024:
            lines = lines[1:]
        records = []
        for line in lines[-count:]:
            try:
                item = json.loads(line)
                if isinstance(item, dict) and not item.get("isSidechain"):
                    records.append(item)
            except (ValueError, UnicodeDecodeError):
                pass
        return records, age
    except (OSError, ValueError):
        return [], 0


MODES = {"default": "STANDARD", "acceptEdits": "ACCEPT EDITS", "plan": "PLAN",
         "bypassPermissions": "BYPASS", "auto": "AUTO", "dontAsk": "DONT ASK"}


def permission_mode(path):
    """Latest permission mode recorded in the transcript.

    The status line JSON has no permission mode, but Claude Code writes it on
    each user turn and on every Shift+Tab change.
    """
    if not path:
        return ""
    try:
        with open(path, "rb") as stream:
            stream.seek(0, os.SEEK_END)
            stream.seek(max(0, stream.tell() - 1024 * 1024))
            tail = stream.read().decode("utf-8", "replace")
    except OSError:
        return ""
    found = re.findall(r'"permissionMode":\s*"([A-Za-z]+)"', tail)
    return found[-1] if found else ""


def activity(records, age):
    messages = [r for r in records if r.get("type") in ("user", "assistant")]
    if not messages or age > 600:
        return "IDLE"
    last = messages[-1]
    if last["type"] == "user":
        content = (last.get("message") or {}).get("content") or ""
        if isinstance(content, str) and content.startswith("[Request interrupted"):
            return "IDLE"
        return "THINKING"
    message = last.get("message") or {}
    content = message.get("content") or []
    if not isinstance(content, list):
        content = []
    if message.get("stop_reason") == "tool_use" or any(
        isinstance(part, dict) and part.get("type") == "tool_use" for part in content
    ):
        return "USING TOOL"
    if age <= 3 and any(
        isinstance(part, dict) and part.get("type") == "text" for part in content
    ):
        return "SPEAKING"
    return "IDLE"


def tokens_per_second(records):
    messages = [r for r in records if r.get("type") == "assistant"]
    if not messages:
        return None
    last = messages[-1]
    message = last.get("message") or {}
    msg_id = message.get("id")
    if not msg_id:
        return None
    group = [r for r in messages if (r.get("message") or {}).get("id") == msg_id]
    output = max(number(((r.get("message") or {}).get("usage") or {}).get("output_tokens")) or 0
                 for r in group)
    if output <= 0:
        return None
    # Streamed chunks land milliseconds apart, so time the reply from the
    # record that triggered it rather than from its own first chunk.
    first = records.index(group[0])
    trigger = next((r for r in reversed(records[:first]) if r.get("timestamp")), group[0])
    try:
        from datetime import datetime
        start = datetime.fromisoformat(trigger["timestamp"].replace("Z", "+00:00"))
        end = datetime.fromisoformat(group[-1]["timestamp"].replace("Z", "+00:00"))
        seconds = (end - start).total_seconds()
        return output / seconds if 0 < seconds < 600 else None
    except (KeyError, TypeError, ValueError):
        return None


def git_info(cwd):
    if not cwd or not Path(cwd).is_dir():
        return None
    cached = _GIT_CACHE.get(cwd)
    if cached and time.monotonic() - cached[0] < 5:
        return cached[1]
    def run(*args):
        try:
            return subprocess.run(["git", "-C", cwd, "--no-optional-locks", *args],
                                  capture_output=True, text=True, timeout=0.4,
                                  check=True).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            return ""
    if run("rev-parse", "--is-inside-work-tree") != "true":
        _GIT_CACHE[cwd] = (time.monotonic(), None)
        return None
    branch = run("symbolic-ref", "--short", "HEAD") or run("rev-parse", "--short", "HEAD")
    dirty = bool(run("status", "--porcelain"))
    result = (branch or "?", dirty)
    _GIT_CACHE[cwd] = (time.monotonic(), result)
    return result


def portrait(path):
    rows = Path(path).read_text(encoding="utf-8").splitlines()
    if not rows:
        raise ValueError(f"Empty portrait: {path}")
    return rows


def tmux(*args):
    try:
        return subprocess.run(["tmux", *args], capture_output=True, text=True,
                              timeout=0.5, check=True).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


_OUTER = []


def outer_terminal():
    """Lower-case name of the terminal emulator, looking through tmux."""
    if not _OUTER:
        program = os.environ.get("TERM_PROGRAM", "").lower()
        client = ""
        if program == "tmux" and os.environ.get("TMUX"):
            # The attached client's XTVERSION ("ghostty 1.4.0", "iTerm2 3.7.6").
            # Pane env and the global env only remember the terminal that
            # started the tmux server, so they are checked after this.
            client = tmux("display-message", "-p", "-t", os.environ.get("TMUX_PANE", ""),
                          "#{client_termtype}").strip().lower()
        if client:
            name = re.match(r"[a-z0-9]*", client).group()
            program = "iterm.app" if name == "iterm2" else name
        elif os.environ.get("WEZTERM_PANE"):
            program = "wezterm"
        elif os.environ.get("LC_TERMINAL") == "iTerm2":
            program = "iterm.app"
        elif program == "tmux" and os.environ.get("TMUX"):
            program = tmux("show-environment", "-g", "TERM_PROGRAM").strip().partition("=")[2].lower()
        _OUTER.append(program)
    return _OUTER[0]


def image_protocol():
    """"kitty", "iterm" or "" for how the portrait can be drawn as a real image."""
    mode = os.environ.get("CLAUDE_STATUSLINE_IMAGE", "auto").lower()
    if mode == "off":
        return ""
    from portable_images import terminal_kind
    kind = terminal_kind()
    if kind == "windowsterminal":
        return ""  # SIXEL passthrough disabled after live viewport corruption.
    if kind == "rex":
        # Rex does not render the Unicode placements this path requires.
        return ""
    if outer_terminal() in ("ghostty", "kitty", "rex"):  # all answer the kitty graphics query
        return "kitty"
    if not os.environ.get("TMUX_PANE"):
        return ""
    if mode == "on" or outer_terminal() in ("iterm.app", "wezterm"):
        return "iterm"
    return ""


def draw_image_later(png, offset, size, marker=MARKER):
    """Fork a detached child that draws png over the blank portrait area.

    Claude Code redraws the status line after this script exits, so the child
    waits, finds the header row with capture-pane and writes an iTerm2 inline
    image through tmux passthrough at that screen position.
    """
    pane = os.environ["TMUX_PANE"]
    sys.stdout.flush()
    if os.fork():
        return
    try:
        os.setsid()
        devnull = os.open(os.devnull, os.O_RDWR)
        for fd in (0, 1, 2):
            os.dup2(devnull, fd)
        time.sleep(0.3)
        info = tmux("display-message", "-p", "-t", pane,
                    "#{pane_tty} #{pane_top} #{pane_left} #{pane_height}").split()
        lines = tmux("capture-pane", "-p", "-t", pane).split("\n")
        row = next(i for i in range(len(lines) - 1, -1, -1)
                   if marker in lines[i] and lines[i].index(marker) >= offset)
        column = lines[row].index(marker) - offset
        if row + size[1] > int(info[3]):
            raise ValueError("Portrait area is off screen")
        status = 0
        if tmux("show-options", "-gv", "status-position").strip() == "top":
            setting = tmux("show-options", "-gv", "status").strip()
            status = 1 if setting == "on" else int(setting) if setting.isdigit() else 0
        data = Path(png).read_bytes()
        osc = (f"\x1b]1337;File=inline=1;width={size[0]};height={size[1]};"
               f"preserveAspectRatio=1;doNotMoveCursor=1;size={len(data)}:").encode()
        osc += base64.b64encode(data) + b"\x07"
        y, x = status + int(info[1]) + row + 1, int(info[2]) + column + 1
        move = f"\x1b[{y};{x}H"
        if x > 1:
            # Windows ConPTY consumes cursor moves and forwards the image at its
            # last rendered cursor. Changing the blank cell left of the portrait
            # makes it render the cursor there first. Alternate two blank glyphs
            # so the cell differs on every refresh.
            flip = Path(tempfile.gettempdir()) / f"naruto-anchor-{os.getuid()}-{pane[1:]}"
            blank = " " if flip.exists() else "⠀"
            flip.unlink() if flip.exists() else flip.touch()
            move = f"\x1b[{y};{x - 1}H{blank}" + move
        payload = b"\x1b7" + move.encode() + osc + b"\x1b8"
        payload = b"\x1bPtmux;" + payload.replace(b"\x1b", b"\x1b\x1b") + b"\x1b\\"
        with open(info[0], "wb") as tty:
            tty.write(payload)
    except (OSError, ValueError, StopIteration, IndexError):
        pass
    finally:
        os._exit(0)


def animation(key):
    """(frame paths, gaps in ms) for a legacy key or a "character/state" cast key."""
    if "/" in key:
        folder = CAST_DIR / key
        frames = sorted(folder.glob("*.png"))
        try:
            gaps = json.loads((folder / "meta.json").read_text())["gaps"]
        except (OSError, ValueError, KeyError):
            gaps = []
        return frames, gaps if len(gaps) == len(frames) else [KITTY_GAP_MS] * len(frames)
    frames = [Path(__file__).parent / "assets" / "png" / f"naruto-{stem}.png"
              for stem in ANIMATIONS[key]]
    return frames, [KITTY_GAP_MS] * len(frames)


def kitty_id(key):
    if not _KEYS:
        _KEYS.extend(sorted(ANIMATIONS))
        _KEYS.extend(f"{name}/{state}" for name in sorted(load_cast()) for state in CAST_STATES)
    return (KITTY_MSB << 24) | (16 + _KEYS.index(key))


def kitty_rows(key):
    image_id = kitty_id(key)
    colour = "\x1b[38;5;%dm" % (image_id & 255)
    # First cell carries row, column 0 and the id MSB; the rest of the row is inferred.
    return [colour + KITTY_PLACEHOLDER + chr(KITTY_DIACRITICS[y]) + chr(KITTY_DIACRITICS[0]) +
            chr(KITTY_MSB_DIACRITIC) + KITTY_PLACEHOLDER * (AVATAR[0] - 1) + "\x1b[39m"
            for y in range(AVATAR[1])]


def terminal_path():
    """Device of the terminal Claude Code draws on, e.g. /dev/ttys012, or None.

    Claude Code starts the status line in a session of its own, so /dev/tty
    does not open; the nearest ancestor that has a terminal is Claude Code.
    """
    try:
        with open("/dev/tty", "rb", buffering=0) as tty:
            return os.ttyname(tty.fileno())
    except OSError:
        pass
    pid = os.getppid()
    for _ in range(4):
        try:
            out = subprocess.run(["ps", "-o", "ppid=,tty=", "-p", str(pid)], capture_output=True,
                                 text=True, timeout=0.5).stdout.split()
        except (OSError, subprocess.SubprocessError):
            return None
        if len(out) != 2:
            return None
        if out[1] not in ("?", "??", "-"):
            return "/dev/" + out[1]
        pid = int(out[0])
    return None


def kitty_target(session):
    """(client key, tty path, wrap for tmux), or None without a terminal."""
    pane = os.environ.get("TMUX_PANE")
    if pane:
        info = tmux("display-message", "-p", "-t", pane,
                    "#{client_pid}-#{client_created} #{pane_tty}").split()
        return (info[0], info[1], True) if len(info) == 2 and info[0] != "-" else None
    name = terminal_path()
    return (f"{name.replace('/', '_')}-{session}", name, False) if name else None


def kitty_ready(key, session):
    """Queue the animation upload unless this client already has it."""
    target = kitty_target(session)
    if not target:
        return False
    client, tty, wrap = target
    frames, gaps = animation(key)
    try:
        newest = int(max(frame.stat().st_mtime for frame in frames))
    except (OSError, ValueError):
        return False
    stamp = Path(tempfile.gettempdir()) / (
        f"naruto-kgp-{os.getuid()}-{client}-{kitty_id(key)}-{newest}")
    try:
        if time.time() - stamp.stat().st_mtime < KITTY_TTL:
            return True
        stamp.unlink()
    except FileNotFoundError:
        pass
    try:
        os.close(os.open(stamp, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600))
    except FileExistsError:
        return True  # another pane is uploading it
    PENDING_UPLOADS.append((tty, wrap, kitty_id(key), frames, gaps, stamp))
    return True


def kitty_payload(image_id, frames, gaps, wrap):
    def apc(ctrl, data=b""):
        seq = b"\x1b_G" + ctrl.encode() + (b";" + data if data else b"") + b"\x1b\\"
        if wrap:
            seq = b"\x1bPtmux;" + seq.replace(b"\x1b", b"\x1b\x1b") + b"\x1b\\"
        return seq

    def send(action, png, extra=""):
        # q=2 on every chunk: no terminal reply may reach the pane as input.
        data = base64.standard_b64encode(png)
        chunks = [data[i:i + 4096] for i in range(0, len(data), 4096)]
        out = b""
        for n, chunk in enumerate(chunks):
            more = int(n < len(chunks) - 1)
            out += apc(f"a={action},f=100,i={image_id},q=2{extra},m={more}" if n == 0
                       else f"m={more},q=2", chunk)
        return out

    out = send("t", frames[0].read_bytes())
    for frame, gap in zip(frames[1:], gaps[1:]):
        out += send("f", frame.read_bytes(), f",z={gap}")
    if len(frames) > 1:
        out += apc(f"a=a,i={image_id},r=1,z={gaps[0]},q=2")  # root frame gap
        out += apc(f"a=a,i={image_id},s=3,v=1,q=2")          # loop forever
    return out + apc(f"a=p,U=1,i={image_id},p=1,c={AVATAR[0]},r={AVATAR[1]},q=2")


def upload_later():
    """Fork a detached child that writes the queued uploads to the terminal."""
    sys.stdout.flush()
    if os.fork():
        return
    try:
        os.setsid()
        devnull = os.open(os.devnull, os.O_RDWR)
        for fd in (0, 1, 2):
            os.dup2(devnull, fd)
        for tty, wrap, image_id, frames, gaps, stamp in PENDING_UPLOADS:
            try:
                payload = kitty_payload(image_id, frames, gaps, wrap)
                # O_NOCTTY: this child is a session leader and must not adopt the tty.
                with open(os.open(tty, os.O_WRONLY | os.O_NOCTTY), "wb") as out:
                    out.write(payload)
            except OSError:
                stamp.unlink(missing_ok=True)
    finally:
        os._exit(0)


def terminal_dimensions():
    try:
        with open("/dev/tty", "rb", buffering=0) as tty:
            terminal = os.get_terminal_size(tty.fileno())
    except OSError:
        terminal = os.terminal_size((100, 30))

    def dimension(name, fallback):
        try:
            value = int(os.environ.get(name, ""))
            return value if value > 0 else fallback
        except ValueError:
            return fallback

    return dimension("COLUMNS", terminal.columns), dimension("LINES", terminal.lines)


def render(data, now=None, forced=None):
    now = time.time() if now is None else now
    agent = 'codex' if data.get('_agent') == 'codex' else 'claude'
    try:
        identity = session_key(agent, data.get('session_id', ''))
        aliases = [session_key(agent, value) for value in data.get('_theme_session_aliases', [])]
    except (ValueError, TypeError):
        identity, aliases = '', []
    selection = effective_preferences(agent, session_id=identity, session_aliases=aliases)
    columns, lines = terminal_dimensions()
    enabled = not os.environ.get("NO_COLOR") and os.environ.get("TERM") != "dumb"
    workspace = data.get("workspace") or {}
    cwd = workspace.get("current_dir") or data.get("cwd") or ""
    if identity and data.get('_theme_register', True):
        theme_sessions.register(agent, identity, cwd, selection, aliases,
                                observer=data.get('_theme_observer'))
    model_data = data.get("model") or {}
    model = model_data.get("display_name") or "Unknown"
    effort_data = data.get("effort") or {}
    effort = (effort_data.get("level") if isinstance(effort_data, dict) else effort_data)
    effort = effort or data.get("effort_level") or ""
    context = data.get("context_window") or {}
    size = number(context.get("context_window_size")) or (
        1_000_000 if "[1m]" in (model_data.get("id") or "").lower() else 200_000
    )
    used = number(context.get("total_input_tokens"))
    pct = number(context.get("used_percentage"))
    if pct is None and used is not None:
        pct = 100 * used / size
    if used is None and pct is not None:
        used = pct * size / 100
    if pct is not None:
        pct = min(100, max(0, pct))
    records, age = tail_records(data.get("transcript_path"))
    state = forced or data.get("_activity_state") or activity(records, age)
    animated = state != "IDLE"
    speed = data.get("_tokens_per_second") if "_tokens_per_second" in data else tokens_per_second(records)
    rate = data.get("rate_limits") or {}
    home = str(Path.home())
    path = "~" + cwd[len(home):] if cwd == home or cwd.startswith(home + os.sep) else cwd
    git = git_info(cwd)
    permission = str(data.get("permission_mode") or data.get("permissionMode") or
                     permission_mode(data.get("transcript_path")) or "default")
    access = MODES.get(permission, permission.replace("_", " ").upper())
    q5, q5_reset, q5_pace, q5_ahead = quota_data(rate.get("five_hour"), 18000, now)
    q7, q7_reset, q7_pace, q7_ahead = quota_data(rate.get("seven_day"), 604800, now)
    mood = mood_from_usage(q5, q7)
    protocol = (data.get("_image_protocol") if "_image_protocol" in data else image_protocol()) if enabled else ""
    portrait_key, portrait_stem, expression = portrait_selection(
        mood, state, now, native=protocol == "kitty")
    display = expression or mood.upper()
    display_tone = {"HAPPY": "green", "LAUGH": "amber", "TALK": "cyan", "RASENGAN": "blue",
                    "FRENZY": "red", "RAGE": "red", "CALM": "blue",
                    "THINKING": "amber"}.get(display, "green")
    marker, marker_tone, quotes, cast_png = MARKER, "orange", QUOTE_PAIRS, None
    person = "漩涡鸣人"
    cast = {} if selection['cast'] == 'legacy' else load_cast()
    if cast and not forced:
        name = choose_character(cast, data.get("session_id") or "", cwd, now, pinned=selection['cast'])
        spec = cast[name]
        wanted = data.get("_cast_state") or cast_state(state, records, age, (q5, q7, pct))
        shown = cast_animation(name, wanted)
        if shown:
            PALETTE["accent"] = tuple(spec.get("accent") or PALETTE["orange"])
            # Accent mixed into the ink background, for card borders.
            PALETTE["accent_dim"] = tuple(round(a * 0.55 + b * 0.45) for a, b in
                                          zip(PALETTE["accent"], PALETTE["ink"]))
            portrait_key = f"{name}/{shown}"
            frames = sorted((CAST_DIR / portrait_key).glob("*.png"))
            from portable_images import frame_at
            cast_png = frame_at(CAST_DIR / portrait_key, now) or frames[0]
            display = (spec.get("labels") or {}).get(wanted) or CAST_LABELS[wanted]
            display_tone = CAST_TONES[wanted]
            # Ensemble packs: each state names who plays it.
            who = ((spec.get("states") or {}).get(shown) or {}).get("who")
            member = (spec.get("members") or {}).get(who) or {}
            marker = member.get("marker") or spec.get("marker") or name.upper()
            person = member.get("name") or spec.get("name") or ""
            marker_tone = "accent"
            quotes = [tuple(pair) for pair in member.get("quotes") or spec.get("quotes") or []
                      ] or QUOTE_PAIRS
    PORTRAIT[:] = [portrait_key, cast_png]
    display = data.get("_display_label") or display
    state_tone = {"IDLE": "green", "THINKING": "amber", "USING TOOL": "cyan",
                  "SPEAKING": "orange"}.get(state, "amber")
    model_name = re.sub(r"\s*\([^)]*context\)", "", model, flags=re.I).upper()
    core = " · ".join([model_name, "CTX N/A" if data.get("_context_unknown") else token_count(size).upper()] +
                      ([str(effort).upper()] if effort else []))
    ctx_note = f"{token_count(used)}/{token_count(size)}".upper() if pct is not None else ""
    gauges = (("CTX", pct, ctx_note, None, False),
              ("5H", q5, q5_reset, q5_pace, q5_ahead),
              ("7D", q7, q7_reset, q7_pace, q7_ahead))
    # API-key and gateway sessions get no rate_limits; show prompt cache and cost.
    quota_known = data.get("_agent") == "codex" or bool(rate) and (q5 is not None or q7 is not None)
    cache = data.get("prompt_cache") or {}
    hit = number(cache.get("hit_ratio"))
    hit = None if hit is None else min(100, max(0, hit * 100))
    expires = number(cache.get("expires_at"))
    if expires is not None and cache.get("warm") and expires > now:
        cache_note = f"WARM {int(expires - now) // 60}:{int(expires - now) % 60:02d}"
    else:
        cache_note = "COLD" if hit is not None else ""
    cost_data = data.get("cost") or {}
    cost = number(cost_data.get("total_cost_usd"))
    elapsed = int((number(cost_data.get("total_duration_ms")) or 0) // 60000)

    def paint(text, tone, bold=False):
        return rgb(text, PALETTE[tone], enabled, bold=bold)

    def readout(value, note, ahead, good_high=False):
        if value is None:
            return paint("N/A ", "muted") + paint(" ┊ ", "frame") + paint("NO SIGNAL", "muted")
        tone = (("green" if value >= 80 else "amber" if value >= 50 else "red") if good_high
                else level_color(value))
        out = paint(f"{value:03.0f}%", tone, True)
        if note:
            out += paint(" ┊ ", "frame") + paint(note, "muted")
        if ahead:
            out += paint(" ▲OVER PACE", "amber", True)
        return out

    def rule(text, total):
        return text + " " + paint("━" * max(2, total - width(text) - 1), "frame")

    def fit(text, limit):
        # Keep the end of long values; cut paths at a "/" ("…/project/dir").
        if width(text) <= limit:
            return text
        while text and width(text) > limit - 1:
            text = text[1:]
        cut = text.find("/")
        return "…" + (text[cut:] if 0 <= cut < len(text) - 1 else text)

    def panel(total, wide):
        # Two aligned columns: identity on the left, telemetry on the right.
        cells = 20 if wide else 10
        right_width = 6 + cells + 2 + 4 + 3 + 9 + 11  # label, gauge, readout, note, pace
        left_width = max(16, total - right_width - 3 - 3 - 5)
        git_text = (git[0] + (" ● MODIFIED" if git[1] else " ✓ CLEAN")) if git else "NO REPO"
        git_tone = ("amber" if git[1] else "green") if git else "muted"
        left = [
            ("PATH", fit(path or "?", left_width), "text"),
            ("GIT", fit(git_text, left_width), git_tone),
            ("CORE", fit(core, left_width), "text"),
            ("MODE", access, "red" if access == "BYPASS" else "text"),
        ]
        left_width = min(left_width, max(width(value) for _, value, _ in left))
        speed_value = (paint(f"{speed:05.1f}", "text", True) if speed is not None
                       else paint("---.-", "muted")) + paint(" T/S", "muted")
        metrics = [(label, gauge(value, enabled, cells, pace) + " " + readout(value, note, ahead))
                   for label, value, note, pace, ahead in gauges]
        if not quota_known:
            cost_value = (paint(f"${cost:.2f}", "text", True) if cost is not None
                          else paint("$-.--", "muted"))
            if elapsed:
                cost_value += paint(" ┊ ", "frame") + paint(
                    f"{elapsed // 60}H{elapsed % 60:02d}M" if elapsed >= 60 else f"{elapsed}M",
                    "muted")
            metrics[1:] = [
                ("CACHE", gauge(hit, enabled, cells, tone="green") + " " +
                 readout(hit, cache_note, False, good_high=True)),
                ("COST", cost_value),
            ]
        metrics.append(("LAST" if data.get("_agent") == "codex" else "OUT", speed_value))
        rows = [""]
        for i, ((label, value, tone), (right_label, metric)) in enumerate(zip(left, metrics)):
            spine = "┗━" if i == len(left) - 1 else "┣╸"
            rows.append(paint(spine, "frame") + " " + paint(label.ljust(5), "label", True) +
                        paint(value, tone) + " " * (left_width - width(value)) + " " +
                        paint("│", "frame") + " " + paint(right_label.ljust(6), "label", True) +
                        metric)
        # Header spans the body width so both right edges line up.
        span = min(total, max(width(row) for row in rows[1:]))
        dot = "○" if animated and int(now) % 2 else "◉"
        scan = "".join(paint("▪", state_tone if i == SCAN[int(now) % len(SCAN)] else "dark")
                       for i in range(5)) + " " if animated else ""
        status = scan + paint(f"{dot} {state}", state_tone, True)
        title = chip(marker, marker_tone, enabled) + " " + chip(display, display_tone, enabled)
        line = (ITALIC if enabled else "") + paint(f"» {quote(now, quotes)}", "muted")
        # Widen the header for the quote when the body is narrow.
        span = max(span, min(total, width(title) + width(line) + width(status) + 8))
        if width(title) + width(line) + width(status) + 8 <= span:
            title += " " + paint("━━", "frame") + " " + line
        rows[0] = rule(title, span - width(status) - 1) + " " + status
        return rows

    # --- Alternative layouts: same data as panel(), five rows each. ---------
    name_text = marker.replace("·", " ")
    quote_text = (ITALIC if enabled else "") + paint(quote(now, quotes), "muted")
    speed_text = f"{speed:.1f} t/s" if speed is not None else "— t/s"
    if data.get("_agent") == "codex":
        speed_text = "LAST " + speed_text
    spent = (f"{elapsed // 60}h{elapsed % 60:02d}m" if elapsed >= 60 else f"{elapsed}m") if elapsed else ""
    cost_text = " · ".join(t for t in ((f"${cost:.2f}" if cost is not None else ""), spent) if t)
    git_tone = ("amber" if git[1] else "green") if git else "muted"
    git_label = ("\ue0a0 " + git[0] + (" ●" if git[1] else "")) if git else "no repo"
    mode_tone = "red" if access == "BYPASS" else "label"

    def spread(left, right, total):
        gap = total - width(left) - width(right)
        return left + " " * gap + right if gap >= 2 else left

    def usage():
        """(label, percent, note, tone override) for the telemetry rows."""
        rows = [("ctx", pct, ctx_note.lower(), None)]
        if quota_known:
            rows += [("5h", q5, q5_reset.lower(), None), ("7d", q7, q7_reset.lower(), None)]
        else:
            tone = None if hit is None else "green" if hit >= 80 else "amber" if hit >= 50 else "red"
            rows.append(("cache", hit, cache_note.lower(), tone))
        return rows

    def bar(value, tone, cells, full, empty):
        filled = 0 if value is None else min(cells, max(0, round(value * cells / 100)))
        if value:
            filled = max(1, filled)
        return paint(full * filled, tone or level_color(value)) + paint(empty * (cells - filled), "dark")

    def meter(label, value, note, tone, cells, full, empty, label_width=0):
        tone = tone or level_color(value)
        out = paint(label.ljust(label_width), "muted") + " " + bar(value, tone, cells, full, empty) + \
            " " + (paint(f"{value:.0f}%", tone, True) if value is not None else paint("n/a", "muted"))
        return out + (paint(f"  {note}", "muted") if note else "")

    def minimal(total):
        # Typography only: no frames, colour marks meaning.
        head = (paint(name_text, "accent", True) + "  " + paint(person, "muted") + "   " +
                paint(display.lower(), display_tone, True))
        place = paint(fit(path or "?", max(16, total - width(git_label) - 4)), "text") + \
            "   " + paint(git_label, git_tone)
        model_row = paint(core.lower(), "muted") + "   " + paint(access.lower(), mode_tone)
        meters = usage()
        ctx_row = meter(*meters[0], cells=28, full="━", empty="─", label_width=5)
        tail = "    ".join(meter(*m, cells=10, full="━", empty="─", label_width=5) for m in meters[1:])
        extra = "   ".join(t for t in ((cost_text if not quota_known else ""), speed_text) if t)
        return [spread(head, quote_text, total), place, model_row, ctx_row,
                tail + ("    " if tail else "") + paint(extra, "muted")]

    def card(total):
        # Rounded card: title in the top edge, quote in the bottom edge.
        w = max(40, min(total, 80))
        inner = w - 4

        def edge(text):
            return paint(text, "accent_dim")

        def line(content):
            content = clip(content, inner)
            return edge("│") + " " + content + " " * max(0, inner - width(content)) + " " + edge("│")

        title = (" " + paint(name_text, "accent", True) + " " + paint(person, "muted") +
                 edge(" · ") + paint(display, display_tone, True) + " ")
        top = edge("╭─") + title + edge("─" * max(1, w - 3 - width(title))) + edge("╮")
        meters = "   ".join(meter(*m, cells=6 if i else 10, full="▰", empty="▱")
                           for i, m in enumerate(usage()))
        if width(meters) > inner:  # quota reset countdowns go first when space is short
            meters = "   ".join(meter(*(m if i == 0 else (*m[:2], "", m[3])), cells=6 if i else 10,
                                      full="▰", empty="▱") for i, m in enumerate(usage()))
        right = paint(cost_text, "muted") if not quota_known and cost_text else ""
        tail = " " + paint(speed_text, "muted") + " "
        quote_part = " " + clip(quote_text, max(4, w - width(tail) - 8)) + " "
        bottom = (edge("╰─") + quote_part + edge("─" * max(1, w - 4 - width(quote_part) - width(tail))) +
                  tail + edge("─╯"))
        return [top,
                line(spread(paint(fit(path or "?", inner - width(git_label) - 3), "text"),
                            paint(git_label, git_tone), inner)),
                line(spread(paint(core, "text"), paint(access, mode_tone, True), inner)),
                line(spread(meters, right, inner) if width(meters) + width(right) + 2 <= inner
                     else meters),
                bottom]

    def pill(text, bg, fg="ink", bold=True):
        return (rgb("\ue0b6", PALETTE[bg], enabled) +
                rgb(f" {text} ", PALETTE[fg], enabled, PALETTE[bg], bold) +
                rgb("\ue0b4", PALETTE[bg], enabled))

    def pills(total):
        # Rounded pills (Nerd Font half circles); accent pill carries the name.
        meters = usage()
        status = [pill(f"{m[0].upper()} {m[1]:.0f}%" if m[1] is not None else f"{m[0].upper()} n/a",
                       "dark", m[3] or level_color(m[1])) for m in meters[1:]]
        if not quota_known and cost_text:
            status.append(pill(cost_text, "dark", "text", False))
        status.append(pill(speed_text, "dark", "muted", False))
        ctx = meters[0]
        return [pill(name_text, "accent") + " " + pill(display, display_tone) + "  " + quote_text,
                pill(fit(path or "?", max(16, total - width(git_label) - 10)), "dark", "text", False) +
                " " + pill(git_label, "dark", git_tone),
                pill(core, "dark", "text", False) + " " + pill(access, "dark", mode_tone),
                pill(f"CTX {ctx[1]:.0f}%" if ctx[1] is not None else "CTX n/a", "dark",
                     level_color(ctx[1])) + " " + bar(ctx[1], None, 24, "▰", "▱") +
                paint(f"  {ctx[2]}" if ctx[2] else "", "muted"),
                " ".join(status)]

    style = selection['style']
    if style == "random":
        # Like the cast: stable per session, different across sessions.
        style = STYLES[zlib.crc32((data.get("session_id") or cwd or "x").encode()) % len(STYLES)]
    layouts = {"minimal": minimal, "card": card, "pill": pills,
               "mecha": lambda total: panel(total, avatar_mode != "small" and columns >= 110)}

    avatar_mode = os.environ.get("CLAUDE_STATUSLINE_AVATAR", "auto").lower()
    png = cast_png or Path(__file__).parent / "assets" / "png" / f"{portrait_stem}.png"
    if enabled and avatar_mode != "compact" and columns >= 60 and lines >= 12:
        avatar_width = AVATAR[0]
        rows = layouts.get(style, layouts["mecha"])(max(40, min(columns - avatar_width - 3, 120)))
        marker_prefix = rows[0].partition(marker)[0] if marker in rows[0] else ""
        image_offset = avatar_width + 2 + width(ESCAPE.sub("", marker_prefix))
        avatar = None
        if data.get("_text_panel_only"):
            return "\n".join(clip(row, columns) for row in rows)
        if protocol == "kitty" and kitty_ready(portrait_key, data.get("session_id") or ""):
            avatar = kitty_rows(portrait_key)
        elif png.is_file() and protocol == "iterm":
            # Braille blanks survive Claude Code trimming leading spaces;
            # draw_image_later fills the area with the PNG.
            avatar = ["\u2800" * avatar_width] * len(rows)
            PENDING_IMAGE[:] = [(png, image_offset, AVATAR, marker)]
        elif cast_png is not None:
            try:
                avatar = portrait(cast_png.with_suffix(".ans"))
            except (OSError, ValueError):
                avatar = None
            if protocol == "sixel" and avatar:
                from portable_images import draw_sixel_later
                draw_sixel_later(cast_png, image_offset, AVATAR, marker)
        elif cast_png is None:
            try:
                avatar = portrait(Path(__file__).parent / "assets" / "ansi" / f"{portrait_stem}.ans")
            except (OSError, ValueError):
                avatar = None
        if avatar and len(avatar) >= len(rows):
            return "\n".join(f"{avatar[i]}  {clip(row, columns - avatar_width - 2)}"
                             for i, row in enumerate(rows))
        if cast_png is not None:
            # Cast characters have no ANSI art: keep the panel, drop the portrait.
            return "\n".join(clip(row, columns) for row in rows)

    face = "(≡>o<≡)" if animated and int(now) % 2 else {
        "happy": "(≡^‿^≡)", "calm": "(≡•_•≡)", "urgent": "(≡>_<≡)", "rage": "(╬ಠ益ಠ)",
    }[mood]

    def plain(label, value, note=""):
        return f"{label} " + gauge(value, False, 10) + " " + (
            f"{value:03.0f}%" if value is not None else "N/A") + (f" {note}" if note else "")

    git_text = (git[0] + (" *" if git[1] else "")) if git else "NO REPO"
    first = paint(f"🍥 {face}", marker_tone, True) + "  " + paint(marker, marker_tone, True) + \
        f" · {display} · {state} · {quote(now, quotes)}"
    second = f"GIT {git_text} │ CORE {core} │ " + plain("CTX", pct, ctx_note)
    third = plain("5H", q5, q5_reset) + " │ " + plain("7D", q7, q7_reset)
    return "\n".join(clip(row, columns) for row in (first, second, third))


def main():
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            data = {}
    except ValueError:
        data = {}
    forced = os.environ.get("CLAUDE_STATUSLINE_DEMO_STATE")
    print(render(data, forced=forced if forced in {"IDLE", "THINKING", "SPEAKING", "USING TOOL"} else None))
    if PENDING_IMAGE:
        draw_image_later(*PENDING_IMAGE[0])
    if PENDING_UPLOADS:
        upload_later()


if __name__ == "__main__":
    main()
