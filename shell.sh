# Stable entry point: CLI updaters do not own this directory.
case ":$PATH:" in
    *":$HOME/.local/share/agent-theme/bin:"*) ;;
    *) export PATH="$HOME/.local/share/agent-theme/bin:$PATH" ;;
esac

if [ -x "$HOME/.local/share/agent-theme/bin/codex" ]; then
    codex() {
        command python3 "$HOME/.local/share/agent-theme/codex-launch.py" "$@"
    }
fi

if [ -n "${ZSH_VERSION:-}" ] && [ -r "$HOME/.local/share/agent-theme/windows-paste.zsh" ]; then
    . "$HOME/.local/share/agent-theme/windows-paste.zsh"
fi
