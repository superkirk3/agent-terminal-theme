#!/usr/bin/env python3
"""Launch a Codex TUI with the shared theme in a five-row tmux pane."""
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import uuid

import portable_images
import native_hud
import windows_paste


def main():
    env = os.environ.copy()
    env.pop('NO_COLOR', None)
    env['AGENT_THEME_TERMINAL'] = portable_images.terminal_kind()
    env['CODEX_HUD_CLI_ONLY'] = '1'
    env['COLORTERM'] = 'truecolor'
    socket = env.get('AGENT_THEME_SOCKET') or 'agent-theme-'+uuid.uuid4().hex
    cwd = str(Path.cwd())
    args = sys.argv[1:]
    session_id = next((x for x in args if re.fullmatch(r'[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}',x)), '') if 'resume' in args else ''
    cmd = [env['AGENT_THEME_REAL_CODEX'], '-c', 'tui.status_line=["task-progress"]', *args]
    launch = shlex.join(cmd)
    cleanup = shlex.join(['tmux','-L',socket,'kill-session','-t','agent'])
    launch += '; code=$?; if [ "$code" -ne 0 ]; then printf "\\nCodex exited (%s). Press Enter.\\n" "$code"; read -r reply; fi; '+cleanup
    def tmux(*args, check=True):
        return subprocess.run(['tmux','-L',socket,'-f','/dev/null',*args],env=env,check=check,capture_output=True,text=True)
    panel = [sys.executable,str(Path(__file__).with_name('codex-pane.py')),
             '--since',str(time.time()-3),'--cwd',cwd,'--instance',socket]
    if session_id:
        panel += ['--session-id',session_id]
    if env.get('TMUX'):
        panel += ['--outer-socket',env['TMUX'].split(',')[0],'--outer-pane',env.get('TMUX_PANE','')]
    footer_socket = ''
    footer_panes = []
    state_dir = ''
    try:
        tmux('new-session','-d','-c',cwd,'-s','agent',launch)
        owner = tmux('display-message', '-p', '-t', 'agent:0.0', '#{pane_pid}').stdout.strip()
        if owner.isdigit(): panel += ['--owner-pid', owner]
        for key,value in [('status','off'),('mouse','on'),('allow-passthrough','all'),('default-terminal','tmux-256color')]:
            tmux('set-option','-g',key,value)
        # Terminals encode Shift+Enter differently. Forward one stable Alt+Enter
        # sequence to Claude/Codex, including through an outer tmux server.
        tmux('set-option','-g','extended-keys','on')
        tmux('bind-key','-n','S-Enter','send-keys','-H','1b','0d')
        inner_socket = tmux('display-message','-p','#{socket_path}').stdout.strip()
        if env['AGENT_THEME_TERMINAL'] == 'windowsterminal' and windows_paste.is_wsl():
            windows_paste.configure(inner_socket)
            if env.get('TMUX'): windows_paste.configure(env['TMUX'].split(',')[0])
        native = (env['AGENT_THEME_TERMINAL'] == 'windowsterminal'
                  and env.get('AGENT_THEME_WINDOWS_TEXT') != '1')
        footer_socket = env['TMUX'].split(',')[0] if env.get('TMUX') else inner_socket
        if native and native_hud.supported(footer_socket):
            state_dir = tempfile.mkdtemp(prefix=socket+'-')
            target = env['TMUX_PANE'] if env.get('TMUX') else 'agent:0.0'
            try:
                footer_panes = native_hud.create(footer_socket, target, panel,
                    state_dir, inner_socket, cwd, env)
            except (OSError, subprocess.SubprocessError) as error:
                print('Native image footer unavailable:', error, file=sys.stderr)
        if not footer_panes:
            tmux('split-window','-d','-v','-l','5','-c',cwd,'-t','agent:0.0',shlex.join(panel))
        # Scrollback remains available through the same mouse behavior as the old HUD.
        subprocess.run(['tmux','-L',socket,'attach-session','-t','agent'],env=env)
    finally:
        if footer_panes:
            native_hud.remove(footer_socket, footer_panes, state_dir)
        tmux('kill-server',check=False)
        if state_dir:
            shutil.rmtree(state_dir, ignore_errors=True)


if __name__ == '__main__':
    main()
