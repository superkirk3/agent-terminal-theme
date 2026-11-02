#!/usr/bin/env python3
"""Paste the Windows clipboard into a WSL pane without logging its contents."""
import argparse
import base64
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import uuid

SCRIPT = r'''
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
try {
    Add-Type -AssemblyName System.Windows.Forms
    function Read-ClipboardObject($data) {
        if ($null -eq $data) { return @{kind='empty'} }
        if ($data.GetDataPresent([Windows.Forms.DataFormats]::FileDrop)) {
            $files = @($data.GetData([Windows.Forms.DataFormats]::FileDrop) | ForEach-Object { [string]$_ })
            return @{kind='files'; files=$files}
        } elseif ($data.GetDataPresent([Windows.Forms.DataFormats]::Bitmap)) {
            $image = $data.GetData([Windows.Forms.DataFormats]::Bitmap)
            $stream = [IO.MemoryStream]::new()
            try {
                $image.Save($stream, [Drawing.Imaging.ImageFormat]::Png)
                return @{kind='image'; png=[Convert]::ToBase64String($stream.ToArray())}
            } finally { $stream.Dispose(); $image.Dispose() }
        } elseif ($data.GetDataPresent([Windows.Forms.DataFormats]::UnicodeText)) {
            return @{kind='text'; text=[string]$data.GetData([Windows.Forms.DataFormats]::UnicodeText)}
        }
        return @{kind='empty'}
    }
    Read-ClipboardObject ([Windows.Forms.Clipboard]::GetDataObject()) | ConvertTo-Json -Compress
} catch {
    [Console]::Error.WriteLine('Windows clipboard read failed.')
    exit 1
}
'''
IMAGES = {'.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp', '.tiff'}


def is_wsl():
    try: return 'microsoft' in Path('/proc/sys/kernel/osrelease').read_text().lower()
    except OSError: return False


def tmux(socket, *args, input=None, check=True):
    return subprocess.run(['tmux', '-S', str(socket), *args], input=input, capture_output=True,
                          check=check, timeout=5)


def environment_for(socket=None, pane=None):
    environment = os.environ.copy()
    if socket and pane:
        # Use the attached terminal's live interop socket before stale server state.
        for field in ('#{client_pid}', '#{pane_pid}'):
            result = tmux(socket, 'display-message', '-p', '-t', pane, field, check=False)
            pid = result.stdout.decode().strip()
            if not pid.isdigit(): continue
            try:
                entries = (Path('/proc')/pid/'environ').read_bytes().split(b'\0')
                selected = {}
                for entry in entries:
                    key, separator, value = entry.partition(b'=')
                    if separator and key in (b'WSL_INTEROP', b'WSL_DISTRO_NAME', b'DISPLAY', b'WAYLAND_DISPLAY', b'XDG_RUNTIME_DIR'):
                        selected[key.decode()] = value.decode()
                if selected.get('WSL_INTEROP') and Path(selected['WSL_INTEROP']).exists():
                    environment.update(selected)
                    break
            except (OSError, UnicodeError): pass
    return environment


def read_clipboard(environment):
    executable = shutil.which('powershell.exe', path=environment.get('PATH'))
    if not executable:
        candidate = Path('/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe')
        if candidate.is_file(): executable = str(candidate)
    if not executable: raise RuntimeError('Windows PowerShell is unavailable')
    # The Linux shell starts promptly even if WSL Windows-process startup stalls.
    result = subprocess.run(['/bin/sh', '-c', 'exec "$@"', 'agent-theme-clipboard', executable,
                             '-NoProfile', '-NonInteractive', '-STA', '-Command', SCRIPT],
                            env=environment, capture_output=True, timeout=10)
    if result.returncode: raise RuntimeError('Windows clipboard is unavailable')
    return json.loads(result.stdout.decode('utf-8-sig').strip())


def mapped_path(value, environment):
    unc = re.match(r'^\\\\wsl(?:\.localhost|\$)\\([^\\]+)\\(.*)$', value, re.I)
    if unc and unc.group(1).lower() == environment.get('WSL_DISTRO_NAME', '').lower():
        path = Path('/'+unc.group(2).replace('\\', '/'))
    else:
        result = subprocess.run(['wslpath', '-u', value], env=environment, capture_output=True,
                                text=True, check=True, timeout=3)
        path = Path(result.stdout.strip())
    if not path.is_file(): raise RuntimeError('A clipboard file is not accessible from WSL')
    return path


def payloads(data, environment, directory=None):
    kind = data.get('kind')
    if kind == 'text': return [data['text'].replace('\r\n', '\n').replace('\r', '\n')] if data.get('text') else []
    if kind == 'empty': return []
    if kind == 'files':
        paths = [mapped_path(value, environment) for value in data['files']]
        if paths and all(path.suffix.lower() in IMAGES for path in paths):
            return [shlex.quote(str(path)) for path in paths]
        return [' '.join(shlex.quote(str(path)) for path in paths)] if paths else []
    if kind == 'image':
        raw = base64.b64decode(data['png'], validate=True)
        if not raw.startswith(b'\x89PNG\r\n\x1a\n'): raise RuntimeError('Clipboard image is not PNG')
        directory = directory or Path.home()/'.cache/agent-theme/clipboard'
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        with tempfile.NamedTemporaryFile('wb', prefix='paste-', suffix='.png', dir=directory, delete=False) as stream:
            stream.write(raw)
            name = stream.name
        return [shlex.quote(name)]
    raise RuntimeError('Unsupported clipboard format')


def paste(socket, pane, values):
    for value in values:
        buffer = 'agent-theme-paste-'+uuid.uuid4().hex
        try:
            tmux(socket, 'load-buffer', '-b', buffer, '-', input=value.encode('utf-8'))
            tmux(socket, 'paste-buffer', '-p', '-d', '-b', buffer, '-t', pane)
        finally:
            tmux(socket, 'delete-buffer', '-b', buffer, check=False)


def configure(socket):
    command = shlex.join([sys.executable, str(Path(__file__).resolve()), '--socket', str(socket), '--pane', '#{pane_id}'])
    tmux(socket, 'bind-key', '-n', 'C-v', 'run-shell', '-b', command)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--socket')
    parser.add_argument('--pane')
    parser.add_argument('--configure', action='store_true')
    parser.add_argument('--print', action='store_true', dest='print_text', help='Return the payload to a local shell widget')
    args = parser.parse_args()
    try:
        if args.configure:
            if not args.socket: parser.error('--configure requires --socket')
            configure(args.socket)
            return
        if not args.print_text and not (args.socket and args.pane): parser.error('Choose --print or --socket with --pane')
        environment = environment_for(args.socket, args.pane)
        values = payloads(read_clipboard(environment), environment)
        if args.print_text: sys.stdout.write(' '.join(values))
        else: paste(args.socket, args.pane, values)
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, subprocess.SubprocessError):
        # Clipboard data must never appear in logs, notifications or exceptions.
        message = 'Clipboard paste failed. Check Windows clipboard and WSL interop.'
        if args.socket and args.pane:
            tmux(args.socket, 'display-message', '-t', args.pane, message, check=False)
        else: print(message, file=sys.stderr)
        raise SystemExit(1)


if __name__ == '__main__': main()
