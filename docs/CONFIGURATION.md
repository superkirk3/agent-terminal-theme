# 配置与数据说明

## 常用环境变量

| 变量 | 值 / 用途 |
| --- | --- |
| `AGENT_THEME_CAST` | Codex 角色；留空自动选择 |
| `AGENT_THEME_STYLE` | Codex 布局：`mecha` / `minimal` / `card` / `pill` / `random` |
| `CODEX_THEME_DISABLE=1` | 直接执行原 Codex，不创建 HUD |
| `AGENT_THEME_WINDOWS_TEXT=1` | Windows Codex 使用静态字符头像 |
| `AGENT_THEME_REAL_CODEX` | 单次覆盖原始 Codex 可执行程序路径 |
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
| `~/.local/state/agent-theme/install.json` | 本机安装记录与原 Codex 路径，权限 600 |
| `~/.local/state/agent-theme/backups/` | 本机配置备份，目录权限 700 |
| `~/.claude/settings.json` | 合并后的 `statusLine` 配置 |
| 所选 shell 启动文件 | 仅添加带标记的主题加载块 |

安装记录和备份在仓库之外。不要把这些真实文件加入 Git。
