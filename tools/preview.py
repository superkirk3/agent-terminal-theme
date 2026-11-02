#!/usr/bin/env python3
"""Print a synthetic, offline Claude-style preview. No account or session log is used."""
import argparse
import os
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import statusline


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cast', default='luffy')
    parser.add_argument('--style', choices=statusline.STYLES, default='mecha')
    args = parser.parse_args()
    os.environ.update({'AGENT_THEME_CAST': args.cast,
                       'AGENT_THEME_STYLE': args.style,
                       'CLAUDE_STATUSLINE_IMAGE': 'off', 'COLUMNS': '140', 'LINES': '30'})
    data = {'session_id': 'synthetic-preview', 'cwd': '~/projects/example',
            'model': {'display_name': 'Example Model'}, 'effort_level': 'high',
            'context_window': {'context_window_size': 200000, 'used_percentage': 37},
            'permission_mode': 'default', '_agent': 'codex',
            '_activity_state': 'WORKING', '_cast_state': 'think',
            '_display_label': 'WORKING', '_tokens_per_second': 12.3,
            '_image_protocol': ''}
    print(statusline.render(data, time.time()))


if __name__ == '__main__': main()
