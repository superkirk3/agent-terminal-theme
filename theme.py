#!/usr/bin/env python3
"""Agent theme switcher: choose persistent characters and layouts locally."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
if not (ROOT/'theme_config.py').is_file(): ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))
import theme_config as config
import theme_sessions as sessions


def show(target=None):
    preferences = config.load_preferences(strict=True)
    if target:
        agent, identity = target['agent'], target['session_id']
        profiles = preferences.get('sessions', {}).get(agent, {})
        saved = {}
        for value in (*target.get('aliases', []), identity): saved.update(profiles.get(value, {}))
        print(f"{agent}:{identity}: cast={saved.get('cast', '<inherit>')}  style={saved.get('style', '<inherit>')}")
        print('Session overrides take priority over environment and client defaults.')
        return
    for agent in config.AGENTS:
        saved = preferences.get(agent, {})
        effective = config.effective_preferences(agent, preferences=preferences)
        print(f"{agent}: cast={effective['cast']}  style={effective['style']}")
        if any(effective[field] != saved.get(field, 'random') for field in ('cast', 'style')):
            print('  Environment overrides saved preferences for this shell.')


def printable(value):
    return ''.join(char if char.isprintable() else '?' for char in str(value))


def show_sessions(agent='all', include_stale=False, as_json=False):
    rows = sessions.records(agent, include_stale)
    if as_json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    elif not rows:
        print('No recently refreshed sessions. Use --all for older entries; upgrade old Codex HUDs with agent-theme refresh.')
    else:
        print('AGENT   SESSION ID / HUD ID                         CAST       STYLE     PROJECT')
        for row in rows:
            choice = row.get('choices', {})
            print(f"{row['agent']:7} {row['session_id']:42} {choice.get('cast', '?'):10} "
                  f"{choice.get('style', '?'):9} {printable(row.get('cwd', ''))}")


def menu_choice(title, choices, default=None):
    print('\n'+title)
    for index, (value, label) in enumerate(choices, 1):
        print(f'  {index}. {label}')
    while True:
        reply = input('Choose a number (Enter keeps the current value): ').strip()
        if not reply: return default
        if reply.isdigit() and 1 <= int(reply) <= len(choices):
            return choices[int(reply)-1][0]
        print('Please choose a listed number.')


def interactive():
    show()
    choices = [('all', 'Codex + Claude defaults'), ('codex', 'Codex defaults'), ('claude', 'Claude defaults')]
    choices += [(row, printable(f"Session {row['agent']}:{row['session_id']} · {row.get('cwd', '')}"))
                for row in sessions.records()]
    selected = menu_choice('Apply to (default: both client defaults)', choices, 'all')
    target = selected if isinstance(selected, dict) else None
    agent = target['agent'] if target else selected
    cast = menu_choice('Character', [('random', 'Random per session')]+
                       [(key, f"{key} · {spec.get('name', key)}") for key, spec in config.catalog().items()])
    style = menu_choice('Layout', [('random', 'Random per session')]+[(key, key) for key in config.STYLES])
    if cast is None and style is None:
        print('No changes.')
        return
    config.save_selection(agent, cast, style, session_id=target['session_id'] if target else None,
                          session_aliases=target.get('aliases', ()) if target else ())
    print('Saved. Running status lines use the selection on their next refresh.')
    show(target)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command')
    commands.add_parser('list', help='List available characters and layouts')
    inspect = commands.add_parser('show', help='Show client defaults or a session override')
    inspect.add_argument('--session', help='Session ID or unique prefix')
    inspect.add_argument('--agent', choices=('all', *config.AGENTS), default='all')
    listing = commands.add_parser('sessions', help='List sessions recently observed by a theme renderer')
    listing.add_argument('--agent', choices=('all', *config.AGENTS), default='all')
    listing.add_argument('--all', action='store_true', help='Include entries older than two minutes')
    listing.add_argument('--json', action='store_true')
    commands.add_parser('refresh', help='Upgrade running Codex HUD renderers without restarting Codex')
    select = commands.add_parser('set', help='Save choices for both agents or one agent')
    select.add_argument('--cast', choices=(*config.catalog(), 'random'))
    select.add_argument('--style', choices=(*config.STYLES, 'random'))
    select.add_argument('--agent', choices=('all', *config.AGENTS), default='all')
    select.add_argument('--session', help='Target only this session; accepts a unique prefix')
    reset = commands.add_parser('reset', help='Clear saved choices; environment overrides remain active')
    reset.add_argument('--agent', choices=('all', *config.AGENTS), default='all')
    reset.add_argument('--session', help='Remove only this session override, restoring its inherited choices')
    args = parser.parse_args()
    try:
        if args.command is None:
            if sys.stdin.isatty(): interactive()
            else: parser.print_help()
        elif args.command == 'list':
            print('Characters (random = stable per session):')
            for key, spec in config.catalog().items(): print(f"  {key:10} {spec.get('name', key)}")
            print('Layouts: '+', '.join((*config.STYLES, 'random')))
        elif args.command == 'sessions': show_sessions(args.agent, args.all, args.json)
        elif args.command == 'refresh':
            import theme_refresh
            count = theme_refresh.refresh()
            print(f'Refreshed {count} Codex HUD renderer(s). Codex processes and tasks were left running.')
        elif args.command == 'show':
            show(sessions.resolve(args.session, args.agent) if args.session is not None else None)
        else:
            target = sessions.resolve(args.session, args.agent) if args.session is not None else None
            config.save_selection(target['agent'] if target else args.agent,
                                  getattr(args, 'cast', None), getattr(args, 'style', None),
                                  reset=args.command == 'reset', session_id=target['session_id'] if target else None,
                                  session_aliases=target.get('aliases', ()) if target else ())
            print('Saved. Running status lines use the selection on their next refresh.')
            show(target)
    except (OSError, ValueError) as error:
        parser.exit(1, str(error)+'\n')
    except (EOFError, KeyboardInterrupt):
        parser.exit(130, '\nCancelled.\n')


if __name__ == '__main__': main()
