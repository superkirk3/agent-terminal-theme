"""Privacy gates must inspect index bytes and must not echo private values."""
import contextlib
import importlib.util
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('privacy_audit', ROOT/'tools/privacy_audit.py')
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class PrivacyTest(unittest.TestCase):
    def test_index_bytes_are_scanned_even_if_worktree_was_cleaned(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            subprocess.run(['git', 'init', '-q', str(root)], check=True)
            value = 'sk-' + 'a' * 32
            file = root/'example.txt'
            file.write_text(value)
            subprocess.run(['git', 'add', 'example.txt'], cwd=root, check=True)
            file.write_text('safe worktree content')
            output = io.StringIO()
            with patch.object(audit, 'ROOT', root), \
                 patch.object(sys, 'argv', ['audit', '--staged']), \
                 contextlib.redirect_stdout(output):
                self.assertTrue(audit.main())
            self.assertIn('API token', output.getvalue())
            self.assertNotIn(value, output.getvalue())

    def test_private_terms_are_checked_in_binary_assets_without_echoing_values(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)/'repo'
            root.mkdir()
            value = 'private-example-host'
            terms = Path(folder)/'terms.txt'
            terms.write_text(value+'\n')
            (root/'avatar.six').write_bytes(b'\x1bP'+value.encode()+b'\x1b\\')
            output = io.StringIO()
            with patch.object(audit, 'ROOT', root), \
                 patch.object(sys, 'argv', ['audit', '--deny-terms-file', str(terms)]), \
                 contextlib.redirect_stdout(output):
                self.assertTrue(audit.main())
            self.assertIn('private deny-list term', output.getvalue())
            self.assertNotIn(value, output.getvalue())


if __name__ == '__main__': unittest.main()
