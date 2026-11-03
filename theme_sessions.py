"""Private renderer heartbeats and unambiguous local session lookup."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

import theme_config as config

RECENT_SECONDS = 120


def registry_directory():
    if os.environ.get('AGENT_THEME_PREFERENCES'):
        return config.preferences_path().parent/'session-registry'
    return Path.home()/'.local/state/agent-theme/session-registry'


def register(agent, identity, cwd, choices, aliases=(), observer=None, now=None):
    """Best effort: discovery failure must never take down a status line."""
    try:
        identity = config.session_key(agent, identity)
        aliases = sorted({config.session_key(agent, value) for value in aliases}-{identity})
        digest = hashlib.sha256((agent+':'+(observer or identity)).encode()).hexdigest()
        target = registry_directory()/(digest+'.json')
        now = time.time() if now is None else now
        data = {'agent': agent, 'session_id': identity, 'aliases': aliases,
                'cwd': str(cwd), 'choices': choices, 'last_seen': now}
        if target.exists() and 0 <= now-target.stat().st_mtime < 3:
            old = json.loads(target.read_text(encoding='utf-8'))
            if isinstance(old, dict) and all(old.get(key) == data[key] for key in ('session_id', 'aliases', 'cwd', 'choices')):
                return
        config.write_private_json(target, data)
    except (OSError, ValueError, TypeError):
        pass


def records(agent='all', include_stale=False, now=None):
    now = time.time() if now is None else now
    merged = {}
    for path in registry_directory().glob('*.json'):
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
            if not isinstance(data, dict) or not isinstance(data.get('choices'), dict): continue
            if not isinstance(data.get('cwd'), str) or not isinstance(data.get('aliases', []), list): continue
            kind = data['agent']
            identity = config.session_key(kind, data['session_id'])
            seen = float(data['last_seen'])
            if agent != 'all' and kind != agent: continue
            if not include_stale and not 0 <= now-seen <= RECENT_SECONDS: continue
            aliases = {config.session_key(kind, value) for value in data.get('aliases', [])}
            key = kind, identity
            previous = merged.get(key)
            if previous:
                aliases.update(previous['aliases'])
                if previous['last_seen'] > seen: data = previous
            merged[key] = {**data, 'session_id': identity, 'aliases': sorted(aliases)}
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return sorted(merged.values(), key=lambda value: (value['agent'], -value['last_seen']))


def resolve(value, agent='all'):
    """Exact IDs win; a short prefix is accepted only for a unique session."""
    if not isinstance(value, str) or not value: raise ValueError('Choose a session ID from agent-theme sessions')
    qualifier, separator, remainder = value.partition(':')
    if separator and qualifier in config.AGENTS:
        if agent not in ('all', qualifier): raise ValueError('Session belongs to a different agent')
        agent, value = qualifier, remainder
    value = config.session_key(agent if agent != 'all' else 'codex', value)
    available = {(row['agent'], row['session_id']): row for row in records(agent, include_stale=True)}
    known_aliases = {(row['agent'], alias) for row in available.values() for alias in row.get('aliases', [])}
    preferences = config.load_preferences(strict=True)
    for kind, entries in preferences.get('sessions', {}).items():
        if agent not in ('all', kind): continue
        for identity in entries:
            if (kind, identity) in known_aliases: continue
            available.setdefault((kind, identity), {'agent': kind, 'session_id': identity, 'aliases': []})
    exact, prefixes = {}, {}
    for key, row in available.items():
        names = [row['session_id'], *row.get('aliases', [])]
        if value in names: exact[key] = row
        elif any(name.startswith(value) for name in names): prefixes[key] = row
    matches = exact or prefixes
    if len(matches) > 1: raise ValueError('Ambiguous session ID. Use the full ID and --agent codex or --agent claude.')
    if matches: return next(iter(matches.values()))
    if agent == 'all': raise ValueError('Unknown session. Use agent-theme sessions, or specify --agent with a full ID.')
    return {'agent': agent, 'session_id': config.session_key(agent, value), 'aliases': []}


def process_tree(owner_pid):
    if not owner_pid: return set()
    try:
        table = subprocess.run(['ps', '-axo', 'pid=,ppid='], capture_output=True, text=True,
                               timeout=1, check=True).stdout
        children = {}
        for line in table.splitlines():
            pid, parent = map(int, line.split())
            children.setdefault(parent, []).append(pid)
        descendants, pending = set(), [int(owner_pid)]
        while pending:
            pid = pending.pop()
            if pid in descendants: continue
            descendants.add(pid)
            pending.extend(children.get(pid, []))
        return descendants
    except (OSError, ValueError, subprocess.SubprocessError):
        return set()


def owned_paths(owner_pid):
    """Read open file paths from this process tree, never another same-cwd CLI."""
    descendants = process_tree(owner_pid)
    if not descendants: return set()
    try:
        paths = set()
        if Path('/proc/self/fd').is_dir():
            for pid in descendants:
                for descriptor in Path(f'/proc/{pid}/fd').glob('*'):
                    try: paths.add(Path(os.readlink(descriptor)))
                    except OSError: pass
        else:
            output = subprocess.run(['lsof', '-n', '-P', '-a', '-p', ','.join(map(str, descendants)), '-Fn'],
                                    capture_output=True, text=True, timeout=1).stdout
            paths = {Path(line[1:]) for line in output.splitlines() if line.startswith('n/')}
        return paths
    except (OSError, ValueError, subprocess.SubprocessError):
        return set()


def owned_codex_session(owner_pid, home):
    """Require exactly one open CLI rollout; ambiguous ownership stays unknown."""
    try:
        paths = owned_paths(owner_pid)
        root = (home/'sessions').resolve()
        identities = set()
        for path in paths:
            if not path.is_relative_to(root) or not path.name.startswith('rollout-') or path.suffix != '.jsonl': continue
            try:
                with path.open('rb') as stream: row = json.loads(stream.readline(65536))
                meta = row.get('payload') or {}
                source = meta.get('source')
                if row.get('type') == 'session_meta' and isinstance(source, str) and source.lower() in ('cli', 'tui'):
                    identities.add(config.session_key('codex', meta.get('id', '')))
            except (OSError, ValueError, TypeError): pass
        return identities.pop() if len(identities) == 1 else ''
    except (OSError, ValueError, subprocess.SubprocessError):
        return ''


def owned_copilot_session(owner_pid, home):
    root = (home/'session-state').resolve()
    identities = set()
    for path in owned_paths(owner_pid):
        if not path.is_relative_to(root): continue
        parts = path.relative_to(root).parts
        if len(parts) != 2 or not (parts[1] == 'session.db' or parts[1].startswith('inuse.')): continue
        try: identities.add(config.session_key('copilot', parts[0]))
        except ValueError: pass
    return identities.pop() if len(identities) == 1 else ''


def owned_copilot_pid(owner_pid):
    """WSL: identify a native CLI even while it has no session open yet."""
    candidates = {}
    for pid in process_tree(owner_pid):
        try:
            proc = Path(f'/proc/{pid}')
            args = (proc/'cmdline').read_bytes().split(b'\0')
            if Path(os.fsdecode(args[0])).name != 'copilot': continue
            if any(b'extension_bootstrap' in value for value in args[1:]): continue
            parent = int((proc/'stat').read_text().rsplit(')', 1)[1].split()[1])
            candidates[pid] = parent
        except (OSError, ValueError, IndexError): pass
    roots = {pid for pid, parent in candidates.items() if parent not in candidates}
    return roots.pop() if len(roots) == 1 else 0
