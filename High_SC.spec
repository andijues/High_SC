# Build on Windows (prepares bundled licenses): python scripts/package_windows.py
from PyInstaller.utils.hooks import collect_submodules, collect_all, copy_metadata
from PyInstaller.utils.win32.versioninfo import VSVersionInfo, FixedFileInfo, StringFileInfo, StringTable, StringStruct, VarFileInfo, VarStruct
from highsc import __version__

pdf_data,pdf_bins,pdf_hidden=collect_all('pymupdf')
resources=[('static/app.css','static'),('static/app.js','static'),('static/index.html','static'),('static/example-preview.png','static'),('static/fonts','static/fonts'),('static/brand','static/brand'),('templates','templates'),('examples/demo.html','examples'),('LICENSE','.'),('THIRD_PARTY_NOTICES.md','.')]
a=Analysis(['windows_entry.py'],pathex=[],binaries=pdf_bins,datas=resources+[('build/licenses','licenses')]+pdf_data+copy_metadata('python-multipart'),hiddenimports=['highsc.server','pystray._win32']+collect_submodules('uvicorn')+pdf_hidden,hookspath=[],runtime_hooks=[],excludes=['tkinter','matplotlib','pytest','IPython'],noarchive=False)
pyz=PYZ(a.pure)
version_parts=tuple(int(n) for n in __version__.split('.'))+(0,)
version=VSVersionInfo(ffi=FixedFileInfo(filevers=version_parts,prodvers=version_parts,mask=0x3f,flags=0,OS=0x40004,fileType=1,subtype=0,date=(0,0)),kids=[StringFileInfo([StringTable('040904B0',[StringStruct('CompanyName','High_SC contributors'),StringStruct('FileDescription','High_SC - Academic Reading Workbench'),StringStruct('FileVersion',__version__),StringStruct('ProductName','High_SC'),StringStruct('ProductVersion',__version__),StringStruct('LegalCopyright','Copyright 2026 High_SC contributors. AGPL-3.0.')])]),VarFileInfo([VarStruct('Translation',[1033,1200])])])
exe=EXE(pyz,a.scripts,a.binaries,a.datas,[],name='High_SC',debug=False,bootloader_ignore_signals=False,strip=False,upx=False,console=False,disable_windowed_traceback=False,icon='static/brand/High_SC.ico',version=version)
