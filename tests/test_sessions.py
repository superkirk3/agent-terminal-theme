"""Session overrides must be isolated, live, private and safe to resolve."""
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import theme_config as config
import theme_sessions as sessions
import statusline
import theme
import test_theme as fixtures


class SessionTest(unittest.TestCase):
    setUp = fixtures.ThemeTest.setUp
    tearDown = fixtures.ThemeTest.tearDown

    def test_same_project_sessions_and_agents_switch_independently(self):
        config.save_selection(cast='luffy', style='mecha')
        os.environ.update({'AGENT_THEME_CAST': 'goku', 'CLAUDE_STATUSLINE_CAST': 'goku'})
        base = {'cwd': '~/projects/example', 'model': {'display_name': 'Example'},
                '_image_protocol': '', '_cast_state': 'idle', '_activity_state': 'IDLE', '_text_panel_only': True}
        for agent in config.AGENTS:
            first = {**base, '_agent': agent, 'session_id': 'session-a'}
            other = {**base, '_agent': agent, 'session_id': 'session-b'}
            before = statusline.render(other, now=1000)
            self.assertIn('GOKU', before)
            config.save_selection(agent, cast='gojo', style='card', session_id='session-a')
            changed = statusline.render(first, now=1000)
            self.assertIn('GOJO', changed)
            self.assertTrue(statusline.PORTRAIT[0].startswith('gojo/'))
            self.assertEqual(statusline.render(other, now=1000), before)
            other_agent = 'claude' if agent == 'codex' else 'codex'
            self.assertNotEqual(config.effective_preferences(other_agent, session_id='session-a')['cast'], 'gojo')
            config.save_selection(agent, reset=True, session_id='session-a')
            self.assertIn('GOKU', statusline.render(first, now=1000))
            self.assertEqual(statusline.render(other, now=1000), before)

    def test_registry_is_private_and_prefixes_are_unambiguous(self):
        for identity in ('session-alpha', 'session-alpine'):
            sessions.register('codex', identity, '~/projects/example', {'cast': 'luffy', 'style': 'mecha'})
        rows = sessions.records()
        self.assertEqual(len(rows), 2)
        self.assertEqual(sessions.resolve('session-alpha')['session_id'], 'session-alpha')
        with self.assertRaises(ValueError): sessions.resolve('session-al')
        sessions.register('claude', 'session-alpha', '~/projects/example', {'cast': 'goku', 'style': 'pill'})
        with self.assertRaises(ValueError): sessions.resolve('session-alpha')
        self.assertEqual(sessions.resolve('claude:session-alpha')['agent'], 'claude')
        self.assertEqual(sessions.records(now=time.time()+130), [])
        self.assertEqual(len(sessions.records(include_stale=True)), 3)
        self.assertEqual(sessions.registry_directory().stat().st_mode & 0o777, 0o700)
        for path in sessions.registry_directory().glob('*.json'):
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_hud_alias_survives_identity_discovery_and_reset_only_clears_target(self):
        config.save_selection('codex', cast='gojo', session_id='hud-a')
        config.save_selection('codex', cast='ryoma', session_id='session-b')
        choice = config.effective_preferences('codex', session_id='session-a', session_aliases=['hud-a'])
        self.assertEqual(choice['cast'], 'gojo')
        sessions.register('codex', 'session-a', '~/projects/example', choice, aliases=['hud-a'], observer='hud-a')
        target = sessions.resolve('hud-a')
        config.save_selection('codex', style='pill', session_id=target['session_id'], session_aliases=target['aliases'])
        self.assertEqual(config.effective_preferences('codex', session_id='session-a'), {'cast': 'gojo', 'style': 'pill'})
        config.save_selection('codex', reset=True, session_id='session-a', session_aliases=['hud-a'])
        self.assertEqual(config.effective_preferences('codex', session_id='session-a', session_aliases=['hud-a'])['cast'], 'random')
        self.assertEqual(config.effective_preferences('codex', session_id='session-b')['cast'], 'ryoma')

    def test_cli_targets_existing_session_without_changing_defaults(self):
        sessions.register('claude', 'session-example-a', '~/projects/example', {'cast': 'luffy', 'style': 'mecha'})
        config.save_selection(cast='luffy', style='mecha')
        command = [sys.executable, str(ROOT/'theme.py')]
        subprocess.run(command+['set', '--session', 'session-example', '--cast', 'gojo'], check=True, capture_output=True)
        self.assertEqual(config.effective_preferences('claude', session_id='session-example-a')['cast'], 'gojo')
        self.assertEqual(config.effective_preferences('claude')['cast'], 'luffy')
        self.assertEqual(config.effective_preferences('codex', session_id='session-example-a')['cast'], 'luffy')
        data = json.loads(subprocess.check_output(command+['sessions', '--json']))
        self.assertEqual(data[0]['session_id'], 'session-example-a')
        before = self.path.read_bytes()
        result = subprocess.run(command+['set', '--session', '', '--cast', 'goku'], capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.path.read_bytes(), before)

    def test_concurrent_session_updates_do_not_erase_each_other(self):
        command = [sys.executable, str(ROOT/'theme.py'), 'set', '--agent', 'codex', '--cast', 'luffy']
        processes = [subprocess.Popen(command+['--session', f'session-{number}'],
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE) for number in range(4)]
        for process in processes:
            process.communicate(timeout=10)
            self.assertEqual(process.returncode, 0)
        for number in range(4):
            self.assertEqual(config.effective_preferences('codex', session_id=f'session-{number}')['cast'], 'luffy')

    def test_invalid_session_never_changes_client_defaults(self):
        config.save_selection(cast='luffy')
        before = self.path.read_bytes()
        for identity in ('', '../invalid', 'claude:session-a'):
            with self.assertRaises(ValueError): config.save_selection('codex', cast='goku', session_id=identity)
        self.assertEqual(self.path.read_bytes(), before)

    def test_corrupt_registry_record_is_repaired_without_breaking_renderer(self):
        sessions.register('claude', 'session-a', '~/projects/example', {'cast': 'luffy', 'style': 'mecha'})
        record = next(sessions.registry_directory().glob('*.json'))
        record.write_text('[]')
        self.assertEqual(sessions.records(), [])
        sessions.register('claude', 'session-a', '~/projects/example', {'cast': 'goku', 'style': 'card'})
        self.assertEqual(sessions.records()[0]['choices']['cast'], 'goku')

    def test_interactive_session_target_preserves_client_defaults(self):
        config.save_selection(cast='luffy', style='mecha')
        sessions.register('codex', 'session-a', '~/projects/example', {'cast': 'luffy', 'style': 'mecha'})
        with patch.object(sys.stdin, 'isatty', return_value=True), \
             patch.object(sys, 'argv', ['agent-theme']), \
             patch('builtins.input', side_effect=['4', '1', '4']), \
             contextlib.redirect_stdout(io.StringIO()):
            theme.main()
        self.assertEqual(config.effective_preferences('codex', session_id='session-a'), {'cast': 'random', 'style': 'card'})
        self.assertEqual(config.effective_preferences('codex'), {'cast': 'luffy', 'style': 'mecha'})
        self.assertEqual(config.effective_preferences('claude', session_id='session-a'), {'cast': 'luffy', 'style': 'mecha'})


if __name__ == '__main__': unittest.main()
