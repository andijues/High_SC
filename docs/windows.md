# Windows EXE 使用与构建

## 直接运行

从仓库 Release 下载 `High_SC-v1.2.0-Windows-x64.exe`，双击运行，无需安装 Python。也可下载同名 ZIP，其中附有使用说明和第三方许可证。

启动时会解包内置运行环境，打开浏览器工作台，并显示系统托盘图标。首次启动可能需要等待数秒。关闭浏览器不停止后台；右键托盘图标可重新打开工作台、打开 HTML 目录、查看数据与日志或退出软件。再次双击 EXE 会复用当前实例。

软件面向 Windows 10/11 x64，已在 Windows 11 验证。当前 EXE 未做数字签名，发布者显示未知；可核对 Release 中的 SHA-256 校验值或自行从源码构建。

普通 API 模式只需填写自己的接口配置并联网。Codex 模式仍需本机已安装并登录官方 Codex CLI；可选 OCR 仍需 Tesseract。这些组件和账号额度不随 EXE 分发。

## 自选 HTML 保存目录

1. 打开顶部“保存设置”。
2. 点击“选择文件夹”，或填写绝对路径；支持中文和空格。
3. 选择是否“生成完成或更新 HTML 后，自动保存到此目录”。
4. 点击“保存设置”，程序会创建目录并检查写入权限。

也可在论文页面点击“保存到指定目录”。同名文件会加编号，已有文件和人工修改内容不会被覆盖。保存失败时，内部 HTML 仍保留，可修改目录后重新保存。

“浏览器下载”仍由浏览器决定位置；保存设置不会改变浏览器自身的下载选项。默认直接保存目录为用户主目录下的 `Downloads/High_SC`，可单独修改。

## 数据、升级与备份

EXE 的设置、论文、缓存与日志保存在 `%LOCALAPPDATA%/High_SC/`。它们独立于 EXE 所在目录和临时解包目录。升级只需退出旧版并替换 EXE；请备份数据目录以保留任务。

源码版继续使用项目下的 `data/`。两种运行方式的数据目录相互独立。需要迁移时先退出两种程序，备份后复制所需数据；Windows 密钥加密绑定当前账户，换账户应重新输入密钥。

## 从源码构建

在 Windows x64、Python 3.11+ 环境运行：

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.venv\Scripts\python.exe scripts\package_windows.py
.venv\Scripts\python.exe tests\smoke_windows_exe.py dist\High_SC.exe
```

构建脚本生成原创 Logo 和 ICO、收集依赖许可证，再使用 `High_SC.spec` 生成单个 EXE 和附说明的 ZIP。依赖安装和构建需要网络；运行已打包 EXE 不需要 Python 或 pip。

实际 EXE 测试会从 PATH 中移除 Python，检查中文/空格目录启动、PDF 导入与完整模拟生成、自选目录保存、同名保护、重启持久化、单实例和托盘图标。测试使用本地模拟模型，不访问付费 API。

图标原始几何见 `static/brand/icon.svg`；PNG、ICO 和字标由 `scripts/build_brand.py` 生成。配色沿用论文工作台的海军蓝、米白和金色，双页对应原文/批注，金色线与节点对应高亮和论证链。
