# 排错与兼容性

## 先确认执行入口

```sh
type codex
codex --version
```

若仍指向原 CLI，先重新开 shell，或加载：

```sh
. "$HOME/.local/share/agent-theme/shell.sh"
```

不希望修改 shell 文件时，安装时选 `--shell none`，再自行配置该加载语句。安装器发现不了原 CLI 时，用 `--codex-bin` 指向原程序；不要指向本主题的 wrapper。

## 中文、图标或进度条错位

选择同时覆盖中文与 Nerd Font 字符的字体，并确认实际生效的是终端当前 profile 的字体。使用支持 UTF-8、真彩色的终端；tmux 可用 `tmux -u` 启动。终端过窄时，布局会裁剪字段。

## 指定 session 后主题没有变化

先用 `agent-theme sessions` 选择主题实际显示的 ID。两个客户端有相同 ID 或前缀不唯一时，加 `--agent codex` / `--agent claude` 或使用完整 ID。Codex 无法确认真实 ID 时会显示独立的 HUD ID，此时可以直接用 HUD ID 定位该窗口。

旧版 Codex 主题进程尚不能读取会话设置时，更新安装后运行 `agent-theme refresh`。它只刷新验证过的显示进程，保留正在工作的 Codex 主进程。如果显示刷新数量为 0，表示没有找到可验证的主题面板；检查安装路径及对应 tmux server，避免对未知面板执行强制重启。

用 `agent-theme show --session SESSION_ID` 查看已保存的覆盖，用 `agent-theme reset --session SESSION_ID` 让该会话恢复继承默认值。会话级覆盖高于环境变量；不带 `--session` 的修改只改变客户端默认值，不会清除已有的会话级选择。

## 图片缺失、残影或大小异常

先查 README 的能力表。Windows Claude / Rex Claude 的字符头像是当前设计的回退路径。Windows Codex 需要 tmux 的 `sixel_support` 为 `1`。

Windows 示例使用背景色 `#282c34`，与 SIXEL 图片底色一致。使用其他背景色时，图片画布可能有色差。请先使用示例背景确认显示链路正常。

Ghostty/kitty/Rex 的 Codex 使用直接图像放置；Claude 在 Ghostty/kitty 使用不同的占位符定位。如果 Claude 的占位符不可见，使用 `CLAUDE_STATUSLINE_IMAGE=off`。

嵌套布局、切换不同终端附着到同一个 tmux session，以及 CLI/终端更新，都可能影响图像协议。Windows 图片异常时可用 `AGENT_THEME_WINDOWS_TEXT=1 codex`；需要排除整个主题时用 `CODEX_THEME_DISABLE=1 codex`。

## 恢复会话后出现多套 HUD

tmux-resurrect / continuum 可能把临时 HUD 分屏和历史画面一起保存。恢复后辅助进程未恢复时，留下的 shell 仍显示旧画面，再启动 Codex 就可能看到重复 HUD。

先查看当前进程与面板：

```sh
tmux list-panes -a -F '#{session_name}:#{window_id} #{pane_id} #{pane_current_command} #{pane_width}x#{pane_height}'
```

只关闭已经确认属于旧 HUD、且没有正在运行任务的空闲 shell 面板。不要按固定 pane 编号复制别人的删除命令，也不要关闭整个 tmux server。新会话通常会在 Codex 退出时清理自己的辅助 pane。

## 状态或额度缺失

先确认 CLI 会话已经产生相应记录。主题不会发网络请求补查账户，不会伪造缺失的额度字段。Codex 更新了日志结构时可能需要更新主题适配器。

账户登录失败、工作区路由失败等发生在 CLI 自身的错误，需先让不带主题的原 CLI 正常启动：

```sh
CODEX_THEME_DISABLE=1 codex
```

## WSL / tmux 的 Ctrl+V 无法粘贴图片

Windows Terminal 的 `Terminal.PasteFromClipboard` 会先处理 Ctrl+V，应用可能收不到图片粘贴按键。请合并 Windows Terminal 示例中的 `AgentTheme.PasteClipboard` 动作，并加载 WSL 剪贴板桥接，见 [Windows 部署说明](WINDOWS-WSL.md#ctrlv--winv-粘贴文字和图片)。

桥接同时支持文字、位图截图以及资源管理器的 FileDrop 图片文件；图片文件路径会转换为 WSL 路径。它不修改系统剪贴板，不把复制文件误当成纯文本，也不需要重启 Codex 会话。

## 恢复或卸载

运行仓库中的 `python3 uninstall.py`，再重新开 shell。安装前备份在本机 `~/.local/state/agent-theme/backups/`。卸载保留较新的 Claude 自定义状态栏和其他配置字段，不用旧备份覆盖整份现有设置。
