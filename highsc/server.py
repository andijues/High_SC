from __future__ import annotations

import json
import hashlib
import os
import secrets
import uuid
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__
from . import output
from .analysis import validate_annotation
from .jobs import ACTIVE, list_papers, now, pause, recover_jobs, submit, update_meta
from .pdf_parser import parse_pdf
from .provider import ModelClient, ModelError, validate_headers
from .renderer import audit_document, render_html
from .storage import DATA, LOCK, PAPERS, ROOT, atomic_json, load_config, paper_dir, read_json, save_config

TOKEN=secrets.token_urlsafe(32)
app=FastAPI(title='High_SC',docs_url=None,redoc_url=None,openapi_url=None)


@app.middleware('http')
async def local_only(request:Request,call_next):
    if request.url.hostname not in {'127.0.0.1','localhost','testserver'}:
        return JSONResponse({'detail':'仅允许本机访问'},status_code=403)
    origin=request.headers.get('origin')
    if origin and origin not in {f'http://{request.headers.get("host")}',f'https://{request.headers.get("host")}'}:
        return JSONResponse({'detail':'不接受外部站点请求'},status_code=403)
    if request.method not in {'GET','HEAD','OPTIONS'} and request.headers.get('X-HighSC-Token')!=TOKEN:
        return JSONResponse({'detail':'页面会话已失效，请刷新页面'},status_code=403)
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Referrer-Policy']='no-referrer'
    return response


@app.exception_handler(ValueError)
@app.exception_handler(ModelError)
async def value_error(request,exc):return JSONResponse({'detail':str(exc)},status_code=400)


@app.exception_handler(FileNotFoundError)
async def not_found(request,exc):return JSONResponse({'detail':str(exc)},status_code=404)


@app.get('/',response_class=HTMLResponse)
def home():
    return (ROOT/'static/index.html').read_text(encoding='utf-8').replace('__SESSION_TOKEN__',TOKEN)


@app.get('/api/health')
def health():return {'app':'High_SC','version':__version__,'pid':os.getpid(),'instance':hashlib.sha256(str(DATA).encode()).hexdigest()[:16],'tray_ready':bool(getattr(app.state,'tray_ready',False))}


class OutputSettings(BaseModel):
    directory:str=Field(min_length=1,max_length=2000)
    auto_save:bool=True


@app.get('/api/output-settings')
def output_settings():return {**output.settings(),'native_picker':os.name=='nt'}


@app.put('/api/output-settings')
def put_output_settings(value:OutputSettings):return output.save_settings(value.directory,value.auto_save)


class FolderChoice(BaseModel):
    initial:str=Field(default='',max_length=2000)


@app.post('/api/output/choose-folder')
def choose_output_folder(value:FolderChoice):return {'directory':output.choose_folder(value.initial)}


@app.post('/api/output/open-folder')
def open_output_folder():
    output.open_directory(output.settings()['directory']);return {'ok':True}


class Settings(BaseModel):
    base_url:str=Field(default='',max_length=1000)
    model:str=Field(default='',max_length=300)
    api_style:Literal['chat','responses','anthropic','codex']='chat'
    api_key:str=Field(default='',max_length=4096)
    clear_api_key:bool=False
    auth_mode:Literal['auto','bearer','x-api-key','api-key','none']='auto'
    endpoint_mode:Literal['auto','exact']='auto'
    token_field:Literal['auto','max_tokens','max_completion_tokens','max_output_tokens','omit']='auto'
    extra_headers:dict[str,str]|None=None
    clear_extra_headers:bool=False
    timeout:int=Field(default=180,ge=15,le=1800)
    max_tokens:int=Field(default=8192,ge=512,le=131072)
    batch_size:int=Field(default=4,ge=1,le=12)
    context_chars:int=Field(default=48000,ge=8000,le=300000)
    retries:int=Field(default=2,ge=0,le=5)
    json_mode:bool=False
    send_temperature:bool=False
    temperature:float=Field(default=.2,ge=0,le=2)
    extra_body:dict=Field(default_factory=dict)
    proxy:str=Field(default='',max_length=1000)
    codex_path:str=Field(default='',max_length=2000)
    codex_effort:Literal['low','medium','high','xhigh','max']='xhigh'

    def checked(self):
        d=self.model_dump();d['base_url']=d['base_url'].strip();d['model']=d['model'].strip()
        if self.proxy:
            u=urlparse(self.proxy)
            if u.scheme not in {'http','https'} or not u.netloc:raise ValueError('代理请使用 http://127.0.0.1:端口 形式')
        if len(json.dumps(self.extra_body))>16000:raise ValueError('额外参数过长')
        if self.extra_headers is not None:
            if len(json.dumps(self.extra_headers))>16000:raise ValueError('自定义请求头过长')
            validate_headers(self.extra_headers)
        return d


@app.get('/api/settings')
def get_settings():return load_config(public=True)


@app.get('/api/codex/status')
def get_codex_status():
    from .codex_client import codex_status
    return codex_status(load_config(public=True))


@app.put('/api/settings')
def put_settings(settings:Settings):return save_config(settings.checked())


@app.post('/api/settings/test')
def test_settings(settings:Settings):
    cfg={**load_config(),**settings.checked()}
    if not settings.api_key and not settings.clear_api_key:cfg['api_key']=load_config()['api_key']
    if settings.clear_extra_headers:cfg['extra_headers']={}
    elif settings.extra_headers is None:cfg['extra_headers']=load_config()['extra_headers']
    return ModelClient(cfg).test()


@app.get('/api/papers')
def papers():return list_papers()


@app.post('/api/papers')
def upload(file:UploadFile=File(...),ocr:bool=Form(False),auto_generate:bool=Form(False)):
    if not (file.filename or '').lower().endswith('.pdf'):raise ValueError('请选择 PDF 文件')
    pid=uuid.uuid4().hex;folder=PAPERS/pid;folder.mkdir(parents=True)
    size=0
    try:
        with (folder/'source.pdf').open('wb') as f:
            while chunk:=file.file.read(1024*1024):
                size+=len(chunk)
                if size>100*1024*1024:raise ValueError('PDF 超过 100 MB，请先压缩或拆分')
                f.write(chunk)
        if (folder/'source.pdf').read_bytes()[:5]!=b'%PDF-':raise ValueError('该文件不是有效的 PDF')
        parsed=parse_pdf(folder/'source.pdf',folder,ocr=ocr)
        atomic_json(folder/'parsed.json',parsed);atomic_json(folder/'notes.json',{})
        meta={'id':pid,'title':parsed['title'],'filename':Path(file.filename).name,'pages':parsed['page_count'],'paragraphs':len(parsed['paragraphs']),'assets':len(parsed['assets']),'references':len(parsed['references']),'state':'ready','stage':'ready','message':'解析完成，可以开始生成','completed':0,'total':len(parsed['paragraphs']),'created_at':now(),'updated_at':now(),'events':[],'error':'','export_ready':False,'warnings':parsed['warnings'],'bytes':size}
        atomic_json(folder/'meta.json',meta)
        if auto_generate:
            try:submit(pid)
            except ModelError as exc:update_meta(folder,message='解析完成，请检查模型设置后再开始生成',error=str(exc))
        return read_json(folder/'meta.json')
    except Exception:
        # No recursive deletion of user data. A failed import leaves its source for diagnosis.
        if not (folder/'meta.json').exists():
            atomic_json(folder/'import-error.json',{'message':'导入未完成','filename':Path(file.filename).name,'time':now()})
        raise
    finally:file.file.close()


@app.get('/api/papers/{pid}')
def get_paper(pid:str):
    folder=paper_dir(pid)
    return {'meta':read_json(folder/'meta.json'),'parsed':read_json(folder/'parsed.json'),'outline':read_json(folder/'outline.json'),'notes':read_json(folder/'notes.json',{}),'review':read_json(folder/'review.json',[])}


class Generate(BaseModel):
    force:bool=False
    paragraph_ids:list[str]=Field(default_factory=list,max_length=5000)


@app.post('/api/papers/{pid}/generate')
def generate(pid:str,options:Generate):return submit(pid,force=options.force,only_ids=options.paragraph_ids or None)


@app.post('/api/papers/{pid}/pause')
def pause_paper(pid:str):return pause(pid)


@app.put('/api/papers/{pid}/paragraphs/{paragraph_id}')
def edit_paragraph(pid:str,paragraph_id:str,annotation:dict):
    folder=paper_dir(pid)
    with LOCK:
        if pid in ACTIVE:raise ValueError('请先暂停生成，再编辑段落')
        parsed=read_json(folder/'parsed.json');p=next((p for p in parsed['paragraphs'] if p['id']==paragraph_id),None)
        if not p:raise ValueError('段落不存在')
        annotation['id']=paragraph_id;value=validate_annotation(annotation,p);value['edited']=True
        notes=read_json(folder/'notes.json',{});notes[paragraph_id]=value;atomic_json(folder/'notes.json',notes)
        update_meta(folder,completed=len(notes),export_ready=False,message='修改已保存，请重新导出以更新 HTML')
    return value


@app.post('/api/papers/{pid}/export')
def export(pid:str):
    folder=paper_dir(pid)
    with LOCK:
        if pid in ACTIVE:raise ValueError('生成过程中暂不能导出，请等待完成或暂停')
        parsed=read_json(folder/'parsed.json');outline=read_json(folder/'outline.json');notes=read_json(folder/'notes.json',{})
        if not outline:raise ValueError('尚未完成全文分析，请先开始生成')
        if any(not a.get('zh') for a in parsed['assets']):raise ValueError('图表说明尚未完成，请继续生成后再导出')
        path=render_html(folder,parsed,outline,notes)
        issues=audit_document(parsed,notes);atomic_json(folder/'review.json',issues)
        saved=output.try_auto_save(path,parsed['title'],pid)
        update_meta(folder,export_ready=True,export_bytes=path.stat().st_size,review_count=len(issues),message='HTML 已更新',**saved)
    return {'url':f'/api/papers/{pid}/html','download':f'/api/papers/{pid}/html?download=1','bytes':path.stat().st_size}


@app.post('/api/papers/{pid}/save-output')
def save_output(pid:str):
    folder=paper_dir(pid)
    with LOCK:
        if not read_json(folder/'meta.json',{}).get('export_ready'):raise ValueError('请先完成生成或更新 HTML')
        try:path=output.save_html(folder/'annotated.html',read_json(folder/'parsed.json')['title'],pid)
        except OSError as exc:raise ValueError('无法保存到指定目录：'+str(exc)) from None
        update_meta(folder,saved_path=path,save_error='')
    return {'path':path}


@app.get('/api/papers/{pid}/html')
def output_html(pid:str,download:bool=False):
    folder=paper_dir(pid)
    if not read_json(folder/'meta.json',{}).get('export_ready'):raise HTTPException(409,'请先完成生成或重新导出')
    filename=f'{read_json(folder/"parsed.json")["title"][:110]}_双栏批注.html'
    filename=''.join(c for c in filename if c not in '<>:"/\\|?*\r\n')
    return FileResponse(folder/'annotated.html',media_type='text/html',filename=filename if download else None)


@app.get('/api/papers/{pid}/source')
def source_pdf(pid:str):return FileResponse(paper_dir(pid)/'source.pdf',media_type='application/pdf')


@app.get('/api/papers/{pid}/cover')
def cover(pid:str):return FileResponse(paper_dir(pid)/'cover.png',media_type='image/png')


@app.get('/api/papers/{pid}/assets/{asset_id}')
def asset_image(pid:str,asset_id:str):
    parsed=read_json(paper_dir(pid)/'parsed.json')
    a=next((a for a in parsed['assets'] if a['id']==asset_id),None)
    if not a:raise HTTPException(404,'图表不存在')
    return FileResponse(paper_dir(pid)/a['image'],media_type='image/png')


@app.get('/example')
def example():return FileResponse(ROOT/'examples/demo.html',media_type='text/html')


app.mount('/static',StaticFiles(directory=ROOT/'static'),name='static')
recover_jobs()
