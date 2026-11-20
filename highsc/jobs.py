from __future__ import annotations

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from .analysis import annotate_assets, annotate_batch, make_outline
from .provider import ModelClient, ModelError
from .renderer import audit_document, render_html
from .output import try_auto_save
from .storage import LOCK, PAPERS, atomic_json, load_config, paper_dir, read_json

EXECUTOR=ThreadPoolExecutor(max_workers=1,thread_name_prefix="highsc")
ACTIVE={}


class Paused(Exception):
    pass


def now():return datetime.now().isoformat(timespec="microseconds")


def update_meta(folder,**values):
    with LOCK:
        meta=read_json(folder/'meta.json',{})
        meta.update(values);meta['updated_at']=now();atomic_json(folder/'meta.json',meta)
        return meta


def log(folder,message,**values):
    with LOCK:
        meta=read_json(folder/'meta.json',{})
        events=meta.get('events',[])
        if message:events.append({'time':now(),'message':message})
        meta.update(values);meta['events']=events[-100:];meta['updated_at']=now()
        if message:meta['message']=message
        atomic_json(folder/'meta.json',meta)


def list_papers():
    PAPERS.mkdir(parents=True,exist_ok=True)
    result=[]
    for p in PAPERS.iterdir():
        if p.is_dir() and (p/'meta.json').exists():result.append(read_json(p/'meta.json'))
    return sorted(result,key=lambda x:x.get('updated_at',''),reverse=True)


def recover_jobs():
    for meta in list_papers():
        if meta.get('state') in {'queued','running','pausing'}:
            update_meta(paper_dir(meta['id']),state='paused',message='上次进程已停止，可继续生成；已完成内容保留')


def submit(pid,force=False,only_ids=None):
    folder=paper_dir(pid)
    cfg=load_config()
    ModelClient(cfg)  # Validate before putting the job into the queue.
    with LOCK:
        if pid in ACTIVE:raise ValueError('这篇论文正在生成，请先暂停')
        parsed=read_json(folder/'parsed.json')
        valid={p['id'] for p in parsed['paragraphs']}
        if only_ids and not set(only_ids)<=valid:raise ValueError('段落编号不存在')
        if force:
            atomic_json(folder/'notes.json',{});atomic_json(folder/'checkpoint.json',{})
            if (folder/'outline.json').exists():(folder/'outline.json').unlink()
            for asset in parsed['assets']:
                for k in ['zh','function','logic','critique']:asset[k]=''
            atomic_json(folder/'parsed.json',parsed)
        if only_ids:
            notes=read_json(folder/'notes.json',{})
            for i in only_ids:notes.pop(i,None)
            atomic_json(folder/'notes.json',notes)
        # An earlier export may remain on disk, but is unavailable until all stages pass again.
        cancel=threading.Event();ACTIVE[pid]=cancel
        log(folder,'任务已排队',state='queued',stage='queued',error='',export_ready=False,run_id=uuid.uuid4().hex)
        EXECUTOR.submit(run,pid,cfg,cancel,only_ids)
    return read_json(folder/'meta.json')


def pause(pid):
    folder=paper_dir(pid)
    with LOCK:
        if pid not in ACTIVE:return read_json(folder/'meta.json')
        ACTIVE[pid].set()
        codex=load_config(public=True).get('api_style')=='codex'
        return update_meta(folder,state='pausing',message='正在停止当前 Codex 请求；已完成内容会保留' if codex else '当前模型请求结束后暂停；已完成内容会保留')


def run(pid,cfg,cancel,only_ids=None):
    folder=paper_dir(pid)
    def check():
        if cancel.is_set():raise Paused()
    def usage(u):
        with LOCK:
            m=read_json(folder/'meta.json')
            tokens=m.get('tokens',{'input':0,'output':0,'calls':0})
            tokens['input']+=int(u.get('prompt_tokens',u.get('input_tokens',0)) or 0)
            tokens['output']+=int(u.get('completion_tokens',u.get('output_tokens',0)) or 0)
            tokens['calls']+=1;update_meta(folder,tokens=tokens)
    try:
        check();log(folder,'准备全文上下文',state='running',stage='outline')
        parsed=read_json(folder/'parsed.json');notes=read_json(folder/'notes.json',{})
        checkpoint=read_json(folder/'checkpoint.json',{})
        client=ModelClient(cfg,usage_callback=usage,cancel_check=check)
        def progress(message):
            check();atomic_json(folder/'checkpoint.json',checkpoint)
            if message:log(folder,message,stage='outline')
        outline=read_json(folder/'outline.json')
        if not outline:
            outline=make_outline(client,parsed,checkpoint,progress)
            atomic_json(folder/'outline.json',outline)
        pending=[p for p in parsed['paragraphs'] if p['id'] not in notes and (not only_ids or p['id'] in only_ids)]
        total=len(parsed['paragraphs'])
        def generate_group(group):
            check()
            log(folder,f'翻译与批注：{len(notes)}/{total} 段已完成',stage='paragraphs',completed=len(notes),total=total)
            try:
                result=annotate_batch(client,parsed,outline,group)
            except ModelError as exc:
                # Smaller batches recover truncated/invalid output without replaying successful work.
                if len(group)>1 and getattr(exc,'allow_split',True) and 'HTTP ' not in str(exc) and '连接' not in str(exc):
                    middle=len(group)//2;generate_group(group[:middle]);generate_group(group[middle:]);return
                raise
            for annotation in result:
                annotation['model']=cfg['model'];notes[annotation['id']]=annotation
            atomic_json(folder/'notes.json',notes)
            update_meta(folder,completed=len(notes))
        group=[];length=0
        for p in pending:
            if group and (len(group)>=cfg['batch_size'] or length+len(p['en'])>12000):
                generate_group(group);group=[];length=0
            group.append(p);length+=len(p['en'])
        if group:generate_group(group)
        check()
        if len(notes)<total:
            log(folder,'所选段落已完成，可继续全文生成',state='paused',stage='paused',completed=len(notes),total=total)
            return
        todo=[a for a in parsed['assets'] if not a.get('zh')]
        for i in range(0,len(todo),3):
            log(folder,f'生成图表说明 {i+1}-{min(i+3,len(todo))}/{len(todo)}',stage='assets')
            results=annotate_assets(client,todo[i:i+3],outline)
            by_id={a['id']:a for a in results}
            for a in parsed['assets']:
                if a['id'] in by_id:a.update(by_id[a['id']])
            atomic_json(folder/'parsed.json',parsed)
        check();log(folder,'检查段落对应、数值与高亮，正在打包离线 HTML',stage='export')
        issues=audit_document(parsed,notes)
        atomic_json(folder/'review.json',issues)
        path=render_html(folder,parsed,outline,notes,cfg['model'])
        saved=try_auto_save(path,parsed['title'],pid)
        log(folder,'生成完成，可预览、编辑或下载 HTML',state='completed',stage='completed',completed=total,total=total,error='',export_ready=True,review_count=len(issues),export_bytes=path.stat().st_size,model=cfg['model'],**saved)
    except Paused:
        log(folder,'已暂停，可继续生成；已完成内容保留',state='paused',stage='paused')
    except Exception as exc:
        detail=str(exc)
        if cfg.get('api_key'):detail=detail.replace(cfg['api_key'],'[密钥已隐藏]')
        log(folder,'生成未完成，可修正配置后继续',state='failed',error=detail[:1800])
    finally:
        with LOCK:ACTIVE.pop(pid,None)
