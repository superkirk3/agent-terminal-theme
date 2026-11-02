"""Shared, local-only theme preferences; reread on each status refresh."""
import json
import os
from pathlib import Path
import tempfile

STYLES = ('mecha', 'minimal', 'card', 'pill')
AGENTS = ('codex', 'claude')
ROOT = Path(__file__).resolve().parent


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
            for field in ('cast', 'style'):
                if field in profile:
                    if not isinstance(profile[field], str): raise ValueError('Invalid theme choice')
                    cleaned[agent][field] = profile[field]
        return cleaned
    except FileNotFoundError:
        return {'version': 1}
    except (OSError, ValueError):
        if strict:
            raise ValueError('Cannot read theme preferences. Fix or move the preferences file before changing it.') from None
        # A broken preferences file must not break a running CLI's status line.
        return {'version': 1}


def effective_preferences(agent, environment=None, preferences=None):
    if agent not in AGENTS: raise ValueError('Unknown agent')
    environment = os.environ if environment is None else environment
    preferences = load_preferences() if preferences is None else preferences
    profile = preferences.get(agent, {})
    prefix = 'AGENT_THEME_' if agent == 'codex' else 'CLAUDE_STATUSLINE_'
    return {field: (environment.get(prefix+field.upper()) or profile.get(field) or 'random').lower()
            for field in ('cast', 'style')}


def save_selection(agent='all', cast=None, style=None, reset=False, path=None):
    if agent not in (*AGENTS, 'all'): raise ValueError('Unknown agent')
    if cast is not None and cast not in (*catalog(), 'random'): raise ValueError('Unknown character')
    if style is not None and style not in (*STYLES, 'random'): raise ValueError('Unknown layout')
    if not reset and cast is None and style is None: raise ValueError('Choose --cast or --style')
    path = path if path is not None else preferences_path()
    data = load_preferences(path, strict=True)
    for target in AGENTS if agent == 'all' else (agent,):
        if reset:
            data.pop(target, None)
        else:
            profile = data.setdefault(target, {})
            if cast is not None: profile['cast'] = cast
            if style is not None: profile['style'] = style
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
    return data
