# Changelog

所有重要变更记录在此文件。格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。

## [Unreleased]

### Added

- 插件 `plugins/guard-email/`：`send_email` 工具、`lib/mailer.py`、SMTP 配置向导
  `scripts/guard-config.py`、`/guard-email:email` 命令与配置示例。与 `guard` 无代码依赖，
  可单独安装；敏感附件与私钥外发的拦截由 `guard` 的策略提供，因此 `plugin.json`、
  README 与 `install.sh` 都提示「建议与 guard 一起安装」（仅提示，不引入依赖）。
- 插件 `plugins/ask_image/`：`ask_image` 工具就图片内容回答一个具体问题（必填 `question`、
  可选 `context`），复用内置 `image_to_text` 的图片解析与视觉模型调用，只替换 prompt 组合，
  输出与报错措辞改为 `ask_image` / `[Image answer via ...]`。
- `scripts/install.sh`：`--list` 列出仓库中的插件，`--only <名称[,名称]>` 只装指定插件
  （未知名直接报错，可重复或逗号分隔），`--all` 重置为全装。
- 支持安装到 ohmo 工作区：`./scripts/install.sh "${OHMO_WORKSPACE:-$HOME/.ohmo}/plugins"`。
- 测试：集合级布局校验（清单有效、目录名与 `name` 一致、根目录不得有 `plugin.json`、
  清单路径不越出插件目录），安装位置解析（用户级 / ohmo / 项目级 / 自定义插件根命中，
  缺失时 fail-open），以及 `ask_image` 的 prompt 组合、委托透传与「只注册自身、
  不重复注册父类」（未安装 openharness 时整体跳过）。

- `OPENHARNESS_GUARD_STRICT=1` 严格模式：hook 脚本找不到时不再静默放行，而是拒绝工具调用
  （退出码 2）并把 `[guard][BLOCKED]` 告警送入模型上下文；默认关闭。审计日志的
  `hook-missing` 事件新增 `strict` 字段，可区分放行与拒绝。

### Changed

**破坏性**

- 仓库改为插件集合：插件从仓库根移到 `plugins/<名称>/`，根目录不再有 `plugin.json`。
  旧布局安装需重新运行 `scripts/install.sh --force`；`/plugin install <仓库根>` 不再有效，
  应指向 `plugins/<名称>`。
- 邮箱能力拆成独立插件 `guard-email`：`send_email`、`lib/mailer.py`、`scripts/guard-config.py`、
  `commands/email.md`、`examples/` 从 `guard` 迁出，命令由 `/guard:email` 改为
  `/guard-email:email`。`guard` 版本升到 0.3.0，`guard-email` 起始版本 0.1.0。
  邮箱相关策略规则（`email-sensitive-attachment`、`leak-smtp-secret`、`private-key-material`
  的 `send_email` 分支）仍留在 `guard/policies/default.json`，按工具名匹配，
  未装 `guard-email` 时不命中。

**其他**

- `plugins/guard/hooks.json` 改为通配查找（`<根>/hooks/*.py`、`<根>/*/hooks/*.py`），
  不再写死 `plugins/guard`；`OPENHARNESS_GUARD_ROOT` 既可以是插件目录，也可以是插件根目录。
- `scripts/install.sh` 遍历 `plugins/*/plugin.json` 逐个安装：先整体检查冲突再写入，
  目录名与清单 `name` 不一致时直接失败；`--link` / `--force` / 自定义插件根的行为不变。
- 默认配置文件路径改为跟随 `${OPENHARNESS_CONFIG_DIR:-~/.openharness}`。
- 明确不在 `settings.json` 中保存插件配置：宿主会忽略未知键并在保存时丢弃。

### Fixed

- hook 脚本按 `OPENHARNESS_GUARD_ROOT` → 用户插件根 → ohmo 工作区插件根 → 项目级插件根
  顺序查找，修复项目级安装时 hook 找不到脚本、进而阻塞全部工具调用的问题；全部缺失时
  告警并放行。

## [0.2.0] - 2026-11-10

### Added

- `send_email` 工具：通过 SMTP 发送文本与本地文件附件，支持 UTF-8 主题/正文、
  多收件人、抄送/密送、附件类型推断与总大小上限。
- `lib/mailer.py`：标准库实现，支持 `ssl` / `starttls` / `none`，配置来自
  环境变量或 `~/.openharness/guard-email.json`，环境变量优先。
- 收件人白名单（`OPENHARNESS_GUARD_EMAIL_ALLOWLIST`）、地址校验与头部注入防护。
- 新增策略规则 `email-sensitive-attachment`，并把 `send_email` 纳入
  `private-key-material` 的检查范围。
- `examples/guard-email.example.json` 与 22 个邮件相关测试。

## [0.1.0] - 2026-11-10

### Added

- OpenHarness 插件清单 `plugin.json`，支持 skills / commands / agents / tools / hooks / MCP 六类扩展点。
- `pre_tool_use` 安全拦截 hook 与 `post_tool_use` JSONL 审计 hook。
- 标准库策略引擎 `lib/guard_core.py`，支持 `off` / `audit` / `enforce` 三种模式。
- 内置规则：破坏性删除、强制推送、管道执行远程脚本、磁盘写入、根目录 `chmod 777`、
  `.env` 读取、凭据文件读取、私钥落盘。
- `guard-safety` 技能、`/guard:guard-audit` 命令、`guard-reviewer` 子代理、`guard_check` 工具。
- 安装脚本与 `unittest` 测试套件。
