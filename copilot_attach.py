"""Attach an owned HUD to an existing tmux Copilot without restarting the CLI."""
import argparse
import fcntl
import os
from pathlib import Path
import signal
import shutil
import subprocess
import sys
import tempfile
import time

import native_hud
import theme_refresh
import theme_sessions

ROOT = Path(__file__).resolve().parent


def fingerprint(pid):
    try:
        # Linux start ticks distinguish a restarted/reused PID from this CLI.
        fields = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()
        return fields[19] if fields[0] != 'Z' else ''
    except (OSError, IndexError): return ''


def attach_running():
    """WSL native SIXEL path; skip unrelated shells and already managed sessions."""
    if not Path('/proc/sys/fs/binfmt_misc/WSLInterop').exists() and not os.environ.get('WSL_DISTRO_NAME'):
        return 0
    state_root = Path.home()/'.local/state/agent-theme'
    state_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(state_root/'copilot-attach.lock', os.O_CREAT | os.O_RDWR, 0o600)
    count = 0
    with os.fdopen(descriptor, 'a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        for socket in theme_refresh.socket_paths():
            if not native_hud.supported(str(socket)): continue
            result = theme_refresh.tmux(socket, 'list-panes', '-a', '-F',
                                        '#{pane_id}\t#{pane_pid}\t#{pane_current_command}\t#{pane_current_path}\t#{@agent-theme-copilot}')
            for line in result.stdout.splitlines():
                parts = line.split('\t')
                if len(parts) != 5: continue
                pane, root_pid, command, cwd, marker = parts
                if marker or command.lower() not in ('copilot', 'mainthread'): continue
                pid = theme_sessions.owned_copilot_pid(root_pid)
                if not fingerprint(pid): continue
                state_dir = tempfile.mkdtemp(prefix='copilot-hud-')
                native_hud.tmux(str(socket), 'set-option', '-p', '-t', pane, '@agent-theme-copilot', state_dir)
                process = subprocess.Popen([sys.executable, str(ROOT/'copilot_attach.py'), '--socket', str(socket),
                    '--pane', pane, '--pid', str(pid), '--cwd', cwd, '--state-dir', state_dir],
                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
                for _ in range(30):
                    if (Path(state_dir)/'ready').exists():
                        count += 1
                        break
                    if process.poll() is not None: break
                    time.sleep(.1)
    return count


def manage(args):
    owner = fingerprint(args.pid)
    panes = []
    def stop(signum, frame): raise SystemExit(0)
    signal.signal(signal.SIGTERM, stop)
    try:
        if not owner: return
        panel = [sys.executable, str(ROOT/'codex-pane.py'), '--agent', 'copilot', '--owner-pid', str(args.pid),
                 '--since', str(time.time()-3), '--cwd', args.cwd, '--instance', Path(args.state_dir).name]
        environment = dict(os.environ, AGENT_THEME_TERMINAL='windowsterminal')
        panes = native_hud.create(args.socket, args.pane, panel, args.state_dir, args.socket, args.cwd, environment)
        (Path(args.state_dir)/'ready').touch(mode=0o600)
        while fingerprint(args.pid) == owner:
            if not Path(args.socket).exists(): break
            time.sleep(2)
    finally:
        native_hud.remove(args.socket, panes, args.state_dir)
        marker = native_hud.tmux(args.socket, 'show-options', '-pqv', '-t', args.pane,
                                '@agent-theme-copilot', check=False).stdout.strip()
        if marker == args.state_dir:
            native_hud.tmux(args.socket, 'set-option', '-pu', '-t', args.pane, '@agent-theme-copilot', check=False)
        shutil.rmtree(args.state_dir, ignore_errors=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--socket', required=True)
    parser.add_argument('--pane', required=True)
    parser.add_argument('--pid', required=True, type=int)
    parser.add_argument('--cwd', required=True)
    parser.add_argument('--state-dir', required=True)
    manage(parser.parse_args())
