# Keep Ctrl+V as ordinary paste in WSL zsh as well as in tmux applications.
[[ -n ${ZSH_VERSION:-} && -r /proc/sys/kernel/osrelease ]] || return 0
[[ "$(</proc/sys/kernel/osrelease)" == *[Mm]icrosoft* ]] || return 0

_agent_theme_clipboard_paste() {
    local clipboard_value
    clipboard_value=$(python3 "$HOME/.local/share/agent-theme/windows_paste.py" --print && printf '\037') || return
    LBUFFER+=${clipboard_value%$'\037'}
    zle redisplay
}
zle -N _agent_theme_clipboard_paste
for clipboard_keymap in emacs viins; do
    bindkey -M "$clipboard_keymap" '^V' _agent_theme_clipboard_paste
done
unset clipboard_keymap

if [[ -n ${TMUX:-} ]]; then
    python3 "$HOME/.local/share/agent-theme/windows_paste.py" --configure --socket "${TMUX%%,*}"
fi
