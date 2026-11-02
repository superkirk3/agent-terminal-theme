#!/usr/bin/env python3
"""Render the shared Claude cast/layout using Codex's own session metrics."""
import argparse
import json
import os
from pathlib import Path
import sys
import time
import zlib

import codex_hud_status as counters
import portable_images as graphics
import statusline as theme
from sixel_frames import render_frame

BASE = Path(__file__).resolve().parent


def avatar_id(instance, key):
    return zlib.crc32(f'codex:{instance}:{key}'.encode()) | 0x80000000


def delete_avatar(image_id, layers):
    return graphics.wrap(f'\x1b_Ga=d,d=I,i={image_id},q=2\x1b\\'.encode(), layers)


def snapshot(state, cwd, identity, now):
    rates = {}
    if state.get('limits'):
        _, limits = state['limits']
        for value in (limits.get('primary'), limits.get('secondary')):
            if not isinstance(value, dict):
                continue
            key = {300: 'five_hour', 10080: 'seven_day'}.get(value.get('window_minutes'))
            if key and (value.get('resets_at') or now+1) > now:
                rates[key] = {'used_percentage': value.get('used_percent'),
                              'resets_at': value.get('resets_at')}
    wanted = 'think' if state['busy'] else ('done' if now-state.get('ended', 0) < 60 else 'idle')
    if state['busy'] and max([v['used_percentage'] or 0 for v in rates.values()] or [0]) >= 80:
        wanted = 'power'
    return {'session_id': 'codex:'+identity, 'cwd': cwd,
            'model': {'display_name': state['model']}, 'effort_level': state['effort'],
            'context_window': {'context_window_size': state.get('context_window'),
                               'used_percentage': state['context_used']},
            'permission_mode': state.get('approval', 'on-request'), 'rate_limits': rates,
            '_agent': 'codex', '_context_unknown': not state.get('context_window'),
            '_activity_state': 'WORKING' if state['busy'] else 'IDLE',
            '_cast_state': wanted, '_display_label': 'WORKING' if state['busy'] else '',
            '_tokens_per_second': state['speed'], '_text_panel_only': True,
            '_image_protocol': ''}


def origin(args):
    def status_rows(socket=None):
        if graphics.tmux('show-options', '-gv', 'status-position', socket=socket) != 'top':
            return 0
        setting = graphics.tmux('show-options', '-gv', 'status', socket=socket)
        return 1 if setting == 'on' else int(setting) if setting.isdigit() else 0
    parts = graphics.tmux('display-message', '-p', '-t', os.environ['TMUX_PANE'],
                          '#{pane_top} #{pane_left}').split()
    top, left = map(int, parts)
    top += status_rows()
    layers = 1
    if args.outer_socket:
        parts = graphics.tmux('display-message', '-p', '-t', args.outer_pane,
                              '#{pane_top} #{pane_left}', socket=args.outer_socket).split()
        if len(parts) == 2:
            top += int(parts[0]); left += int(parts[1])
        top += status_rows(args.outer_socket)
        layers += 1
    return top+1, left+1, layers


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--since', type=float, required=True)
    p.add_argument('--cwd', required=True)
    p.add_argument('--session-id', default='')
    p.add_argument('--instance', required=True)
    p.add_argument('--outer-socket', default='')
    p.add_argument('--outer-pane', default='')
    p.add_argument('--native-state', default='')
    p.add_argument('--watch-socket', default='')
    args = p.parse_args()
    args.log = None
    home = Path(os.environ.get('CODEX_HOME', Path.home()/'.codex'))
    if args.session_id:
        args.log = counters.session_by_id(home, args.session_id)
    # A footer can use the full five lines of every Claude layout.
    os.environ['LINES'] = '30'
    terminal = graphics.terminal_kind()
    protocol = ('kitty' if terminal in ('ghostty','kitty','rex') else
                'iterm' if terminal in ('wezterm','iterm.app','iterm2') else
                'text' if terminal == 'windowsterminal' else '')
    # Windows SIXEL passthrough corrupted the live viewport. Keep every update
    # inside this tmux pane until a graphics path is visually verified in isolation.
    native = bool(args.native_state)
    text_only = protocol == 'text' or native
    text_column = 1 if native else 13
    previous_text = previous_image = None
    state = None
    next_state = 0
    next_origin = 0
    last_size = None
    coordinates = (1, 1, 1)
    image_cells = (10,20)
    placed_image = None
    placed_layers = 1
    sys.stdout.buffer.write(b'\x1b[2J\x1b[H\x1b[?25l')
    try:
        while True:
            if args.watch_socket and not Path(args.watch_socket).exists():
                break
            now = time.time()
            size = os.get_terminal_size()
            if size.lines != 5:
                graphics.tmux('resize-pane', '-t', os.environ['TMUX_PANE'], '-y', '5')
            if now >= next_state:
                state = counters.current_state(args, now, home)
                next_state = now+.9
            if not text_only and (now >= next_origin or size != last_size):
                coordinates = origin(args)
                if protocol == 'sixel':
                    image_cells = graphics.cell_size(socket=args.outer_socket or None,
                        pane=args.outer_pane if args.outer_socket else os.environ['TMUX_PANE'],
                        terminal=terminal)
                next_origin = now+2
                last_size = size
            os.environ['COLUMNS'] = str(max(60, size.columns+(12 if native else 0)))
            data = snapshot(state, args.cwd, args.session_id or args.instance, now)
            text = theme.render(data, now)
            rows = text.splitlines()[:5]
            out = b''
            if text != previous_text:
                for i in range(5):
                    out += f'\x1b[{i+1};{text_column}H\x1b[0K'.encode() + (theme.clip(rows[i], max(0,size.columns-text_column+1)).encode() if i<len(rows) else b'')
                previous_text = text
            key, png = theme.PORTRAIT
            if native and key != previous_image:
                target = Path(args.native_state)
                temporary = target.with_suffix('.tmp')
                temporary.write_text(json.dumps({'key': key}))
                temporary.replace(target)
                previous_image = key
            elif png and not native:
                folder = png.parent
                # Windows gets one ANSI portrait per state. It scales with text
                # and is not cleared/redrawn for every animation or usage update.
                frame = (next(iter(sorted(folder.glob('*.png'))),png) if text_only
                         else graphics.frame_at(folder, now))
                row, col, layers = coordinates
                image_key = (key, row, col, layers, image_cells, None if protocol=='kitty' else str(frame))
                if image_key != previous_image or (out and protocol == 'iterm'):
                    if protocol == 'kitty':
                        image_id = avatar_id(args.instance, key)
                        if placed_image is not None and placed_image != image_id:
                            out += delete_avatar(placed_image, placed_layers)
                        payload = theme.kitty_payload(image_id, *theme.animation(key), False)
                        payload = payload.replace(b'a=p,U=1,', b'a=p,C=1,')
                        out += graphics.position(payload, row, col, layers)
                        placed_image, placed_layers = image_id, layers
                    elif protocol == 'iterm':
                        out += graphics.position(graphics.inline_png(frame), row, col, layers)
                    elif protocol == 'sixel' and frame.with_suffix('.six').exists():
                        image = render_frame(str(frame),image_cells[0]*10,image_cells[1]*5)
                        out += graphics.position(image, row, col, layers, clear=True, sync=True)
                    else:
                        for i, line in enumerate(frame.with_suffix('.ans').read_text().splitlines()):
                            out += f'\x1b[{i+1};1H'.encode()+line.encode()
                    previous_image = image_key
            if out:
                sys.stdout.buffer.write(out+b'\x1b[?25l')
                sys.stdout.buffer.flush()
            time.sleep(1 if text_only else .2 if protocol != 'kitty' else .5)
    except (KeyboardInterrupt, BrokenPipeError):
        pass
    finally:
        if placed_image is not None:
            sys.stdout.buffer.write(delete_avatar(placed_image, placed_layers))
        sys.stdout.buffer.write(b'\x1b[0m\x1b[?25h')
        sys.stdout.buffer.flush()


if __name__ == '__main__':
    main()
