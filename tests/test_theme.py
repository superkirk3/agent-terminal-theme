"""Selections must survive restarts and reach both renderers without relaunching."""
import contextlib
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import statusline
import theme
import theme_config as config


class ThemeTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)/'local preferences/preferences.json'
        self.environment = patch.dict(os.environ, {'AGENT_THEME_PREFERENCES': str(self.path),
                                      'AGENT_THEME_CAST': '', 'AGENT_THEME_STYLE': '',
                                      'CLAUDE_STATUSLINE_CAST': '', 'CLAUDE_STATUSLINE_STYLE': '',
                                      'COPILOT_STATUSLINE_CAST': '', 'COPILOT_STATUSLINE_STYLE': '',
                                      'NO_COLOR': '', 'COLUMNS': '180', 'LINES': '30', 'TERM': 'xterm-256color'})
        self.environment.start()

    def tearDown(self):
        self.environment.stop()
        self.temp.cleanup()

    def test_both_agents_switch_and_partial_updates_preserve_other_choices(self):
        config.save_selection(cast='luffy', style='mecha')
        config.save_selection('claude', cast='gojo')
        self.assertEqual(config.effective_preferences('codex'), {'cast': 'luffy', 'style': 'mecha'})
        self.assertEqual(config.effective_preferences('claude'), {'cast': 'gojo', 'style': 'mecha'})
        config.save_selection(style='pill')
        self.assertEqual(config.effective_preferences('claude'), {'cast': 'gojo', 'style': 'pill'})
        self.assertEqual(config.effective_preferences('codex'), {'cast': 'luffy', 'style': 'pill'})
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.path.parent.stat().st_mode & 0o777, 0o700)

    def test_environment_overrides_only_its_own_agent_and_reset_keeps_other_agent(self):
        config.save_selection(cast='luffy', style='mecha')
        os.environ.update({'AGENT_THEME_CAST': 'goku', 'CLAUDE_STATUSLINE_STYLE': 'card'})
        self.assertEqual(config.effective_preferences('codex'), {'cast': 'goku', 'style': 'mecha'})
        self.assertEqual(config.effective_preferences('claude'), {'cast': 'luffy', 'style': 'card'})
        config.save_selection('codex', reset=True)
        self.assertEqual(config.effective_preferences('codex'), {'cast': 'goku', 'style': 'random'})
        self.assertEqual(config.effective_preferences('claude')['cast'], 'luffy')
        config.save_selection(reset=True)
        self.assertEqual(config.effective_preferences('claude')['cast'], 'random')

    def test_running_renderer_rereads_character_and_layout_for_each_agent(self):
        data = {'session_id': 'switch-test', 'cwd': '~/projects/example',
                'model': {'display_name': 'Example Model'}, '_image_protocol': '',
                '_cast_state': 'idle', '_activity_state': 'IDLE', '_text_panel_only': True}
        for agent in config.AGENTS:
            with self.subTest(agent=agent):
                data['_agent'] = agent
                config.save_selection(agent, cast='luffy', style='mecha')
                first = statusline.render(data, now=1000)
                self.assertIn('LUFFY', first)
                self.assertTrue(statusline.PORTRAIT[0].startswith('luffy/'))
                config.save_selection(agent, style='pill')
                restyled = statusline.render(data, now=1000)
                self.assertIn('LUFFY', restyled)
                self.assertNotEqual(first, restyled)
                config.save_selection(agent, cast='goku')
                second = statusline.render(data, now=1000)
                self.assertIn('GOKU', second)
                self.assertNotIn('LUFFY', second)
                self.assertTrue(statusline.PORTRAIT[0].startswith('goku/'))

    def test_bad_input_never_writes_and_broken_file_does_not_break_renderer(self):
        for arguments in ({'cast': '../../invalid'}, {'style': 'unknown'}, {}):
            with self.assertRaises(ValueError): config.save_selection(**arguments)
        self.assertFalse(self.path.exists())
        self.path.parent.mkdir()
        self.path.write_text('{broken')
        self.assertEqual(config.effective_preferences('codex'), {'cast': 'random', 'style': 'random'})
        with self.assertRaises(ValueError): config.save_selection(cast='luffy')
        self.assertEqual(self.path.read_text(), '{broken')

    def test_interactive_menu_saves_both_agents_without_shell_exports(self):
        output = io.StringIO()
        # target=both; character=random; layout=card
        with patch.object(sys.stdin, 'isatty', return_value=True), \
             patch.object(sys, 'argv', ['agent-theme']), \
             patch('builtins.input', side_effect=['1', '1', '4']), \
             contextlib.redirect_stdout(output):
            theme.main()
        for agent in config.AGENTS:
            self.assertEqual(config.effective_preferences(agent), {'cast': 'random', 'style': 'card'})

    def test_noninteractive_cli_persists_choices_and_no_argument_does_not_wait(self):
        command = [sys.executable, str(ROOT/'theme.py')]
        result = subprocess.run(command+['set', '--cast', 'luffy', '--style', 'minimal'],
                                capture_output=True, text=True, check=True)
        self.assertIn('codex: cast=luffy  style=minimal', result.stdout)
        result = subprocess.run(command+['show'], capture_output=True, text=True, check=True)
        self.assertIn('claude: cast=luffy  style=minimal', result.stdout)
        before = self.path.read_bytes()
        result = subprocess.run(command, input='', capture_output=True, text=True, check=True, timeout=5)
        self.assertIn('usage:', result.stdout)
        self.assertEqual(self.path.read_bytes(), before)

    def test_cancelling_menu_does_not_save_a_partial_selection(self):
        with patch.object(sys.stdin, 'isatty', return_value=True), \
             patch.object(sys, 'argv', ['agent-theme']), \
             patch('builtins.input', side_effect=['1', '1', KeyboardInterrupt]), \
             contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as error: theme.main()
        self.assertEqual(error.exception.code, 130)
        self.assertFalse(self.path.exists())


if __name__ == '__main__': unittest.main()
