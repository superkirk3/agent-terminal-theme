# 配置与数据说明

## 保存与切换主题

```sh
agent-theme                                      # 交互菜单
agent-theme set --cast ryoma --style card          # 同时应用到两个客户端
agent-theme set --agent codex --style minimal     # 只改 Codex 布局，保留其角色
agent-theme set --agent claude --cast random      # Claude 恢复按会话选角
agent-theme show
agent-theme reset --agent claude
```

选择只保存在本机，不上传或跨机器同步。角色、布局、轮播可以分别修改；不带 `--session` 时，`--agent all` 是默认值，会更新 Codex、Claude、Copilot 的默认字段。`reset` 清除所选客户端的默认值，不移除环境变量，也不删除会话级覆盖。

```sh
agent-theme set --rotation cycle --interval 30           # 默认每 30 秒轮播当前包的角色/动作
agent-theme set --session SESSION_ID --rotation activity # 此会话跟随真实工作状态
agent-theme set --agent copilot --cast bleach
```

轮播间隔可设为 10–3600 秒。群像按人物均匀轮换，再轮换每个人物的动作；不会更换所选主题包。文字工作状态与额度独立于头像轮播，等待批准/错误时优先显示对应状态头像。

优先级：**指定 session 的覆盖 → 该客户端的环境变量 → 客户端保存的默认选择 → 会话随机选择**。按字段分别继承，例如只改某个会话的角色，不会改它的布局。Codex 使用 `AGENT_THEME_CAST` / `AGENT_THEME_STYLE`，Claude 使用 `CLAUDE_STATUSLINE_CAST` / `CLAUDE_STATUSLINE_STYLE`，两者互不覆盖。

每次渲染都会重新读取偏好，已经运行的 HUD/状态栏也能切换。会话级覆盖能够覆盖该进程已有的角色/布局环境变量。主题偏好文件损坏时，运行中的状态栏回退到默认值；切换命令会报错且不覆盖原文件，修正或移走损坏文件后再设置。

## 指定某个 session

```sh
agent-theme sessions                    # 最近刷新过的会话
agent-theme sessions --agent codex --all # 包含 Codex 的旧记录
agent-theme sessions --json
```

复制需要修改的会话 ID，替换下面的 `SESSION_ID`：

```sh
agent-theme set --session SESSION_ID --cast luffy --style mecha
agent-theme set --agent claude --session SESSION_ID --style card
agent-theme show --session SESSION_ID
agent-theme reset --session SESSION_ID
```

`--session` 支持唯一前缀，完整 ID 优先匹配。如果同一个 ID 同时属于 Codex 和 Claude，必须指定客户端；歧义不会触发批量修改。可用 `codex:SESSION_ID` 或 `claude:SESSION_ID` 明确客户端，也可用 `--agent` 和完整 ID 预先设置尚未出现在列表中的会话。

会话覆盖保存于同一份本机偏好文件，按客户端和会话 ID 分开。它不会修改其他会话或客户端默认值；更新、部分卸载都不会删除它。并发修改使用文件锁及原子替换，避免两个终端的操作相互覆盖。

### 会话识别与刷新

Claude 使用状态栏 JSON 提供的 `session_id`。Codex 优先验证 TUI 进程树实际打开的 CLI 会话文件；WSL 使用 `/proc`，macOS 使用系统的 `lsof`。未能确认真实 ID 时，保留独立的 HUD ID，不按同一项目目录猜测归属。默认 HUD 编号使用随机值，避免进程号复用造成设置串用。

真实 ID 的设置会在恢复同一会话后继续生效；HUD ID 只对应当前显示实例。之前按 HUD ID 保存的设置，在该 HUD 识别出真实 ID 后仍有效。一个真实会话如果在多个窗口打开，真实 ID 的覆盖会作用于这些窗口。

会话列表是主题渲染器的本机刷新记录，不是进程存活证明。默认显示最近 120 秒内刷新的记录；暂停或退出的会话可以通过 `--all` 找到，恢复后继续使用保存的主题。目录、ID 和刷新时间只保存在本机。

旧版 Codex HUD 尚不能注册 ID 时，安装新版后执行一次：

```sh
agent-theme refresh
```

该命令只重新启动确认仍在运行的 `codex-pane.py` 显示进程，不向 Codex 输入命令，不重启 Codex 主进程，也不清理 tmux server。恢复出来的空闲 shell 和无关 Python 面板会跳过。之后运行 `agent-theme sessions` 或菜单即可选择原来正在运行的会话。Claude 不需要此操作，会在下一次状态栏调用时加载新代码。

## 常用环境变量

| 变量 | 值 / 用途 |
| --- | --- |
| `AGENT_THEME_CAST` | Codex 角色；留空自动选择 |
| `AGENT_THEME_STYLE` | Codex 布局：`mecha` / `minimal` / `card` / `pill` / `random` |
| `CODEX_THEME_DISABLE=1` | 直接执行原 Codex，不创建 HUD |
| `AGENT_THEME_WINDOWS_TEXT=1` | Windows Codex 使用静态字符头像 |
| `AGENT_THEME_REAL_CODEX` | 单次覆盖原始 Codex 可执行程序路径 |
| `AGENT_THEME_PREFERENCES` | 可选的本机偏好文件路径；默认 `~/.config/agent-theme/preferences.json` |
| `CLAUDE_STATUSLINE_CAST` | Claude 角色，与 Codex 使用同一组角色名 |
| `CLAUDE_STATUSLINE_STYLE` | Claude 布局，与 Codex 使用同一组布局名 |
| `CLAUDE_STATUSLINE_IMAGE=off` | 关闭 Claude 的真实图片路径，使用字符回退 |

## 显示内容

- `PATH`：当前项目目录；这是运行时本地显示的数据。
- `GIT`：Git 分支信息；非 Git 目录显示 `NO REPO`。
- `CORE`：当前会话提供的模型、上下文窗口及推理强度。
- `MODE`：当前会话记录的审批/权限模式。结构化的分项审批显示为 `GRANULAR n/5`，表示五类中有 n 类可弹出审批提示；关闭提示的类别会自动拒绝相应请求，这不是文件/网络访问权限的计数。未知结构仅显示 `GRANULAR` 或 `CUSTOM`，不会展开原始配置。主题不修改权限。
- `CTX`：本地会话记录提供的上下文使用量。
- `5H`、`7D`：CLI 记录提供的额度窗口；没有数据时显示 `N/A` / `NO SIGNAL`。
- `AVG`：Codex 整轮输出 token 总和 / 整轮耗时。工具执行与等待也计入分母；新一轮开始后重新计数。新格式直接使用 `turn_token_usage`，旧格式使用去重后的累计输出差值。
- `API`：Copilot 最近请求的输出 token / `duration`（毫秒转秒）；Claude 使用会话累计输出 token / 累计 API 耗时。包含首 token 等待，不是纯解码速度。
- `EST`：Claude 未提供 API 耗时的情况下，按转录时间估计。无有效计数/耗时则显示未知。
- `[FAST ON/OFF/?]`：客户端明确报告的速度模式；Codex `priority` / `fast` 显示 ON，明确的标准层显示 OFF，未报告则显示问号。只显示、不启用或改变模式；服务端实际调度也可能与客户端请求不同。
- `TOKENS`：Copilot 本机日志记录的请求 token 累计。premium-request cost 不当作美元价格显示。

不估算账户余额、订阅余量或不存在的五小时额度。字段可用性取决于 CLI 版本、账户和日志格式。Codex 长日志使用增量读取，避免工具输出过长后丢失本轮的工作状态与推理强度。

Claude 接收官方状态栏 JSON；Codex 读取本机 `CODEX_HOME`（默认 `~/.codex`）内的会话记录和模型默认配置。Copilot 读取 `COPILOT_HOME`（默认 `~/.copilot`）内归属明确的会话事件。这些数据不上传到本项目或 GitHub。Fast 字段来源参见 [OpenAI 官方速度模式说明](https://learn.chatgpt.com/docs/agent-configuration/speed)。

Copilot 对应环境变量为 `COPILOT_STATUSLINE_CAST`、`COPILOT_STATUSLINE_STYLE`、`COPILOT_STATUSLINE_ROTATION`、`COPILOT_STATUSLINE_INTERVAL`；Codex 和 Claude 使用各自前缀的 `ROTATION` / `INTERVAL` 设置轮播。会话级覆盖优先级最高。

## 文件位置

| 位置 | 内容 |
| --- | --- |
| `~/.local/share/agent-theme/` | 主题代码、素材和独立 Codex 入口 |
| `~/.config/agent-theme/preferences.json` | 客户端默认值与会话级角色/布局，权限 600 |
| `~/.local/state/agent-theme/session-registry/` | 会话 ID、项目目录、刷新时间及显示选择，目录 700、文件 600 |
| `~/.local/state/agent-theme/install.json` | 本机安装记录与原 Codex 路径，权限 600 |
| `~/.local/state/agent-theme/backups/` | 本机配置备份，目录权限 700 |
| `~/.claude/settings.json` | 合并后的 `statusLine` 配置 |
| 所选 shell 启动文件 | 仅添加带标记的主题加载块 |

安装记录和备份在仓库之外。不要把这些真实文件加入 Git。

使用 `AGENT_THEME_PREFERENCES` 指定独立偏好文件时，刷新记录会放在它旁边的 `session-registry/`，便于不同配置各自列出会话。
