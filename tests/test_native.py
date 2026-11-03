"""Regression checks for the native footer's screen boundaries and text path."""
import importlib.util
import io
import json
import math
import os
from pathlib import Path
import shlex
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import native_avatar
import native_hud
from sixel_frames import load_frame

spec = importlib.util.spec_from_file_location('native_panel', ROOT/'codex-pane.py')
panel = importlib.util.module_from_spec(spec)
spec.loader.exec_module(panel)


class NativeTest(unittest.TestCase):
    def test_all_animation_frames_have_valid_indexed_data(self):
        for path in (ROOT/'assets/cast').glob('*/*/*.png'):
            with self.subTest(frame=path.relative_to(ROOT)):
                w, h, palette, pixels = load_frame(str(path))
                self.assertEqual(len(pixels), w*h)
                self.assertTrue(all(value < len(palette) or value == 255 for value in set(pixels)))

    def test_native_footer_forwards_preferences_without_stale_tmux_overrides(self):
        commands = []
        def tmux(socket, *args, **kwargs):
            commands.append(args)
            return SimpleNamespace(stdout='%20\n' if '-v' in args else '%21\n')
        with tempfile.TemporaryDirectory() as folder, patch.object(native_hud, 'tmux', side_effect=tmux):
            preferences = str(Path(folder)/'preferences with spaces.json')
            native_hud.create('/tmp/test-socket', '%1', ['python3', 'codex-pane.py'], folder,
                              '/tmp/watch-socket', '/tmp', {'AGENT_THEME_PREFERENCES': preferences})
        command = shlex.split(next(args[-1] for args in commands if args[0] == 'split-window' and '-v' in args))
        self.assertIn('AGENT_THEME_PREFERENCES='+preferences, command)
        for key in ('AGENT_THEME_STYLE', 'AGENT_THEME_CAST', 'AGENT_THEME_PREFERENCES'):
            self.assertIn(('-u', key), list(zip(command, command[1:])))

    def test_final_band_stays_inside_pane_after_client_scaling(self):
        # Include the actual source/client mismatch that scrolled Windows.
        for source_height in (16, 19, 20, 32, 34, 48):
            for client_height in (12, 19, 20, 24, 32, 34, 48):
                _, height = native_avatar.canvas(12, 5, 16, source_height)
                scaled = math.floor(height*client_height/source_height)
                final_band = math.ceil(scaled/6)*6
                self.assertLess(final_band, 5*client_height)
        self.assertIsNone(native_avatar.canvas(12, 1, 16, 32))
        self.assertEqual(native_avatar.canvas(12, 5, 16, 32), (192, 126))

    def test_native_text_publishes_state_without_drawing_portrait(self):
        class Output:
            def __init__(self): self.buffer = io.BytesIO()
            def flush(self): pass
        out = Output()
        state = {'busy': False, 'model': 'gpt-6.1-sol', 'effort': 'xhigh',
                 'limits': None, 'context_used': None, 'context_window': None,
                 'speed': None, 'approval': 'on-request', 'ended': 0}
        def render(*args):
            panel.theme.PORTRAIT[:] = ['luffy/idle', ROOT/'assets/cast/luffy/idle/000.png']
            return '\n'.join(['stable native text']*5)
        with tempfile.TemporaryDirectory() as folder:
            target = str(Path(folder)/'portrait.json')
            args = ['codex-pane.py', '--since', '0', '--cwd', '/tmp',
                    '--instance', 'native-test', '--native-state', target]
            with patch.object(sys, 'argv', args), patch.object(sys, 'stdout', out), \
                 patch.object(os, 'get_terminal_size', return_value=os.terminal_size((90, 5))), \
                 patch.object(panel.graphics, 'terminal_kind', return_value='windowsterminal'), \
                 patch.object(panel.graphics, 'position', side_effect=AssertionError('passthrough forbidden')), \
                 patch.object(panel.graphics, 'frame_at', side_effect=AssertionError('image belongs in companion')), \
                 patch.object(panel.theme, 'render', side_effect=render), \
                 patch.object(panel.counters, 'current_state', return_value=state), \
                 patch.object(panel.time, 'sleep', side_effect=KeyboardInterrupt):
                panel.main()
            self.assertEqual(json.loads(Path(target).read_text()), {'key': 'luffy/idle'})
        raw = out.buffer.getvalue()
        self.assertNotIn(b'\x1bP', raw)
        self.assertNotIn(b'2026', raw)
        self.assertFalse(any(0x2800 <= ord(c) <= 0x28ff for c in raw.decode()))
        for row in range(1, 6):
            self.assertIn(f'\x1b[{row};1H'.encode(), raw)


if __name__ == '__main__':
    unittest.main()
