"""Shared, local-only theme preferences; reread on each status refresh."""
import json
import fcntl
import os
from pathlib import Path
import re
import tempfile

STYLES = ('mecha', 'minimal', 'card', 'pill')
AGENTS = ('codex', 'claude', 'copilot')
FIELDS = ('cast', 'style', 'rotation', 'interval')
ROOT = Path(__file__).resolve().parent


def session_key(agent, value):
    if agent not in AGENTS: raise ValueError('Unknown agent')
    if not isinstance(value, str): raise ValueError('Invalid session ID')
    if value.startswith(agent+':'): value = value[len(agent)+1:]
    if any(value.startswith(other+':') for other in AGENTS if other != agent):
        raise ValueError('Session belongs to a different agent')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,199}', value):
        raise ValueError('Invalid session ID')
    return value.lower() if re.fullmatch(r'[0-9a-fA-F-]{36}', value) else value


def catalog():
    data = json.loads((ROOT/'cast.json').read_text(encoding='utf-8'))
    return {name: spec for name, spec in data.items()
            if (ROOT/'assets/cast'/name).is_dir()}


def preferences_path():
    override = os.environ.get('AGENT_THEME_PREFERENCES')
    return Path(override).expanduser() if override else Path.home()/'.config/agent-theme/preferences.json'


def load_preferences(path=None, strict=False):
    path = path if path is not None else preferences_path()
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(data, dict) or data.get('version', 1) != 1:
            raise ValueError('Unsupported preferences format')
        cleaned = {'version': 1}
        for agent in AGENTS:
            profile = data.get(agent, {})
            if not isinstance(profile, dict): raise ValueError('Invalid agent profile')
            cleaned[agent] = {}
            for field in FIELDS:
                if field in profile:
                    if not isinstance(profile[field], str): raise ValueError('Invalid theme choice')
                    cleaned[agent][field] = profile[field]
        sessions = data.get('sessions', {})
        if not isinstance(sessions, dict): raise ValueError('Invalid session preferences')
        cleaned['sessions'] = {}
        for agent in AGENTS:
            profiles = sessions.get(agent, {})
            if not isinstance(profiles, dict): raise ValueError('Invalid session preferences')
            cleaned['sessions'][agent] = {}
            for identity, profile in profiles.items():
                if not isinstance(profile, dict): raise ValueError('Invalid session profile')
                identity = session_key(agent, identity)
                if any(not isinstance(profile.get(key, ''), str) for key in FIELDS):
                    raise ValueError('Invalid session choice')
                cleaned['sessions'][agent][identity] = {key: profile[key] for key in FIELDS if key in profile}
        return cleaned
    except FileNotFoundError:
        return {'version': 1}
    except (OSError, ValueError):
        if strict:
            raise ValueError('Cannot read theme preferences. Fix or move the preferences file before changing it.') from None
        # A broken preferences file must not break a running CLI's status line.
        return {'version': 1}


def effective_preferences(agent, environment=None, preferences=None, session_id=None, session_aliases=(), include_visuals=False):
    if agent not in AGENTS: raise ValueError('Unknown agent')
    environment = os.environ if environment is None else environment
    preferences = load_preferences() if preferences is None else preferences
    profile = preferences.get(agent, {})
    overrides = {}
    sessions = preferences.get('sessions', {}).get(agent, {})
    if session_id:
        for identity in (*session_aliases, session_id):
            overrides.update(sessions.get(session_key(agent, identity), {}))
    prefix = {'codex': 'AGENT_THEME_', 'claude': 'CLAUDE_STATUSLINE_', 'copilot': 'COPILOT_STATUSLINE_'}[agent]
    defaults = {'cast': 'random', 'style': 'random', 'rotation': 'cycle', 'interval': '30'}
    return {field: str(overrides.get(field) or environment.get(prefix+field.upper()) or profile.get(field) or defaults[field]).lower()
            for field in FIELDS if include_visuals or field in ('cast', 'style')}


def save_selection(agent='all', cast=None, style=None, reset=False, path=None, session_id=None, session_aliases=(), rotation=None, interval=None):
    if agent not in (*AGENTS, 'all'): raise ValueError('Unknown agent')
    if cast is not None and cast not in (*catalog(), 'random'): raise ValueError('Unknown character')
    if style is not None and style not in (*STYLES, 'random'): raise ValueError('Unknown layout')
    if rotation is not None and rotation not in ('cycle', 'activity'): raise ValueError('Unknown rotation mode')
    if interval is not None:
        if isinstance(interval, bool) or not str(interval).isdigit() or not 10 <= int(interval) <= 3600:
            raise ValueError('Rotation interval must be 10–3600 seconds')
        interval = str(int(interval))
    changes = {key: value for key, value in dict(cast=cast, style=style, rotation=rotation, interval=interval).items() if value is not None}
    if not reset and not changes: raise ValueError('Choose --cast, --style, --rotation or --interval')
    if session_id is not None and agent == 'all': raise ValueError('A session must belong to exactly one agent')
    if session_id is not None: session_id = session_key(agent, session_id)
    aliases = [session_key(agent, value) for value in session_aliases] if session_id is not None else []
    path = path if path is not None else preferences_path()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Independent terminal commands must not erase each other's session changes.
    descriptor = os.open(str(path)+'.lock', os.O_CREAT | os.O_RDWR, 0o600)
    with os.fdopen(descriptor, 'a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        data = load_preferences(path, strict=True)
        if session_id:
            profiles = data.setdefault('sessions', {}).setdefault(agent, {})
            merged = {}
            for identity in (*aliases, session_id): merged.update(profiles.pop(identity, {}))
            if not reset: profiles[session_id] = merged
            profile = profiles.get(session_id, {})
            if not reset:
                profile.update(changes)
        else:
            for target in AGENTS if agent == 'all' else (agent,):
                if reset: data.pop(target, None)
                else:
                    profile = data.setdefault(target, {})
                    profile.update(changes)
        write_private_json(path, data)
    return data


def write_private_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.NamedTemporaryFile('w', dir=path.parent, prefix='.preferences-',
                                     encoding='utf-8', delete=False) as stream:
        temporary = Path(stream.name)
        try:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    try:
        temporary.replace(path)
        path.chmod(0o600)
    finally:
        temporary.unlink(missing_ok=True)
