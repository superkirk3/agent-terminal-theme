"""Keep image placements aligned with top status rows in Mac tmux layouts."""
import argparse
import importlib.util
import os
import re
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location('mac_panel', ROOT/'codex-pane.py')
panel = importlib.util.module_from_spec(spec)
spec.loader.exec_module(panel)


class MacOriginTest(unittest.TestCase):
    def test_avatar_slot_is_stable_across_states_and_isolated_by_hud(self):
        first = panel.avatar_id('session-a', 'goku/idle')
        self.assertNotEqual(first, panel.avatar_id('session-b', 'goku/idle'))
        self.assertEqual(first, panel.avatar_id('session-a', 'goku/think'))
        self.assertEqual(first, panel.avatar_id('session-a', 'goku/idle'))
        packet = panel.delete_avatar(first, 1)
        self.assertIn(f'd=I,i={first},q=2'.encode(), packet)
        self.assertNotIn(b'd=A', packet)

    def test_state_changes_and_killed_renderer_restart_keep_one_image(self):
        live, frame_counts = {}, {}
        def consume(raw):
            for match in re.finditer(rb'\x1b_G([^;\x1b]*)(?:;[^\x1b]*)?\x1b\\', raw):
                parts = dict(item.split(b'=', 1) for item in match[1].split(b',') if b'=' in item)
                action, image = parts.get(b'a'), parts.get(b'i')
                if action == b'd' and parts.get(b'd') in (b'i', b'I'):
                    live.pop(image, None); frame_counts.pop(image, None)
                elif action == b't': frame_counts[image] = 1
                elif action == b'f': frame_counts[image] += 1
                elif action == b'p': live[image] = True
        first = panel.KittyAvatar('example-hud', 'rex')
        consume(first.draw('goku/idle', 1, 1, 0))
        consume(first.draw('luffy/tool', 1, 1, 0))
        self.assertEqual(len(live), 1)
        self.assertEqual(frame_counts[str(first.image_id).encode()], len(panel.theme.animation('luffy/tool')[0]))
        # Simulate SIGKILL: no close() call before the replacement renderer.
        replacement = panel.KittyAvatar('example-hud', 'rex')
        consume(replacement.draw('naruto/think', 2, 1, 0))
        self.assertEqual(len(live), 1)
        self.assertEqual(frame_counts[str(first.image_id).encode()], len(panel.theme.animation('naruto/think')[0]))
        consume(replacement.close())
        self.assertEqual(live, {})

    def test_hidden_window_stops_its_avatar_and_redraws_when_visible(self):
        avatar = panel.KittyAvatar('visibility-example')
        avatar.draw('goku/idle', 1, 1, 0)
        self.assertIn(b'a=d,d=I', avatar.hide(0))
        self.assertFalse(avatar.started)
        self.assertEqual(avatar.hide(0), b'')
        self.assertIn(b'a=p,C=1', avatar.draw('goku/think', 1, 1, 0))

    def test_new_cli_in_same_outer_pane_reuses_slot_without_affecting_neighbors(self):
        first = panel.KittyAvatar('old-instance', slot='outer:%1')
        replacement = panel.KittyAvatar('new-instance', slot='outer:%1')
        neighbor = panel.KittyAvatar('third-instance', slot='outer:%2')
        self.assertEqual(first.image_id, replacement.image_id)
        self.assertNotEqual(first.image_id, neighbor.image_id)
        args = argparse.Namespace(outer_socket='/tmp/outer', outer_pane='%5', instance='example')
        with patch.dict(os.environ, {'REX_BLOCK': 'example-block'}):
            self.assertEqual(panel.graphics_slot(args), 'tmux:/tmp/outer:%5')

    def test_nested_hud_requires_both_windows_visible_and_respects_zoom(self):
        args = argparse.Namespace(outer_socket='/tmp/outer', outer_pane='%5')
        def check(inner, outer):
            with patch.dict(os.environ, {'TMUX_PANE': '%1'}), \
                 patch.object(panel.graphics, 'tmux', side_effect=lambda *a, socket=None: outer if socket else inner):
                return panel.graphics_visible(args)
        self.assertTrue(check('1|0|0|1', '1|0|1|1'))
        self.assertFalse(check('1|0|0|1', '0|0|1|1'))
        self.assertFalse(check('1|1|0|1', '1|0|1|1'))
        self.assertFalse(check('1|0|0|0', '1|0|1|1'))

    def test_rex_migration_cleans_old_theme_ids_without_global_delete(self):
        avatar = panel.KittyAvatar('example-hud', 'rex')
        old_state = panel.zlib.crc32(b'codex:example-hud:goku/idle') | 0x80000000
        legacy_placeholder = panel.theme.kitty_id(next(iter(panel.theme.ANIMATIONS)))
        packet = avatar.draw('goku/idle', 1, 1, 1)
        for image in (old_state, legacy_placeholder, avatar.image_id):
            self.assertIn(f'd=I,i={image},q=2'.encode(), packet)
        self.assertNotIn(b'd=A', packet)
        self.assertNotIn(b'd=a,', packet)

    def test_direct_footer_includes_two_top_status_rows(self):
        def tmux(*args, socket=None):
            if args[0] == 'display-message': return '35 0'
            return 'top' if args[-1] == 'status-position' else '2'
        with patch.dict(os.environ, {'TMUX_PANE': '%5'}), \
             patch.object(panel.graphics, 'tmux', side_effect=tmux):
            self.assertEqual(panel.origin(argparse.Namespace(outer_socket='', outer_pane='')), (38, 1, 1))

    def test_nested_footer_counts_each_top_bar_once(self):
        def tmux(*args, socket=None):
            if args[0] == 'display-message': return '3 4' if socket else '20 0'
            return 'top' if args[-1] == 'status-position' else '2' if socket else 'off'
        with patch.dict(os.environ, {'TMUX_PANE': '%1'}), \
             patch.object(panel.graphics, 'tmux', side_effect=tmux):
            self.assertEqual(panel.origin(argparse.Namespace(outer_socket='/tmp/outer', outer_pane='%5')), (26, 5, 2))


if __name__ == '__main__':
    unittest.main()
