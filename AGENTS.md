# AGENTS.md

面向在该仓库工作的 AI Agent 的说明。

## 项目是什么

`guard` 是 OpenHarness 的扩展插件，通过 `pre_tool_use` hook 在工具执行前做安全拦截，
并提供技能、命令、子代理、工具与 MCP 挂载点。仓库根目录就是一个可安装的插件目录。

## 结构

- `plugin.json`：插件清单，新增顶层目录时保持与清单字段一致。
- `hooks.json`：扁平 hook 配置；`pre_tool_use` 拦截，`post_tool_use` 审计。命令必须
  依次兼容 `$OPENHARNESS_GUARD_ROOT`、用户插件目录、`$PWD/.openharness/plugins/guard`
  三种安装位置，修改后同步更新 `tests/test_plugin_layout.py` 的 `InstallResolutionTest`。
- `lib/guard_core.py`：策略引擎，**只允许使用 Python 标准库**。
- `policies/default.json`：默认规则；修改后必须补测试。
- `hooks/guard_hook.py`：拦截入口，退出码 2 表示阻止；异常时 fail-open。
- `hooks/guard_audit.py`：审计日志，写入失败不得阻断。
- `tools/guard_check.py`：`guard_check` 工具，加载 `openharness.tools.base.BaseTool`。
- `lib/mailer.py`：SMTP 配置、附件读取与邮件构造，**只允许使用 Python 标准库**。
- `tools/send_email.py`：`send_email` 工具，负责收件人白名单、附件大小上限与错误转换。
- `skills/`、`commands/`、`agents/`：OpenHarness 约定的扩展目录。
- `tests/`：`unittest`，不依赖第三方库。
- `scripts/install.sh`：复制安装（排除 `.git`/`.venv`）或 `--link` 软链接安装。
- `scripts/guard-config.py`：SMTP 配置向导（setup/show/test），权限 600，授权码不回显。
  非交互配置只允许 `--password-env <变量名>` 或 `--from-env`，禁止新增明文密码参数。

## 约定

- 规则 ID 使用 kebab-case；每条规则必须有 `reason`，说明风险和替代方案。
- 新增或修改规则时同步更新 `tests/test_guard_core.py`，并覆盖“允许”和“拦截”两侧。
- 不要硬编码本机绝对路径；脚本通过 `Path(__file__)` 推导插件根目录。
- 不要把密钥、令牌、真实日志写入仓库或测试夹具；SMTP 密码只来自环境变量或
  `~/.openharness/guard-email.json`，不得作为工具参数或写入日志。
- 邮件测试必须使用假 SMTP 客户端（见 `tests/test_mailer.py`），禁止真实发信。
- 不要把插件配置写进 OpenHarness 的 `settings.json`：`Settings` 忽略未知键，
  `save_settings()` 会重写文件并丢掉它们；配置走 `guard-email.json` 或环境变量。
- 提交前运行：

  ```bash
  python3 -m unittest discover -s tests -v
  ```

## 边界

- 这是启发式防护，不替代沙箱、权限系统或人工审批。
- 引擎异常时选择 fail-open，修改该行为需要同步更新 README 与测试。
