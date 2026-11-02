"""Exercise two running tmux HUDs with synthetic clients, without API calls."""
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import theme_config as config
import theme_refresh
import theme_sessions as sessions


@unittest.skipUnless(shutil.which('tmux') and (Path('/proc/self/fd').is_dir() or shutil.which('lsof')),
                     'Requires tmux and /proc or lsof for process ownership verification')
class RunningSessionTest(unittest.TestCase):
    def wait_for(self, predicate, message):
        deadline = time.monotonic()+10
        while time.monotonic() < deadline:
            if predicate(): return
            time.sleep(.1)
        self.fail(message)

    def test_hud_only_upgrade_and_session_switch_preserve_both_running_clients(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            preferences = root/'preferences.json'
            project = root/'project'
            project.mkdir()
            home = root/'synthetic-data'
            (home/'sessions').mkdir(parents=True)
            bootstrap = root/'bootstrap'
            bootstrap.mkdir()
            # Redirect only the test subprocess's readers to synthetic data.
            # HOME and CODEX_HOME are never changed, and no real CLI is started.
            (bootstrap/'sitecustomize.py').write_text(
                'from pathlib import Path\nimport codex_hud_status as counters\nimport theme_sessions\n'
                "counters.current_state = lambda *args: dict(busy=False, model='Synthetic Model', effort='high', "
                "limits=None, context_used=20, context_window=200000, speed=None, approval='on-request', ended=0)\n"
                '_owned = theme_sessions.owned_codex_session\n'
                f'theme_sessions.owned_codex_session = lambda pid, home: _owned(pid, Path({str(home)!r}))\n')
            environment = os.environ.copy()
            environment.pop('TMUX', None)
            environment.pop('TMUX_PANE', None)
            active = []
            def tmux(socket, *args, check=True):
                return subprocess.run(['tmux', '-S', str(socket), *args], env=environment,
                                      capture_output=True, text=True, check=check, timeout=5).stdout.strip()
            def pane_pid(socket, pane):
                return tmux(socket, 'display-message', '-p', '-t', pane, '#{pane_pid}')
            def capture(socket, pane):
                return tmux(socket, 'capture-pane', '-p', '-t', pane)
            overrides = {'AGENT_THEME_PREFERENCES': str(preferences), 'AGENT_THEME_CAST': '',
                         'AGENT_THEME_STYLE': '', 'CLAUDE_STATUSLINE_CAST': '', 'CLAUDE_STATUSLINE_STYLE': ''}
            with patch.dict(os.environ, overrides):
                config.save_selection(cast='luffy', style='mecha')
                try:
                    for suffix in ('a', 'b'):
                        socket = root/f'tmux-{suffix}.sock'
                        active.append(socket)
                        identity = 'session-live-'+suffix
                        log = home/'sessions'/f'rollout-{identity}.jsonl'
                        log.write_text(json.dumps({'type': 'session_meta', 'payload':
                                      {'id': identity, 'source': 'cli', 'cwd': str(project)}})+'\n')
                        prefix = ['env', 'AGENT_THEME_TERMINAL=windowsterminal',
                                  'AGENT_THEME_PREFERENCES='+str(preferences), 'AGENT_THEME_CAST=', 'AGENT_THEME_STYLE=',
                                  'PYTHONPATH='+str(bootstrap)+os.pathsep+str(ROOT)]
                        client = [*prefix, sys.executable, '-u', '-c',
                                  "import sys,time; handle=open(sys.argv[1]); print('Synthetic CLI running'); time.sleep(60)", str(log)]
                        tmux(socket, '-f', '/dev/null', 'new-session', '-d', '-x', '160', '-y', '16',
                             '-s', 'agent', '-c', str(project), shlex.join(client))
                        panel = [*prefix, sys.executable, str(ROOT/'codex-pane.py'), '--since', str(time.time()),
                                 '--cwd', str(project), '--instance', 'runtime-'+suffix]
                        pane = tmux(socket, 'split-window', '-d', '-v', '-l', '5', '-P', '-F', '#{pane_id}',
                                    '-t', 'agent:0.0', shlex.join(panel))
                        setattr(self, suffix, (socket, pane))
                        self.wait_for(lambda: 'LUFFY' in capture(socket, pane), 'Initial HUD did not render')
                    main_before = [pane_pid(socket, 'agent:0.0') for socket in active]
                    hud_before = [pane_pid(*getattr(self, suffix)) for suffix in ('a', 'b')]
                    with patch.object(theme_refresh, 'socket_paths', return_value=iter(active)):
                        refreshed = theme_refresh.refresh()
                    if refreshed != 2:
                        details = [tmux(socket, 'list-panes', '-a', '-F',
                                   '#{pane_id}\t#{pane_pid}\t#{pane_current_command}\t#{pane_start_command}') for socket in active]
                        details += [subprocess.check_output(['ps', '-p', pid, '-o', 'command='], text=True) for pid in hud_before]
                        self.fail(f'Refreshed {refreshed} renderers: {details!r}')
                    self.wait_for(lambda: {row['session_id'] for row in sessions.records()} ==
                                  {'session-live-a', 'session-live-b'}, 'HUDs did not discover their own session IDs')
                    self.assertEqual([pane_pid(socket, 'agent:0.0') for socket in active], main_before)
                    hud_after = [pane_pid(*getattr(self, suffix)) for suffix in ('a', 'b')]
                    self.assertTrue(all(before != after for before, after in zip(hud_before, hud_after)))
                    other_before = capture(*self.b)
                    config.save_selection('codex', cast='goku', style='card', session_id='session-live-a')
                    self.wait_for(lambda: 'GOKU' in capture(*self.a), 'Running session A did not switch')
                    self.assertEqual(capture(*self.b).splitlines()[1:], other_before.splitlines()[1:])
                    self.assertIn('LUFFY', capture(*self.b))
                    self.assertEqual([pane_pid(socket, 'agent:0.0') for socket in active], main_before)
                    self.assertEqual([pane_pid(*getattr(self, suffix)) for suffix in ('a', 'b')], hud_after)
                finally:
                    for socket in active: tmux(socket, 'kill-server', check=False)


class RefreshSafetyTest(unittest.TestCase):
    def test_renderer_path_in_another_programs_arguments_is_never_a_refresh_target(self):
        unrelated = shlex.join([sys.executable, 'user-task.py', 'python3', str(ROOT/'codex-pane.py')])
        self.assertIsNone(theme_refresh.renderer_command(unrelated))
        self.assertIsNone(theme_refresh.renderer_command(shlex.join([sys.executable, '-c', 'print(1)',
                                                                    'python3', str(ROOT/'codex-pane.py')])))

    def test_refresh_skips_agent_panes_idle_shells_and_unrelated_python(self):
        renderer = shlex.join([sys.executable, str(ROOT/'codex-pane.py'), '--instance', 'example', '--since', '0', '--cwd', '/tmp'])
        listing = ('%0\t100\tcodex\tcodex\n'
                   '%1\t101\tzsh\t'+renderer+'\n'
                   '%2\t102\tpython3\t'+renderer+'\n'
                   '%3\t103\tpython3\tpython3 user-task.py\n')
        commands = []
        def tmux(socket, *args):
            commands.append(args)
            output = listing if args[0] == 'list-panes' else '%0\t100' if args[0] == 'display-message' else ''
            return subprocess.CompletedProcess([], 0, stdout=output)
        with patch.object(theme_refresh, 'socket_paths', return_value=iter([Path('/tmp/test.sock')])), \
             patch.object(theme_refresh, 'tmux', side_effect=tmux), \
             patch.object(theme_refresh.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, stdout=renderer)):
            self.assertEqual(theme_refresh.refresh(), 1)
        respawns = [args for args in commands if args[0] == 'respawn-pane']
        self.assertEqual(len(respawns), 1)
        self.assertEqual(respawns[0][3], '%2')
        self.assertFalse(any(args[0] in ('kill-server', 'kill-pane', 'send-keys') for args in commands))


if __name__ == '__main__': unittest.main()
