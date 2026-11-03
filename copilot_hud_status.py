"""Local Copilot event telemetry. No prompts, credentials or account API calls."""
import json
from pathlib import Path

from codex_hud_status import when
from theme_config import session_key

_CACHE = {}


def session_by_id(home, identity):
    try: identity = session_key('copilot', identity)
    except ValueError: return None
    path = home/'session-state'/identity/'events.jsonl'
    return path if path.is_file() else None


def summarize(rows, previous=None):
    state = dict(previous or {'busy': False, 'model': 'Copilot', 'effort': '',
                 'speed': None, 'speed_label': 'API', 'context_used': None,
                 'context_window': None, 'total_tokens': None, 'ended': 0,
                 'approval': 'default', 'tier_known': False})
    for row in rows:
        kind, data = row.get('type'), row.get('data') or {}
        timestamp = when(row.get('timestamp'))
        if kind == 'session.model_change':
            state['model'] = data.get('newModel') or state['model']
            state['effort'] = data.get('reasoningEffort') or ''
        elif kind in ('assistant.turn_start', 'model.turn_started'):
            state.update(busy=True, activity='WORKING', cast_state='think')
        elif kind == 'tool.execution_start':
            state.update(busy=True, activity='USING TOOL', cast_state='tool')
        elif kind in ('assistant.turn_end', 'session.task_complete', 'session.abort'):
            state.update(busy=False, ended=timestamp, activity='IDLE', cast_state='done')
        elif kind == 'permission.requested':
            state.update(activity='WAITING', cast_state='wait')
        elif kind == 'permission.completed':
            state.update(activity='WORKING', cast_state='think')
        elif kind == 'session.usage_record':
            usage = data.get('usage') or {}
            state['model'] = usage.get('modelDisplayName') or usage.get('model') or state['model']
            state['effort'] = usage.get('reasoningEffort') or state['effort']
            output, duration = usage.get('outputTokens'), usage.get('duration')
            state['speed'] = (output/(duration/1000) if isinstance(output, (int, float)) and output >= 0
                              and isinstance(duration, (int, float)) and duration > 0 else None)
            inputs, maximum = usage.get('inputTokens'), usage.get('maxPromptTokens')
            if isinstance(inputs, (int, float)) and isinstance(output, (int, float)):
                state['total_tokens'] = (state.get('total_tokens') or 0)+inputs+output
                if isinstance(maximum, (int, float)) and maximum > 0:
                    state['context_window'] = maximum
                    state['context_used'] = min(100, max(0, 100*(inputs+output)/maximum))
            cached = usage.get('cacheReadTokens')
            if isinstance(cached, (int, float)) and isinstance(inputs, (int, float)) and inputs > 0:
                state['cache_ratio'] = min(1, max(0, cached/inputs))
            # Premium-request cost is not USD. Deliberately omit all cost fields.
            if 'serviceTier' in usage:
                state.update(service_tier=usage['serviceTier'], tier_known=True)
            if isinstance(usage.get('fastMode'), bool): state['fast_mode'] = usage['fastMode']
    return state


def session_counters(path, now=0, fallback_model=None):
    if path is None: return summarize([])
    try:
        info = path.stat()
        identity = info.st_dev, info.st_ino
        cached = _CACHE.get(path)
        if not cached or identity != cached['identity'] or info.st_size < cached['offset']:
            cached = {'identity': identity, 'offset': 0, 'state': summarize([])}
        with path.open('rb') as stream:
            stream.seek(cached['offset'])
            while True:
                offset = stream.tell()
                line = stream.readline()
                if not line or not line.endswith(b'\n'):
                    cached['offset'] = offset
                    break
                try: row = json.loads(line)
                except (ValueError, UnicodeDecodeError): continue
                if isinstance(row, dict): cached['state'] = summarize([row], cached['state'])
        _CACHE[path] = cached
        return dict(cached['state'])
    except OSError:
        return summarize([])
