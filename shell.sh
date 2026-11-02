# Stable entry point: CLI updaters do not own this directory.
case ":$PATH:" in
    *":$HOME/.local/share/agent-theme/bin:"*) ;;
    *) export PATH="$HOME/.local/share/agent-theme/bin:$PATH" ;;
esac

codex() {
    command python3 "$HOME/.local/share/agent-theme/codex-launch.py" "$@"
}
