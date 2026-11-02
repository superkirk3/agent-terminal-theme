"""Long turns must retain their state when tool output exceeds the tail window."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import codex_hud_status as counters


def record(kind, payload, timestamp='2026-11-01T02:30:00Z'):
    return json.dumps({'type': kind, 'payload': payload, 'timestamp': timestamp})+'\n'


class CounterTest(unittest.TestCase):
    def test_long_turn_retains_context_and_tracks_completion_incrementally(self):
        with tempfile.TemporaryDirectory() as folder:
            log = Path(folder)/'rollout.jsonl'
            log.write_text(record('event_msg', {'type': 'task_started'})+
                record('turn_context', {'model': 'gpt-6.1-sol', 'effort': 'xhigh', 'approval_policy': 'never'})+
                record('response_item', {'type': 'function_call_output', 'output': 'x'*1_600_000}))
            state = counters.session_counters(log, 0, ('fallback', 'medium'))
            self.assertTrue(state['busy'])
            self.assertEqual((state['model'], state['effort'], state['approval']), ('gpt-6.1-sol', 'xhigh', 'never'))
            with log.open('a') as file:
                file.write(record('event_msg', {'type': 'task_complete'}, '2026-11-01T02:40:00Z'))
            state = counters.session_counters(log, 0, ('fallback', 'medium'))
            self.assertFalse(state['busy'])
            self.assertEqual(state['effort'], 'xhigh')
            log.write_text(record('turn_context', {'model': 'new-model', 'effort': 'high'}))
            state = counters.session_counters(log, 0, ('fallback', 'medium'))
            self.assertFalse(state['busy'])
            self.assertEqual(state['model'], 'new-model')

    def test_partial_record_is_retried_after_writer_finishes(self):
        with tempfile.TemporaryDirectory() as folder:
            log = Path(folder)/'rollout.jsonl'
            data = record('event_msg', {'type': 'task_started'})
            log.write_text(data[:-4])
            self.assertFalse(counters.session_counters(log, 0, ('m', 'high'))['busy'])
            with log.open('a') as file: file.write(data[-4:])
            self.assertTrue(counters.session_counters(log, 0, ('m', 'high'))['busy'])


if __name__ == '__main__':
    unittest.main()
