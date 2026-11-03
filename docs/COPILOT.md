# GitHub Copilot CLI · Windows/WSL

在已经安装并登录 Copilot CLI 的 WSL 中执行；不支持原生 PowerShell 安装。运行时要求 Python 3.11+、tmux。真实动图还需要 Windows Terminal 与启用 SIXEL 的 tmux，参见 [Windows/WSL 部署](WINDOWS-WSL.md)。接入与事件格式已用 Copilot CLI 1.0.105 验证；未知字段保持未知，不根据速度推测模式。

```sh
python3 install.py --copilot --shell zsh  # bash 用户改为 --shell bash
. "$HOME/.local/share/agent-theme/shell.sh"
copilot
```

也可以 `python3 install.py --codex --claude --copilot` 一起部署。无法发现原始 Linux 程序时，添加 `--copilot-bin /path/to/copilot`。安装器保留原程序，并在主题自己的 `bin/` 下创建入口。`--help`、`--version`、`-p`/`--prompt`、ACP 等非交互调用直接交给原 CLI。

## 给已运行的 tmux 会话挂载

在另一个 WSL shell 中运行：

```sh
agent-theme refresh
agent-theme sessions --agent copilot
agent-theme set --agent copilot --cast kimetsu --style mecha
agent-theme set --session SESSION_ID --rotation cycle --interval 30
```

`refresh` 只为进程归属可确认的 Copilot 面板添加五行 HUD，并跳过已有 HUD 的窗口。它不会重启 Copilot、提交提示词或清理 tmux server。挂载管理器只在原 CLI 退出后移除自己创建的辅助面板。已有 Codex/Copilot HUD 的文字渲染器也会更新；CLI 主进程保留。

已有 snippet 入口参数相同：`~/snippets/agent-theme refresh`。人物、布局和轮播可按 Copilot 默认值或单个 session 保存，与 Codex/Claude 分开。

## 数据与原生 statusLine

Copilot 官方提供命令式 `statusLine`；本项目为保留 Windows 上真实动画，使用独立 tmux HUD。原有 `statusLine` 和 `footer` 保持原值。如旧自定义文字栏同时显示，可在 Copilot 自己的 `/footer` 中调整。[GitHub 官方配置说明](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-config-dir-reference)

面板只增量读取当前 Copilot 进程实际打开的 `~/.copilot/session-state/<session>/events.jsonl`，不按最近修改时间或相同项目目录猜会话。无法确认时显示未知指标。读取过程不保存提示词、工具输出、登录信息或账户配置，也不发起计费/额度请求。

`CTX` 来自最近请求的输入与输出量、上下文上限；`CACHE` 来自该请求缓存命中量；`TOKENS` 是本机日志已记录的请求 token 总和，包含多次发送的上下文。`API` 是最近请求输出 token / API 耗时，耗时单位由毫秒转换为秒，包含首 token 等待。Copilot 的 premium-request `cost` 不当作美元显示。当前版本未提供明确 Fast 字段时显示 `[FAST ?]`。

临时绕过主题：

```sh
COPILOT_THEME_DISABLE=1 copilot
```

卸载入口：`python3 uninstall.py --copilot`。它不改 Copilot 的设置或账户文件。Mac 可使用同一包装入口的图片协议回退，但 Copilot 此次验证范围为 WSL。
