"""User-controlled HTML exports; existing files are never overwritten."""
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from . import storage


def default_directory():
    return str(Path(os.environ.get('HIGHSC_OUTPUT_DIR') or Path.home() / 'Downloads' / 'High_SC').expanduser().resolve())


def settings():
    return {'directory':default_directory(), 'auto_save':True, **storage.read_json(storage.DATA / 'output-settings.json', {})}


def directory_path(value):
    path=Path(value.strip()).expanduser()
    if not value.strip() or not path.is_absolute():raise ValueError('请填写完整的绝对目录路径，或使用“选择文件夹”')
    if path.exists() and not path.is_dir():raise ValueError('保存路径指向文件，请选择一个文件夹')
    return path.resolve()


def save_settings(directory, auto_save):
    path=directory_path(directory)
    try:
        path.mkdir(parents=True,exist_ok=True)
        # Check permission without modifying existing user files.
        import tempfile
        with tempfile.TemporaryFile(dir=path):pass
    except OSError as exc:raise ValueError('该目录无法写入，请选择其他文件夹：'+str(exc)) from None
    result={'directory':str(path),'auto_save':auto_save}
    storage.atomic_json(storage.DATA / 'output-settings.json',result)
    return result


def save_html(source:Path, title:str, paper_id:str, directory=None, automatic=False):
    cfg=settings()
    if automatic and not cfg['auto_save']:return None
    target=directory_path(directory or cfg['directory'])
    target.mkdir(parents=True,exist_ok=True)
    title=re.sub(r'[<>:"/\\|?*\x00-\x1f]','_',title).strip(' .')[:85] or '论文'
    stem=f'{title}_{paper_id[:8]}_双栏批注'
    with storage.LOCK:
        for i in range(1,10001):
            dest=target / (stem+(f' ({i})' if i>1 else '')+'.html')
            try:stream=dest.open('xb')
            except FileExistsError:continue
            try:
                with stream, source.open('rb') as src:shutil.copyfileobj(src,stream)
            except BaseException:
                dest.unlink(missing_ok=True)
                raise
            return str(dest)
    raise ValueError('同名文件过多，请选择其他目录')


def try_auto_save(source, title, paper_id):
    try:return {'saved_path':save_html(source,title,paper_id,automatic=True) or '', 'save_error':''}
    except (OSError,ValueError) as exc:return {'saved_path':'','save_error':str(exc)}


def choose_folder(initial=''):
    if os.name!='nt':raise ValueError('此平台请直接填写完整目录路径')
    from .windows import choose_folder as dialog
    try:return dialog(initial)
    except Exception:
        import logging
        logging.getLogger(__name__).exception('Windows folder picker failed')
        raise ValueError('系统文件夹窗口未能打开。请先在“保存文件夹”中手动填写完整路径并保存；详细错误已记录到本机日志。') from None


def open_directory(path):
    folder=directory_path(str(path))
    if not folder.is_dir():raise ValueError('该文件夹尚不存在，请先保存文件')
    if os.name=='nt':os.startfile(str(folder))
    else:subprocess.Popen(['open' if sys.platform=='darwin' else 'xdg-open',str(folder)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
