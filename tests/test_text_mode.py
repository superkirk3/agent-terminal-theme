"""Regression gate: Windows graphics must not corrupt an active work terminal."""
import importlib.util
import io
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
spec = importlib.util.spec_from_file_location('recovery_panel',ROOT/'codex-pane.py')
panel = importlib.util.module_from_spec(spec)
spec.loader.exec_module(panel)


class TextModeTest(unittest.TestCase):
    def test_windows_static_portrait_never_writes_graphics(self):
        class Output:
            def __init__(self):self.buffer=io.BytesIO()
            def flush(self):pass
        out=Output()
        state={'busy':False,'model':'gpt-6.1-sol','effort':'xhigh','limits':None,
               'context_used':None,'context_window':None,'speed':None,
               'approval':'on-request','ended':0}
        args=['codex-pane.py','--since','0','--cwd','/tmp','--instance','recovery-test']
        frames=sorted((ROOT/'assets/cast/luffy/think').glob('*.png'))
        picks=iter((frames[0],frames[-1]))
        def render(*args):
            panel.theme.PORTRAIT[:]=['luffy/think',next(picks)]
            return '\n'.join(['stable panel']*5)
        with patch.object(sys,'argv',args),patch.object(sys,'stdout',out), \
             patch.object(os,'get_terminal_size',return_value=os.terminal_size((100,5))), \
             patch.object(panel.graphics,'terminal_kind',return_value='windowsterminal'), \
             patch.object(panel.graphics,'position',side_effect=AssertionError('graphics forbidden')), \
             patch.object(panel,'render_frame',side_effect=AssertionError('encoder forbidden')), \
             patch.object(panel.graphics,'frame_at',side_effect=AssertionError('animation forbidden')), \
             patch.object(panel.theme,'render',side_effect=render), \
             patch.object(panel.counters,'current_state',return_value=state), \
             patch.object(panel.time,'sleep',side_effect=[None,KeyboardInterrupt]):
            panel.main()
        raw=out.buffer.getvalue()
        self.assertNotIn(b'\x1bP',raw)
        self.assertNotIn(b'2026',raw)
        for row in range(1,6):
            self.assertEqual(raw.count(f'\x1b[{row};1H'.encode()),1)
            self.assertIn(f'\x1b[{row};13H'.encode(),raw)
        self.assertTrue(any(0x2800<=ord(c)<=0x28ff for c in raw.decode()))


if __name__=='__main__':unittest.main()
