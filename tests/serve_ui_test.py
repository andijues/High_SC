"""Isolated browser-test service: never writes settings/jobs into the actual app data."""
import json
import os
import sys
import uuid
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
ARTIFACTS=ROOT/'tests/artifacts'
ARTIFACTS.mkdir(exist_ok=True)
os.environ['HIGHSC_DATA_DIR']=str(ARTIFACTS/('ui-data-'+uuid.uuid4().hex))
os.environ['NO_PROXY']='127.0.0.1,localhost'
sys.path.insert(0,str(ROOT))
from mock_provider import MockProvider
import uvicorn

if __name__=='__main__':
    mock=MockProvider(delay=.05)
    (ARTIFACTS/'ui-endpoint.json').write_text(json.dumps({'base_url':mock.url,'data_dir':os.environ['HIGHSC_DATA_DIR']}),encoding='utf-8')
    uvicorn.run('highsc.server:app',host='127.0.0.1',port=8695,access_log=False)
