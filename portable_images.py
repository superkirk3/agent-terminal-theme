"""Terminal detection and positioned graphics for the shared agent theme."""
import base64
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import unicodedata


def tmux(*args, socket=None):
    try:
        cmd = ['tmux', *(['-S', socket] if socket else []), *args]
        return subprocess.run(cmd, capture_output=True, text=True, timeout=.6).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ''


def terminal_kind():
    explicit = os.environ.get('AGENT_THEME_TERMINAL', '').lower()
    if explicit:
        return explicit
    name = os.environ.get('TERM_PROGRAM', '').lower()
    if os.environ.get('TMUX'):
        pane = os.environ.get('TMUX_PANE', '')
        version = tmux('display-message', '-p', '-t', pane, '#{client_termtype}').lower()
        for kind in ('ghostty', 'rex', 'wezterm', 'iterm2', 'kitty'):
            if version.startswith(kind):
                return 'iterm.app' if kind == 'iterm2' else kind
        pid = tmux('display-message', '-p', '-t', pane, '#{client_pid}')
        try:
            env = Path(f'/proc/{pid}/environ').read_bytes().split(b'\0')
            if any(e.startswith(b'WT_SESSION=') for e in env):
                return 'windowsterminal'
        except OSError:
            pass
        session = tmux('display-message', '-p', '-t', pane, '#{session_id}')
        saved = tmux('show-environment', '-t', session, 'TERM_PROGRAM')
        if saved.startswith('TERM_PROGRAM='):
            name = saved.partition('=')[2].lower()
    if os.environ.get('WT_SESSION'):
        return 'windowsterminal'
    return name


def wrap(payload, layers=1):
    for _ in range(layers):
        payload = b'\x1bPtmux;' + payload.replace(b'\x1b', b'\x1b\x1b') + b'\x1b\\'
    return payload


def cell_size(socket=None, pane='', terminal='windowsterminal'):
    """Use the outer image client's font metrics, not stale nested-tmux metrics."""
    session = tmux('display-message','-p','-t',pane,'#{session_id}',socket=socket) if pane else ''
    args = ['list-clients', *(['-t',session] if session else []), '-F',
            '#{client_cell_width}|#{client_cell_height}|#{client_termtype}|#{client_activity}']
    candidates = []
    for line in tmux(*args,socket=socket).splitlines():
        parts = line.split('|')
        if len(parts)!=4:
            continue
        try:
            w,h,activity = int(parts[0]),int(parts[1]),int(parts[3])
        except ValueError:
            continue
        if not (0<w<100 and 0<h<150):
            continue
        name = parts[2].lower()
        match = not name or 'windows' in name if terminal=='windowsterminal' else terminal in name
        candidates.append((match,activity,w,h))
    if candidates:
        _,_,w,h = max(candidates)
        return w,h
    try:
        import fcntl,struct,termios
        rows,cols,x,y = struct.unpack('HHHH',fcntl.ioctl(sys.stdout.fileno(),termios.TIOCGWINSZ,b'\0'*8))
        if rows and cols and x and y:
            return max(1,x//cols),max(1,y//rows)
    except (OSError,ValueError):
        pass
    return 10,20


def position(payload, row, col, layers=1, clear=False, sync=False):
    prefix = (b'\x1b[?2026h' if sync else b'') + b'\x1b7'
    if clear:
        # Erase the previous frame with the terminal's current default background.
        # Send this through passthrough too: identical tmux cells may not repaint.
        prefix += b'\x1b[0m'
        for y in range(row,row+5):
            prefix += f'\x1b[{y};{col}H'.encode() + b' '*10
    suffix = b'\x1b8' + (b'\x1b[?2026l' if sync else b'')
    return wrap(prefix + f'\x1b[{row};{col}H'.encode() + payload + suffix, layers)


def frame_at(folder, now):
    frames = sorted(folder.glob('*.png'))
    if not frames:
        return None
    try:
        gaps = json.loads((folder/'meta.json').read_text())['gaps']
        if len(gaps) != len(frames) or not all(g > 0 for g in gaps):
            raise ValueError('invalid gaps')
    except (OSError, ValueError, KeyError, TypeError):
        gaps = [120] * len(frames)
    tick = (now * 1000) % sum(gaps)
    for frame, gap in zip(frames, gaps):
        if tick < gap:
            return frame
        tick -= gap
    return frames[-1]


def inline_png(png):
    raw = png.read_bytes()
    return (f'\x1b]1337;File=inline=1;width=10;height=5;preserveAspectRatio=1;'
            f'doNotMoveCursor=1;size={len(raw)}:').encode() + base64.b64encode(raw) + b'\x07'


def draw_sixel_later(png, offset, size, marker):
    """Draw after Claude has printed its status line; ANSI remains as fallback."""
    pane = os.environ.get('TMUX_PANE')
    if not pane or not png.with_suffix('.six').is_file():
        return
    sys.stdout.flush()
    if os.fork():
        return
    try:
        os.setsid()
        null = os.open(os.devnull, os.O_RDWR)
        for fd in (0, 1, 2):
            os.dup2(null, fd)
        time.sleep(.3)
        info = tmux('display-message', '-p', '-t', pane,
                    '#{pane_tty} #{pane_top} #{pane_left} #{pane_height}').split()
        rows = tmux('capture-pane', '-p', '-t', pane).splitlines()
        found = next(i for i in range(len(rows)-1, -1, -1) if marker in rows[i])
        prefix = rows[found].partition(marker)[0]
        width = sum(0 if unicodedata.combining(c) else 2 if unicodedata.east_asian_width(c) in 'WF' else 1 for c in prefix)
        column = width-offset
        if column < 0 or found+size[1] > int(info[3]):
            return
        status = 0
        if tmux('show-options', '-gv', 'status-position') == 'top':
            v = tmux('show-options', '-gv', 'status')
            status = 1 if v == 'on' else int(v) if v.isdigit() else 0
        from sixel_frames import render_frame
        cw,ch = cell_size(pane=pane)
        image = render_frame(str(png),cw*10,ch*5)
        payload = position(image, status+int(info[1])+found+1,
                           int(info[2])+column+1, clear=True, sync=True)
        fd = os.open(info[0], os.O_WRONLY | os.O_NOCTTY)
        with os.fdopen(fd, 'wb') as out:
            out.write(payload)
    except (OSError, ValueError, IndexError, StopIteration):
        pass
    finally:
        os._exit(0)
