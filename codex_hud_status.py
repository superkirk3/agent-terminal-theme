#!/usr/bin/env python3
"""Render a Naruto-themed tmux HUD from local Codex session counters."""

from __future__ import annotations

import argparse
from datetime import datetime
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
import tomllib


BASE = Path(__file__).resolve().parent
QUOTES = [item["text"] for item in json.loads((BASE / "naruto-quotes.json").read_text())["quotes"]]
SPRITES = json.loads((BASE / "naruto-sprites.json").read_text())
PALETTE = {
    "background": "#101320",
    "orange": "#ff9d55",
    "cyan": "#65d6e8",
    "green": "#76dfaa",
    "amber": "#ffd166",
    "red": "#ff668c",
    "violet": "#c6a0ff",
    "muted": "#9aa7bf",
}


def when(value: str | None) -> float:
    if not value:
        return 0.0
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def tail_rows(path: Path, max_bytes: int = 1_500_000) -> list[dict]:
    try:
        with path.open("rb") as file:
            size = file.seek(0, os.SEEK_END)
            start = max(0, size - max_bytes)
            file.seek(start)
            if start:
                file.readline()
            data = file.read()
    except OSError:
        return []
    rows = []
    for line in data.splitlines():
        try:
            rows.append(json.loads(line))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
    return rows


def session_meta(path: Path) -> dict:
    try:
        with path.open("rb") as file:
            row = json.loads(file.readline())
        return row.get("payload", {}) if row.get("type") == "session_meta" else {}
    except (OSError, json.JSONDecodeError):
        return {}


def recent_paths(home: Path, since: float) -> list[Path]:
    root = home / "sessions"
    if not root.exists():
        return []
    paths = []
    for path in root.rglob("rollout-*.jsonl"):
        try:
            modified = path.stat().st_mtime
        except OSError:
            continue
        if modified >= since - 30:
            paths.append((modified, path))
    return [path for _, path in sorted(paths, reverse=True)[:40]]


def session_by_id(home: Path, session_id: str) -> Path | None:
    if not re.fullmatch(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", session_id):
        return None
    return next((home / "sessions").rglob(f"rollout-*-{session_id}.jsonl"), None)


def choose_session(paths: list[Path], cwd: str, since: float, *, cli_only: bool = False) -> Path | None:
    for path in paths:
        meta = session_meta(path)
        source = meta.get("source")
        if isinstance(source, str) and ("cli" in source.lower() or "tui" in source.lower()):
            if not cwd or meta.get("cwd") == cwd:
                return path
    if cli_only:
        return None
    for path in paths:
        meta = session_meta(path)
        if meta.get("cwd") == cwd and not isinstance(meta.get("source"), dict):
            return path
    return None


def config_model(home: Path) -> tuple[str, str]:
    try:
        config = tomllib.loads((home / "config.toml").read_text())
        return str(config.get("model", "Codex")), str(config.get("model_reasoning_effort", ""))
    except (OSError, tomllib.TOMLDecodeError):
        return "Codex", ""


def summarize(rows: list[dict], now: float, fallback_model: tuple[str, str], previous: dict | None = None) -> dict:
    model, effort = fallback_model
    previous = previous or {}
    model, effort = previous.get('model', model), previous.get('effort', effort)
    started, ended = previous.get('_started', 0.0), previous.get('ended', 0.0)
    last_turn_speed = previous.get('speed')
    latest_limits: tuple[float, dict] | None = previous.get('limits')
    context_used = previous.get('context_used')
    total_tokens = previous.get('total_tokens')
    context_window = previous.get('context_window')
    approval = previous.get('approval', 'on-request')
    for row in rows:
        timestamp = when(row.get("timestamp"))
        payload = row.get("payload") or {}
        kind = payload.get("type") if row.get("type") == "event_msg" else None
        if row.get("type") == "turn_context":
            model = payload.get("model") or model
            effort = payload.get("effort") or effort
            approval = payload.get("approval_policy") or approval
        elif kind == "task_started":
            started = timestamp
        elif kind in {"task_complete", "turn_aborted", "task_cancelled"}:
            ended = timestamp
        elif kind == "token_count":
            info = payload.get("info") or {}
            usage = info.get("total_token_usage") or {}
            last = info.get("last_token_usage") or {}
            output = last.get("output_tokens")
            if (isinstance(output, (int, float)) and output > 0 and started
                    and 0 < timestamp - started < 600):
                last_turn_speed = output / (timestamp - started)
            total = usage.get("total_tokens")
            if isinstance(total, (int, float)):
                total_tokens = int(total)
            window = info.get("model_context_window")
            if isinstance(window, (int, float)) and window > 0:
                context_window = int(window)
            inputs = last.get("input_tokens")
            outputs = last.get("output_tokens")
            if isinstance(window, (int, float)) and window > 0 and isinstance(inputs, (int, float)):
                context_used = max(0, min(100, round(100 * (inputs + (outputs or 0)) / window)))
            if payload.get("rate_limits"):
                latest_limits = (timestamp, payload["rate_limits"])

    busy = bool(started and started > ended)
    return {
        "busy": busy,
        "model": str(model),
        "effort": str(effort),
        "speed": last_turn_speed,
        "limits": latest_limits,
        "context_used": context_used,
        "total_tokens": total_tokens,
        "context_window": context_window,
        "approval": approval,
        "ended": ended,
        "_started": started,
    }


_SESSION_COUNTERS: dict[Path, dict] = {}


def session_counters(path: Path | None, now: float, fallback_model: tuple[str, str]) -> dict:
    """Retain turn metadata across large tool outputs without rereading the log."""
    if path is None:
        return summarize([], now, fallback_model)
    try:
        stat = path.stat()
        identity = (stat.st_dev, stat.st_ino)
        cached = _SESSION_COUNTERS.get(path)
        if cached is None or cached['identity'] != identity or stat.st_size < cached['offset']:
            cached = {'identity': identity, 'offset': 0,
                      'state': summarize([], now, fallback_model)}
        state = cached['state']
        with path.open('rb') as file:
            file.seek(cached['offset'])
            while True:
                offset = file.tell()
                line = file.readline()
                if not line or not line.endswith(b'\n'):
                    # A writer may still be appending this JSON record.
                    cached['offset'] = offset
                    break
                try:
                    row = json.loads(line)
                except (ValueError, UnicodeDecodeError):
                    continue
                if row.get('type') in ('turn_context', 'event_msg'):
                    state = summarize([row], now, fallback_model, state)
        cached['state'] = state
        _SESSION_COUNTERS[path] = cached
        return dict(state)
    except OSError:
        return summarize([], now, fallback_model)


def limit_percent(limits: tuple[float, dict] | None, minutes: int, now: float) -> str:
    if not limits:
        return "--"
    timestamp, data = limits
    for window in (data.get("primary"), data.get("secondary")):
        if not isinstance(window, dict) or window.get("window_minutes") != minutes:
            continue
        value = window.get("used_percent")
        if not isinstance(value, (int, float)):
            return "--"
        reset = window.get("resets_at")
        if isinstance(reset, (int, float)) and now >= reset:
            return "--"
        suffix = "~" if now - timestamp > 900 else ""
        return f"{round(value):d}%{suffix}"
    return "--"


def reset_progress(limits: tuple[float, dict] | None, minutes: int, now: float) -> tuple[str, str]:
    if not limits:
        return "--", ""
    _, data = limits
    for window in (data.get("primary"), data.get("secondary")):
        if not isinstance(window, dict) or window.get("window_minutes") != minutes:
            continue
        reset = window.get("resets_at")
        if not isinstance(reset, (int, float)) or reset <= now:
            return "--", ""
        period = minutes * 60
        progress = max(0, min(99, round(100 * (now - (reset - period)) / period)))
        remaining = max(0, round(reset - now))
        days, remainder = divmod(remaining, 86400)
        hours = (remainder + 3599) // 3600
        if hours >= 24:
            days += 1
            hours = 0
        countdown = f"剩{days}天{hours}时" if days and hours else f"剩{days}天" if days else f"剩{hours}小时"
        return f"{progress}%", countdown
    return "--", ""


def usage_color(value: str) -> str:
    match = re.match(r"^(\d+)%", value)
    if not match:
        return PALETTE["muted"]
    percent = int(match.group(1))
    if percent >= 80:
        return PALETTE["red"]
    if percent >= 50:
        return PALETTE["amber"]
    return PALETTE["green"]


def paint(text: str, color: str, plain: bool, *, bold: bool = False, background: str | None = None) -> str:
    clean = text.replace("#", "＃").replace("\n", " ").replace("\r", " ")
    if plain:
        return clean
    weight = ",bold" if bold else ""
    backdrop = f",bg={background}" if background else ""
    return f"#[fg={color}{backdrop}{weight}]{clean}#[default]"


def usage_bar(value: str) -> str:
    match = re.match(r"^(\d+)%", value)
    if not match:
        return "▱" * 8
    used = max(0, min(8, round(int(match.group(1)) * 8 / 100)))
    return "▰" * used + "▱" * (8 - used)


def usage_background(value: str) -> str:
    color = usage_color(value)
    if color == PALETTE["green"]:
        return "#19392f"
    if color == PALETTE["amber"]:
        return "#40321f"
    if color == PALETTE["red"]:
        return "#402335"
    return "#262b36"


def avatar_cell(pixels: list[str], plain: bool) -> str:
    colors = [tuple(int(color[index : index + 2], 16) for index in (1, 3, 5)) for color in pixels]
    first = colors[0]
    second = max(colors, key=lambda color: sum((a - b) ** 2 for a, b in zip(color, first)))
    for _ in range(3):
        groups = [[], []]
        for color in colors:
            distances = [sum((a - b) ** 2 for a, b in zip(color, center)) for center in (first, second)]
            groups[0 if distances[0] <= distances[1] else 1].append(color)
        if not groups[0] or not groups[1]:
            break
        first, second = (
            tuple(round(sum(color[channel] for color in group) / len(group)) for channel in range(3))
            for group in groups
        )
    foreground, background = (first, second) if len(groups[0]) <= len(groups[1]) else (second, first)
    bits = (1, 2, 3, 7, 4, 5, 6, 8)
    codepoint = 0
    for color, bit in zip(colors, bits):
        distance_foreground = sum((a - b) ** 2 for a, b in zip(color, foreground))
        distance_background = sum((a - b) ** 2 for a, b in zip(color, background))
        if distance_foreground < distance_background:
            codepoint |= 1 << (bit - 1)
    glyph = chr(0x2800 + codepoint)
    if plain:
        return glyph
    fg = "#%02x%02x%02x" % foreground
    bg = "#%02x%02x%02x" % background
    return f"#[fg={fg},bg={bg}]{glyph}"


def render_avatar(state: dict, now: float, row: int, plain: bool) -> str:
    frame = "talking" if state["busy"] and int(now) % 2 else "idle"
    pixels = SPRITES[frame]
    output = []
    for x in range(0, len(pixels[0]), 2):
        cell = [pixels[row * 4 + y][x + dx] for dx in range(2) for y in range(4)]
        output.append(avatar_cell(cell, plain))
    return "".join(output) + ("" if plain else "#[default]")


def git_branch(cwd: str) -> str:
    if not cwd:
        return ""
    try:
        result = subprocess.run(
            ["git", "-C", cwd, "symbolic-ref", "--quiet", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=0.5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return result.stdout.strip()[:30] if result.returncode == 0 else ""


def current_state(args: argparse.Namespace, now: float, home: Path) -> dict:
    paths = [args.log] if args.log else recent_paths(home, args.since)
    selected = args.log or choose_session(
        paths, args.cwd, args.since,
        cli_only=os.environ.get("CODEX_HUD_CLI_ONLY") == "1",
    )
    fallback = config_model(home)
    state = session_counters(selected, now, fallback)
    state["session_id"] = session_meta(selected).get("id", "") if selected else ""
    if not state["limits"]:
        for path in paths:
            limits = session_counters(path, now, fallback)["limits"]
            if limits:
                state["limits"] = limits
                break
    return state


def cached_state(args: argparse.Namespace, now: float, home: Path) -> dict:
    if not args.cache:
        return current_state(args, now, home)
    lock_path = args.cache.with_suffix(".lock")
    with lock_path.open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            cached = json.loads(args.cache.read_text())
            if 0 <= now - cached["time"] < 0.9:
                return cached["state"]
        except (OSError, ValueError, KeyError, TypeError):
            pass
        state = current_state(args, now, home)
        with tempfile.NamedTemporaryFile("w", dir=args.cache.parent, prefix=".codex-hud-", delete=False) as temporary:
            json.dump({"time": now, "state": state}, temporary)
            temporary_path = Path(temporary.name)
        os.replace(temporary_path, args.cache)
        return state


def render_row(state: dict, now: float, row: int, plain: bool, cwd: str) -> str:
    avatar = render_avatar(state, now, row, plain)
    week = limit_percent(state["limits"], 10080, now)
    five_hour = limit_percent(state["limits"], 300, now)
    speed = "--" if state["speed"] is None else f"≈{state['speed']:.1f}"
    context = "--" if state["context_used"] is None else f"{state['context_used']}%"
    context_label = "--" if context == "--" else f"≈{context}"
    if row == 0:
        activity = "待命中" if not state["busy"] else "工作中"
        model = state["model"][:22]
        if state["effort"]:
            model += f"/{state['effort']}"
        details = "  ".join(
            [
                paint(" 漩涡鸣人 ", PALETTE["orange"], plain, bold=True, background="#432719"),
                paint(f" {activity} ", PALETTE["green"] if not state["busy"] else PALETTE["cyan"], plain),
                paint(f" ◆ {model} ", PALETTE["violet"], plain, bold=True, background="#2b2440"),
            ]
        )
    elif row == 1:
        quote = QUOTES[int(now // 9) % len(QUOTES)]
        details = paint(f" 「{quote}」", PALETTE["muted"], plain)
    elif row == 2:
        details = paint(f" 周已用 {usage_bar(week)} {week} ", usage_color(week), plain, bold=True, background=usage_background(week))
    elif row == 3:
        details = "  ".join(
            [
                paint(f" 5h 已用 {usage_bar(five_hour)} {five_hour} ", usage_color(five_hour), plain, background=usage_background(five_hour)),
                paint(f" 上下文已用 {usage_bar(context)} {context_label} ", usage_color(context), plain, background=usage_background(context)),
            ]
        )
    else:
        items = [paint(f" ⚡ 近45秒 {speed} tok/s ", PALETTE["cyan"], plain, bold=True, background="#17333d")]
        if state["total_tokens"] is not None:
            items.append(paint(f" 累计 {state['total_tokens']:,} tok ", PALETTE["muted"], plain))
        branch = git_branch(cwd)
        if branch:
            items.append(paint(f" ⎇ {branch} ", PALETTE["violet"], plain))
        details = "  ".join(items)
    return avatar + "  " + details


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--segment", choices=("all", "mascot", "metrics", *(f"row{i}" for i in range(5))), default="all")
    parser.add_argument("--since", type=float, default=0)
    parser.add_argument("--cwd", default="")
    parser.add_argument("--plain", action="store_true")
    parser.add_argument("--log", type=Path, help="Use one session log for a preview")
    parser.add_argument("--cache", type=Path, help="Share one sampled state across tmux rows")
    args = parser.parse_args()
    now = time.time()
    home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
    state = cached_state(args, now, home)
    if args.segment == "all":
        rows = range(5)
    elif args.segment == "mascot":
        rows = [0]
    elif args.segment == "metrics":
        rows = [2]
    else:
        rows = [int(args.segment[-1])]
    for row in rows:
        print(render_row(state, now, row, args.plain, args.cwd))


if __name__ == "__main__":
    main()
