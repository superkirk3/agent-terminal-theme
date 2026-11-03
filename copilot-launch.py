#!/usr/bin/env python3
"""Agent theme Copilot launcher: preserve the original CLI and noninteractive use."""
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
if not (ROOT/'theme_config.py').is_file(): ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

DIRECT = {'help', 'version', 'login', 'logout', 'update', 'init', 'plugin', 'mcp', 'completion'}


def use_hud(args, stdin_tty, stdout_tty):
    if not stdin_tty or not stdout_tty: return False
    if any(arg in ('-h', '--help', '-v', '--version', '-p', '--prompt', '--headless', '--acp', '--stdio')
           or arg.startswith(('--prompt=', '--headless=', '--acp=')) for arg in args): return False
    return not args or args[0] not in DIRECT


def main():
    try:
        manifest = json.loads((Path.home()/'.local/state/agent-theme/install.json').read_text())
    except (OSError, ValueError): manifest = {}
    real = Path(os.environ.get('AGENT_THEME_REAL_COPILOT') or manifest.get('real_copilot') or Path.home()/'.local/bin/copilot')
    if not real.is_file() or real.resolve().is_relative_to(ROOT):
        raise SystemExit('Original Copilot CLI not found. Reinstall with --copilot-bin PATH.')
    args = sys.argv[1:]
    if os.environ.get('COPILOT_THEME_DISABLE') or not use_hud(args, sys.stdin.isatty(), sys.stdout.isatty()):
        os.execv(str(real), [str(real), *args])
    environment = dict(os.environ, AGENT_THEME_AGENT='copilot', AGENT_THEME_REAL_COPILOT=str(real))
    os.execve(sys.executable, [sys.executable, str(ROOT/'codex-hud.py'), *args], environment)


if __name__ == '__main__': main()
