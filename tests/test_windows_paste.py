"""Clipboard content is data, never a shell command or a submitted prompt."""
import base64
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import windows_paste as paste


class ClipboardTest(unittest.TestCase):
    def test_unicode_multiline_text_remains_data_and_buffers_are_deleted(self):
        text = '中文 $(printf unsafe) `id`\r\nsecond line\r\n'
        values = paste.payloads({'kind': 'text', 'text': text}, {})
        self.assertEqual(values, ['中文 $(printf unsafe) `id`\nsecond line\n'])
        calls = []
        def tmux(socket, *args, **kwargs):
            calls.append((args, kwargs))
            return subprocess.CompletedProcess([], 0, stdout=b'')
        with patch.object(paste, 'tmux', side_effect=tmux): paste.paste('/tmp/test.sock', '%3', values)
        self.assertEqual(calls[0][1]['input'], values[0].encode())
        self.assertNotIn(values[0], calls[0][0])
        self.assertEqual(calls[1][0][0], 'paste-buffer')
        self.assertIn('-p', calls[1][0])
        self.assertIn('-d', calls[1][0])
        self.assertEqual(calls[2][0][0], 'delete-buffer')
        self.assertFalse(any(args[0] == 'send-keys' for args, _ in calls))

    def test_bitmap_is_a_private_png_not_clipboard_text(self):
        raw = next((ROOT/'assets/cast/luffy/idle').glob('*.png')).read_bytes()
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)/'clipboard'
            values = paste.payloads({'kind': 'image', 'png': base64.b64encode(raw).decode()}, {}, directory)
            file = Path(shlex.split(values[0])[0])
            self.assertEqual(file.read_bytes(), raw)
            self.assertEqual(file.stat().st_mode & 0o777, 0o600)
            self.assertEqual(directory.stat().st_mode & 0o777, 0o700)

    def test_copied_image_files_become_individual_quoted_wsl_paths(self):
        with tempfile.TemporaryDirectory() as folder:
            paths = [Path(folder)/'first image.png', Path(folder)/'second image.jpg']
            for path in paths: path.write_bytes(b'fixture')
            with patch.object(paste, 'mapped_path', side_effect=paths):
                values = paste.payloads({'kind': 'files', 'files': ['C:\\one.png', 'C:\\two.jpg']}, {})
            self.assertEqual([shlex.split(value)[0] for value in values], list(map(str, paths)))

    def test_wsl_unc_file_drop_uses_the_current_distribution(self):
        with tempfile.TemporaryDirectory() as folder:
            file = Path(folder)/'image with spaces.png'
            file.write_bytes(b'fixture')
            unc = '\\\\wsl.localhost\\Ubuntu'+str(file).replace('/', '\\')
            self.assertEqual(paste.mapped_path(unc, {'WSL_DISTRO_NAME': 'Ubuntu'}), file)

    def test_failed_paste_still_deletes_the_temporary_tmux_buffer(self):
        calls = []
        def tmux(socket, *args, **kwargs):
            calls.append(args)
            if args[0] == 'paste-buffer': raise subprocess.CalledProcessError(1, 'tmux')
        with patch.object(paste, 'tmux', side_effect=tmux):
            with self.assertRaises(subprocess.CalledProcessError): paste.paste('/tmp/test.sock', '%1', ['example'])
        self.assertEqual(calls[-1][0], 'delete-buffer')


if __name__ == '__main__': unittest.main()
