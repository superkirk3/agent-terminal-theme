"""Keep image placements aligned with top status rows in Mac tmux layouts."""
import argparse
import importlib.util
import os
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
    def test_avatar_ownership_is_scoped_to_session_and_state(self):
        first = panel.avatar_id('session-a', 'goku/idle')
        self.assertNotEqual(first, panel.avatar_id('session-b', 'goku/idle'))
        self.assertNotEqual(first, panel.avatar_id('session-a', 'goku/think'))
        self.assertEqual(first, panel.avatar_id('session-a', 'goku/idle'))
        packet = panel.delete_avatar(first, 1)
        self.assertIn(f'd=I,i={first},q=2'.encode(), packet)
        self.assertNotIn(b'd=A', packet)

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
