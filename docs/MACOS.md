# macOS 部署

所有命令都在 Mac 终端中执行。Codex 与 Claude 可以分别安装主题，也可以一起安装。

## 1. 准备环境

使用 Homebrew 准备基础依赖：

```sh
brew install git python tmux
python3 --version
tmux -V
```

Python 需要 3.11 或更新版本。先完成原版 CLI 的安装及登录，再部署主题。例如，已经有 Node.js/npm 时可安装 Codex CLI：

```sh
npm install -g @openai/codex
codex login
```

Claude Code 按 [官方安装步骤](https://code.claude.com/docs/en/setup)安装，并运行一次 `claude` 完成登录。主题不提供也不需要你的登录凭据。

## 2. 安装主题

```sh
git clone --depth 1 https://github.com/superkirk3/agent-terminal-theme.git
cd agent-terminal-theme
python3 install.py --codex --claude --shell zsh
. "$HOME/.local/share/agent-theme/shell.sh"
```

只使用其中一个客户端时改成 `--codex` 或 `--claude`。使用 bash 时选择 `--shell bash`。如果 shell 文件由其他工具生成，可以通过 `--shell-file` 指定你自己的本地覆盖文件，或用 `--shell none` 后手动加载 `shell.sh`。

```sh
type codex
codex --version
codex
claude
```

`codex --version`、`codex login`、`codex exec` 等非交互式命令直接交给原 CLI；只有交互式 Codex TUI 才进入 HUD。

## 3. 字体与终端

安装带中文覆盖的 Nerd Font。示例使用 Maple Mono NF CN，但字体需另外安装，本项目不打包字体。

### Ghostty

将 [Ghostty 示例](../examples/ghostty.conf)中的选项合并到自己的配置中，不要用示例覆盖整个配置文件。

```ini
font-family = Maple Mono NF CN
font-size = 14
keybind = shift+enter=text:\x1b\r
```

保存后用 Ghostty 的 Reload Configuration 操作加载。示例不重绑 Cmd 键；Cmd+C/V、Cmd+T 等继续由终端原生处理。

Codex 可直接显示 Kitty 动画。Claude 的 Kitty 占位符路径受终端和 tmux 版本影响：如果只看到占位符，可用 `CLAUDE_STATUSLINE_IMAGE=off claude` 切换到稳定的彩色头像。

### iTerm2 / WezTerm

在终端的字体设置中选择同样的中文 Nerd Font。Codex 使用逐帧 PNG。Claude 的图片定位需要在 tmux 内运行：

```sh
tmux
claude
```

需要自定义 Shift+Enter 时，让终端发送十六进制字节 `1b 0d`。不要改普通 Enter。

### Rex

Codex 使用 Kitty 直接放置动画。Claude 当前使用字符头像回退。Rex 的 Shift+Enter 设置见 [示例 init.lua](../examples/rex-init.lua)；合并到自己的配置后重新加载，不要覆盖其他键位。

## 4. 持久配置

推荐用菜单或命令保存选择，已运行的状态栏会在下次刷新时读取：

```sh
agent-theme
agent-theme set --cast luffy --style mecha
agent-theme set --agent claude --cast gojo --style pill
```

也可把这些变量写入自己的 shell 启动文件；它们的优先级高于菜单保存的选择：

```sh
export AGENT_THEME_STYLE=mecha
export AGENT_THEME_CAST=luffy
export CLAUDE_STATUSLINE_STYLE=mecha
export CLAUDE_STATUSLINE_CAST=luffy
```

不指定角色时，由会话选择角色。请不要把自己的完整 shell 文件、CLI 设置、账户文件或会话日志复制进公开仓库。
