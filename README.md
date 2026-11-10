# guard

[OpenHarness](https://github.com/HKUDS/OpenHarness) 的安全护栏扩展：在 Agent 执行工具调用前拦截高风险操作，并提供审计日志、审计技能、斜杠命令、审查子代理、自检工具与邮箱通知。

> 目标：拦住代价高、不可逆、明显越权的操作。它不替代沙箱、权限系统或人工审批。

## 能力

| 扩展点 | 位置 | 说明 |
| --- | --- | --- |
| Hook | `hooks.json` | `pre_tool_use` 拦截高风险调用；`post_tool_use` 写入审计日志 |
| 策略引擎 | `lib/guard_core.py`、`policies/default.json` | 只依赖标准库的规则匹配 |
| 技能 | `skills/guard-safety/SKILL.md` | 安全作业流程与审计清单 |
| 命令 | `commands/audit.md`、`commands/email.md` | `/guard:audit` 安全审计、`/guard:email` 邮箱配置与测试 |
| 子代理 | `agents/guard-reviewer.md` | 只读安全审查代理 |
| 工具 | `tools/guard_check.py` | `guard_check`：执行前预演一次判定 |
| 工具 | `tools/send_email.py` | `send_email`：通过 SMTP 发送文本与文件附件 |
| MCP | `mcp.json` | 预留 MCP 服务器挂载点（默认空） |

## 内置规则

| 规则 ID | 作用 |
| --- | --- |
| `destructive-rm-root` | 拦截对 `/`、`~`、`$HOME` 的递归删除 |
| `force-push` | 拦截 `git push --force` / `-f` |
| `pipe-to-shell` | 拦截 `curl ... \| bash` 一类远程代码执行 |
| `disk-destroy` | 拦截 `dd of=/dev/*`、`mkfs /dev/*` |
| `chmod-root-777` | 拦截对根目录 `chmod 777` |
| `read-dotenv-file` / `read-dotenv-command` | 拦截读取 `.env`（`.env.example` 等模板除外） |
| `read-credentials` | 拦截读取 SSH 私钥、云凭证、`.netrc` 等 |
| `private-key-material` | 拦截写入、输出或邮寄私钥内容 |
| `email-sensitive-attachment` | 拦截通过邮件外发 `.env`、SSH 私钥、云凭证等文件 |
| `leak-smtp-secret` | 拦截在命令中展开或打印 `OPENHARNESS_GUARD_SMTP_PASSWORD` |

规则匹配的是工具名 + 指定字段的正则，属于**启发式防线**：无法识别混淆或间接执行。高风险环境请同时启用 OpenHarness 的沙箱与权限限制。

## 安装

guard 是标准 OpenHarness 插件，仓库根目录就是插件目录（`plugin.json` 在根上）。安装前确认：

- 已安装 OpenHarness，`oh` / `openharness` 可运行；
- 运行 OpenHarness 的环境有 `python3`（hook 用它执行策略脚本）；
- 跑测试不需要联网；邮箱通知需要另外配置 SMTP（见下文）。

### 方式一：用户级插件（推荐）

```bash
git clone https://github.com/biglanmao/guard.git
cd guard
./scripts/install.sh          # 复制安装
# 或
./scripts/install.sh --link   # 软链接安装：改仓库代码立即生效，适合开发
```

默认目标：`${OPENHARNESS_CONFIG_DIR:-$HOME/.openharness}/plugins/guard`。
安装到自定义根目录：`./scripts/install.sh /path/to/plugins`。

手动等价的软链接方式：

```bash
mkdir -p "${OPENHARNESS_CONFIG_DIR:-$HOME/.openharness}/plugins"
ln -s "$(pwd)" "${OPENHARNESS_CONFIG_DIR:-$HOME/.openharness}/plugins/guard"
```

### 方式二：项目级插件（只对当前工作区生效）

```bash
mkdir -p .openharness/plugins
ln -s /path/to/guard .openharness/plugins/guard
```

项目级插件默认禁用，需要在 `${OPENHARNESS_CONFIG_DIR:-$HOME/.openharness}/settings.json` 中开启：

```json
{
  "allow_project_plugins": true
}
```

该开关会加载当前工作区的所有项目级插件，只应对可信仓库开启。

### 方式三：`/plugin install`

在 `oh` 中执行 `/plugin install /path/to/guard` 也可以，但它会原样复制整个目录
（包含 `.git`、`.venv`）。本仓库建议使用 `scripts/install.sh`，它会排除这些目录。

### 安装位置与 hook 解析

`pre_tool_use` / `post_tool_use` hook 会依次在以下位置查找脚本：

1. `$OPENHARNESS_GUARD_ROOT`
2. `${OPENHARNESS_CONFIG_DIR:-$HOME/.openharness}/plugins/guard`
3. `$PWD/.openharness/plugins/guard`（项目级安装）

都找不到时输出告警并放行（fail-open），避免 hook 异常把整个 Agent 锁死。
因此**安装到非默认根目录时请设置 `OPENHARNESS_GUARD_ROOT`**。

### 验证安装

启动 `oh` 后：

```text
/plugin            # 列表里应出现 guard 0.2.0
/reload-plugins    # 修改插件后重新加载
```

在对话中调用 `guard_check` 预演一次判定：

```json
{"tool_name": "bash", "tool_input": {"command": "rm -rf /"}}
```

返回示例：

```json
{
  "allowed": false,
  "action": "deny",
  "tool_name": "bash",
  "rule_id": "destructive-rm-root",
  "reason": "检测到可能删除根目录或家目录的 rm 命令，请改用具体路径并先确认内容。",
  "matched": "rm -rf /"
}
```

也可以在命令行直接验证 hook（默认安装路径）：

```bash
OPENHARNESS_HOOK_PAYLOAD='{"tool_name":"bash","tool_input":{"command":"rm -rf /"}}' \
python3 "${OPENHARNESS_CONFIG_DIR:-$HOME/.openharness}/plugins/guard/hooks/guard_hook.py"; echo "exit=$?"
```

预期输出拦截原因且 `exit=2`。

### 卸载

- 用户级复制安装：`/plugin uninstall guard`，或删除 `${OPENHARNESS_CONFIG_DIR:-$HOME/.openharness}/plugins/guard`；
- 用户级软链接安装：删除该软链接即可；
- 项目级安装：删除 `.openharness/plugins/guard` 软链接。

## 邮箱通知

`send_email` 工具把文本内容与本地文件作为附件发送到指定邮箱，适合在长任务结束后
发送报告、日志或构建产物。它通过 SMTP 发送，不依赖第三方库。

### 配置 SMTP

`oh` 的 `/config set` 和 `oh config set` 只接受 OpenHarness 内置的 `Settings` 字段，插件也不能注册
`oh` 子命令；因此 guard 自带一个配置脚本，在终端里交互式写入配置（授权码用 `getpass`
隐藏输入，文件权限自动设为 600），并可直接测试 SMTP 登录：

```bash
# 默认安装路径
python3 ~/.openharness/plugins/guard/scripts/guard-config.py setup
python3 ~/.openharness/plugins/guard/scripts/guard-config.py show
python3 ~/.openharness/plugins/guard/scripts/guard-config.py test
python3 ~/.openharness/plugins/guard/scripts/guard-config.py test --send-to you@example.com
```

`setup` 会依次询问服务商（qq/163/126/gmail/outlook/custom）、主机、端口、加密方式、
账号和授权码。默认写入 `${OPENHARNESS_CONFIG_DIR:-$HOME/.openharness}/guard-email.json`。

也可以手动写文件（参考 `examples/guard-email.example.json`）：

```json
{
  "host": "smtp.example.com",
  "port": 587,
  "security": "starttls",
  "username": "bot@example.com",
  "password": "授权码或应用专用密码",
  "from": "guard@example.com"
}
```

或者用环境变量覆盖（优先级高于配置文件）：

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `OPENHARNESS_GUARD_SMTP_HOST` | 无（必填） | SMTP 服务器 |
| `OPENHARNESS_GUARD_SMTP_PORT` | 465 / 587 / 25 | 随 `security` 取值 |
| `OPENHARNESS_GUARD_SMTP_SECURITY` | `starttls` | `ssl`（465）、`starttls`（587）、`none`（25） |
| `OPENHARNESS_GUARD_SMTP_USER` | 无 | 登录用户名 |
| `OPENHARNESS_GUARD_SMTP_PASSWORD` | 无 | 登录密码或授权码 |
| `OPENHARNESS_GUARD_SMTP_FROM` | 同用户名 | 发件人地址 |
| `OPENHARNESS_GUARD_SMTP_TIMEOUT` | `30` | 连接与发送超时（秒） |
| `OPENHARNESS_GUARD_EMAIL_CONFIG` | `${OPENHARNESS_CONFIG_DIR:-~/.openharness}/guard-email.json` | 配置文件路径 |
| `OPENHARNESS_GUARD_EMAIL_ALLOWLIST` | 空（不限制） | 收件人白名单，如 `me@example.com,@corp.com` |
| `OPENHARNESS_GUARD_EMAIL_MAX_BYTES` | `20971520`（20 MiB） | 附件总大小上限 |

### 斜杠命令

在 `oh` 会话中：

```text
/guard:email              # 查看邮箱配置状态（不显示密码）
/guard:email test         # 测试 SMTP 连接与登录
/guard:email send me@example.com   # 发送测试邮件
/guard:audit              # 对当前工作区做安全审计
```

也可以在对话里完成配置——但授权码只通过**环境变量名**传递，不进入对话：

```bash
# 在启动 oh 的终端里先导出授权码
export OPENHARNESS_GUARD_SMTP_PASSWORD='授权码'
oh
```

```text
/guard:email setup host=smtp.qq.com port=465 security=ssl username=you@qq.com from=you@qq.com password_env=OPENHARNESS_GUARD_SMTP_PASSWORD
```

Agent 只会执行：

```bash
python3 <脚本> setup --host smtp.qq.com --port 465 --security ssl   --username you@qq.com --from you@qq.com   --password-env OPENHARNESS_GUARD_SMTP_PASSWORD
```

脚本在本地读取环境变量并写入 600 权限文件，模型和会话历史里只出现变量名。已有配置时
命令需要 `--force`；如果所有字段都已导出为 `OPENHARNESS_GUARD_SMTP_*`，也可以用
`/guard:email setup from_env`。

### 为什么授权码不直接发到对话里

对话内容会作为请求发送给模型服务商；挂在历史里的授权码无法撤回。工具从环境变量或
文件读取并只返回「已设置」时，授权码不经过模型上下文。交互式 `setup` 必须留在终端，
还因为 OpenHarness 的 Bash 工具没有 TTY（`stdin=DEVNULL`），`getpass` 无法在那里运行。

需要说清楚边界：`--password-env` 只是让**常规流程**不回显授权码，环境变量仍然存在于
`oh` 进程里，Agent 理论上可以用 `bash` 打印它（内置规则 `leak-smtp-secret` 会拦截直接
展开/打印的写法，但这不是硬隔离）。需要硬隔离时，用终端里的交互式 `setup`，让授权码
从未进入 `oh` 进程。

### 调用示例

```json
{
  "to": ["me@example.com"],
  "subject": "guard 审计报告",
  "body": "任务已完成，详见附件。",
  "attachments": ["reports/audit.md", "/var/log/build.log"]
}
```

相对路径基于当前工作目录。返回发送摘要（收件人、附件名、邮件大小），失败时返回
`is_error: true` 与原因。

### 安全约束

- 建议设置 `OPENHARNESS_GUARD_EMAIL_ALLOWLIST`，避免模型把数据发到任意地址。
- 附件有总大小上限，且内置策略 `email-sensitive-attachment` 会拦截 `.env`、SSH 私钥、
  云凭证等敏感文件；私钥内容出现在正文中也会被 `private-key-material` 拦截。
- 正文与附件内容本身无法完全审计，发送前请确认收件人与内容；高风险环境请配合
  沙箱与人工审批。

## 工作方式

```text
工具调用
   │
   ▼
pre_tool_use hook ──► hooks/guard_hook.py ──► guard_core.check()
   │                                              │
   │                              allow ◄─────────┤
   │                                │             │
   ▼                                ▼             ▼ deny
执行工具                       继续执行      退出码 2 + stderr 原因
   │
   ▼
post_tool_use hook ──► hooks/guard_audit.py ──► JSONL 审计日志
```

- `hooks.json` 中的 `block_on_failure: true` 让非零退出码成为“拦截”。
- 引擎自身异常时 **fail-open**（放行并告警），避免策略文件损坏导致 Agent 无法使用工具。
- 审计日志默认写入 `${OPENHARNESS_LOGS_DIR:-$HOME/.openharness/logs}/guard-audit.jsonl`，只记录工具名与参数（截断），不记录执行结果。参数本身可能含敏感信息，请按需限制日志权限或关闭该 hook。

## 配置

| 环境变量 | 取值 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `OPENHARNESS_GUARD_MODE` | `off` / `audit` / `enforce` | `enforce` | `audit` 只告警不拦截，`off` 关闭判定 |
| `OPENHARNESS_GUARD_POLICY` | 文件路径 | 内置 `policies/default.json` | 自定义策略文件 |
| `OPENHARNESS_GUARD_ROOT` | 目录 | `${OPENHARNESS_CONFIG_DIR:-$HOME/.openharness}/plugins/guard` | hook 脚本定位插件根目录 |
| `OPENHARNESS_GUARD_AUDIT_LOG` | 文件路径 | `$OPENHARNESS_LOGS_DIR/guard-audit.jsonl` | 审计日志位置 |
| `OPENHARNESS_LOGS_DIR` | 目录 | `~/.openharness/logs` | OpenHarness 日志目录 |

钩子实际执行的是：

```bash
python3 "${OPENHARNESS_GUARD_ROOT:-${OPENHARNESS_CONFIG_DIR:-$HOME/.openharness}/plugins/guard}/hooks/guard_hook.py"
```

因此运行 OpenHarness 的环境需要有 `python3`。安装到非默认位置时，请设置 `OPENHARNESS_GUARD_ROOT`。

### 自定义策略

策略文件是 JSON：

```json
{
  "version": 1,
  "mode": "enforce",
  "rules": [
    {
      "id": "block-prod-deploy",
      "description": "禁止在本地直接部署生产环境",
      "action": "deny",
      "tools": ["bash"],
      "fields": ["command"],
      "regex": "\\bdeploy\\s+--env\\s+prod\\b",
      "reason": "生产部署必须走 CI，请不要在本地直接执行。"
    }
  ]
}
```

字段说明：

- `id`：唯一规则名，用于日志与测试。
- `action`：`deny`（拦截）或 `warn`（只告警）。
- `tools`：工具名 glob 列表，`*` 表示全部。
- `fields`：要检查的顶层参数字段；省略时递归检查所有字符串（嵌套对象里的字符串也会被检查）。
- `regex`：Python 正则，命中任一字段即触发。
- `reason`：拦截时展示给用户与模型的原因。

## 目录结构

```text
guard/
├── plugin.json              # OpenHarness 插件清单
├── hooks.json               # pre/post tool use hook 配置
├── mcp.json                 # MCP 服务器（默认空）
├── lib/guard_core.py        # 策略引擎（标准库）
├── lib/mailer.py            # SMTP 发送与附件处理（标准库）
├── policies/default.json    # 内置规则
├── hooks/guard_hook.py      # pre_tool_use 拦截入口
├── hooks/guard_audit.py     # post_tool_use 审计日志
├── skills/guard-safety/     # 技能
├── commands/audit.md        # /guard:audit
├── commands/email.md        # /guard:email
├── agents/guard-reviewer.md # 子代理
├── tools/guard_check.py     # guard_check 工具
├── tools/send_email.py      # send_email 工具（邮箱通知）
├── examples/                # 配置示例
├── tests/                   # 单元测试与集成测试
└── scripts/install.sh       # 安装脚本
```

## 开发

```bash
python3 -m unittest discover -s tests -v
```

约定：

- 新增规则必须同时补测试，并确认不会误伤常见开发命令（见 `tests/test_guard_core.py`）。
- 规则 ID 用 kebab-case，`reason` 说明“为什么”和“怎么做更安全”。
- `lib/guard_core.py` 与 `lib/mailer.py` 只使用标准库，保证 hook 与工具可以在最小 Python 环境中运行。
- 邮箱相关测试使用假 SMTP 客户端，不依赖真实网络；不要把真实密码写入仓库。

## 许可证

[GPL-3.0](LICENSE)。
