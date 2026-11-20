"""Integration smoke test for the actual frozen executable, not Python source."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import time
import urllib.request

import httpx
from mock_provider import MockProvider
from native_folder_dialog import call_with_dialog_action
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from highsc import __version__

ROOT=Path(__file__).resolve().parents[1]


def run(executable):
    artifact=ROOT/'tests/artifacts'/('exe-'+str(time.time_ns()))
    artifact.mkdir(parents=True)
    binary=artifact/'中文 路径'/'High_SC.exe';binary.parent.mkdir();shutil.copy2(executable,binary)
    data=artifact/'user data';dest=artifact/'指定 导出目录'
    env={**os.environ,'HIGHSC_DATA_DIR':str(data),'HIGHSC_OUTPUT_DIR':str(dest),'NO_PROXY':'127.0.0.1,localhost','PATH':os.pathsep.join([str(Path(os.environ['WINDIR'])/'System32'),os.environ['WINDIR']])}
    env.pop('HIGHSC_ROOT',None)
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    client=httpx.Client(base_url=f'http://127.0.0.1:{port}',trust_env=False,timeout=10)
    process=None;pid=None
    def start(tray=False):
        nonlocal process,pid
        process=subprocess.Popen([str(binary),'--no-browser','--port',str(port)]+([] if tray else ['--no-tray']),env=env,creationflags=subprocess.CREATE_NO_WINDOW)
        end=time.monotonic()+75
        while time.monotonic()<end:
            try:
                result=client.get('/api/health').json()
                if result.get('version')==__version__ and (not tray or result.get('tray_ready')):pid=result['pid'];return result
            except (httpx.HTTPError,ValueError):pass
            if process.poll() is not None:raise AssertionError('EXE exited early: '+str(process.returncode))
            time.sleep(.25)
        raise AssertionError('Frozen server did not become ready; inspect '+str(data))
    def stop():
        nonlocal process,pid
        if pid:subprocess.run(['taskkill','/PID',str(pid),'/T','/F'],capture_output=True)
        if process:
            try:process.wait(timeout=15)
            except subprocess.TimeoutExpired:process.kill()
        process=None;pid=None;time.sleep(.3)
    mock=MockProvider()
    try:
        start()
        page=client.get('/').text;token=re.search(r'name="highsc-token" content="([^"]+)',page)[1];headers={'X-HighSC-Token':token}
        assert 'files-template' in page
        assert client.get('/static/brand/High_SC.ico').status_code==200
        assert client.get('/example').status_code==200
        dest.mkdir(parents=True,exist_ok=True)
        selected=call_with_dialog_action(lambda:client.post('/api/output/choose-folder',json={'initial':str(dest)},headers=headers,timeout=30),pid)
        selected.raise_for_status();assert Path(selected.json()['directory']).resolve()==dest.resolve()
        cancelled=call_with_dialog_action(lambda:client.post('/api/output/choose-folder',json={'initial':str(dest)},headers=headers,timeout=30),pid,cancel=True)
        cancelled.raise_for_status();assert cancelled.json()['directory'] is None
        r=client.put('/api/settings',json={'base_url':mock.url,'model':'mock-reader','api_style':'chat','api_key':'exe-smoke-test-key','timeout':30,'retries':0,'batch_size':2},headers=headers);r.raise_for_status()
        r=client.put('/api/output-settings',json={'directory':str(dest),'auto_save':True},headers=headers);r.raise_for_status()
        with (ROOT/'examples/source.pdf').open('rb') as source:r=client.post('/api/papers',files={'file':('original-demo.pdf',source,'application/pdf')},data={'auto_generate':'false'},headers=headers)
        r.raise_for_status();paper=r.json()['id']
        client.post(f'/api/papers/{paper}/generate',json={},headers=headers).raise_for_status()
        end=time.monotonic()+60
        while time.monotonic()<end:
            doc=client.get('/api/papers/'+paper).json()
            if doc['meta']['state']=='failed':raise AssertionError(doc['meta']['error'])
            if doc['meta']['state']=='completed':break
            time.sleep(.2)
        assert doc['meta']['state']=='completed'
        assert len(doc['notes'])==len(doc['parsed']['paragraphs'])>0
        saved=Path(doc['meta']['saved_path']);assert saved.parent==dest.resolve() and saved.is_file()
        first_hash=hashlib.sha256(saved.read_bytes()).hexdigest()
        r=client.post(f'/api/papers/{paper}/save-output',headers=headers);r.raise_for_status();assert Path(r.json()['path'])!=saved
        assert hashlib.sha256(saved.read_bytes()).hexdigest()==first_hash
        assert 'exe-smoke-test-key' not in saved.read_text(encoding='utf-8')
        stop();start()
        assert client.get('/api/papers/'+paper).json()['meta']['state']=='completed'
        assert client.get('/api/output-settings').json()['directory']==str(dest.resolve())
        duplicate=subprocess.Popen([str(binary),'--no-browser','--no-tray','--port',str(port)],env=env,creationflags=subprocess.CREATE_NO_WINDOW)
        assert duplicate.wait(timeout=45)==0
        assert client.get('/api/health').json()['pid']==pid
        stop();tray=start(tray=True);assert tray['tray_ready'];stop()
        result={'ok':True,'version':__version__,'native_folder_select':True,'native_folder_cancel':True,'paragraphs':len(doc['notes']),'python_on_path':False,'chinese_exe_path':True,'saved_directory':True,'no_overwrite':True,'restart_persistence':True,'single_instance':True,'tray_ready':True}
        (artifact/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(json.dumps(result))
    finally:
        stop();mock.close();client.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('executable',type=Path);run(parser.parse_args().executable.resolve())
