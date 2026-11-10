---
description: 查看 guard 邮箱配置、测试 SMTP，或发送测试邮件
argument-hint: "[status|test|send <邮箱>]"
when_to_use: 首次配置后验证、需要发送测试邮件、或排查发信失败时。
---

处理 guard 的邮箱通知。参数：$ARGUMENTS（为空时按 status 处理）。

先定位脚本，使用第一个存在的路径：

- `$OPENHARNESS_GUARD_ROOT/scripts/guard-config.py`
- `${OPENHARNESS_CONFIG_DIR:-$HOME/.openharness}/plugins/guard/scripts/guard-config.py`
- `.openharness/plugins/guard/scripts/guard-config.py`

执行规则：

1. **不要向用户索要 SMTP 授权码**，也不要把授权码写进对话、命令参数或任何文件。
2. `status`：运行 `python3 <脚本> show`，向用户转述配置状态（host、port、security、from、
   密码是否已设置、哪些环境变量在覆盖）。不要读取或输出密码字段。
3. `test`：运行 `python3 <脚本> test`，报告连接与登录结果；失败时按“授权码错误 /
   端口与加密方式不匹配 / 网络或防火墙 / 服务商未开启 SMTP”给出排查建议。
4. `send <邮箱>`：先运行 `show` 确认已配置，再用 `send_email` 工具发送一封
   主题为「guard 邮件测试」的短邮件；未配置时提示用户先完成 setup。
5. `setup ...`：解析 `host=... port=... security=... username=... from=... password_env=<变量名>`，
   然后运行（已有配置时加 `--force`）：
   ```bash
   python3 <脚本> setup --host HOST --port PORT --security SSL|STARTTLS|NONE \
     --username USER --from FROM --password-env VAR [--force]
   ```
   只接受 `password_env=<变量名>`：脚本从环境变量读取授权码，模型只看到变量名，
   禁止运行 `env`、`printenv`、`echo $VAR` 等会显示授权码的命令，
   绝不把授权码写进命令、参数或输出。用户直接给出明文授权码时必须拒绝，并解释原因。
   用户已在启动 `oh` 前导出全部 `OPENHARNESS_GUARD_SMTP_*` 时，可改用
   `python3 <脚本> setup --from-env [--force]`。
6. 如果用户没有可用的环境变量：让其在启动 `oh` 的终端执行
   `python3 <脚本> setup` 交互配置（getpass 隐藏输入、权限 600），
   或先 `export OPENHARNESS_GUARD_SMTP_PASSWORD='授权码'` 后重新启动 `oh`。
