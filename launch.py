from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT=Path(__file__).resolve().parent
RUNTIME=ROOT/'data/runtime.json'


def health(port):
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/health',timeout=1) as r:
            result=json.load(r)
            return result if result.get('app')=='High_SC' else None
    except Exception:return None


def launch(open_browser=True):
    os.chdir(ROOT)
    (ROOT/'data').mkdir(exist_ok=True);(ROOT/'logs').mkdir(exist_ok=True)
    if RUNTIME.exists():
        try:
            stored=json.loads(RUNTIME.read_text(encoding='utf-8'));current=health(stored['port'])
            if current and current['pid']==stored['pid']:
                url=f"http://127.0.0.1:{stored['port']}"
                if open_browser:webbrowser.open(url)
                return url
        except (KeyError,ValueError):pass
    port=None
    for candidate in range(8693,8724):
        with socket.socket() as sock:
            try:sock.bind(('127.0.0.1',candidate));port=candidate;break
            except OSError:continue
    if port is None:raise RuntimeError('8693-8723 端口均被占用，请关闭其他程序后重试')
    python=sys.executable
    if python.lower().endswith('pythonw.exe'):python=str(Path(python).with_name('python.exe'))
    log=(ROOT/'logs/server.log').open('a',encoding='utf-8')
    process=subprocess.Popen([python,str(ROOT/'run.py'),'--port',str(port)],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    RUNTIME.write_text(json.dumps({'pid':process.pid,'port':port},indent=2),encoding='utf-8')
    for _ in range(120):
        if process.poll() is not None:raise RuntimeError('本机服务启动失败，请打开 logs/server.log 查看原因，或运行“安装或修复.cmd”')
        running=health(port)
        if running:
            # On Windows a venv redirector may spawn the actual Python process.
            RUNTIME.write_text(json.dumps({'pid':running['pid'],'launcher_pid':process.pid,'port':port},indent=2),encoding='utf-8')
            url=f'http://127.0.0.1:{port}'
            if open_browser:webbrowser.open(url)
            return url
        time.sleep(.25)
    raise RuntimeError('服务启动时间较长，请稍后重试。日志位于 logs/server.log')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--no-browser',action='store_true');args=parser.parse_args()
    try:
        url=launch(not args.no_browser)
        if sys.stdout:print(url)
    except Exception as exc:
        (ROOT/'logs').mkdir(exist_ok=True)
        (ROOT/'logs/launch-error.log').write_text(str(exc),encoding='utf-8')
        if os.name=='nt':
            import ctypes
            ctypes.windll.user32.MessageBoxW(None,str(exc),'High_SC 启动提示',0x10)
        elif sys.stderr:print(str(exc),file=sys.stderr)
        sys.exit(1)
