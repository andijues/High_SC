import base64
import json
import os
import re
import sys
import tempfile
import io
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from mock_provider import MockProvider
from fastapi.testclient import TestClient
import pymupdf as fitz
from highsc import storage, jobs, server
from highsc.analysis import validate_annotation, annotate_assets
from highsc.provider import ModelClient, ModelError, parse_json, endpoint
from highsc.pdf_parser import parse_pdf

ROOT=Path(__file__).resolve().parents[1]


def short_pdf():
    d=fitz.open();p=d.new_page(width=612,height=792)
    p.insert_text((50,60),'A Test of Reliable Academic Reading',fontsize=22)
    p.insert_textbox((50,120,562,240),'Abstract: We study how semantic checks affect reliable agent execution. Across 32 tasks, success improves from 25.0% to 50.0%. The result is not statistically significant in the smallest subgroup.',fontsize=11)
    p.insert_text((50,270),'I. INTRODUCTION',fontsize=12)
    p.insert_textbox((50,300,562,470),'An operation can return a successful status code while violating a user constraint. Therefore, correctness should include both final state and the safety of intermediate actions. This controlled example motivates richer monitoring [1].',fontsize=11)
    p.insert_text((50,540),'REFERENCES',fontsize=12)
    p.insert_textbox((50,560,562,650),'[1] A. Example. Reliable workflows. 2026.',fontsize=10)
    result=d.tobytes();d.close();return result


class WorkflowTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();data=Path(self.temp.name)/'data';papers=data/'papers';papers.mkdir(parents=True)
        self.patches=[patch.object(storage,'DATA',data),patch.object(storage,'PAPERS',papers),patch.object(jobs,'PAPERS',papers),patch.object(server,'PAPERS',papers),patch.dict(os.environ,{'NO_PROXY':'127.0.0.1,localhost'})]
        for p in self.patches:p.start()
        self.client=TestClient(server.app);self.headers={'X-HighSC-Token':server.TOKEN}
        self.mock=MockProvider()
    def tearDown(self):
        for cancel in list(jobs.ACTIVE.values()):cancel.set()
        end=time.time()+10
        while jobs.ACTIVE and time.time()<end:time.sleep(.05)
        self.mock.close();self.client.close()
        for p in reversed(self.patches):p.stop()
        self.temp.cleanup()
    def settings(self,style='chat'):
        return {'base_url':self.mock.url,'model':'mock-reader','api_style':style,'api_key':'integration-test-secret','batch_size':2,'retries':0,'timeout':20}
    def save_settings(self):
        r=self.client.put('/api/settings',json=self.settings(),headers=self.headers);self.assertEqual(r.status_code,200,r.text);return r
    def upload(self):
        r=self.client.post('/api/papers',files={'file':('test.pdf',short_pdf(),'application/pdf')},data={'auto_generate':'false'},headers=self.headers)
        self.assertEqual(r.status_code,200,r.text);return r.json()['id']
    def wait_for(self,pid,states):
        end=time.time()+15
        while time.time()<end:
            d=self.client.get('/api/papers/'+pid).json()
            if d['meta']['state'] in states and pid not in jobs.ACTIVE:return d
            time.sleep(.04)
        self.fail('Job did not reach expected state')
    def test_secret_and_local_request_boundaries(self):
        r=self.save_settings();self.assertNotIn('integration-test-secret',r.text);self.assertNotIn('integration-test-secret',storage.read_json(storage.DATA/'settings.json')['api_key_protected'])
        self.assertEqual(storage.load_config()['api_key'],'integration-test-secret')
        self.assertEqual(self.client.put('/api/settings',json=self.settings()).status_code,403)
        self.assertEqual(self.client.get('/api/settings',headers={'Origin':'https://external.example'}).status_code,403)
        r=self.client.put('/api/settings',json={**self.settings(),'api_key':''},headers=self.headers);self.assertTrue(r.json()['has_api_key'])
    def test_all_three_api_protocols(self):
        for style in ['chat','responses','anthropic']:
            c={**storage.DEFAULT_CONFIG,**self.settings(style)}
            self.assertTrue(ModelClient(c).test()['ok'])
        self.assertEqual(parse_json('```json\n{"ok":true}\n```'),{'ok':True})
    def test_xhigh_connection_test_preserves_reasoning_budget(self):
        config={**storage.DEFAULT_CONFIG,**self.settings('responses'),'model':'gpt-6.1-sol','max_tokens':32768,'extra_body':{'reasoning':{'effort':'xhigh'}}}
        self.assertTrue(ModelClient(config).test()['ok'])
        request=self.mock.requests[-1]
        self.assertEqual(request['model'],'gpt-6.1-sol')
        self.assertEqual(request['reasoning'],{'effort':'xhigh'})
        self.assertEqual(request['max_output_tokens'],32768)
    def test_official_endpoint_requires_key_before_job_submission(self):
        config={**storage.DEFAULT_CONFIG,'base_url':'https://api.openai.com/v1','model':'gpt-6.1-sol','api_style':'responses','api_key':''}
        with self.assertRaisesRegex(ModelError,'API Key'):
            ModelClient(config)
    def test_third_party_auth_routes_and_output_fields(self):
        for style,route in [('chat','chat/completions'),('responses','responses'),('anthropic','messages')]:
            cfg={**storage.DEFAULT_CONFIG,**self.settings(style),'base_url':self.mock.url+'/'+route+'?api-version=2026-01-01','auth_mode':'api-key','token_field':'max_completion_tokens','extra_headers':{'X-Gateway-Key':'${API_KEY}','X-Route':'reader'}}
            self.assertTrue(ModelClient(cfg).test()['ok'])
            meta=self.mock.request_meta[-1];headers={k.lower():v for k,v in meta['headers'].items()}
            self.assertEqual(meta['path'],'/v1/'+route+'?api-version=2026-01-01')
            self.assertEqual(headers['api-key'],'integration-test-secret');self.assertEqual(headers['x-gateway-key'],'integration-test-secret');self.assertNotIn('authorization',headers)
            self.assertIn('max_completion_tokens',self.mock.requests[-1]);self.assertNotIn('max_tokens',self.mock.requests[-1]);self.assertNotIn('max_output_tokens',self.mock.requests[-1])
        cfg={**storage.DEFAULT_CONFIG,**self.settings(),'base_url':self.mock.url+'/custom-invoke?route=reader','endpoint_mode':'exact','auth_mode':'none','token_field':'omit'}
        ModelClient(cfg).test()
        self.assertEqual(self.mock.request_meta[-1]['path'],'/v1/custom-invoke?route=reader');self.assertNotIn('Authorization',self.mock.request_meta[-1]['headers'])
        self.assertFalse({'max_tokens','max_completion_tokens','max_output_tokens'} & self.mock.requests[-1].keys())
        self.assertEqual(endpoint('https://gateway.example/v1/responses?api-version=1','chat'),'https://gateway.example/v1/chat/completions?api-version=1')
    def test_custom_headers_are_private_preserved_and_clearable(self):
        values={**self.settings(),'extra_headers':{'X-Gateway':'private-gateway-token'}}
        r=self.client.put('/api/settings',json=values,headers=self.headers)
        self.assertEqual(r.status_code,200,r.text);self.assertNotIn('private-gateway-token',r.text);self.assertTrue(r.json()['has_extra_headers'])
        stored=(storage.DATA/'settings.json').read_text();self.assertNotIn('private-gateway-token',stored)
        self.assertEqual(storage.load_config()['extra_headers'],values['extra_headers'])
        self.client.put('/api/settings',json=self.settings(),headers=self.headers)
        self.assertEqual(storage.load_config()['extra_headers'],values['extra_headers'])
        r=self.client.post('/api/settings/test',json=self.settings(),headers=self.headers);self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(self.mock.request_meta[-1]['headers']['X-Gateway'],'private-gateway-token')
        r=self.client.put('/api/settings',json={**self.settings(),'clear_extra_headers':True},headers=self.headers)
        self.assertFalse(r.json()['has_extra_headers']);self.assertEqual(storage.load_config()['extra_headers'],{})
    def test_gateway_errors_redact_credentials(self):
        cfg={**storage.DEFAULT_CONFIG,**self.settings(),'extra_headers':{'X-Gateway':'private-gateway-token'}}
        self.mock.error_status=401;self.mock.error_text='rejected integration-test-secret private-gateway-token'
        with self.assertRaises(ModelError) as error:ModelClient(cfg).test()
        self.assertNotIn('integration-test-secret',str(error.exception));self.assertNotIn('private-gateway-token',str(error.exception))
        self.mock.error_status=0;self.mock.error_json={'error':{'message':'private-gateway-token'}}
        with self.assertRaisesRegex(ModelError,'模型服务返回错误') as error:ModelClient(cfg).test()
        self.assertNotIn('private-gateway-token',str(error.exception))
    def test_invalid_gateway_configuration_rejected(self):
        cfg={**storage.DEFAULT_CONFIG,**self.settings()}
        for header in [{'Host':'other.example'},{'X-Token':'value\r\nInjected: yes'},{'X Token':'value'}]:
            with self.assertRaises(ModelError):ModelClient({**cfg,'extra_headers':header})
        with self.assertRaisesRegex(ModelError,'密钥'):ModelClient({**cfg,'base_url':self.mock.url+'?api_key=hidden'})
    def test_public_demo_is_self_contained_and_original(self):
        r=self.client.get('/example');self.assertEqual(r.status_code,200)
        self.assertIn('data:application/pdf;base64,',r.text)
        self.assertIn('自制教学',r.text);self.assertIn('p006',r.text);self.assertNotIn('Zotero',r.text);self.assertNotIn('src="https://',r.text)
    def test_codex_mode_full_workflow_without_api_key(self):
        from highsc import codex_client
        from mock_provider import fixture_response
        calls=[]
        class FakeProcess:
            def __init__(self,args,**kw):
                self.returncode=None;self.pid=777;calls.append({'args':args,'env':kw['env']})
                owner=self
                class Input(io.BytesIO):
                    def close(stream):
                        payload=json.loads(stream.getvalue().decode().split('TASK_DATA:\n',1)[1])
                        Path(args[args.index('-o')+1]).write_text(json.dumps(fixture_response(payload),ensure_ascii=False),encoding='utf-8')
                        kw['stdout'].write((json.dumps({'type':'turn.completed','usage':{'input_tokens':100,'output_tokens':50}})+'\n').encode())
                        kw['stdout'].flush();owner.returncode=0;super().close()
                self.stdin=Input()
            def poll(self):return self.returncode
        with patch.object(codex_client,'DATA',storage.DATA),patch.object(codex_client,'codex_status',return_value={'chatgpt_login':True}),patch.object(codex_client,'resolve_codex',return_value='codex.exe'),patch.object(codex_client.subprocess,'Popen',FakeProcess),patch.dict(os.environ,{'OPENAI_API_KEY':'must-not-reach-codex','CODEX_API_KEY':'also-not-forwarded'}):
            settings={**self.settings(),'api_style':'codex','base_url':'','api_key':'','model':'gpt-6.1-sol','codex_effort':'xhigh'}
            r=self.client.put('/api/settings',json=settings,headers=self.headers);self.assertEqual(r.status_code,200,r.text)
            pid=self.upload();self.client.post(f'/api/papers/{pid}/generate',json={},headers=self.headers)
            d=self.wait_for(pid,{'completed','failed'});self.assertEqual(d['meta']['state'],'completed',d['meta'].get('error'))
            self.assertEqual(len(d['notes']),2);self.assertTrue(d['meta']['export_ready']);self.assertFalse(storage.load_config(public=True)['has_api_key'])
            self.assertEqual(self.mock.calls,[])
            self.assertTrue(calls)
            for call in calls:
                self.assertIn('model_reasoning_effort="xhigh"',call['args']);self.assertIn('--ignore-user-config',call['args']);self.assertIn('read-only',call['args']);self.assertNotIn('OPENAI_API_KEY',call['env']);self.assertNotIn('CODEX_API_KEY',call['env'])
            self.assertEqual(list((storage.DATA/'codex-runs').iterdir()),[])
    def test_codex_cancellation_stops_process(self):
        from highsc import codex_client
        class Cancelled(Exception):pass
        class HangingProcess:
            def __init__(self,*args,**kw):self.stdin=io.BytesIO();self.returncode=None
            def poll(self):return self.returncode
        checks=0
        def check():
            nonlocal checks
            checks+=1
            if checks>1:raise Cancelled()
        with patch.object(codex_client,'DATA',storage.DATA),patch.object(codex_client,'resolve_codex',return_value='codex.exe'),patch.object(codex_client.subprocess,'Popen',HangingProcess),patch.object(codex_client,'terminate') as stop:
            with self.assertRaises(Cancelled):codex_client.request({**storage.DEFAULT_CONFIG,'model':'gpt-6.1-sol'},'test',{'task':'test'},True,lambda _:None,check)
            stop.assert_called_once()
    def test_end_to_end_edit_and_export(self):
        self.save_settings();pid=self.upload();d=self.client.get('/api/papers/'+pid).json()
        self.assertEqual(len(d['parsed']['paragraphs']),2)
        self.assertTrue(d['parsed']['paragraphs'][0]['en'].startswith('We study'))
        self.assertEqual(len(d['parsed']['references']),1)
        r=self.client.post(f'/api/papers/{pid}/generate',json={},headers=self.headers);self.assertEqual(r.status_code,200,r.text)
        d=self.wait_for(pid,{'completed','failed'});self.assertEqual(d['meta']['state'],'completed',d['meta'].get('error'))
        self.assertEqual(len(d['notes']),2);self.assertTrue(d['review'])
        content=self.client.get(f'/api/papers/{pid}/html').text
        self.assertIn('A Test of Reliable Academic Reading',content);self.assertIn('本地模拟测试译文',content);self.assertIn('data:application/pdf;base64,',content)
        self.assertNotIn('integration-test-secret',content);self.assertNotIn('src="https://',content)
        p=d['parsed']['paragraphs'][0];a=d['notes'][p['id']];a['zh']='人工校对译文：成功率从 25.0% 提升至 50.0%，子组结果不显著。'
        r=self.client.put(f'/api/papers/{pid}/paragraphs/{p["id"]}',json=a,headers=self.headers);self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(self.client.get(f'/api/papers/{pid}/html').status_code,409)
        r=self.client.post(f'/api/papers/{pid}/export',headers=self.headers);self.assertEqual(r.status_code,200,r.text)
        self.assertIn('人工校对译文',self.client.get(f'/api/papers/{pid}/html').text)
        before=len(self.mock.calls)
        self.client.post(f'/api/papers/{pid}/generate',json={},headers=self.headers);self.wait_for(pid,{'completed'})
        self.assertEqual(len(self.mock.calls),before,'Resume should reuse complete results')
        folder=storage.paper_dir(pid);cached=storage.read_json(folder/'notes.json')
        second=d['parsed']['paragraphs'][1]['id'];cached.pop(second)
        storage.atomic_json(folder/'notes.json',cached);jobs.update_meta(folder,state='paused',completed=1)
        self.client.post(f'/api/papers/{pid}/generate',json={'paragraph_ids':[p['id']]},headers=self.headers)
        partial=self.wait_for(pid,{'paused'})
        self.assertIn(p['id'],partial['notes']);self.assertNotIn(second,partial['notes'],'Single-paragraph regeneration must not generate unrelated pending paragraphs')
    def test_pause_and_failure_resume(self):
        self.save_settings();pid=self.upload();self.mock.delay=.25
        self.client.post(f'/api/papers/{pid}/generate',json={},headers=self.headers)
        self.client.post(f'/api/papers/{pid}/pause',headers=self.headers)
        self.wait_for(pid,{'paused'})
        self.mock.delay=0;self.mock.fail_annotation=True
        self.client.post(f'/api/papers/{pid}/generate',json={},headers=self.headers)
        d=self.wait_for(pid,{'failed'});self.assertIn('HTTP 503',d['meta']['error'])
        outlines=self.mock.calls.count('outline');self.mock.fail_annotation=False
        self.client.post(f'/api/papers/{pid}/generate',json={},headers=self.headers)
        self.wait_for(pid,{'completed'});self.assertEqual(self.mock.calls.count('outline'),outlines)
    def test_highlight_quotes_are_grounded(self):
        p={'id':'p1','en':'The controlled experiment used 32 tasks.'}
        raw={'id':'p1','zh':'受控实验使用 32 个任务。','function':'提供证据','logic':'支持方法可行性判断。','critique':'实验规模有限，不能推论全部场景。','highlights':[{'category':'evidence','quote':'32 tasks'},{'category':'thesis','quote':'not in the source'}]}
        a=validate_annotation(raw,p);self.assertEqual(len(a['highlights']),1);self.assertTrue(a['warnings'])
    def test_translation_math_preserves_scientific_exponents(self):
        from highsc.renderer import translated_prose
        result=translated_prose('p = 1.19 × 10−7；普通减法 10-7；<script>')
        self.assertIn('× 10<sup>−7</sup>',result);self.assertIn('普通减法 10-7',result);self.assertNotIn('<script>',result)
    def test_asset_paths_cannot_be_overwritten_by_model(self):
        client=ModelClient({**storage.DEFAULT_CONFIG,**self.settings()})
        result=annotate_assets(client,[{'id':'asset-001','label':'Table 1','en':'Table 1. Test'}],{})
        self.assertNotIn('image',result[0])
    def test_original_agentops_regression(self):
        fixture=os.environ.get('HIGHSC_REGRESSION_PDF')
        if not fixture:self.skipTest('Optional private paper: set HIGHSC_REGRESSION_PDF locally')
        path=Path(fixture)
        p=parse_pdf(path,Path(self.temp.name)/'parsed')
        self.assertEqual((len(p['paragraphs']),len(p['sections']),len(p['assets']),len(p['references'])),(108,12,20,125))
        self.assertEqual(sum(len(x['en'].split()) for x in p['paragraphs']),9880)
        self.assertIn('SYSTEM ANOMALIES?',p['sections'][6]['en'])
        self.assertIn('composite pass from 25.0% to 50.0%', ' '.join(x['en'] for x in p['paragraphs']))


if __name__=='__main__':unittest.main(verbosity=2)
