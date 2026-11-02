"""Create an image/text footer in the tmux server directly facing the terminal."""
from pathlib import Path
import shlex
import subprocess
import sys

ROOT = Path(__file__).resolve().parent


def tmux(socket, *args, check=True):
    return subprocess.run(['tmux', '-S', socket, *args], check=check,
                          capture_output=True, text=True)


def supported(socket):
    return tmux(socket, 'display-message', '-p', '#{sixel_support}',
                check=False).stdout.strip() == '1'


def remove(socket, panes, owner):
    for pane in reversed(panes):
        value = tmux(socket, 'show-options', '-pqv', '-t', pane,
                     '@agent-theme-owner', check=False).stdout.strip()
        if value == owner:
            tmux(socket, 'kill-pane', '-t', pane, check=False)


def create(socket, target, panel, state_dir, watch_socket, cwd, env=None):
    state_dir = Path(state_dir)
    state = str(state_dir/'portrait.json')
    owner = str(state_dir)
    prefix = ['env', 'AGENT_THEME_TERMINAL=windowsterminal']
    for key in ('AGENT_THEME_STYLE', 'AGENT_THEME_CAST', 'CODEX_HOME'):
        if env and env.get(key):
            prefix.append(key+'='+env[key])
    panel = [*prefix, *panel, '--native-state', state,
             '--watch-socket', watch_socket]
    image = [sys.executable, str(ROOT/'native_avatar.py'), '--state', state,
             '--watch-socket', watch_socket, '--stats', str(state_dir/'image.json')]
    panes = []
    try:
        text = tmux(socket, 'split-window', '-d', '-v', '-l', '5', '-c', cwd,
                    '-t', target, '-P', '-F', '#{pane_id}', shlex.join(panel)).stdout.strip()
        panes.append(text)
        tmux(socket, 'set-option', '-p', '-t', text, '@agent-theme-owner', owner)
        picture = tmux(socket, 'split-window', '-d', '-h', '-b', '-l', '12',
                       '-c', cwd, '-t', text, '-P', '-F', '#{pane_id}',
                       shlex.join(image)).stdout.strip()
        panes.append(picture)
        tmux(socket, 'set-option', '-p', '-t', picture, '@agent-theme-owner', owner)
        for pane in panes:
            tmux(socket, 'select-pane', '-t', pane, '-P', 'bg=#282c34')
        return panes
    except Exception:
        remove(socket, panes, owner)
        raise
