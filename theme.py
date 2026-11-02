#!/usr/bin/env python3
"""Agent theme switcher: choose persistent characters and layouts locally."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
if not (ROOT/'theme_config.py').is_file(): ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))
import theme_config as config


def show():
    preferences = config.load_preferences(strict=True)
    for agent in config.AGENTS:
        saved = preferences.get(agent, {})
        effective = config.effective_preferences(agent, preferences=preferences)
        print(f"{agent}: cast={effective['cast']}  style={effective['style']}")
        if any(effective[field] != saved.get(field, 'random') for field in ('cast', 'style')):
            print('  Environment overrides saved preferences for this shell.')


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
    agent = menu_choice('Apply to (default: both)',
                        [('all', 'Codex + Claude'), ('codex', 'Codex'), ('claude', 'Claude')], 'all')
    cast = menu_choice('Character', [('random', 'Random per session')]+
                       [(key, f"{key} · {spec.get('name', key)}") for key, spec in config.catalog().items()])
    style = menu_choice('Layout', [('random', 'Random per session')]+[(key, key) for key in config.STYLES])
    if cast is None and style is None:
        print('No changes.')
        return
    config.save_selection(agent, cast, style)
    print('Saved. Running status lines use the selection on their next refresh.')
    show()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command')
    commands.add_parser('list', help='List available characters and layouts')
    commands.add_parser('show', help='Show effective choices, including environment overrides')
    select = commands.add_parser('set', help='Save choices for both agents or one agent')
    select.add_argument('--cast', choices=(*config.catalog(), 'random'))
    select.add_argument('--style', choices=(*config.STYLES, 'random'))
    select.add_argument('--agent', choices=('all', *config.AGENTS), default='all')
    reset = commands.add_parser('reset', help='Clear saved choices; environment overrides remain active')
    reset.add_argument('--agent', choices=('all', *config.AGENTS), default='all')
    args = parser.parse_args()
    try:
        if args.command is None:
            if sys.stdin.isatty(): interactive()
            else: parser.print_help()
        elif args.command == 'list':
            print('Characters (random = stable per session):')
            for key, spec in config.catalog().items(): print(f"  {key:10} {spec.get('name', key)}")
            print('Layouts: '+', '.join((*config.STYLES, 'random')))
        elif args.command == 'show': show()
        else:
            config.save_selection(args.agent, getattr(args, 'cast', None), getattr(args, 'style', None),
                                  reset=args.command == 'reset')
            print('Saved. Running status lines use the selection on their next refresh.')
            show()
    except (OSError, ValueError) as error:
        parser.exit(1, str(error)+'\n')
    except (EOFError, KeyboardInterrupt):
        parser.exit(130, '\nCancelled.\n')


if __name__ == '__main__': main()
