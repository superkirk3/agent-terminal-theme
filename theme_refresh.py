"""Replace only verified theme renderer panes, preserving every agent process."""
import os
from pathlib import Path
import re
import shlex
import stat
import subprocess

ROOT = Path(__file__).resolve().parent
PYTHON = re.compile(r'python(?:3(?:\.\d+)?)?', re.I)


def tmux(socket, *arguments):
    return subprocess.run(['tmux', '-S', str(socket), *arguments], capture_output=True,
                          text=True, timeout=3)


def socket_paths():
    roots = {Path(os.environ.get('TMUX_TMPDIR') or '/tmp')/f'tmux-{os.getuid()}'}
    current = os.environ.get('TMUX', '').split(',')[0]
    candidates = {Path(current)} if current else set()
    if current: roots.add(Path(current).parent)
    for root in roots:
        candidates.update(root.glob('*'))
    for path in sorted(candidates):
        try:
            info = path.stat()
            if info.st_uid == os.getuid() and stat.S_ISSOCK(info.st_mode): yield path
        except OSError: pass


def renderer_command(command):
    try:
        tokens = shlex.split(command)
        # tmux formats quote a shell-command argument as one complete word.
        if len(tokens) == 1: tokens = shlex.split(tokens[0])
    except ValueError: return None
    allowed = {ROOT/'codex-pane.py', Path.home()/'.local/share/agent-theme/codex-pane.py'}
    index = 0
    if tokens and Path(tokens[0]).name == 'env':
        index = 1
        while index < len(tokens):
            value = tokens[index]
            if value in ('-u', '--unset'): index += 2
            elif value.startswith('--unset=') or re.match(r'[A-Za-z_][A-Za-z0-9_]*=', value): index += 1
            elif value == '--':
                index += 1
                break
            else: break
    if index >= len(tokens) or not PYTHON.fullmatch(Path(tokens[index]).name): return None
    index += 1
    while index < len(tokens) and tokens[index] in ('-u', '-B', '-E', '-s', '-S', '-I', '-O', '-OO'):
        index += 1
    return tokens if index < len(tokens) and Path(tokens[index]) in allowed else None


def refresh():
    count = 0
    for socket in socket_paths():
        try:
            listing = tmux(socket, 'list-panes', '-a', '-F',
                           '#{pane_id}\t#{pane_pid}\t#{pane_current_command}\t#{pane_start_command}')
            if listing.returncode: continue
            for line in listing.stdout.splitlines():
                parts = line.split('\t', 3)
                if len(parts) != 4: continue
                pane, pid, current, command = parts
                tokens = renderer_command(command)
                if not tokens or not pid.isdigit() or not PYTHON.fullmatch(current): continue
                running = subprocess.run(['ps', '-p', pid, '-o', 'command='], capture_output=True,
                                         text=True, timeout=1)
                if not renderer_command(running.stdout.strip()): continue
                inner = socket
                if '--watch-socket' in tokens:
                    inner = Path(tokens[tokens.index('--watch-socket')+1])
                owner = tmux(inner, 'display-message', '-p', '-t', 'agent:0.0', '#{pane_id}\t#{pane_pid}')
                values = owner.stdout.strip().split('\t')
                if owner.returncode or len(values) != 2 or not values[1].isdigit(): continue
                if inner == socket and values[0] == pane: continue
                if '--owner-pid' in tokens:
                    tokens[tokens.index('--owner-pid')+1] = values[1]
                else: tokens += ['--owner-pid', values[1]]
                result = tmux(socket, 'respawn-pane', '-k', '-t', pane, shlex.join(tokens))
                if not result.returncode: count += 1
        except (OSError, ValueError, IndexError, subprocess.SubprocessError):
            continue
    return count
