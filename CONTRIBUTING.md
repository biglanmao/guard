# Contributing

欢迎提交规则、文档与测试。

## 开发流程

```bash
python3 -m unittest discover -s tests -v
```

- 只使用 Python 标准库实现 `lib/` 与 `hooks/`，保证最小运行环境可用。
- 新增规则时：
  1. 在 `policies/default.json` 追加规则（ID 用 kebab-case）；
  2. 在 `tests/test_guard_core.py` 覆盖“命中”和“不命中”两类用例；
  3. 确认不会误伤常见开发命令。
- 修改 hook 行为时同步更新 `README.md` 与 `AGENTS.md`。

## 提交

- 一个提交只做一件事，提交信息说明动机与影响。
- 不要提交密钥、真实审计日志或本机绝对路径。

## 许可证

提交即表示同意以 [GPL-3.0](LICENSE) 发布。
