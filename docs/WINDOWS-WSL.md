# Windows Terminal + WSL 部署

终端界面运行在 Windows，Codex、Claude、Python、tmux 和主题运行在 **WSL Linux 内**。不要把本项目的 HUD 当作原生 PowerShell 程序安装。

## 1. 准备 WSL

如果尚未安装 WSL，可在管理员 PowerShell 中执行：

```powershell
wsl --install -d Ubuntu
```

按系统提示完成安装并创建 Linux 用户，然后从 Windows Terminal 打开 Ubuntu 标签。之后本页的 shell 命令都在该标签中执行。

```sh
sudo apt update
sudo apt install -y git python3 tmux
python3 --version
tmux -V
```

Python 需要 3.11+。较旧发行版自带的 Python/tmux 可能不满足要求，请先升级发行版或按对应项目的官方文档安装。

在 **WSL 中**安装并登录 CLI。例如，WSL 内已有 Node.js/npm 时：

```sh
npm install -g @openai/codex
codex login
```

Claude Code 按 [官方 WSL 安装步骤](https://code.claude.com/docs/en/setup#install-in-wsl)安装，并运行一次 `claude` 完成登录。不要混用 Windows 的 `codex.exe`/npm shim 和 WSL 的 Linux 安装。

## 2. 安装主题

```sh
git clone --depth 1 https://github.com/superkirk3/agent-terminal-theme.git
cd agent-terminal-theme
python3 install.py --codex --claude --shell bash
. "$HOME/.local/share/agent-theme/shell.sh"
```

如果使用 zsh，替换为 `--shell zsh`。只部署一个客户端时保留对应的 `--codex` 或 `--claude`。

## 3. 设置 Windows Terminal

1. 在 **Windows** 安装支持中文的 Nerd Font，例如 Maple Mono NF CN。
2. 在 Windows Terminal 的 Ubuntu profile 中选择该字体。
3. 合并 [Windows Terminal 配置片段](../examples/windows-terminal.settings.example.json)，保留自己已有的 profiles、actions 和 keybindings。
4. 重新打开 Ubuntu 标签，让字体和终端识别生效。

建议的 profile commandline：

```text
wsl.exe --distribution Ubuntu --cd ~ -- env TERM_PROGRAM=WindowsTerminal bash -l
```

使用 zsh 时替换最后的 `bash -l`。希望先进入已有 tmux 会话时：

```text
wsl.exe --distribution Ubuntu --cd ~ -- env TERM_PROGRAM=WindowsTerminal tmux -u new -A -s main
```

不需要配置任何 SSH 主机、NAS、反向隧道或密钥。

## 4. 启动与图片支持

```sh
codex
codex resume
claude
claude --continue
```

Windows Terminal 的真实图片路径要求终端支持 SIXEL，且 tmux **编译启用了 SIXEL**。在 tmux 中检查：

```sh
tmux display-message -p '#{sixel_support}'
```

输出 `1` 才能使用本项目的原生 SIXEL HUD；空值/`0` 表示需要支持该功能的 tmux 构建。验证过的组合为 Windows Terminal 1.24 与启用 SIXEL 的 tmux 3.6。安装器不自动编译或替换系统 tmux。

### 可选：构建兼容的 SIXEL tmux

系统软件包没有 SIXEL 支持时，可按下面的步骤构建 **3.6b** 兼容版本。该版本修复了 3.6 系列的 SIXEL 图片移除崩溃问题，见 [上游说明](https://github.com/tmux/tmux/issues/5109)。这是固定兼容版本的示例，不表示它是最新版本；构建方式参考 [tmux 官方安装文档](https://github.com/tmux/tmux/wiki/Installing)。

```sh
sudo apt install -y build-essential autoconf automake pkg-config bison libevent-dev libncurses-dev
git clone --depth 1 --branch 3.6b https://github.com/tmux/tmux.git tmux-sixel-3.6b
cd tmux-sixel-3.6b
sh autogen.sh
./configure --enable-sixel --prefix="$HOME/.local"
make -j"$(nproc)"
make install
export PATH="$HOME/.local/bin:$PATH"
tmux -V
```

这会安装到用户目录，不替换 `/usr/bin/tmux`。将 PATH 语句加入自己的 shell 启动文件以持久生效。已经运行的旧 tmux server 不会自动升级；保留其中的任务，在新的 WSL 标签中用独立 server 检查新版本：

```sh
tmux -L agent-theme-sixel -f /dev/null new-session -A -s main
# 进入后执行；应输出 1
tmux display-message -p '#{sixel_support}'
codex
```

Codex 图片与文字使用辅助 pane；图片由直接连接 Windows Terminal 的 tmux 管理，避免经过两层 tmux。底部保留一行安全余量，防止 SIXEL 末行越界引起滚屏。

Claude 在 Windows Terminal 中使用彩色字符头像；这与 Codex 的独立图像 pane 接入方式不同，不是安装失败。

## 5. Shift+Enter 和回退

示例键位让 Shift+Enter 发送 `ESC CR`（`1b 0d`）。HUD 自己的 tmux server 也会转发该键位；外层自建 tmux 可合并 [tmux 示例](../examples/tmux.conf)。

如果图片不正常，可先这样启动：

```sh
AGENT_THEME_WINDOWS_TEXT=1 codex
```

恢复默认图片模式时去掉该变量。要完全绕过 HUD：

```sh
CODEX_THEME_DISABLE=1 codex
```

如果使用 tmux 会话自动恢复，请阅读 [旧辅助分屏的处理](TROUBLESHOOTING.md#恢复会话后出现多套-hud)。不要用 `tmux kill-server` 清理单个 HUD。
