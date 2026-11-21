"""Private, content-addressed analysis cache. Never contains credentials or PDFs."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from . import storage

REVISION = 'academic-analysis-v2-20261121'


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()


def identity(folder, parsed, config, system):
    # Hash credentials/routing too: different accounts or gateways must not
    # accidentally share model results. No credential is written to the cache.
    fields=('api_style','base_url','model','codex_effort','codex_path','extra_body',
            'send_temperature','temperature','json_mode','token_field','auth_mode',
            'endpoint_mode','api_key','extra_headers','context_chars')
    profile=digest({k:config.get(k) for k in fields})
    content={
        'title':parsed['title'],'sections':parsed['sections'],
        'paragraphs':[{k:p.get(k) for k in ('id','section_id','en','subheading','pages')} for p in parsed['paragraphs']],
        'assets':[{k:a.get(k) for k in ('id','en','label','source_text','after','page','rect')} for a in parsed['assets']],
        'references':parsed.get('references',[]),
    }
    source_hash=hashlib.sha256((Path(folder)/'source.pdf').read_bytes()).hexdigest()
    return digest({'revision':REVISION,'system':system,'profile':profile,'source':source_hash,'parsed':content})


def path_for(key):
    if len(key)!=64 or any(c not in '0123456789abcdef' for c in key):raise ValueError('缓存编号无效')
    return storage.DATA/'cache'/key/'analysis.json'


def load(key, parsed):
    from .analysis import validate_annotation, validate_outline
    try:
        raw=storage.read_json(path_for(key),{})
        if raw.get('revision')!=REVISION or raw.get('key')!=key:return {}
        result={'notes':{},'assets':{}}
        if not raw.get('outline'):return {}
        result['outline']=validate_outline(raw['outline'],parsed)
        for p in parsed['paragraphs']:
            note=raw.get('notes',{}).get(p['id'])
            if note and not note.get('edited'):
                try:
                    checked=validate_annotation(note,p)
                    prior=[w for w in note.get('warnings',[]) if isinstance(w,str)]
                    checked['warnings']=list(dict.fromkeys(prior+checked['warnings']))
                    result['notes'][p['id']]={**checked,'model':note.get('model','')}
                except (ValueError,RuntimeError):pass
        allowed={'id','zh','function','logic','critique','tone'}
        for a in parsed['assets']:
            value=raw.get('assets',{}).get(a['id'])
            if isinstance(value,dict) and value.get('id')==a['id'] and all(isinstance(value.get(k),str) and value[k].strip() for k in ('zh','function','logic','critique')):
                result['assets'][a['id']]={k:v for k,v in value.items() if k in allowed}
        return result
    except (ValueError,TypeError,KeyError,AttributeError,RuntimeError,OSError):
        # A corrupt or obsolete cache is a miss, never a failed paper import.
        return {}


def store(key, outline=None, notes=None, assets=None):
    with storage.LOCK:
        try:packet=storage.read_json(path_for(key),{})
        except (ValueError,OSError):packet={}
        if not isinstance(packet,dict) or packet.get('key')!=key or packet.get('revision')!=REVISION:
            packet={'revision':REVISION,'key':key,'notes':{},'assets':{}}
        for field in ('notes','assets'):
            if not isinstance(packet.get(field),dict):packet[field]={}
        if outline is not None and packet.get('outline')!=outline:
            packet['notes']={};packet['assets']={}
        if outline is not None:packet['outline']=outline
        for note in notes or []:
            if not note.get('edited'):packet.setdefault('notes',{})[note['id']]=note
        for asset in assets or []:
            packet.setdefault('assets',{})[asset['id']]={k:asset[k] for k in ('id','zh','function','logic','critique','tone')}
        storage.atomic_json(path_for(key),packet)


def is_fresh(folder, parsed):
    return not storage.read_json(folder/'outline.json') and not storage.read_json(folder/'notes.json',{}) and not any(a.get('zh') for a in parsed['assets'])


def eligible(folder, parsed, key):
    return storage.read_json(folder/'meta.json',{}).get('analysis_key')==key or is_fresh(folder,parsed)


def complete(parsed, packet):
    return bool(packet.get('outline')) and all(p['id'] in packet.get('notes',{}) for p in parsed['paragraphs']) and all(a['id'] in packet.get('assets',{}) for a in parsed['assets'])
