# guard

[OpenHarness](https://github.com/HKUDS/OpenHarness) 的插件集合：每个插件独立成包、独立安装，
可以整包装也可以只挑需要的。仓库名沿用最早的安全护栏插件 `guard`。

| 插件 | 作用 | 依赖 |
| --- | --- | --- |
| [`guard`](#guard-插件能力) | 工具调用前拦截高风险操作，附审计日志、审计技能、`/guard:audit` 命令与审查子代理 | 仅 Python 标准库 |
| [`guard-email`](#guard-email-插件) | `send_email` 工具经 SMTP 发送文本与文件附件，附配置向导与 `/guard-email:email` 命令 | 仅 Python 标准库 |
| [`ask_image`](#ask_image-插件) | 就图片内容回答一个具体问题（读报错、按钮文案、表格等），比 `image_to_text` 更聚焦 | openharness、pydantic（随宿主提供） |

三个插件互不 import、可各自单独安装：想要拦截装 `guard`，需要发邮件再装 `guard-email`，
不装 `guard-email` 时 `guard` 的邮箱相关规则只是不命中（见[内置规则](#guard-插件内置规则)）。
`--only` 用于挑选安装（见[安装](#安装)）。

## guard 插件能力

| 扩展点 | 位置 | 说明 |
| --- | --- | --- |
| Hook | `plugins/guard/hooks.json` | `pre_tool_use` 拦截高风险调用；`post_tool_use` 写入审计日志 |
| 策略引擎 | `plugins/guard/lib/guard_core.py`、`plugins/guard/policies/default.json` | 只依赖标准库的规则匹配 |
| 技能 | `plugins/guard/skills/guard-safety/SKILL.md` | 安全作业流程与审计清单 |
| 命令 | `plugins/guard/commands/audit.md` | `/guard:audit` 安全审计 |
| 子代理 | `plugins/guard/agents/guard-reviewer.md` | 只读安全审查代理 |
| 工具 | `plugins/guard/tools/guard_check.py` | `guard_check`：执行前预演一次判定 |
| MCP | `plugins/guard/mcp.json` | 预留 MCP 服务器挂载点（默认空） |

## guard 插件内置规则

| 规则 ID | 作用 |
| --- | --- |
| `destructive-rm-root` | 拦截对 `/`、`~`、`$HOME` 的递归删除 |
| `force-push` | 拦截 `git push --force` / `-f` |
| `pipe-to-shell` | 拦截 `curl ... \| bash` 一类远程代码执行 |
| `disk-destroy` | 拦截 `dd of=/dev/*`、`mkfs /dev/*` |
| `chmod-root-777` | 拦截对根目录 `chmod 777` |
| `read-dotenv-file` / `read-dotenv-command` | 拦截读取 `.env`（`.env.example` 等模板除外） |
| `read-credentials` | 拦截读取 SSH 私钥、云凭证、`.netrc` 等 |
| `private-key-material` | 拦截写入、输出或邮寄私钥内容（`send_email` 分支需装 `guard-email`） |
| `email-sensitive-attachment` | 拦截通过邮件外发 `.env`、SSH 私钥、云凭证等文件（需装 `guard-email`） |
| `leak-smtp-secret` | 拦截在命令中展开或打印 `OPENHARNESS_GUARD_SMTP_PASSWORD` |

后两条与 `send_email` 相关：规则按**工具名**匹配，没装 `guard-email` 时 `send_email`
不存在，规则不会命中，也不会报错。

规则匹配的是工具名 + 指定字段的正则，属于**启发式防线**：无法识别混淆或间接执行。高风险环境请同时启用 OpenHarness 的沙箱与权限限制。

## 安装

本仓库是**插件集合**：每个插件放在 `plugins/<名称>/` 下，各自带一份 `plugin.json`，
当前包含 `plugins/guard/`、`plugins/guard-email/`、`plugins/ask_image/`。仓库根目录本身不是插件，
`scripts/install.sh` 会遍历 `plugins/*/plugin.json` 发现插件；`update.sh` / `uninstall.sh`
用同样的方式识别哪些插件属于本仓库。安装前确认：

- 已安装 OpenHarness，`oh` / `openharness` 可运行；
- 运行 OpenHarness 的环境有 `python3`（hook 用它执行策略脚本）；
- 跑测试不需要联网；`guard-email` 需要另外配置 SMTP（见下文）。

### 方式一：用户级插件（推荐）

```bash
git clone https://github.com/biglanmao/guard.git
cd guard
./scripts/install.sh --list              # 看有哪些插件、各自版本与作用
./scripts/install.sh --only guard                  # 只装安全护栏
./scripts/install.sh --only guard --only guard-email  # 需要发邮件时一起装
./scripts/install.sh --only guard,guard-email      # 同上，逗号分隔
./scripts/install.sh --only ask_image              # 只装图片问答
./scripts/install.sh                               # 装全部
./scripts/install.sh --link              # 软链接：改仓库代码立即生效，适合开发
```

默认目标：`${OPENHARNESS_CONFIG_DIR:-$HOME/.openharness}/plugins/<插件名>`（即
`plugins/guard` → `~/.openharness/plugins/guard`）。
安装到自定义插件根目录：`./scripts/install.sh /path/to/plugins`。
`--only` 接受逗号分隔的多选（如 `--only guard,ask_image`），未安装的插件不会加载；
已存在的插件需要 `--force` 才会覆盖。

手动等价的软链接方式（注意目标是插件目录，不是仓库根）：

```bash
mkdir -p "${OPENHARNESS_CONFIG_DIR:-$HOME/.openharness}/plugins"
ln -s "$(pwd)/plugins/guard" "${OPENHARNESS_CONFIG_DIR:-$HOME/.openharness}/plugins/guard"
```

### 方式二：项目级插件（只对当前工作区生效）

```bash
mkdir -p .openharness/plugins
ln -s /path/to/guard/plugins/guard .openharness/plugins/guard
```

项目级插件默认禁用，需要在 `${OPENHARNESS_CONFIG_DIR:-$HOME/.openharness}/settings.json` 中开启：

```json
{
  "allow_project_plugins": true
}
```

该开关会加载当前工作区的所有项目级插件，只应对可信仓库开启。

### 方式三：ohmo 工作区

ohmo 没有独立的插件格式，它把 `<workspace>/plugins` 作为额外的插件根交给 OpenHarness 加载，
所以同一个 guard 插件可以直接装进 ohmo，不需要改 ohmo 源码：

```bash
./scripts/install.sh "${OHMO_WORKSPACE:-$HOME/.ohmo}/plugins"
```

默认工作区是 `~/.ohmo`（可用 `OHMO_WORKSPACE` 覆盖），`ohmo init` 会创建 `plugins/` 目录。

### 方式四：`/plugin install`

在 `oh` 中执行 `/plugin install /path/to/guard/plugins/guard`（或 `.../plugins/ask_image`）
也可以，但它会原样复制整个插件目录。本仓库建议使用 `scripts/install.sh`：它按
`plugin.json` 发现插件、校验目录名、支持只装指定插件，并排除 `.git`、`.venv`、
`__pycache__` 等目录。

### 安装位置与 hook 解析

`pre_tool_use` / `post_tool_use` hook 会依次在以下插件根目录中查找脚本：

1. `$OPENHARNESS_GUARD_ROOT`
2. `${OPENHARNESS_CONFIG_DIR:-$HOME/.openharness}/plugins`（用户级安装）
3. `${OHMO_WORKSPACE:-$HOME/.ohmo}/plugins`（ohmo 工作区安装）
4. `$PWD/.openharness/plugins`（项目级安装）

每一层都先看目录本身（`<根>/hooks/guard_hook.py`），再看一层子目录
（`<根>/*/hooks/guard_hook.py`），因此 `OPENHARNESS_GUARD_ROOT` 既可以是插件目录
（`.../plugins/guard`），也可以是插件根目录（`.../plugins`）。

都找不到时**放行（fail-open）**，避免 hook 异常把整个 Agent 锁死。但放行不是静默的：
stderr 会输出以 `[guard][WARN]` 开头的告警，明确写出「本次工具调用未经任何拦截」
和实际查找过的四个路径，同时往审计日志追加一条 `hook-missing` 事件——
装错位置时既能当场看见，也能事后从日志里查出来。

因此**把插件装到非默认插件根目录时请设置 `OPENHARNESS_GUARD_ROOT`**；看到
`[guard][WARN]` 就说明当前没有护栏，先修路径再执行高风险操作。

**严格模式**：设置 `OPENHARNESS_GUARD_STRICT=1` 后，找不到脚本时不再静默放行，而是
拒绝每一次工具调用（退出码 2），告警以 `[guard][BLOCKED]` 开头并进入模型上下文——
适合 CI、批处理、无人值守任务。代价是配错路径会锁死所有工具，恢复方式是修好安装或
`unset OPENHARNESS_GUARD_STRICT`；默认关闭，不影响交互式使用。

### 验证安装

启动 `oh` 后：

```text
/plugin            # 列表里应出现已安装的插件，如 guard 0.3.0、guard-email 0.1.0
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

### 更新

`update.sh` 把**已经安装**的插件重装成当前 checkout 的内容，不会顺带安装没装过的插件：

```bash
./scripts/update.sh                 # 重装已安装的全部插件
./scripts/update.sh --only guard    # 只更新一个
./scripts/update.sh --dry-run       # 只打印计划
./scripts/update.sh /path/to/plugins
```

- 复制安装的插件会被覆盖重装（旧文件会被清掉，比如布局调整后残留的 `examples/`）；
  因此「更新」也是迁移脚本：旧单插件布局的安装会被替换成新布局；
- 软链接安装的插件指向仓库，本来就即时生效，脚本会跳过；
- 输出里会打印版本变化，例如 `更新 guard：0.2.0 -> 0.3.0`。

拉取新代码后再跑一次即可：

```bash
git pull --ff-only
./scripts/update.sh
```

### 卸载

```bash
./scripts/uninstall.sh --list          # 看每个插件装没装、是复制还是软链接
./scripts/uninstall.sh                 # 移除本仓库安装的全部插件
./scripts/uninstall.sh --only guard    # 只移除一个
./scripts/uninstall.sh --dry-run       # 只打印将要删除的内容
./scripts/uninstall.sh /path/to/plugins
```

脚本只会删除「`plugin.json` 的 `name` 与目录名一致」的目标；目录被别的插件占用时会
跳过并告警，不会误删。软链接安装只删链接本身，不动仓库。配置
（`${OPENHARNESS_CONFIG_DIR:-$HOME/.openharness}/guard-email.json`）与审计日志不会被删除。

也可以手动处理：在 `oh` 里 `/plugin uninstall <名称>`，或直接删除
`<插件根>/<插件名>`（用户级、ohmo 工作区、项目级的插件根见上一节）。

卸载 `guard-email` 不影响拦截，只是 `send_email` 与 `/guard-email:email` 不再可用。

## ask_image 插件

内置 `image_to_text` 回答「这张图是什么」，`ask_image` 回答「这张图里问的那个问题」：

| | `image_to_text`（内置工具） | `ask_image`（本插件） |
| --- | --- | --- |
| 输入 | 图片 + 通用描述 prompt | 图片 + 必填 `question`（可选 `context`） |
| 适用 | 需要完整描述 | 读报错文案、按钮标签、表格字段等定向信息 |
| 输出 | `[Image description via ...]` | `[Image answer via ...]` |

调用示例：

```json
{
  "image_path": "screenshots/ci-failure.png",
  "question": "构建失败的报错信息是什么？",
  "context": "这是 CI 日志截图，只输出报错那一行文本。"
}
```

- `question`：必填，越具体越好；图里没有相关信息时会明确说找不到，而不是编造。
- `context`：可选，补充背景或指定输出格式（例如「用 JSON 返回」）。
- 其余字段（`image_data`、`image_path`、`media_type`、`max_tokens`）与 `image_to_text` 一致。
- 只读工具，不写文件；未配置视觉模型时返回
  `ask_image failed: vision model is not configured...`。

依赖宿主已配置视觉模型：`vision.model` + `vision.api_key`，或环境变量
`OPENHARNESS_VISION_MODEL` / `OPENHARNESS_VISION_API_KEY`。

## guard-email 插件

独立插件，装不装都不影响 `guard` 的拦截判定。它提供 `send_email` 工具，把文本内容与
本地文件作为附件发送到指定邮箱，适合在长任务结束后发送报告、日志或构建产物；
通过 SMTP 发送，只依赖标准库。

| 扩展点 | 位置 | 说明 |
| --- | --- | --- |
| 工具 | `plugins/guard-email/tools/send_email.py` | `send_email`：通过 SMTP 发送文本与文件附件 |
| 库 | `plugins/guard-email/lib/mailer.py` | SMTP 配置、附件读取与邮件构造（标准库） |
| 命令 | `plugins/guard-email/commands/email.md` | `/guard-email:email`：查看配置、测试 SMTP、发送测试邮件 |
| 脚本 | `plugins/guard-email/scripts/guard-config.py` | SMTP 配置向导（`setup` / `show` / `test`） |

> 命令名随插件名确定为 `/guard-email:email`（原 `/guard:email`）。

**建议与 `guard` 一起安装。** 两者没有代码依赖，可以只装 `guard-email`，但差异在保护范围：

| 安装组合 | `send_email` 的保护 |
| --- | --- |
| `guard` + `guard-email` | 收件人白名单 + 体积上限，外加 `guard` 策略拦截 `.env`、SSH 私钥、云凭证等敏感附件与私钥正文 |
| 只装 `guard-email` | 只有收件人白名单（`OPENHARNESS_GUARD_EMAIL_ALLOWLIST`）与附件体积上限，**不检查附件是否敏感** |

`scripts/install.sh` 在只装 `guard-email` 时会提示这一点。邮件发往外部，属于不可撤销的
副作用，除非明确不需要，建议把 `guard` 一起装上。

### 配置 SMTP

`oh` 的 `/config set` 和 `oh config set` 只接受 OpenHarness 内置的 `Settings` 字段，插件也不能注册
`oh` 子命令；因此 `guard-email` 自带一个配置脚本，在终端里交互式写入配置（授权码用 `getpass`
隐藏输入，文件权限自动设为 600），并可直接测试 SMTP 登录：

```bash
# 默认安装路径
python3 ~/.openharness/plugins/guard-email/scripts/guard-config.py setup
python3 ~/.openharness/plugins/guard-email/scripts/guard-config.py show
python3 ~/.openharness/plugins/guard-email/scripts/guard-config.py test
python3 ~/.openharness/plugins/guard-email/scripts/guard-config.py test --send-to you@example.com
```

`setup` 会依次询问服务商（qq/163/126/gmail/outlook/custom）、主机、端口、加密方式、
账号和授权码。默认写入 `${OPENHARNESS_CONFIG_DIR:-$HOME/.openharness}/guard-email.json`。

也可以手动写文件（参考 `plugins/guard-email/examples/guard-email.example.json`）：

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
/guard-email:email                     # 查看邮箱配置状态（不显示密码）
/guard-email:email test                # 测试 SMTP 连接与登录
/guard-email:email send me@example.com # 发送测试邮件
/guard:audit                           # 对当前工作区做安全审计（guard 插件）
```

也可以在对话里完成配置——但授权码只通过**环境变量名**传递，不进入对话：

```bash
# 在启动 oh 的终端里先导出授权码
export OPENHARNESS_GUARD_SMTP_PASSWORD='授权码'
oh
```

```text
/guard-email:email setup host=smtp.qq.com port=465 security=ssl username=you@qq.com from=you@qq.com password_env=OPENHARNESS_GUARD_SMTP_PASSWORD
```

Agent 只会执行：

```bash
python3 <脚本> setup --host smtp.qq.com --port 465 --security ssl   --username you@qq.com --from you@qq.com   --password-env OPENHARNESS_GUARD_SMTP_PASSWORD
```

脚本在本地读取环境变量并写入 600 权限文件，模型和会话历史里只出现变量名。已有配置时
命令需要 `--force`；如果所有字段都已导出为 `OPENHARNESS_GUARD_SMTP_*`，也可以用
`/guard-email:email setup from_env`。

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
- 附件有总大小上限，且 `guard` 的内置策略 `email-sensitive-attachment` 会拦截 `.env`、
  SSH 私钥、云凭证等敏感文件；私钥内容出现在正文中也会被 `private-key-material` 拦截。
  这两条规则在 `guard` 里，没装 `guard` 时只剩 `send_email` 自身的白名单与大小上限。
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
| `OPENHARNESS_GUARD_POLICY` | 文件路径 | 内置 `plugins/guard/policies/default.json` | 自定义策略文件 |
| `OPENHARNESS_GUARD_ROOT` | 目录 | 见下节查找顺序 | hook 脚本定位插件根目录或插件根，优先于默认位置 |
| `OPENHARNESS_GUARD_STRICT` | `0` / `1` | `0` | `1` 时若找不到 hook 脚本则拒绝工具调用（fail-closed），而不是静默放行 |
| `OPENHARNESS_GUARD_AUDIT_LOG` | 文件路径 | `$OPENHARNESS_LOGS_DIR/guard-audit.jsonl` | 审计日志位置 |
| `OPENHARNESS_LOGS_DIR` | 目录 | `~/.openharness/logs` | OpenHarness 日志目录 |

钩子实际执行的是一个查找循环（`plugins/guard/hooks.json`）：

```bash
for d in "${OPENHARNESS_GUARD_ROOT:-}" \
         "${OPENHARNESS_CONFIG_DIR:-$HOME/.openharness}/plugins" \
         "${OHMO_WORKSPACE:-$HOME/.ohmo}/plugins" \
         "$PWD/.openharness/plugins"; do
  [ -n "$d" ] || continue
  for f in "$d/hooks/guard_hook.py" "$d"/*/hooks/guard_hook.py; do
    [ -f "$f" ] && exec python3 "$f"
  done
done
```

因此运行 OpenHarness 的环境需要有 `python3`。插件目录名不写死在 hook 里：只要
`<插件根>/<任意名称>/hooks/guard_hook.py` 存在就会被执行，新增插件不必改 guard 的
hook 配置；反过来，同一层若有多个副本按 glob 字典序取第一个。装到非默认插件根时
请设置 `OPENHARNESS_GUARD_ROOT`。

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

仓库根是插件集合根，每个插件自带完整的 `plugin.json` 与扩展目录：

```text
guard/                              # 仓库 = 插件集合
├── plugins/
│   ├── ask_image/                  # 插件：图片问答
│   │   ├── plugin.json             # OpenHarness 插件清单
│   │   └── tools/ask_image.py      # ask_image 工具（继承内置 image_to_text）
│   ├── guard/                      # 插件：安全护栏
│   │   ├── plugin.json             # OpenHarness 插件清单
│   │   ├── hooks.json              # pre/post tool use hook 配置
│   │   ├── mcp.json                # MCP 服务器（默认空）
│   │   ├── lib/guard_core.py       # 策略引擎（标准库）
│   │   ├── policies/default.json   # 内置规则（含邮箱相关规则）
│   │   ├── hooks/guard_hook.py     # pre_tool_use 拦截入口
│   │   ├── hooks/guard_audit.py    # post_tool_use 审计日志
│   │   ├── skills/guard-safety/    # 技能
│   │   ├── commands/audit.md       # /guard:audit
│   │   ├── agents/guard-reviewer.md# 子代理
│   │   └── tools/guard_check.py    # guard_check 工具
│   └── guard-email/                # 插件：邮箱通知（可单独安装）
│       ├── plugin.json             # OpenHarness 插件清单
│       ├── lib/mailer.py           # SMTP 发送与附件处理（标准库）
│       ├── tools/send_email.py     # send_email 工具
│       ├── commands/email.md       # /guard-email:email
│       ├── scripts/guard-config.py # SMTP 配置向导
│       └── examples/               # 配置示例
├── scripts/
│   ├── install.sh                  # 安装（遍历 plugins/*，支持 --only / --link / --force）
│   ├── update.sh                   # 重装已安装的插件（= 更新，兼旧布局迁移）
│   ├── uninstall.sh                # 移除本仓库安装的插件（只删自己装的）
│   └── common.sh                   # 插件发现与路径工具（三个脚本共用）
└── tests/                          # 跨插件测试
```

新增插件：建 `plugins/<名称>/`，放一份 `name` 与目录名一致的 `plugin.json`，
`install.sh`、`--list` 与布局测试会自动纳入，无需改脚本。插件之间不要互相 import，
也不要引用别的插件的路径——每个插件都要能单独安装、单独启用。

## 开发

```bash
python3 -m unittest discover -s tests -v
```

约定：

- 新增规则必须同时补测试，并确认不会误伤常见开发命令（见 `tests/test_guard_core.py`）。
- 规则 ID 用 kebab-case，`reason` 说明“为什么”和“怎么做更安全”。
- `plugins/guard/lib/guard_core.py` 与 `plugins/guard-email/lib/mailer.py` 只使用标准库，
  保证 hook 与工具可以在最小 Python 环境中运行。
- 邮箱相关测试使用假 SMTP 客户端，不依赖真实网络；不要把真实密码写入仓库。
- `guard` 只用标准库；`ask_image` 依赖宿主的 `openharness`，相关测试在缺包时整体跳过
  （`tests/test_ask_image.py`）。

## 许可证

[GPL-3.0](LICENSE)。
