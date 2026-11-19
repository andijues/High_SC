# 参与开发

先阅读 README，建立 Python 3.11+ 虚拟环境并安装 `requirements.lock.txt`，提交前运行 `python -m unittest discover -s tests -v`。前端变更请同时检查桌面与窄屏，参考 `docs/testing.md`。

问题报告请注明操作系统、Python / Codex 版本、所选 API 协议、预期与实际行为，并提供可重复的最小示例。可用 `examples/source.pdf` 复现流程。请删除密钥、认证头、个人论文与日志中的敏感内容。

新增渠道请说明其协议差异并提供模拟测试。不要让失败自动切换到其他账号、模型或服务；不要把文档内容变成系统指令。涉及 API 参数时，以渠道当前官方文档为依据。

提交的代码采用仓库的 AGPL v3 许可。请不要提交 `data/`、`.venv/`、第三方未授权论文或登录凭据。
