#!/usr/bin/env python3
"""Detach the theme without removing either CLI or replacing unrelated settings."""
import argparse
import json
from pathlib import Path
import re

from install import BEGIN, END, load_manifest, private_json


def uninstall(home=None, codex=True, claude=True):
    home = home or Path.home()
    state = home/'.local/state/agent-theme/install.json'
    manifest = load_manifest(home)
    if not manifest:
        print('No theme installation manifest found. Nothing changed.')
        return
    if codex and 'codex' in manifest.get('components', []):
        startup = Path(manifest['shell_file']) if manifest.get('shell_file') else None
        if startup and startup.exists():
            content = startup.read_text()
            content = re.sub(r'(?m)^'+re.escape(BEGIN)+r'\n.*?^'+re.escape(END)+r'\n?', '', content, flags=re.S)
            startup.write_text(content)
        wrapper = home/'.local/share/agent-theme/bin/codex'
        if wrapper.exists() and b'Agent theme Codex launcher' in wrapper.read_bytes()[:300]:
            wrapper.unlink()
        manifest['components'].remove('codex')
    if claude and 'claude' in manifest.get('components', []):
        settings = home/'.claude/settings.json'
        data = json.loads(settings.read_text()) if settings.exists() else {}
        if data.get('statusLine') == manifest.get('claude_installed_statusline'):
            if manifest.get('claude_had_statusline'):
                data['statusLine'] = manifest.get('claude_previous_statusline')
            else: data.pop('statusLine', None)
            private_json(settings, data)
        else: print('Claude statusLine was changed after installation; preserved the newer value.')
        manifest['components'].remove('claude')
    private_json(state, manifest)
    print('Theme detached. Open a new shell to discard the current shell function.')
    print('Runtime assets and private backups are retained for manual review/removal.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--codex', action='store_true')
    parser.add_argument('--claude', action='store_true')
    args = parser.parse_args()
    uninstall(codex=args.codex or not args.claude, claude=args.claude or not args.codex)


if __name__ == '__main__': main()
