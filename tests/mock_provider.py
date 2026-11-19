"""Local protocol fixture. It does not evaluate real model quality or use any paid API."""
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit


def fixture_response(payload):
    task=payload.get('task')
    if task=='test':return {'ok':True}
    if task=='chunk_summary':return {'summary':'本段为测试数据：研究问题、已有证据与局限。','anchors':[]}
    if task=='outline':
        ids=[p['id'] for p in payload.get('paragraphs',[])]
        return {'title_zh':'测试接口生成的论文分析（用于功能验证）','core_claim':'测试接口验证全文分析、逐段生成与离线导出之间的数据流。','chain':[{'stage':s,'text':'这是本地测试接口的固定响应，用于验证功能，不代表真实学术分析。','paragraph_ids':ids[:1]} for s in ['问题','论点','证据','让步与反驳','结论']],'strongest':{'text':'测试流程保留英文原文与对应编号。','paragraph_ids':ids[:1]},'weakest':{'text':'模拟响应不用于评估真实模型的翻译或论证能力。','paragraph_ids':ids[:1]},'evidence_boundary':'本次使用本地模拟接口验证工程流程，未测量真实大模型质量。','sections':[{'id':s['id'],'zh':'测试章节 '+str(i+1),'logic':'用于核对章节对应关系。'} for i,s in enumerate(payload['sections'])],'glossary':[{'en':'agent','zh':'智能体'}]}
    if task=='annotate':
        return {'annotations':[{'id':p['id'],'zh':'【本地模拟测试译文】这段内容用于检验翻译、批注、保存和导出的完整链路；真实译文由用户配置的大模型生成。','function':'验证段落处理','logic':'用于检验该段与全文框架的编号对应关系。','critique':'这是一条明确标注的模拟批注，不代表对原论文的实际学术评价。','tone':'method','highlights':[{'category':'method','quote':p['text'][:min(40,len(p['text']))]}],'support_quotes':[p['text'][:40]]} for p in payload['paragraphs']]}
    if task=='assets':
        return {'assets':[{'id':a['id'],'zh':'【本地模拟测试】图表原图保留，真实说明由配置的大模型生成。','function':'验证图表处理','logic':'用于检验图表与正文的关联。','critique':'模拟接口没有分析图像内容，不据此推断数据。','tone':'method','image':'../../should-not-be-used'} for a in payload['assets']]}
    raise ValueError('Unknown test task')


class MockProvider:
    def __init__(self,delay=0):
        self.calls=[];self.requests=[];self.request_meta=[];self.delay=delay;self.fail_annotation=False
        self.error_status=0;self.error_text='';self.error_json=None
        owner=self
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                data=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                owner.requests.append(data)
                owner.request_meta.append({'path':self.path,'headers':dict(self.headers)})
                if owner.error_status:
                    self.send_response(owner.error_status);self.end_headers();self.wfile.write(owner.error_text.encode());return
                if owner.error_json is not None:
                    self.send_response(200);self.end_headers();self.wfile.write(json.dumps(owner.error_json).encode());return
                messages=data.get('messages') or data.get('input');content=messages[-1]['content']
                payload=json.loads(content);owner.calls.append(payload['task'])
                if owner.delay:time.sleep(owner.delay)
                if owner.fail_annotation and payload['task']=='annotate':
                    self.send_response(503);self.end_headers();self.wfile.write(b'test outage');return
                text=json.dumps(fixture_response(payload),ensure_ascii=False)
                if urlsplit(self.path).path.endswith('/messages'):result={'content':[{'type':'text','text':text}],'stop_reason':'end_turn','usage':{'input_tokens':12,'output_tokens':30}}
                elif urlsplit(self.path).path.endswith('/responses'):result={'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':text}]}],'usage':{'input_tokens':12,'output_tokens':30}}
                else:result={'choices':[{'message':{'content':text},'finish_reason':'stop'}],'usage':{'prompt_tokens':12,'completion_tokens':30}}
                body=json.dumps(result,ensure_ascii=False).encode();self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
            def log_message(self,*args):pass
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.url=f'http://127.0.0.1:{self.server.server_port}/v1'
    def close(self):self.server.shutdown();self.server.server_close();self.thread.join(timeout=3)


if __name__=='__main__':
    mock=MockProvider(delay=.05)
    print(mock.url,flush=True)
    try:
        while True:time.sleep(1)
    except KeyboardInterrupt:mock.close()
