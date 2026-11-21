# 测试与验证边界

## 核心测试

```bash
python -m pip install -r requirements.lock.txt
python -m unittest discover -s tests -v
```

本地模拟 HTTP 服务检验 Chat Completions、Responses、Messages 的请求和响应、路由拼接、认证头、参数切换和错误处理。集成测试覆盖上传、论证骨架、逐段批注、导出、人工编辑、暂停和断点继续。Codex 流程使用模拟子进程，验证参数、环境隔离和取消，不消耗模型额度。

有一项可选解析回归测试针对开发时的特定长篇论文。该论文不随仓库分发；默认跳过。仅在持有相应材料时，将 `HIGHSC_REGRESSION_PDF` 设置为该原文的本地路径再运行。普通用户无需配置。

## 浏览器检查

需要 Node.js 20+。在两个终端分别执行：

```bash
# 终端一：隔离的测试服务，数据仅写入 tests/artifacts/
python tests/serve_ui_test.py
```

```bash
# 终端二
npm install
npx playwright install chromium
npm run test:browser
```

测试使用项目自制 PDF，通过模拟模型完成导入与导出，检查桌面/手机布局、设置兼容字段、控制台错误和示例页面。可用 `HIGHSC_BROWSER_CHANNEL=msedge` 指定本机浏览器；默认 Playwright Chromium。截图和结果写入忽略的 `tests/artifacts/browser/`。

## 实际验证范围

- Windows 本机：已验证官方 Codex 的 ChatGPT 登录、`gpt-6.1-sol` / `xhigh` 短调用及真实论文的少量段落分析。
- 完整论文工程流程：曾用本地模拟接口验证；模拟输出不代表真实翻译质量。
- 第三方渠道：使用协议模拟测试，没有逐一购买厂商账号进行实测。
- CI：运行 Windows / Ubuntu 的核心测试；不执行付费 API 或真实 Codex 登录。

测试通过表示对应功能流程符合预期，不代表任意 PDF 的解析或任意模型的学术判断都正确。

## Windows EXE 验证

构建后执行 `python tests/smoke_windows_exe.py dist/High_SC.exe`。测试从启动环境的 PATH 中移除 Python，用实际 EXE 验证生成与自选目录、文件不覆盖、中文路径、重启持久化、单实例和托盘。完整构建方式见 [Windows 指南](windows.md)。

这检验内置运行环境和核心流程，不代表已在所有 Windows 版本、杀毒软件或硬件上验证。

EXE 冒烟测试实际调用 Windows 文件夹窗口，自动选择中文目录并取消一次；测试只操作该测试 EXE 自己创建的窗口。它与浏览器模拟测试分开，能发现 ctypes 参数、窗口创建和取消返回值的问题。

1.2.0 增加 `test_optimizations.py`，覆盖缓存与身份隔离、合格段落保留、定向重试、自适应批量、章节上下文与业务用量记录。实际 EXE 还验证相同 PDF 以新任务再次导入后，模型请求为零且批注一致。真实 Codex 小样本和工程模拟基准分别说明，见 [优化说明](optimization.md)。
