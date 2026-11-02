#!/usr/bin/env python3
"""Install the theme without replacing either CLI or uploading local settings."""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import shlex
import shutil
import sys
import tempfile

SOURCE = Path(__file__).resolve().parent
RUNTIME = ('theme_config.py', 'theme_sessions.py', 'theme_refresh.py', 'theme.py', 'statusline.py', 'codex-launch.py', 'codex-hud.py', 'codex-pane.py',
           'codex_hud_status.py', 'portable_images.py', 'sixel_frames.py',
           'native_avatar.py', 'native_hud.py', 'shell.sh', 'cast.json',
           'naruto-quotes.json', 'naruto-sprites.json')
BEGIN = '# >>> agent-terminal-theme >>>'
END = '# <<< agent-terminal-theme <<<'


def private_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.NamedTemporaryFile('w', dir=path.parent, prefix='.'+path.name+'.',
                                     encoding='utf-8', delete=False) as file:
        temporary = Path(file.name)
        json.dump(value, file, indent=2, ensure_ascii=False)
        file.write('\n')
    temporary.replace(path)
    path.chmod(0o600)


def load_manifest(home):
    path = home/'.local/state/agent-theme/install.json'
    try: return json.loads(path.read_text())
    except FileNotFoundError: return {}


def discover_codex(home, explicit=None, previous=None):
    candidates = []
    if explicit:
        candidates.append(Path(explicit).expanduser().absolute())
    else:
        if previous: candidates.append(Path(previous))
        candidates.extend((home/'.codex/packages/standalone/current/bin/codex',
                           home/'.local/bin/codex-real'))
        candidates.extend(Path(part)/'codex' for part in os.get_exec_path() if part)
    target = home/'.local/share/agent-theme'
    for candidate in candidates:
        if not candidate.is_file() or not os.access(candidate, os.X_OK): continue
        resolved = candidate.resolve()
        if resolved.is_relative_to(target.resolve()) or resolved.name.lower().endswith('.exe'): continue
        with candidate.open('rb') as file: header = file.read(300)
        if b'Agent theme Codex launcher' in header: continue
        if b'node.exe' in header: continue
        # Preserve package-manager/standalone symlinks so CLI updates still work.
        return str(candidate.absolute())
    raise RuntimeError('Linux/macOS Codex executable not found. Install Codex first or pass --codex-bin PATH.')


def backup_file(path, backup, label):
    if not path.exists(): return
    backup.mkdir(parents=True, exist_ok=True, mode=0o700)
    saved = backup/label
    shutil.copy2(path, saved)
    saved.chmod(0o600)


def install(args, home=None):
    home = home or Path.home()
    if os.name != 'posix': raise RuntimeError('Use macOS or WSL. Native PowerShell is not supported.')
    if sys.version_info < (3, 11): raise RuntimeError('Python 3.11 or newer is required.')
    target = home/'.local/share/agent-theme'
    state = home/'.local/state/agent-theme'
    manifest = load_manifest(home)
    manifest.setdefault('version', 1)
    manifest.setdefault('components', [])
    real = None
    if args.codex:
        if not shutil.which('tmux'): raise RuntimeError('tmux is required for the Codex HUD.')
        real = discover_codex(home, args.codex_bin, manifest.get('real_codex'))
    shell = args.shell
    if shell == 'auto': shell = Path(os.environ.get('SHELL', '/bin/bash')).name
    if shell not in ('bash', 'zsh', 'none'):
        raise RuntimeError('Choose --shell bash, --shell zsh, or --shell none.')
    settings = home/'.claude/settings.json'
    data = json.loads(settings.read_text()) if args.claude and settings.exists() else {}
    if not isinstance(data, dict): raise RuntimeError('Claude settings must contain a JSON object.')
    summary = {'target': str(target), 'codex': args.codex, 'claude': args.claude,
               'shell': shell, 'real_codex': real}
    if args.dry_run:
        print(json.dumps(summary, indent=2))
        return summary
    backup = state/'backups'/datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    state.chmod(0o700)
    target.mkdir(parents=True, exist_ok=True)
    for name in RUNTIME: shutil.copy2(SOURCE/name, target/name)
    shutil.copytree(SOURCE/'assets', target/'assets', dirs_exist_ok=True)
    manifest['target'] = str(target)
    (target/'bin').mkdir(exist_ok=True)
    switcher = target/'bin/agent-theme'
    shutil.copy2(SOURCE/'theme.py', switcher)
    switcher.chmod(0o755)
    if args.codex:
        wrapper = target/'bin/codex'
        shutil.copy2(SOURCE/'codex-launch.py', wrapper)
        wrapper.chmod(0o755)
        manifest['real_codex'] = real
        if 'codex' not in manifest['components']: manifest['components'].append('codex')
    if shell != 'none':
        startup = Path(args.shell_file).expanduser().absolute() if args.shell_file else home/('.'+shell+'rc')
        text = startup.read_text() if startup.exists() else ''
        if BEGIN not in text:
            backup_file(startup, backup, 'shellrc')
            startup.parent.mkdir(parents=True, exist_ok=True)
            text += ('\n'+BEGIN+'\n'
                     '[ ! -r "$HOME/.local/share/agent-theme/shell.sh" ] || '
                     '. "$HOME/.local/share/agent-theme/shell.sh"\n'+END+'\n')
            startup.write_text(text)
        manifest['shell_file'] = str(startup)
    if args.claude:
        if 'claude' not in manifest['components']:
            manifest['claude_had_statusline'] = 'statusLine' in data
            manifest['claude_previous_statusline'] = data.get('statusLine')
            manifest['components'].append('claude')
        backup_file(settings, backup, 'claude-settings.json')
        command = shlex.join([sys.executable, str(target/'statusline.py')])
        data['statusLine'] = {'type': 'command', 'command': command, 'refreshInterval': 1}
        private_json(settings, data)
        manifest['claude_installed_statusline'] = data['statusLine']
    manifest['last_backup'] = str(backup)
    private_json(state/'install.json', manifest)
    print('Theme installed:', target)
    if args.codex:
        print('Original Codex:', real)
    print('Open a new shell, or run: . "$HOME/.local/share/agent-theme/shell.sh"')
    print('Switch characters and layouts with: agent-theme')
    if args.claude: print('Claude: start or resume normally; existing settings were merged.')
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--codex', action='store_true', help='Install the Codex HUD entry point')
    parser.add_argument('--claude', action='store_true', help='Set Claude Code statusLine')
    parser.add_argument('--codex-bin', help='Path to an existing Linux/macOS Codex executable')
    parser.add_argument('--shell', choices=('auto', 'bash', 'zsh', 'none'), default='auto')
    parser.add_argument('--shell-file', help='Optional shell startup file override')
    parser.add_argument('--dry-run', action='store_true', help='Show planned changes without writing files')
    args = parser.parse_args()
    if not (args.codex or args.claude): parser.error('Choose --codex, --claude, or both.')
    try: install(args)
    except (OSError, ValueError, RuntimeError) as error:
        parser.exit(1, str(error)+'\n')


if __name__ == '__main__': main()
