# Changelog

所有重要变更记录在此文件。格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。

## [Unreleased]

### Changed

- **布局变更（破坏性）**：仓库改为插件集合，插件从仓库根移到 `plugins/guard/`，根目录不再有
  `plugin.json`。已安装的旧布局需要重新运行 `scripts/install.sh`；`/plugin install <仓库根>`
  不再有效，应改为指向 `plugins/guard`。
- `scripts/install.sh` 遍历 `plugins/*/plugin.json` 逐个安装：先整体检查冲突再写入，目录名与清单
  `name` 不一致时直接失败；`--link` / `--force` / 自定义插件根的行为不变。
- `plugins/guard/hooks.json` 改为通配查找（`<根>/hooks/*.py`、`<根>/*/hooks/*.py`），不再写死
  `plugins/guard`；`OPENHARNESS_GUARD_ROOT` 现在既可以是插件目录也可以是插件根目录。
- hook 脚本按 `OPENHARNESS_GUARD_ROOT` → 用户插件根 → ohmo 工作区插件根 → 项目级插件根顺序
  查找，修复项目级安装时 hook 找不到脚本、进而阻塞全部工具调用的问题；全部缺失时告警并放行。
- `scripts/install.sh` 新增 `--link` 软链接安装，便于开发时立即生效；补充安装前置条件、
  安装方式、验证与卸载说明。
- 默认配置文件路径改为跟随 `${OPENHARNESS_CONFIG_DIR:-~/.openharness}`。
- 斜杠命令改为 `/guard:audit`（原 `commands/guard-audit.md` 重命名）；邮箱命令随插件改名为 `/guard-email:email`。
- 明确不在 `settings.json` 中保存插件配置：宿主会忽略未知键并在保存时丢弃。
- **邮箱能力拆成独立插件 `guard-email`（破坏性）**：`send_email`、`lib/mailer.py`、
  `scripts/guard-config.py`、`commands/email.md`、`examples/` 从 `guard` 迁出；命令由
  `/guard:email` 改为 `/guard-email:email`。`guard` 只保留拦截、审计、审查与自检，
  不再包含邮件实现。邮箱相关策略规则（`email-sensitive-attachment`、`leak-smtp-secret`、
  `private-key-material` 的 `send_email` 分支）仍留在 `guard/policies/default.json`，
  按工具名匹配，未装 `guard-email` 时不命中。
- `guard` 版本升到 0.3.0，新增插件 `guard-email` 0.1.0。
- 明确 `guard-email` 与 `guard` 的搭配关系：前者可独立运行，但敏感附件/私钥外发的拦截
  由后者提供。`plugin.json` 与 README 标注建议一起安装，`install.sh` 在只装
  `guard-email` 时给出提示（只做提示，不引入代码依赖）。
- `scripts/install.sh` 支持按需挑选插件：`--list` 列出仓库里的插件，`--only <名称[,名称]>`
  只装指定插件（未知名直接报错），`--all` 恢复默认全装。

### Added

- 支持安装到 ohmo 工作区：`./scripts/install.sh "${OHMO_WORKSPACE:-$HOME/.ohmo}/plugins"`。
  hook 查找路径新增 `${OHMO_WORKSPACE:-$HOME/.ohmo}/plugins`（通配插件根），并补集成测试。
- 新增 `/guard-email:email` 斜杠命令：`status` 查看配置、`test` 测试 SMTP、`send <邮箱>` 发送测试邮件；
  明确不通过对话接收授权码。
- `guard-config.py setup` 新增非交互模式：`--password-env <变量名>` / `--from-env`，
  授权码只从环境变量读取，可经 `/guard-email:email setup ...` 完成配置而不进入模型上下文。
- `plugins/guard-email/scripts/guard-config.py` 配置向导：`setup`（服务商预设、授权码隐藏输入、权限 600）、
  `show`（不显示密码）、`test` / `test --send-to`（验证 SMTP 登录或发测试邮件）。
- `mailer.verify_connection()` 与配置脚本测试。
- 策略规则 `leak-smtp-secret`：拦截在命令中展开或打印 SMTP 授权码环境变量。
- 安装位置解析的集成测试（用户级 / ohmo / 项目级 / 自定义插件根命中，缺失时 fail-open），
  以及集合级布局校验（清单有效、目录名与 `name` 一致、根目录不得有 `plugin.json`、
  清单路径不越出插件目录）。
- 新插件 `plugins/ask_image/`：`ask_image` 工具就图片内容回答一个具体问题
  （必填 `question`、可选 `context`），复用内置 `image_to_text` 的图片解析与视觉模型调用，
  输出与报错措辞改为 `ask_image` / `[Image answer via ...]`。
- `tests/test_ask_image.py`：覆盖 prompt 组合、委托透传、输出改称与「只注册 ask_image、
  不重复注册父类」；未安装 openharness 时整体跳过。

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
