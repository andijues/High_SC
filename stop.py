import json
import os
import signal
from pathlib import Path

from launch import ROOT, RUNTIME, health

if RUNTIME.exists():
    stored=json.loads(RUNTIME.read_text(encoding='utf-8'))
    current=health(stored['port'])
    if current and current['pid']==stored['pid']:
        os.kill(stored['pid'],signal.SIGTERM)
        print('High_SC 已停止。生成缓存保留，下次可继续。')
    else:print('High_SC 当前未运行。')
else:print('High_SC 当前未运行。')
