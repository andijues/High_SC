"""Frozen Windows launcher: embedded server, browser workbench, system tray."""
import argparse
import ctypes
import hashlib
import json
import logging
import multiprocessing
import os
import socket
import sys
import threading
import time
import urllib.request
import webbrowser

from highsc.paths import DATA, ROOT


def health(port):
    try:
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(f'http://127.0.0.1:{port}/api/health',timeout=1) as response:return json.load(response)
    except Exception:return None


def main():
    multiprocessing.freeze_support()
    parser=argparse.ArgumentParser()
    parser.add_argument('--no-browser',action='store_true')
    parser.add_argument('--no-tray',action='store_true')
    parser.add_argument('--port',type=int)
    args=parser.parse_args()
    DATA.mkdir(parents=True,exist_ok=True)
    logs=DATA/'logs';logs.mkdir(exist_ok=True)
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s',handlers=[logging.FileHandler(logs/'server.log',encoding='utf-8')])
    runtime=DATA/'runtime.json'
    identity=hashlib.sha256(str(DATA).encode()).hexdigest()[:16]
    kernel=ctypes.windll.kernel32
    kernel.CreateMutexW.restype=ctypes.c_void_p
    mutex=kernel.CreateMutexW(None,False,'Local\\High_SC_'+identity)
    duplicate=kernel.GetLastError()==183
    if not mutex:raise OSError('无法创建 High_SC 进程锁')
    if duplicate:
        for _ in range(60):
            try:
                saved=json.loads(runtime.read_text(encoding='utf-8'));current=health(saved['port'])
                if current and current.get('instance')==identity and current['pid']==saved['pid']:
                    if not args.no_browser:webbrowser.open(f"http://127.0.0.1:{saved['port']}")
                    return
            except (OSError,ValueError,KeyError):pass
            time.sleep(.5)
        raise RuntimeError('High_SC 正在启动或退出，请稍后重试')
    port=None
    for candidate in ([args.port] if args.port else range(8693,8724)):
        with socket.socket() as sock:
            try:sock.bind(('127.0.0.1',candidate));port=candidate;break
            except OSError:continue
    if port is None:raise RuntimeError('本机端口被占用，请退出其他 High_SC 实例后重试')
    import uvicorn
    import highsc.server
    server=uvicorn.Server(uvicorn.Config(highsc.server.app,host='127.0.0.1',port=port,log_config=None,access_log=False))
    runtime.write_text(json.dumps({'pid':os.getpid(),'port':port,'instance':identity}),encoding='utf-8')
    if args.no_tray:
        server.run();return
    worker=threading.Thread(target=server.run,daemon=True,name='highsc-server');worker.start()
    for _ in range(120):
        if health(port):break
        if not worker.is_alive():raise RuntimeError('服务启动失败，请查看数据文件夹中的 logs/server.log')
        time.sleep(.25)
    else:raise RuntimeError('启动超时，请稍后重试')
    url=f'http://127.0.0.1:{port}'
    if not args.no_browser:webbrowser.open(url)
    import pystray
    from PIL import Image
    from highsc import __version__, output
    from highsc.jobs import ACTIVE
    def open_workbench(icon=None,item=None):webbrowser.open(url)
    def open_exports(icon,item):
        folder=output.directory_path(output.settings()['directory']);folder.mkdir(parents=True,exist_ok=True);os.startfile(str(folder))
    def quit_app(icon,item):
        if ACTIVE and ctypes.windll.user32.MessageBoxW(None,'退出会停止当前生成，已完成段落会保留。确认退出？','High_SC',0x24)!=6:return
        for event in list(ACTIVE.values()):event.set()
        server.should_exit=True;icon.stop()
    icon=pystray.Icon('High_SC',Image.open(ROOT/'static/brand/icon.png'),f'High_SC {__version__}',menu=pystray.Menu(
        pystray.MenuItem('打开工作台',open_workbench,default=True),
        pystray.MenuItem('打开 HTML 保存目录',open_exports),
        pystray.MenuItem('打开数据与日志目录',lambda icon,item:os.startfile(str(DATA))),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem('退出 High_SC',quit_app)))
    def ready(icon):
        icon.visible=True;highsc.server.app.state.tray_ready=True
        logging.info('High_SC system tray ready')
    icon.run(setup=ready);server.should_exit=True;worker.join(timeout=3)
    if ACTIVE:os._exit(0)


if __name__=='__main__':
    try:main()
    except Exception as exc:
        DATA.mkdir(parents=True,exist_ok=True)
        (DATA/'launch-error.log').write_text(str(exc),encoding='utf-8')
        if '--no-tray' not in sys.argv:ctypes.windll.user32.MessageBoxW(None,str(exc),'High_SC 启动提示',0x10)
        raise SystemExit(1)
