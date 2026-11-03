# Agent Terminal Theme

为 **Codex CLI**、**Claude Code** 和 **GitHub Copilot CLI（WSL）** 提供统一的动漫状态栏：12 组角色、4 种布局、中英文台词、人物轮播、Fast 模式标记，以及支持终端中的真实动画。

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

Copilot 在 WSL 复用 Codex 的独立 tmux 图片/文字面板，保留真实动图。它不覆盖 Copilot 已有的 `statusLine`、账户或模型设置；已运行的 tmux Copilot 也可挂载面板，见 [Copilot 接入](docs/COPILOT.md)。

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

# WSL：只装 Copilot，或把 --copilot 加到其他安装选项后
python3 install.py --copilot

# 不确定改动时先预览
python3 install.py --codex --claude --dry-run

# 自动检测不到 Codex 时，明确指定已有的原始程序
python3 install.py --codex --codex-bin "$(command -v codex)"
```

安装器将主题放入 `~/.local/share/agent-theme/`，通过独立的 shell 入口启动 Codex。它不会覆盖原 Codex/Claude 程序，也不改 Codex 的模型、账户、权限或 `config.toml`。

Claude 设置采用合并写入；旧设置和 shell 启动文件的备份只保存在本机 `~/.local/state/agent-theme/backups/`，不会放进 Git 仓库。更多内容见 [隐私与安全](SECURITY.md)。

## 选择角色和布局

安装后运行 `agent-theme` 打开交互菜单，选择要修改的客户端、角色和布局。Mac 与 WSL 使用相同命令，各自保存本机选择。

```sh
agent-theme                                         # 交互选择
agent-theme list                                    # 查看角色、布局
agent-theme set --cast luffy --style mecha           # 切换所有客户端默认值
agent-theme set --agent claude --cast gojo --style pill  # 只切换 Claude
agent-theme show                                    # 查看当前选择
agent-theme reset --agent codex                     # 恢复 Codex 的会话随机选择
agent-theme reset                                  # 恢复所有客户端的会话随机选择
```

从另一个终端标签或 tmux 面板执行即可。**已运行的状态栏会在下次刷新时读取选择，无需中断任务**；命令只保存显示偏好，不重启客户端。选择保存在本机 `~/.config/agent-theme/preferences.json`，更新和卸载都会保留。

### 只切换某个 session

运行 `agent-theme` 后可在菜单中直接选择某一行 **Session**，也可以用命令操作。将下面的 `SESSION_ID` 替换为列表中的完整 ID 或唯一前缀：

```sh
agent-theme sessions
agent-theme set --session SESSION_ID --cast gojo --style pill
agent-theme show --session SESSION_ID
agent-theme reset --session SESSION_ID
```

这些操作只修改目标会话的显示偏好，不改变客户端默认主题或其他会话。会话级设置优先于环境变量，所以已经运行且固定了角色的会话也能单独切换。`reset --session` 只移除该会话的覆盖，让它重新继承环境变量及默认主题。

如果两个客户端的 ID 重复，添加 `--agent codex` 或 `--agent claude`；前缀不唯一时命令会拒绝修改。列表显示最近两分钟刷新过的主题会话，`agent-theme sessions --all` 可查看旧记录，`--json` 可供脚本读取。

Codex 会在确认进程归属后显示真实 session ID；无法确认时显示该窗口独有的 HUD ID，可直接用它切换当前窗口。不会根据项目路径猜测会话。真实 ID 的设置可在恢复同一会话时继续生效；HUD ID 针对当前 HUD 实例。更多说明见 [会话识别](docs/CONFIGURATION.md#会话识别与刷新)。

环境变量仍然优先于客户端默认选择，适合单次覆盖；显式会话覆盖具有更高优先级：

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

### 人物自动轮播、Fast 与速度

默认每 **30 秒**切换当前角色包内的动画。群像主题 `bleach`、`kimetsu` 会轮到各个人物；其他主题轮播该人物的不同动作。头像和台词轮播时，工作状态、错误与额度仍来自真实会话，明确的等待/错误状态优先显示对应头像。

```sh
agent-theme set --rotation cycle --interval 30
agent-theme set --agent copilot --cast bleach --style mecha
agent-theme set --session SESSION_ID --rotation activity  # 此会话按实际工作状态选头像
```

`[FAST ON]` / `[FAST OFF]` 表示 CLI 明确提供的模式，`[FAST ?]` 表示来源未提供信息。主题只显示模式，不替你开启 Fast。速度行已改为明确的平均值：Codex `AVG` 是整轮输出 token / 整轮耗时，包含工具与等待；Copilot `API` 是最近单次请求输出 token / API 耗时；Claude 有累计 API 耗时时显示 `API`，否则显示转录估计 `EST`。这些都不是瞬时解码速度。详见 [指标口径](docs/CONFIGURATION.md#显示内容)。

`--cast random` / `--style random` 表示按会话自动选择。若之前在 shell 中 `export` 了角色或布局，`agent-theme show` 会提示覆盖。可以用 `--session` 直接覆盖指定会话；若要让整个客户端跟随默认值，需去掉这些变量后启动新会话。

从旧版升级时，先按下节更新安装，再运行 `agent-theme refresh` 加载新的 Codex HUD 代码。它只刷新经验证的主题渲染面板，保留 Codex 主进程及任务；之后切换主题无需刷新面板或重启会话。Claude 状态栏会在下次调用时加载新代码。选择 `--shell none` 的用户可以直接执行 `python3 "$HOME/.local/share/agent-theme/theme.py"`，参数相同。

详细变量和指标含义见 [配置说明](docs/CONFIGURATION.md)。

## 更新与卸载

在克隆的项目目录中：

```sh
git pull --ff-only
python3 install.py --codex --claude
. "$HOME/.local/share/agent-theme/shell.sh"
agent-theme refresh

# 卸载所有入口，或加 --codex / --claude / --copilot 单独卸载
python3 uninstall.py
```

卸载只移除本项目的入口，并在 Claude 的状态栏配置仍属于本项目时恢复其原值；其他新增设置会保留。然后重新打开终端，或执行 `unset -f codex`。素材、主题选择及本地备份保留，便于自行检查。只卸载一个客户端时，另一个客户端仍可使用 `agent-theme`。

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
- [GitHub：Copilot CLI 配置目录](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-config-dir-reference)
- [tmux](https://github.com/tmux/tmux)
