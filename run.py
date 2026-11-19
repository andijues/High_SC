from __future__ import annotations

import argparse
import os
from pathlib import Path

import uvicorn

if __name__=='__main__':
    parser=argparse.ArgumentParser(description='High_SC 本地服务')
    parser.add_argument('--port',type=int,default=8693)
    args=parser.parse_args()
    os.chdir(Path(__file__).resolve().parent)
    uvicorn.run('highsc.server:app',host='127.0.0.1',port=args.port,access_log=False,log_level='info')
