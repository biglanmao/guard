---
name: guard-safety
description: >
  OpenHarness 安全护栏（guard）的使用与审计指南。当需要评估某次工具调用是否
  安全、解释 guard 的拦截原因、调整或扩展护栏规则，或对仓库做一次安全风险
  审计时使用。
---

# guard 安全护栏

guard 是 OpenHarness 的扩展插件，在每次工具调用前执行 `pre_tool_use` hook，
命中策略时阻止调用并给出原因。它不替代人工判断，目标是拦住代价高、不可逆、
明显越权的操作。

## 工作流程

1. 先判断操作是否可逆、影响范围有多大；可逆且局部的操作直接执行。
2. 不确定时调用 `guard_check` 工具预演：
   ```json
   {"tool_name": "bash", "tool_input": {"command": "rm -rf build"}}
   ```
3. 若 guard 拦截了调用，不要绕过（例如改写命令、拆分命令、切换工具）后用等价
   方式继续执行；应当：
   - 向用户说明命中的规则和风险；
   - 给出更安全的替代方案；
   - 只有在用户明确确认后才执行等价的高风险操作。

## 规则来源

- 内置策略：`plugins/guard/policies/default.json`（也可看当前安装目录下的 `policies/default.json`）
- 自定义策略：设置 `OPENHARNESS_GUARD_POLICY` 指向自己的 JSON 文件
- 模式：`OPENHARNESS_GUARD_MODE=off|audit|enforce`，默认 `enforce`

## 审计清单

对仓库做安全审计时，按以下顺序检查：

1. **命令执行**：`curl | sh`、`rm -rf` 根目录/家目录、`dd of=/dev/*`、`mkfs`、
   根目录 `chmod 777`、强制推送。
2. **凭据暴露**：`.env`、`~/.ssh/id_*`、`~/.aws/credentials`、`.git-credentials`、
   `.netrc`、`.kube/config`，以及私钥内容是否被写入文件或日志。
3. **网络与依赖**：不可信源安装脚本、直接执行远程代码、跳过校验和的下载。
4. **权限边界**：是否写入仓库之外、是否修改系统级配置、是否触碰生产环境。

## 邮箱外发（需另装 guard-email 插件）

`send_email` 工具与 `/guard-email:email` 命令来自 `guard-email` 插件；没装时本插件只剩
下列判定规则（规则按工具名匹配，未装则不命中）。使用 `send_email` 发送报告或附件前：

- 确认收件人地址，优先配合 `OPENHARNESS_GUARD_EMAIL_ALLOWLIST` 使用。
- 不要附加 `.env`、SSH 私钥、云凭证等文件（会被 `email-sensitive-attachment` 拦截）。
- 不要把密钥、令牌粘贴到正文；私钥内容会被 `private-key-material` 拦截。
- 附件尽量精简，避免把整份日志或大型构建产物发到外部邮箱。

## 扩展规则

在 `policies/default.json` 的 `rules` 数组追加对象：

```json
{
  "id": "my-rule",
  "description": "规则说明",
  "action": "deny",
  "tools": ["bash"],
  "fields": ["command"],
  "regex": "\\b危险命令\\b",
  "reason": "面向用户的拦截原因"
}
```

新增规则必须同时添加测试，并确认不会误伤常见开发命令。
