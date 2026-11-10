# Changelog

所有重要变更记录在此文件。格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。

## [Unreleased]

### Added

- 新增 `/guard:email` 斜杠命令：`status` 查看配置、`test` 测试 SMTP、`send <邮箱>` 发送测试邮件；
  明确不通过对话接收授权码。
- `guard-config.py setup` 新增非交互模式：`--password-env <变量名>` / `--from-env`，
  授权码只从环境变量读取，可经 `/guard:email setup ...` 完成配置而不进入模型上下文。
- `scripts/guard-config.py` 配置向导：`setup`（服务商预设、授权码隐藏输入、权限 600）、
  `show`（不显示密码）、`test` / `test --send-to`（验证 SMTP 登录或发测试邮件）。
- `mailer.verify_connection()` 与配置脚本测试。
- 策略规则 `leak-smtp-secret`：拦截在命令中展开或打印 SMTP 授权码环境变量。

### Changed

- 默认配置文件路径改为跟随 `${OPENHARNESS_CONFIG_DIR:-~/.openharness}`。
- 斜杠命令改为 `/guard:audit` 与 `/guard:email`（原 `commands/guard-audit.md` 重命名）。
- 明确不在 `settings.json` 中保存插件配置：宿主会忽略未知键并在保存时丢弃。

### Changed

- hook 脚本按 `OPENHARNESS_GUARD_ROOT` → 用户插件目录 → 项目级插件目录顺序查找，
  修复项目级安装时 hook 找不到脚本、进而阻塞全部工具调用的问题；全部缺失时告警并放行。
- `scripts/install.sh` 新增 `--link` 软链接安装，便于开发时立即生效；补充安装前置条件、
  三种安装方式、验证与卸载说明。

### Added

- 安装位置解析的集成测试（项目级安装命中、缺失时 fail-open）。

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
