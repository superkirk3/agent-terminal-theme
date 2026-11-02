#!/usr/bin/env python3
"""Agent theme Codex launcher: wrap interactive TUI runs, pass through CLI tools."""

from __future__ import annotations

import os
import json
from pathlib import Path
import subprocess
import sys


DIRECT_COMMANDS = {
    "agents", "exec", "review", "login", "logout", "mcp", "plugin",
    "app-server", "remote-control", "app", "completion", "update",
    "doctor", "debug", "apply", "queue", "archive", "delete",
    "migrate-rollouts", "migrate-nfs-db", "unarchive", "cloud",
    "exec-server", "features", "help", "sandbox",
}
VALUE_OPTIONS = {
    "-c", "--config", "-i", "--image", "-m", "--model",
    "-p", "--profile", "-s", "--sandbox", "-C", "--cd",
    "--remote", "--remote-auth-token-env", "--local-provider",
    "--add-dir", "--enable", "--disable",
}


def first_positional(args: list[str]) -> str:
    index = 0
    while index < len(args):
        argument = args[index]
        if argument in VALUE_OPTIONS:
            index += 2
        elif argument == "--":
            return args[index + 1] if index + 1 < len(args) else ""
        elif argument.startswith("-"):
            index += 1
        else:
            return argument
    return ""


def use_hud(args: list[str], stdin_tty: bool, stdout_tty: bool) -> bool:
    if not stdin_tty or not stdout_tty:
        return False
    if any(argument in {"-h", "--help", "-V", "--version"} for argument in args):
        return False
    return first_positional(args) not in DIRECT_COMMANDS


def terminal_program(environment: dict[str, str]) -> str:
    program = environment.get("TERM_PROGRAM", "").lower()
    if program == "tmux" and environment.get("TMUX"):
        result = subprocess.run(
            ["tmux", "show-environment", "-g", "TERM_PROGRAM"],
            capture_output=True, text=True, check=False,
        )
        if result.returncode == 0 and result.stdout.startswith("TERM_PROGRAM="):
            program = result.stdout.partition("=")[2].strip().lower()
    if not program and environment.get("ITERM_SESSION_ID"):
        program = "iterm.app"
    return program


def main() -> None:
    arguments = sys.argv[1:]
    manifest = Path.home()/'.local/state/agent-theme/install.json'
    try:
        configured = json.loads(manifest.read_text()).get('real_codex')
    except (OSError, ValueError):
        configured = None
    default = (Path.home() / '.codex/packages/standalone/current/bin/codex'
               if sys.platform == 'darwin' else Path.home() / '.local/bin/codex-real')
    real = Path(os.environ.get('AGENT_THEME_REAL_CODEX') or configured or default)
    if not real.is_file():
        print(f"Codex CLI not found: {real}", file=sys.stderr)
        raise SystemExit(2)
    if os.environ.get('CODEX_THEME_DISABLE') or not use_hud(arguments, sys.stdin.isatty(), sys.stdout.isatty()):
        os.execv(str(real), [str(real), *arguments])

    environment = os.environ.copy()
    environment['AGENT_THEME_REAL_CODEX'] = str(real)
    hud = Path.home() / '.local/share/agent-theme/codex-hud.py'
    if not hud.is_file():
        print(f"Codex HUD not found: {hud}", file=sys.stderr)
        raise SystemExit(2)
    os.execve(sys.executable, [sys.executable, str(hud), *arguments], environment)


if __name__ == "__main__":
    main()
