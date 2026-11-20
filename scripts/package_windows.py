"""Build the self-contained Windows application and its portable ZIP."""
import importlib.metadata as metadata
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from highsc import __version__


def build():
    if os.name!='nt':raise SystemExit('Build the Windows executable on Windows.')
    os.chdir(ROOT)
    subprocess.run([sys.executable,'scripts/build_brand.py'],check=True)
    licenses=ROOT/'build/licenses';licenses.mkdir(parents=True,exist_ok=True)
    packages=[line.split('==')[0] for line in (ROOT/'requirements.lock.txt').read_text().splitlines() if '==' in line]+['pillow','pystray','pyinstaller']
    for name in packages:
        dist=metadata.distribution(name)
        for item in dist.files or []:
            text=str(item).lower()
            if '.dist-info/' in text and any(x in Path(text).name for x in ('license','copying','notice')):
                dest=licenses/name/Path(item).name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(dist.locate_file(item),dest)
    python_license=Path(sys.base_prefix)/'LICENSE.txt'
    if not python_license.exists():raise RuntimeError('Python runtime license was not found')
    shutil.copy2(python_license,licenses/'Python-LICENSE.txt')
    subprocess.run([sys.executable,'-m','PyInstaller','--noconfirm','High_SC.spec'],check=True)
    dest=ROOT/'dist';name=f'High_SC-v{__version__}-Windows-x64.exe';shutil.copy2(dest/'High_SC.exe',dest/name)
    readme=f'''High_SC {__version__} - Windows x64

双击 {name} 即可启动，无需安装 Python。程序会打开浏览器工作台，并在系统托盘显示 High_SC 图标。

1. 在“模型设置”中填写自己的 API；也可使用本机已经安装并登录的官方 Codex CLI。
2. 在“保存设置”中选择 HTML 输出文件夹并保存，可开启自动保存。
3. 导入英文 PDF，完成后预览、保存到指定目录或使用浏览器下载。
4. 右键系统托盘图标可打开目录或退出程序；关闭浏览器不会退出后台服务。

数据与日志：%LOCALAPPDATA%\\High_SC\\
默认 HTML 目录：用户主目录下 Downloads\\High_SC，可在软件内更改。
升级时更换 EXE 即可，数据保存在独立目录中。本包不包含模型额度、密钥、Codex CLI 或可选 OCR 的 Tesseract。

面向 Windows 10/11 x64，本次验证使用 Windows 11。EXE 未进行数字签名。
源码与说明：https://github.com/andijues/High_SC
软件采用 AGPL v3；字体、Python 及其他依赖保留各自许可。所有许可见 licenses/、LICENSE 与 THIRD_PARTY_NOTICES.md。
'''
    guide=dest/'Windows-README.txt';guide.write_text(readme,encoding='utf-8')
    with zipfile.ZipFile(dest/f'High_SC-v{__version__}-Windows-x64.zip','w',zipfile.ZIP_DEFLATED) as archive:
        for source,target in [(dest/name,name),(guide,'使用说明.txt'),(ROOT/'LICENSE','LICENSE'),(ROOT/'THIRD_PARTY_NOTICES.md','THIRD_PARTY_NOTICES.md')]:archive.write(source,'High_SC/'+target)
        for source in sorted(licenses.rglob('*')):
            if source.is_file():archive.write(source,'High_SC/licenses/'+source.relative_to(licenses).as_posix())
        for name in ['LICENSES.txt','IBMPlexSans-OFL.txt']:archive.write(ROOT/'static/fonts'/name,'High_SC/licenses/fonts/'+name)
    print('Built Windows executable and portable ZIP, including third-party licenses.')


if __name__=='__main__':build()
