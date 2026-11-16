# AGENTS.md

面向在该仓库工作的 AI Agent 的说明。

## 项目是什么

本仓库是 OpenHarness 的**插件集合**：每个插件放 `plugins/<名称>/`，各自带一份
`plugin.json`，可单独安装、单独启用。当前有三个插件：

- `plugins/guard/`：安全护栏，`pre_tool_use` hook 拦截高风险操作，附审计、技能、命令、
  子代理、工具与 MCP 挂载点。
- `plugins/guard-email/`：邮箱通知，`send_email` 工具 + SMTP 配置向导 +
  `/guard-email:email` 命令。与 `guard` 无代码依赖，**装不装都不影响拦截判定**；
  但敏感附件拦截由 `guard` 提供，因此文档与 `plugin.json` 都标注「建议与 guard 一起装」，
  `install.sh` 在只装它时给出提示。**不要为此引入代码依赖**（会让 `--only guard-email` 装不动）。
- `plugins/ask_image/`：`ask_image` 工具，就图片内容回答一个具体问题（继承内置
  `image_to_text`，只改 prompt 组合与输出措辞）。

仓库根目录不是插件，不要把它当插件目录安装。

## 结构

- `plugins/<名称>/plugin.json`：插件清单；`name` 必须与目录名一致（`install.sh` 与
  布局测试都依赖该约定）。新增顶层目录时保持与清单字段一致。
- `plugins/guard/hooks.json`：扁平 hook 配置；`pre_tool_use` 拦截，`post_tool_use` 审计。
  命令按 `$OPENHARNESS_GUARD_ROOT`、用户插件根、ohmo 工作区插件根、
  `$PWD/.openharness/plugins` 的顺序查找，每层先试 `<根>/hooks/*.py` 再试
  `<根>/*/hooks/*.py`；**不要写死插件目录名**。全部缺失时保持 fail-open，但必须输出
  `[guard][WARN]` 告警（写明「未经任何拦截」与查找路径）并追加 `hook-missing` 审计事件，
  不要让它静默失效。修改后同步更新
  `tests/test_plugin_layout.py` 的 `InstallResolutionTest`。
- `plugins/guard/lib/guard_core.py`：策略引擎，**只允许使用 Python 标准库**。
- `plugins/guard/policies/default.json`：默认规则；修改后必须补测试。其中
  `email-sensitive-attachment`、`leak-smtp-secret` 与 `private-key-material` 的 `send_email`
  分支面向 `guard-email` 的工具，按工具名匹配，**未装 guard-email 时不会命中**；
  改这里不要顺手把规则搬进 `guard-email`（引擎只读单一策略文件）。
- `plugins/guard/hooks/guard_hook.py`：拦截入口，退出码 2 表示阻止；异常时 fail-open。
- `plugins/guard/hooks/guard_audit.py`：审计日志，写入失败不得阻断。
- `plugins/guard/tools/guard_check.py`：`guard_check` 工具，加载 `openharness.tools.base.BaseTool`。
- `plugins/guard-email/lib/mailer.py`：SMTP 配置、附件读取与邮件构造，**只允许使用 Python 标准库**。
- `plugins/guard-email/tools/send_email.py`：`send_email` 工具，负责收件人白名单、附件大小上限与错误转换。
- `plugins/guard/skills/`、`commands/`、`agents/`：OpenHarness 约定的扩展目录。
- `tests/`：`unittest`，不依赖第三方库；同时承载集合级校验（清单、目录名、多插件发现）。
- `scripts/install.sh`：集合级安装脚本，遍历 `plugins/*/plugin.json`，支持 `--list`
  列出插件、`--only <名称[,名称]>` 只装指定插件；复制安装（排除 `.git`/`.venv`）或
  `--link` 软链接安装。
- `plugins/guard-email/scripts/guard-config.py`：SMTP 配置向导（setup/show/test），权限 600，授权码不回显。
  非交互配置只允许 `--password-env <变量名>` 或 `--from-env`，禁止新增明文密码参数。
- `plugins/ask_image/tools/ask_image.py`：`ask_image` 工具。加载器会扫描模块里的每个
  `BaseTool` 子类并实例化，所以只能 `from openharness.tools import image_to_text_tool`
  后引用模块，**不要**直接 import `ImageToTextTool`（否则父类会被再次注册成
  `image_to_text`，覆盖内置工具）。`tests/test_ask_image.py` 覆盖该约束。

## 约定

- 规则 ID 使用 kebab-case；每条规则必须有 `reason`，说明风险和替代方案。
- 新增或修改规则时同步更新 `tests/test_guard_core.py`，并覆盖“允许”和“拦截”两侧。
- 新增插件时新建 `plugins/<名称>/plugin.json`（`name` = 目录名），并让
  `python3 -m unittest discover -s tests` 通过；不要为单个插件改 `scripts/install.sh`。
- 判断某能力该放哪个插件，看它是否**运行期必需**：拦截判定必需 → `guard`；只是在
  装了它之后才可用的能力（发邮件、看图问答）→ 各自独立插件。命令名前缀等于插件名，
  所以独立插件会得到 `/guard-email:email` 这样的名字，迁移命令前先在 CHANGELOG 标为破坏性变更。
- 插件之间必须保持独立：不互相 import、不引用别的插件的路径、不共享运行时状态，
  保证任意插件都能被单独安装后正常加载（布局测试 `test_each_plugin_is_self_contained`
  校验清单路径不越界）。
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
