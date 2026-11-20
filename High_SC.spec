# Build on Windows: python -m PyInstaller --noconfirm High_SC.spec
from PyInstaller.utils.hooks import collect_submodules, collect_all, copy_metadata
from PyInstaller.utils.win32.versioninfo import VSVersionInfo, FixedFileInfo, StringFileInfo, StringTable, StringStruct, VarFileInfo, VarStruct

pdf_data,pdf_bins,pdf_hidden=collect_all('pymupdf')
resources=[('static/app.css','static'),('static/app.js','static'),('static/index.html','static'),('static/example-preview.png','static'),('static/fonts','static/fonts'),('static/brand','static/brand'),('templates','templates'),('examples/demo.html','examples'),('LICENSE','.'),('THIRD_PARTY_NOTICES.md','.')]
a=Analysis(['windows_entry.py'],pathex=[],binaries=pdf_bins,datas=resources+[('build/licenses','licenses')]+pdf_data+copy_metadata('python-multipart'),hiddenimports=['highsc.server','pystray._win32']+collect_submodules('uvicorn')+pdf_hidden,hookspath=[],runtime_hooks=[],excludes=['tkinter','matplotlib','pytest','IPython'],noarchive=False)
pyz=PYZ(a.pure)
version=VSVersionInfo(ffi=FixedFileInfo(filevers=(1,1,0,0),prodvers=(1,1,0,0),mask=0x3f,flags=0,OS=0x40004,fileType=1,subtype=0,date=(0,0)),kids=[StringFileInfo([StringTable('040904B0',[StringStruct('CompanyName','High_SC contributors'),StringStruct('FileDescription','High_SC - Academic Reading Workbench'),StringStruct('FileVersion','1.1.0'),StringStruct('ProductName','High_SC'),StringStruct('ProductVersion','1.1.0'),StringStruct('LegalCopyright','Copyright 2026 High_SC contributors. AGPL-3.0.')])]),VarFileInfo([VarStruct('Translation',[1033,1200])])])
exe=EXE(pyz,a.scripts,a.binaries,a.datas,[],name='High_SC',debug=False,bootloader_ignore_signals=False,strip=False,upx=False,console=False,disable_windowed_traceback=False,icon='static/brand/High_SC.ico',version=version)
