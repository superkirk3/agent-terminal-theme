"""Check telemetry units, truthful mode badges, and reachable ensemble artwork."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import codex_hud_status as codex
import copilot_hud_status as copilot
import statusline
import theme_config as config
import theme_sessions
import test_theme as fixtures


def event(kind, payload, second=0):
    return {'timestamp': f'2026-11-01T00:00:{second:02d}Z', 'type': 'event_msg',
            'payload': dict(payload, type=kind)}


class TelemetryTest(unittest.TestCase):
    def test_numeric_task_timestamps_use_unix_milliseconds(self):
        start = codex.when('2026-11-01T00:00:00Z')
        self.assertEqual(codex.when(int(start*1000)), start)
        self.assertEqual(codex.when(start), start)
        rows = [event('task_started', {'started_at': int(start*1000)}),
                {'type': 'token_usage_record', 'timestamp': '2026-11-01T00:00:15Z',
                 'payload': {'turn_token_usage': {'output_tokens': 600}}},
                event('task_complete', {'started_at': int(start*1000), 'completed_at': int((start+20)*1000), 'duration_ms': 20000}, 20)]
        state = codex.summarize(rows, 0, ('Example', 'high'))
        self.assertEqual(state['speed'], 30)
        self.assertFalse(state['busy'])

    def test_codex_turn_average_sums_requests_and_ignores_duplicate_counts(self):
        def count(total, last, second):
            return event('token_count', {'info': {'total_token_usage': {'total_tokens': total, 'output_tokens': total},
                       'last_token_usage': {'output_tokens': last}}}, second)
        rows = [event('task_started', {}), count(100, 100, 5), count(100, 100, 6), count(300, 200, 15),
                event('task_complete', {'duration_ms': 30000}, 30)]
        state = codex.summarize(rows, 0, ('Example', 'high'))
        self.assertEqual(state['speed'], 10)
        self.assertEqual(state['speed_label'], 'AVG')
        self.assertFalse(state['busy'])

    def test_structured_cumulative_usage_and_explicit_fast_mode(self):
        rows = [event('task_started', {}),
                {'type': 'token_usage_record', 'timestamp': '2026-11-01T00:00:15Z',
                 'payload': {'turn_token_usage': {'output_tokens': 600}}},
                event('token_count', {'info': {'total_token_usage': {'total_tokens': 600},
                                             'last_token_usage': {'output_tokens': 200}}}, 16),
                event('thread_settings_applied', {'thread_settings': {'service_tier': 'priority'}}, 17),
                event('task_complete', {'duration_ms': 20000}, 20)]
        state = codex.summarize(rows, 0, ('Example', 'high'))
        self.assertEqual(state['speed'], 30)
        self.assertEqual(statusline.fast_mode(state), 'ON')
        state = codex.summarize([event('thread_settings_applied', {'thread_settings': {'service_tier': None}})], 0, ('m', ''), state)
        self.assertEqual(statusline.fast_mode(state), 'OFF')
        self.assertEqual(statusline.fast_mode({}), '?')

    def test_copilot_api_duration_is_milliseconds_and_cost_is_never_usd(self):
        rows = [{'type': 'assistant.turn_start', 'data': {}},
                {'type': 'session.usage_record', 'data': {'usage': {'inputTokens': 20000,
                 'outputTokens': 300, 'duration': 1500, 'maxPromptTokens': 200000,
                 'cacheReadTokens': 10000, 'cost': 15, 'interTokenLatencyMs': .2}}}]
        state = copilot.summarize(rows)
        self.assertEqual(state['speed'], 200)
        self.assertAlmostEqual(state['context_used'], 10.15)
        self.assertEqual(state['cache_ratio'], .5)
        self.assertNotIn('cost', state)
        self.assertEqual(statusline.fast_mode(state), '?')
        state = copilot.summarize([{'type': 'assistant.turn_end', 'timestamp': '2026-11-01T00:00:20Z'}], state)
        self.assertFalse(state['busy'])

    def test_copilot_partial_records_and_replaced_file_do_not_duplicate_tokens(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'events.jsonl'
            row = json.dumps({'type': 'session.usage_record', 'data': {'usage': {'inputTokens': 100, 'outputTokens': 50, 'duration': 1000}}})+'\n'
            path.write_text(row[:-2])
            self.assertIsNone(copilot.session_counters(path)['speed'])
            with path.open('a') as stream: stream.write(row[-2:])
            self.assertEqual(copilot.session_counters(path)['total_tokens'], 150)
            self.assertEqual(copilot.session_counters(path)['total_tokens'], 150)
            path.write_text('')
            self.assertIsNone(copilot.session_counters(path)['total_tokens'])

    def test_copilot_owner_requires_one_open_session_not_latest_cwd(self):
        home = Path('/synthetic/copilot')
        paths = {home/'session-state/session-a/inuse.12.hold'}
        with patch.object(theme_sessions, 'owned_paths', return_value=paths):
            self.assertEqual(theme_sessions.owned_copilot_session(12, home), 'session-a')
            paths.add(home/'session-state/session-b/session.db')
            self.assertEqual(theme_sessions.owned_copilot_session(12, home), '')

    def test_copilot_launcher_passes_noninteractive_commands_through(self):
        spec = importlib.util.spec_from_file_location('copilot_launcher', ROOT/'copilot-launch.py')
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        for args in (['--version'], ['--prompt', 'test'], ['-p', 'test'], ['--acp'], ['plugin', 'list']):
            self.assertFalse(module.use_hud(args, True, True))
        self.assertTrue(module.use_hud(['--resume'], True, True))
        self.assertFalse(module.use_hud([], False, True))


class VisualTest(unittest.TestCase):
    setUp = fixtures.ThemeTest.setUp
    tearDown = fixtures.ThemeTest.tearDown

    def test_structured_approval_policy_stays_compact_in_every_layout(self):
        policy = {'granular': {'sandbox_approval': True, 'rules': False,
                  'skill_approval': True, 'request_permissions': False, 'mcp_elicitations': False}}
        state = codex.summarize([{'type': 'turn_context', 'payload': {'approval_policy': policy}}], 0, ('Example', 'high'))
        self.assertEqual(statusline.permission_label(state['approval']), 'GRANULAR 2/5')
        data = {'_agent': 'codex', 'session_id': 'approval-example', 'permission_mode': state['approval'],
                '_text_panel_only': True, '_image_protocol': '', '_theme_register': False}
        for style in config.STYLES:
            config.save_selection('codex', cast='saitama', style=style)
            text = statusline.render(data, now=1000)
            self.assertIn('granular 2/5', text.lower())
            self.assertNotIn('SANDBOX', text.upper())
            self.assertNotIn('FALSE', text.upper())
            self.assertLessEqual(len(text.splitlines()), 5)

    def test_unknown_policy_structures_do_not_dump_their_contents(self):
        for policy, label in (({'granular': {'future_category': True}}, 'GRANULAR'),
                              ({'future_policy': {'private_value': True}}, 'CUSTOM'),
                              ('on-request', 'ON-REQUEST'), ('never', 'NEVER'),
                              ('bypassPermissions', 'BYPASS'), (None, 'UNKNOWN')):
            self.assertEqual(statusline.permission_label(policy), label)

    def test_every_ensemble_member_and_animation_is_reachable_while_idle(self):
        for name in ('bleach', 'kimetsu'):
            spec = statusline.load_cast()[name]
            states = {statusline.visual_state(name, spec, 'idle', 'rotation-example', tick*30,
                      {'rotation': 'cycle', 'interval': '30'}) for tick in range(120)}
            self.assertEqual(states, set(spec['states']))
            self.assertEqual({spec['states'][key]['who'] for key in states}, set(spec['members']))
            self.assertEqual(statusline.visual_state(name, spec, 'wait', 'x', 0, {'rotation': 'cycle'}),
                             statusline.cast_animation(name, 'wait'))

    def test_cycle_changes_artwork_without_claiming_error_or_fast(self):
        config.save_selection('codex', cast='luffy', style='mecha', rotation='cycle', interval=10)
        data = {'_agent': 'codex', 'session_id': 'rotation-example', '_activity_state': 'IDLE',
                '_cast_state': 'idle', '_image_protocol': '', '_text_panel_only': True, '_theme_register': False}
        keys = set()
        for tick in range(12):
            rendered = statusline.render(data, now=tick*10)
            keys.add(statusline.PORTRAIT[0])
            self.assertIn('IDLE', rendered)
            self.assertIn('CHILL', rendered)
            self.assertNotIn('ERROR', rendered)
            self.assertIn('[FAST ?]', rendered)
        self.assertGreater(len(keys), 3)
        config.save_selection('codex', rotation='activity', session_id='rotation-example')
        for tick in range(3):
            statusline.render(data, now=tick*10)
            self.assertEqual(statusline.PORTRAIT[0], 'luffy/idle')
        self.assertEqual(config.effective_preferences('codex', include_visuals=True)['rotation'], 'cycle')

    def test_fast_box_appears_in_every_layout(self):
        data = {'session_id': 'mode-example', '_text_panel_only': True, '_image_protocol': '',
                '_theme_register': False, 'service_tier': 'priority', '_activity_state': 'IDLE'}
        for style in config.STYLES:
            config.save_selection('claude', cast='luffy', style=style)
            rendered = statusline.render(data, now=1000)
            self.assertIn('[FAST ON]', rendered)
            self.assertLessEqual(len(rendered.splitlines()), 5)
        data['service_tier'] = None
        self.assertIn('[FAST OFF]', statusline.render(data, now=1000))


if __name__ == '__main__': unittest.main()
