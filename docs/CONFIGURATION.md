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

选择只保存在本机，不上传或跨机器同步。角色和布局可以分别修改；`--agent all` 是默认值，会更新两个客户端的对应字段。`reset` 清除所选客户端的保存值，不移除环境变量。

优先级：**该客户端的环境变量 → 保存的选择 → 会话随机选择**。Codex 使用 `AGENT_THEME_CAST` / `AGENT_THEME_STYLE`，Claude 使用 `CLAUDE_STATUSLINE_CAST` / `CLAUDE_STATUSLINE_STYLE`，两者互不覆盖。

每次渲染都会重新读取偏好，已经运行的 HUD/状态栏也能切换。首次从旧版升级时，先重新启动一次 Codex HUD 以加载新代码。若会话启动时带有显式环境变量，该进程会保留它们；需要不带这些变量启动新会话后，才能跟随保存值。主题偏好文件损坏时，运行中的状态栏回退到默认值；切换命令会报错且不覆盖原文件，修正或移走损坏文件后再设置。

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
- `MODE`：当前会话记录的权限模式。主题不修改权限。
- `CTX`：本地会话记录提供的上下文使用量。
- `5H`、`7D`：CLI 记录提供的额度窗口；没有数据时显示 `N/A` / `NO SIGNAL`。
- `LAST`：Codex 已记录 token 事件计算的输出速度估计，不是实时生成速率。

不估算账户余额、订阅余量或不存在的五小时额度。字段可用性取决于 CLI 版本、账户和日志格式。Codex 长日志使用增量读取，避免工具输出过长后丢失本轮的工作状态与推理强度。

Claude 接收官方状态栏 JSON；Codex 读取本机 `CODEX_HOME`（默认 `~/.codex`）内的会话记录和模型默认配置。这些数据不上传到本项目或 GitHub。

## 文件位置

| 位置 | 内容 |
| --- | --- |
| `~/.local/share/agent-theme/` | 主题代码、素材和独立 Codex 入口 |
| `~/.config/agent-theme/preferences.json` | 两个客户端分别保存的角色和布局，权限 600 |
| `~/.local/state/agent-theme/install.json` | 本机安装记录与原 Codex 路径，权限 600 |
| `~/.local/state/agent-theme/backups/` | 本机配置备份，目录权限 700 |
| `~/.claude/settings.json` | 合并后的 `statusLine` 配置 |
| 所选 shell 启动文件 | 仅添加带标记的主题加载块 |

安装记录和备份在仓库之外。不要把这些真实文件加入 Git。
