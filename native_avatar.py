#!/usr/bin/env python3
"""Draw native tmux SIXEL in a dedicated pane, with space below every frame."""
import argparse
import json
import os
from pathlib import Path
import sys
import struct
import time
import zlib

import portable_images as graphics
from sixel_frames import load_frame, render_frame

ROOT = Path(__file__).resolve().parent
BG = (40, 44, 52)
STYLE = b'\x1b[0m\x1b[48;2;40;44;52m\x1b[38;2;230;234;242m'


def canvas(columns, rows, cw, ch, bottom_padding=1):
    # The last SIXEL band is six pixels high even when the raster declaration
    # names fewer pixels. Native tmux rescales to each attached client's cells,
    # so rounding the source height to six alone does not prevent an overflow.
    # Reserve a complete text row after scaling. Never draw in a one-row pane.
    usable = min(rows, 5)-bottom_padding
    if usable < 1:
        return None
    return min(columns, 12)*cw, max(6, usable*ch//6*6)


def folder_for(key):
    if not isinstance(key, str) or len(key.split('/')) != 2:
        return None
    root = ROOT/'assets/cast'
    folder = (root/key).resolve()
    return folder if folder.is_relative_to(root.resolve()) and folder.is_dir() else None


def paint(key_provider, seconds=0, stats='', bottom_padding=1, watch_socket=''):
    sys.stdout.buffer.write(STYLE+b'\x1b[2J\x1b[?25l')
    start = time.monotonic()
    previous = None
    metrics = (16, 32)
    next_metrics = 0
    frames = 0
    try:
        while not seconds or time.monotonic()-start < seconds:
            if watch_socket and not Path(watch_socket).exists():
                break
            size = os.get_terminal_size()
            pane = os.environ.get('TMUX_PANE', '')
            if size.lines != 5 or size.columns != 12:
                graphics.tmux('resize-pane', '-t', pane, '-x', '12', '-y', '5')
                size = os.get_terminal_size()
            now = time.monotonic()
            if now >= next_metrics:
                values = graphics.tmux('display-message', '-p', '-t', pane,
                    '#{window_cell_width} #{window_cell_height}').split()
                if len(values) == 2 and all(v.isdigit() and int(v)>0 for v in values):
                    metrics = tuple(map(int, values))
                next_metrics = now+2
            key = key_provider()
            folder = folder_for(key)
            dimensions = canvas(size.columns, size.lines, *metrics, bottom_padding)
            frame = graphics.frame_at(folder, time.time()) if folder else None
            identity = (str(frame), dimensions)
            if frame and dimensions and identity != previous:
                try:
                    _, _, _, pixels = load_frame(str(frame))
                    # Some source animations contain completely transparent
                    # transition frames. Retain the visible frame through them.
                    if pixels.count(255) == len(pixels):
                        time.sleep(.2)
                        continue
                    raw = render_frame(str(frame), *dimensions, matte=BG)
                except (OSError, ValueError, struct.error, zlib.error):
                    # An incomplete/custom asset must not kill the image pane.
                    time.sleep(.2)
                    continue
                # Native tmux owns the pane, image, and cursor. No passthrough,
                # ancestor coordinates, manual erases, or DECSET 2026 are used.
                sys.stdout.buffer.write(b'\x1b[1;1H'+raw)
                sys.stdout.buffer.flush()
                frames += 1
                previous = identity
                if stats:
                    data = {'frames': frames, 'key': key, 'canvas': dimensions,
                            'pane': [size.columns, size.lines], 'cell': metrics,
                            'bottom_padding': bottom_padding}
                    temporary = Path(stats+'.tmp')
                    temporary.write_text(json.dumps(data))
                    temporary.replace(stats)
            time.sleep(.2)
    except (KeyboardInterrupt, BrokenPipeError):
        pass


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--state', required=True)
    p.add_argument('--watch-socket', default='')
    p.add_argument('--stats', default='')
    args = p.parse_args()
    def key():
        try:
            return json.loads(Path(args.state).read_text()).get('key')
        except (OSError, ValueError, AttributeError):
            return None
    paint(key, stats=args.stats, watch_socket=args.watch_socket)


if __name__ == '__main__':
    main()
