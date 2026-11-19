from __future__ import annotations

import base64
import html
import re
from datetime import datetime
from pathlib import Path

from .storage import ROOT

COLORS={"thesis":"核心论点","term":"关键概念","evidence":"证据 / 数据","concession":"让步 / 反驳","method":"方法说明"}
esc=lambda s:html.escape(str(s))


def translated_prose(text):
    return re.sub(r'([×*]\s*10)\s*([−-]\d+)',r'\1<sup>\2</sup>',esc(text))


def data_uri(path:Path, kind):
    return f"data:{kind};base64,"+base64.b64encode(path.read_bytes()).decode()


def highlighted(text, annotation, references):
    parts=[];last=0
    intervals=[]
    for h in annotation.get("highlights",[]):
        quote=h.get("quote","");start=text.find(quote)
        if start<0 or not quote:continue
        end=start+len(quote)
        if any(start<b and end>a for a,b,_ in intervals):continue
        category=h.get("category","method")
        if category not in COLORS:continue
        intervals.append((start,end,category))
    for start,end,category in sorted(intervals):
        parts.append(esc(text[last:start]));parts.append(f'<mark class="{category}" title="{COLORS[category]}">{esc(text[start:end])}</mark>');last=end
    parts.append(esc(text[last:]))
    result="".join(parts)
    result=re.sub(r'10(−\d+)',r'10<sup>\1</sup>',result)
    def citation(m):
        n=int(m[1])
        return f'<a class="cite" href="#ref-{n}">[{n}]</a>' if n in references else m[0]
    return re.sub(r'\[(\d{1,3})\]',citation,result)


def note_card(a,label):
    tone=a.get("tone","method")
    if tone not in COLORS:tone="method"
    return f'''<aside class="note {tone}" aria-label="{esc(label)} 的中文批注"><div class="note-top"><span>论证批注</span><span>{esc(label)}</span></div><dl><dt>段落功能</dt><dd>{esc(a.get('function',''))}</dd><dt>逻辑角色</dt><dd>{esc(a.get('logic',''))}</dd><dt>技巧与审视</dt><dd>{esc(a.get('critique',''))}</dd></dl></aside>'''


def audit_document(parsed,notes):
    issues=[]
    pids={p["id"] for p in parsed["paragraphs"]}
    if set(notes)!=pids:
        issues.append({"type":"coverage","message":f"还有 {len(pids-set(notes))} 段未完成","paragraph_id":""})
    for p in parsed["paragraphs"]:
        a=notes.get(p["id"])
        if not a:continue
        for f in a.get("review_flags",[])+a.get("warnings",[]):
            issues.append({"type":"review","message":f,"paragraph_id":p["id"]})
        for h in a.get("highlights",[]):
            if h.get("quote","") not in p["en"]:
                issues.append({"type":"highlight","message":"高亮片段无法定位","paragraph_id":p["id"]})
    return issues


def render_html(folder:Path,parsed,outline,notes,model_label="") -> Path:
    missing=[p["id"] for p in parsed["paragraphs"] if p["id"] not in notes]
    if missing:raise ValueError(f"尚有 {len(missing)} 段未完成，请继续生成后再导出")
    css=(ROOT/'templates/reader.css').read_text(encoding='utf-8')
    js=(ROOT/'templates/reader.js').read_text(encoding='utf-8')
    fonts=ROOT/'static/fonts'
    for family,filename,weight in [('Lora','Lora.ttf','400 700'),('IBM Plex Sans','IBMPlexSans.ttf','100 700')]:
        css+=f"@font-face{{font-family:'{family}';src:url({data_uri(fonts/filename,'font/ttf')}) format('truetype');font-weight:{weight};font-display:swap}}"
    css+='\n.review-info{font-size:12px;margin:14px 0;padding:12px 16px;background:#f0ece2}.glossary{font-size:12px}.review-info a{color:#557990}'
    refs={r['number'] for r in parsed['references']}
    title=parsed['title'];title_zh=outline.get('title_zh','')
    section_info={s['id']:s for s in outline.get('sections',[])}
    legend=''.join(f'<button type="button" data-dimension="{k}" aria-pressed="true"><span class="swatch {k}"></span>{v}</button>' for k,v in COLORS.items())
    nav=''.join(f'<a href="#{s["id"]}">{esc(section_info.get(s["id"],{}).get("zh") or s["zh"] or s["en"])}</a>' for s in parsed['sections'])+'<a href="#argument">论证总览</a><a href="#references">参考文献</a>'
    original=data_uri(folder/'source.pdf','application/pdf')
    head=f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)} · 双栏论证批注</title><style>{css}</style></head><body><a class="skip" href="#main">跳转到正文</a><header class="masthead" id="top"><div class="wrap"><div class="mast-top"><span class="publication">High_SC · 学术论文双语批注</span><a class="download" href="{original}" download="original.pdf">下载内嵌原始 PDF</a></div><h1 lang="en">{esc(title)}</h1><p class="zh-title">{esc(title_zh)}</p><p class="byline">{parsed['page_count']} 页 · {len(notes)} 段正文 · 生成时间 {datetime.now():%Y-%m-%d %H:%M}</p><div class="legend">{legend}<span class="legend-note">点击图例切换高亮</span></div></div></header><nav class="section-nav" aria-label="章节导航"><div class="wrap nav-inner">{nav}</div></nav><main id="main" class="wrap"><section class="reading-intro"><div class="brief-grid"><div><h2>沿着论证链，理解全文</h2><p class="reading-map">左栏为英文原文与中文意译，右栏逐段说明功能、逻辑角色与论证边界。点击图表可放大，引用编号可跳转到参考文献。</p></div><div class="reading-meta"><strong>{len(notes)} 段英中对照 · {len(parsed['sections'])} 个章节</strong><br>{len(parsed['assets'])} 项图表 · {len(parsed['references'])} 条参考文献<br>英文正文保留提取结果，批注由所配置模型生成</div></div><p class="scope">原文仅作排版断行整理；图表原样内嵌并附中文说明，参考文献保留原始书目。译文和批注属于辅助阅读内容，可对照内嵌 PDF 核对。</p><div class="toolbar"><div class="search-wrap"><label for="search">文内查找</label><input id="search" type="search" placeholder="搜索英文、中文或批注"><span id="search-status" class="search-status" role="status"></span></div><div class="view-controls"><button type="button" id="toggle-translation" aria-pressed="true">中文译文</button><button type="button" id="toggle-notes" aria-pressed="true">中文批注</button><button type="button" id="print">打印 / 存为 PDF</button></div></div>'''
    issues=audit_document(parsed,notes)
    if parsed['warnings'] or issues:
        messages=[esc(w) for w in parsed['warnings']]
        messages += [f'<a href="#{esc(i["paragraph_id"])}">{esc(i["paragraph_id"])}</a>：{esc(i["message"])}' for i in issues if i['paragraph_id']]
        head+=f'<details class="review-info"><summary>阅读核对提示（{len(messages)} 项）</summary><ul>'+''.join(f'<li>{m}</li>' for m in messages)+'</ul></details>'
    head+='<div class="column-labels"><span>原文与译文 · English / 中文</span><span>中文批注 · Argument notes</span></div></section><p id="empty-message" class="empty-message hidden">没有匹配内容，请尝试其他关键词。</p>'
    body=[]
    for s in parsed['sections']:
        info=section_info.get(s['id'],{})
        body.append(f'<section class="paper-section" id="{s["id"]}"><header class="section-heading"><div class="section-title"><h2 lang="en">{esc(s["en"])}<span lang="zh-CN">{esc(info.get("zh") or s["zh"])}</span></h2></div><p class="section-logic">本节逻辑：{esc(info.get("logic", ""))}</p></header>')
        for p in [p for p in parsed['paragraphs'] if p['section_id']==s['id']]:
            a=notes[p['id']];pages='、'.join(map(str,p['pages']))
            if p.get('subheading'):body.append(f'<h3 class="subheading">{esc(p["subheading"])}</h3>')
            body.append(f'<article class="pair text-pair" id="{p["id"]}"><div class="passage"><div class="para-meta"><a href="#{p["id"]}">¶ {p["id"][1:]}</a><span>原文第 {pages} 页</span></div><p class="english" lang="en">{highlighted(p["en"],a,refs)}</p><div class="translation"><span class="translation-label">中文译文</span><p>{translated_prose(a["zh"])}</p></div></div>{note_card(a,p["id"])}</article>')
            for asset in [x for x in parsed['assets'] if x['after']==p['id']]:
                image=data_uri(folder/asset['image'],'image/png')
                width=int((asset['rect'][2]-asset['rect'][0])*2)
                height=int((asset['rect'][3]-asset['rect'][1])*2)
                body.append(f'<article class="pair media-pair" id="{asset["id"]}"><figure class="source-figure"><div class="para-meta"><span>{esc(asset["label"])} · 原图</span><span>原文第 {asset["page"]} 页</span></div><button class="figure-open" type="button" aria-label="放大图表"><img loading="lazy" width="{width}" height="{height}" src="{image}" alt="{esc(asset.get("zh") or asset["en"])}"><span class="zoom-label">点击放大</span></button><figcaption><p class="figure-caption" lang="en">{esc(asset["en"])}</p><div class="translation"><span class="translation-label">中文图表说明</span><p>{esc(asset.get("zh", ""))}</p></div></figcaption></figure>{note_card(asset,asset["label"])}</article>')
        body.append('</section>')
    def links(item):
        return ' '.join(f'<a href="#{esc(pid)}">{esc(pid)}</a>' for pid in item.get('paragraph_ids',[]) if pid in notes)
    body.append(f'<section class="argument-overview" id="argument"><h2>全文论证结构总览</h2><p class="overview-lead">以下为基于全文重构的论证结构；缺少明确反驳时保留该事实，不替作者补写证据。</p><blockquote class="one-sentence"><small>作者核心主张 · 一句话概括</small>{esc(outline["core_claim"])}</blockquote><ol class="argument-chain">')
    for item in outline['chain']:body.append(f'<li><strong>{esc(item.get("stage",""))}</strong><p>{esc(item["text"])}</p>{links(item)}</li>')
    body.append('</ol><div class="evaluation">')
    for k,label in [('strongest','论证最强处'),('weakest','论证最弱处')]:
        item=outline[k];body.append(f'<article><h3>{label}</h3><p>{esc(item["text"])}</p>{links(item)}</article>')
    body.append(f'</div><p class="evidence-boundary"><strong>证据边界：</strong>{esc(outline["evidence_boundary"])}</p></section>')
    body.append(f'<section class="references" id="references"><h2>References · 参考文献</h2><p>书目保持原文，不作论证段落翻译；可对照内嵌 PDF。</p><details id="reference-details"><summary>展开参考文献（{len(refs)} 条）</summary><ol class="ref-list">')
    for ref in parsed['references']:body.append(f'<li id="ref-{ref["number"]}"><span class="ref-n">[{ref["number"]}]</span> {esc(ref["text"])}</li>')
    body.append('</ol></details></section>')
    body.append('<footer class="footer"><span>High_SC · 原文、译文与独立批注分开呈现</span><span>全部图片、字体与原始 PDF 已内嵌，可离线阅读。 <a href="#top">返回顶部 ↑</a></span></footer></main><dialog id="image-dialog" aria-labelledby="zoom-caption"><div class="dialog-top"><span id="zoom-caption">原图放大</span><button type="button" id="close-dialog">关闭 ×</button></div><img id="zoom-image" alt=""></dialog>')
    licenses=(fonts/'LICENSES.txt').read_text(encoding='utf-8').replace('--','- -')
    result=head+''.join(body)+'<script>'+js+'</script><!-- Font licenses:\n'+licenses+'\n--></body></html>'
    path=folder/'annotated.html';tmp=folder/'annotated.html.tmp'
    tmp.write_text(result,encoding='utf-8');tmp.replace(path)
    return path
