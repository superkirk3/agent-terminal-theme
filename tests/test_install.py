import argparse
import importlib.util
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import install
import uninstall


class InstallTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.home = self.base/'home with spaces'
        self.home.mkdir()
        self.fixture = self.base/'source'
        self.fixture.mkdir()
        for name in install.RUNTIME: shutil.copy2(ROOT/name, self.fixture/name)
        (self.fixture/'assets').mkdir()
        (self.fixture/'assets/example.txt').write_text('fixture')
        (self.fixture/'assets/cast/luffy').mkdir(parents=True)
        self.binary = self.base/'toolchain/codex'
        self.binary.parent.mkdir()
        self.binary.write_text('#!/bin/sh\nprintf "codex test\\n"\n')
        self.binary.chmod(0o755)
        self.source_patch = patch.object(install, 'SOURCE', self.fixture)
        self.source_patch.start()
        self.tmux_patch = patch.object(install.shutil, 'which', return_value='/usr/bin/tmux')
        self.tmux_patch.start()

    def tearDown(self):
        self.tmux_patch.stop(); self.source_patch.stop(); self.temp.cleanup()

    def args(self, **overrides):
        values = dict(codex=True, claude=True, codex_bin=str(self.binary),
                      shell='bash', shell_file=None, dry_run=False)
        values.update(overrides)
        return argparse.Namespace(**values)

    def test_install_is_idempotent_and_uninstall_preserves_unrelated_settings(self):
        settings = self.home/'.claude/settings.json'
        settings.parent.mkdir()
        original = {'statusLine': {'type': 'command', 'command': 'printf old'},
                    'env': {'SENTINEL': 'keep-local'}}
        settings.write_text(json.dumps(original))
        shell = self.home/'.bashrc'
        shell.write_text('# existing shell settings\n')
        install.install(self.args(), self.home)
        install.install(self.args(), self.home)
        self.assertEqual(shell.read_text().count(install.BEGIN), 1)
        data = json.loads(settings.read_text())
        self.assertEqual(data['env'], original['env'])
        self.assertEqual(shlex.split(data['statusLine']['command'])[1],
                         str(self.home/'.local/share/agent-theme/statusline.py'))
        data['new_setting'] = True
        settings.write_text(json.dumps(data))
        shell.write_text(shell.read_text()+'# added after installation\n')
        environment = os.environ.copy()
        environment['AGENT_THEME_REAL_CODEX'] = str(self.binary)
        wrapper = self.home/'.local/share/agent-theme/bin/codex'
        result = subprocess.run([sys.executable, str(wrapper), '--version'], env=environment,
                                capture_output=True, text=True, check=True)
        self.assertEqual(result.stdout.strip(), 'codex test')
        self.assertEqual(self.binary.read_text(), '#!/bin/sh\nprintf "codex test\\n"\n')
        uninstall.uninstall(self.home)
        data = json.loads(settings.read_text())
        self.assertEqual(data['statusLine'], original['statusLine'])
        self.assertEqual(data['env'], original['env'])
        self.assertTrue(data['new_setting'])
        self.assertIn('# added after installation', shell.read_text())
        self.assertNotIn(install.BEGIN, shell.read_text())
        self.assertFalse(wrapper.exists())

    def test_dry_run_does_not_create_runtime_or_change_settings(self):
        install.install(self.args(dry_run=True), self.home)
        self.assertFalse((self.home/'.local').exists())
        self.assertFalse((self.home/'.claude').exists())

    def test_claude_only_needs_no_codex_and_preserves_newer_statusline_on_uninstall(self):
        install.install(self.args(codex=False), self.home)
        settings = self.home/'.claude/settings.json'
        data = json.loads(settings.read_text())
        data['statusLine'] = {'type': 'command', 'command': 'printf newer'}
        settings.write_text(json.dumps(data))
        uninstall.uninstall(self.home)
        self.assertEqual(json.loads(settings.read_text())['statusLine']['command'], 'printf newer')

    def test_manifest_and_backup_permissions_are_private(self):
        settings = self.home/'.claude/settings.json'
        settings.parent.mkdir()
        settings.write_text('{}')
        install.install(self.args(), self.home)
        manifest = self.home/'.local/state/agent-theme/install.json'
        data = json.loads(manifest.read_text())
        self.assertEqual(manifest.stat().st_mode & 0o777, 0o600)
        self.assertEqual(manifest.parent.stat().st_mode & 0o777, 0o700)
        self.assertEqual(Path(data['last_backup']).joinpath('claude-settings.json').stat().st_mode & 0o777, 0o600)

    def test_installed_switcher_survives_update_and_partial_uninstall(self):
        install.install(self.args(), self.home)
        switcher = self.home/'.local/share/agent-theme/bin/agent-theme'
        preferences = self.home/'.config/agent-theme/preferences.json'
        environment = os.environ.copy()
        environment['AGENT_THEME_PREFERENCES'] = str(preferences)
        subprocess.run([sys.executable, str(switcher), 'set', '--cast', 'luffy', '--style', 'pill'],
                       env=environment, capture_output=True, text=True, check=True)
        saved = preferences.read_bytes()
        install.install(self.args(), self.home)
        self.assertEqual(preferences.read_bytes(), saved)
        uninstall.uninstall(self.home, codex=True, claude=False)
        self.assertTrue(switcher.exists())
        self.assertIn(install.BEGIN, (self.home/'.bashrc').read_text())
        self.assertIn('statusLine', json.loads((self.home/'.claude/settings.json').read_text()))
        uninstall.uninstall(self.home, codex=False, claude=True)
        self.assertFalse(switcher.exists())
        self.assertNotIn(install.BEGIN, (self.home/'.bashrc').read_text())
        self.assertEqual(preferences.read_bytes(), saved)

    def test_claude_only_installs_switcher_without_intercepting_codex(self):
        install.install(self.args(codex=False), self.home)
        self.assertTrue((self.home/'.local/share/agent-theme/bin/agent-theme').exists())
        self.assertFalse((self.home/'.local/share/agent-theme/bin/codex').exists())
        self.assertIn(install.BEGIN, (self.home/'.bashrc').read_text())

    def test_copilot_entry_preserves_binary_settings_and_other_components(self):
        settings = self.home/'.copilot/settings.json'
        settings.parent.mkdir()
        settings.write_text('{"statusLine":{"command":"existing-hook"}}')
        original = settings.read_bytes()
        install.install(self.args(codex=False, claude=False, copilot=True, copilot_bin=str(self.binary)), self.home)
        wrapper = self.home/'.local/share/agent-theme/bin/copilot'
        self.assertTrue(wrapper.exists())
        self.assertEqual(settings.read_bytes(), original)
        result = subprocess.run([sys.executable, str(wrapper), '--version'],
            env=dict(os.environ, AGENT_THEME_REAL_COPILOT=str(self.binary)), capture_output=True, text=True, check=True)
        self.assertEqual(result.stdout.strip(), 'codex test')
        uninstall.uninstall(self.home, codex=False, claude=False, copilot=True)
        self.assertFalse(wrapper.exists())
        self.assertEqual(settings.read_bytes(), original)
        self.assertTrue(self.binary.exists())


if __name__ == '__main__': unittest.main()
