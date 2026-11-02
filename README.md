# Agent Terminal Theme

为 **Codex CLI** 和 **Claude Code** 提供统一的动漫状态栏：12 组角色、4 种布局、中英文台词、上下文与额度进度条，以及支持终端中的真实动画。

适用于 **macOS** 和 **Windows Terminal + WSL**。运行时仅使用 Python 标准库；主题本身不需要 API key，也不会上传会话或配置。

> Windows 的部署位置是 **WSL 内部**。本项目不支持把 Python/tmux HUD 直接装进原生 PowerShell，也不修改 Codex 桌面应用的界面。

## 显示能力

| 系统与终端 | Codex CLI | Claude Code |
| --- | --- | --- |
| macOS · Ghostty / kitty | Kitty 协议真实动画 | Kitty 动画，tmux 中使用占位符定位 |
| macOS · Rex | Kitty 直接放置的真实动画 | 彩色字符头像回退 |
| macOS · iTerm2 / WezTerm | 逐帧 PNG | tmux 内逐帧 PNG；其他情况使用回退 |
| Windows Terminal · WSL | 启用 SIXEL 的 tmux 可显示真实动画 | 彩色字符头像回退 |
| 其他终端 | 彩色字符头像回退 | 彩色字符头像回退 |

Codex 使用单独的五行 tmux HUD；Claude 使用官方 `statusLine` 命令。它们共享素材和布局，但接入方式不同。Claude 在 Windows Terminal/Rex 中不发送实验性的图片转义序列，以保持文字显示稳定。

## 快速开始

先安装并登录所需的 Codex CLI / Claude Code，准备 Python **3.11+**、Git，以及 Codex HUD 所需的 tmux。

```sh
git clone --depth 1 https://github.com/superkirk3/agent-terminal-theme.git
cd agent-terminal-theme

# 同时部署两个客户端；自动选择当前 bash/zsh。
python3 install.py --codex --claude

# 在当前 shell 加载入口，或重新打开终端。
. "$HOME/.local/share/agent-theme/shell.sh"
```

随后正常使用：

```sh
codex
codex resume
claude
claude --continue
```

完整步骤：**[macOS 部署](docs/MACOS.md)** · **[Windows/WSL 部署](docs/WINDOWS-WSL.md)**。

## 分别部署

```sh
# 只装 Codex
python3 install.py --codex --shell zsh

# 只装 Claude，不要求已安装 Codex 或 tmux
python3 install.py --claude

# 不确定改动时先预览
python3 install.py --codex --claude --dry-run

# 自动检测不到 Codex 时，明确指定已有的原始程序
python3 install.py --codex --codex-bin "$(command -v codex)"
```

安装器将主题放入 `~/.local/share/agent-theme/`，通过独立的 shell 入口启动 Codex。它不会覆盖原 Codex/Claude 程序，也不改 Codex 的模型、账户、权限或 `config.toml`。

Claude 设置采用合并写入；旧设置和 shell 启动文件的备份只保存在本机 `~/.local/state/agent-theme/backups/`，不会放进 Git 仓库。更多内容见 [隐私与安全](SECURITY.md)。

## 选择角色和布局

```sh
# 单次指定
AGENT_THEME_CAST=luffy AGENT_THEME_STYLE=mecha codex
CLAUDE_STATUSLINE_CAST=gojo CLAUDE_STATUSLINE_STYLE=pill claude

# 禁用 Codex HUD，直接运行原始 CLI
CODEX_THEME_DISABLE=1 codex

# Windows 需要暂时关闭真实图片时
AGENT_THEME_WINDOWS_TEXT=1 codex
```

角色：`naruto`、`goku`、`luffy`、`gojo`、`doraemon`、`saitama`、`mob`、`levi`、`natsu`、`ryoma`、`bleach`、`kimetsu`。

布局：`mecha`、`minimal`、`card`、`pill`；默认随机选择并尽量在同一会话中保持稳定。素材含多种状态，缺少的状态会使用回退动画。

详细变量和指标含义见 [配置说明](docs/CONFIGURATION.md)。

## 更新与卸载

在克隆的项目目录中：

```sh
git pull --ff-only
python3 install.py --codex --claude

# 卸载两个入口，或加 --codex / --claude 只卸载其中之一
python3 uninstall.py
```

卸载只移除本项目的入口，并在 Claude 的状态栏配置仍属于本项目时恢复其原值；其他新增设置会保留。然后重新打开终端，或执行 `unset -f codex`。素材及本地备份保留，便于自行检查。

## 检查与排错

```sh
python3 -m unittest discover -s tests -p 'test_*.py'
python3 tools/privacy_audit.py
```

- **升级 Codex 后主题消失**：重新打开 shell，检查 `type codex` 是否加载了主题函数。入口不依赖更新器管理的 Codex 符号链接。
- **中文错位或图标变方框**：安装覆盖中文及 Nerd Font 字符的字体，例如 [Maple Mono NF CN](https://github.com/subframe7536/maple-font)，并在实际终端中选择它。
- **Shift+Enter 不换行**：使用平台文档中的 `ESC CR` 键位示例；也可使用 CLI 支持的 Alt+Enter。
- **Windows 图片缺失**：检查 tmux 是否包含 SIXEL 支持，或先使用 `AGENT_THEME_WINDOWS_TEXT=1`。
- **重启后出现多余小分屏**：如果使用 tmux-resurrect/continuum，它可能恢复旧 HUD 的辅助面板。请只关闭确认已变成空闲 shell 的旧辅助面板，再从主面板启动 Codex；不要为了清理 HUD 而关闭整个 tmux server。

详见 [排错与兼容性](docs/TROUBLESHOOTING.md)。

## 素材与许可

项目代码采用 [MIT License](LICENSE)。动漫角色和动画素材不在代码的 MIT 授权范围内，来源见 [cast.json](cast.json)，权利说明见 [NOTICE.md](NOTICE.md)。本项目与 OpenAI、Anthropic、各终端及动漫权利人无隶属关系。

## 官方参考

- [OpenAI：Codex 配置参考](https://learn.chatgpt.com/docs/config-file/config-reference)
- [Anthropic：Claude Code 状态栏](https://code.claude.com/docs/en/statusline)
- [Anthropic：Claude Code 安装](https://code.claude.com/docs/en/setup)
- [tmux](https://github.com/tmux/tmux)
