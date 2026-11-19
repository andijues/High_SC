'use strict';
const $=(s,r=document)=>r.querySelector(s), $$=(s,r=document)=>[...r.querySelectorAll(s)];
const E=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const token=$('meta[name="highsc-token"]').content;
const state={papers:[],settings:null,selected:null,data:null,tab:'progress',paragraph:null,filter:'',reviewOnly:false,importing:false,drafts:new Map(),toastTimer:null};
const labels={ready:'待生成',queued:'排队中',running:'生成中',pausing:'正在暂停',paused:'已暂停',failed:'需要处理',completed:'已完成'};
const tones={thesis:'黄色 · 核心论点',term:'红色 · 关键概念',evidence:'蓝色 · 证据数据',concession:'绿色 · 让步反驳',method:'紫色 · 方法说明'};

async function api(url,options={}){
  const opts={...options,headers:{...(options.headers||{})}};
  if(options.method&&options.method!=='GET')opts.headers['X-HighSC-Token']=token;
  if(opts.body&&!(opts.body instanceof FormData)&&typeof opts.body!=='string'){opts.headers['Content-Type']='application/json';opts.body=JSON.stringify(opts.body)}
  const r=await fetch('/api'+url,opts);let result;
  try{result=await r.json()}catch{throw Error(`请求未完成（HTTP ${r.status}），请查看本机服务状态`)}
  if(!r.ok)throw Error(typeof result.detail==='string'?result.detail:JSON.stringify(result.detail||result));
  return result;
}
function toast(message,error=false){clearTimeout(state.toastTimer);const el=$('#toast');el.textContent=message;el.classList.toggle('error',error);el.hidden=false;state.toastTimer=setTimeout(()=>el.hidden=true,error?9000:4000)}
function configured(){return !!(state.settings?.model&&(state.settings.api_style==='codex'||state.settings.base_url))}
function busy(meta=state.data?.meta){return ['running','queued','pausing'].includes(meta?.state)}
function status(meta){return `<span class="status-label ${E(meta.state)}">${E(labels[meta.state]||meta.state)}</span>`}
function template(id){$('#content').replaceChildren($(id).content.cloneNode(true))}
function nav(page){$$('.app-header nav a').forEach(a=>a.classList.toggle('active',a.dataset.page===page))}

function renderLibrary(){
  $('#paper-list').innerHTML=state.papers.length?state.papers.map(p=>`<button class="paper-item ${p.id===state.selected?'selected':''}" data-paper="${p.id}" title="${E(p.title)}"><strong>${E(p.title)}</strong><small><span>${p.pages} 页 · ${p.completed||0}/${p.total} 段</span><span>${E(labels[p.state]||p.state)}</span></small></button>`).join(''):'<p class="library-empty">还没有导入论文。<br>选择 PDF，开始你的第一篇精读。</p>';
}
async function refreshLibrary(){state.papers=await api('/papers');renderLibrary()}

function welcome(){
  state.selected=null;state.data=null;nav('workspace');renderLibrary();template('#welcome-template');
  $('#setup-hint').hidden=configured();
  const drop=$('#drop-zone');drop.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();$('#file-input').click()}});
  for(const event of ['dragenter','dragover'])drop.addEventListener(event,e=>{e.preventDefault();drop.classList.add('dragover')});
  for(const event of ['dragleave','drop'])drop.addEventListener(event,e=>{e.preventDefault();drop.classList.remove('dragover')});
  drop.addEventListener('drop',e=>{if(e.dataTransfer.files.length)importPDF(e.dataTransfer.files[0])});
}
async function importPDF(file){
  if(state.importing||!file)return;
  if(!file.name.toLowerCase().endsWith('.pdf'))return toast('请选择英文 PDF 文件',true);
  if(file.size>100*1024*1024)return toast('PDF 超过 100 MB，请先压缩或拆分',true);
  const auto=$('#auto-generate')?.checked??true,ocr=$('#enable-ocr')?.checked??false;
  state.importing=true;$('#file-input').disabled=true;$('#import-small').disabled=true;
  const info=$('#import-status');if(info)info.textContent='正在解析 PDF、识别段落与图表，请稍候…';
  try{
    const form=new FormData();form.append('file',file);form.append('ocr',String(ocr));form.append('auto_generate',String(auto&&configured()));
    const result=await api('/papers',{method:'POST',body:form});await refreshLibrary();location.hash='paper/'+result.id;
    if(auto&&!configured())toast('论文已解析，请先完成模型设置，再开始生成');
  }catch(e){toast(e.message,true);if(info)info.textContent='导入未完成，请检查 PDF 后重试。'}
  finally{state.importing=false;$('#file-input').disabled=false;$('#import-small').disabled=false;$('#file-input').value=''}
}

function settingsPage(){
  state.selected=null;state.data=null;nav('settings');renderLibrary();template('#settings-template');
  const f=$('#settings-form'),c=state.settings;
  for(const [key,value] of Object.entries(c||{})){const input=f.elements[key];if(!input)continue;if(input.type==='checkbox')input.checked=!!value;else input.value=key==='extra_body'?JSON.stringify(value||{},null,2):value}
  f.elements.api_key.value='';f.elements.extra_headers.value='';$('#headers-state').textContent=c?.has_extra_headers?'已有自定义请求头，留空保留；填写新 JSON 将整体替换。':'留空保留；使用 ${API_KEY} 引用上方密钥。Windows 下加密保存，不回显。';$('#key-state').textContent=c?.has_api_key?'已保存密钥，留空会保留。Windows 下由当前账户加密。':'Windows 下使用当前账户加密保存。';
  f.addEventListener('submit',async e=>{e.preventDefault();const button=$('#save-settings');button.disabled=true;try{const v=readSettings();state.settings=await api('/settings',{method:'PUT',body:v});f.elements.api_key.value='';f.elements.clear_api_key.checked=false;f.elements.extra_headers.value='';f.elements.clear_extra_headers.checked=false;$('#headers-state').textContent=state.settings.has_extra_headers?'已有自定义请求头，留空保留；填写新 JSON 将整体替换。':'未保存自定义请求头。';$('#key-state').textContent=state.settings.has_api_key?'已保存密钥，留空会保留。Windows 下由当前账户加密。':'未保存密钥，本地免密服务可正常使用。';settingStatus('配置已保存',false);toast('模型配置已保存')}catch(err){settingStatus(err.message,true)}finally{button.disabled=false}});
  f.elements.api_style.addEventListener('change',()=>updateProviderFields());updateProviderFields();
  $('#test-settings').addEventListener('click',async()=>{if(!f.reportValidity())return;const b=$('#test-settings');b.disabled=true;settingStatus('正在测试连接与 JSON 输出…',false);try{const result=await api('/settings/test',{method:'POST',body:readSettings()});settingStatus(result.message,false)}catch(e){settingStatus(e.message,true)}finally{b.disabled=false}});
}
async function updateProviderFields(){
  const f=$('#settings-form');if(!f)return;const codex=f.elements.api_style.value==='codex';
  for(const el of $$('[data-api-only]',f)){el.hidden=codex;$$('input,select,textarea',el).forEach(i=>i.disabled=codex)}
  for(const el of $$('[data-codex-only]',f)){el.hidden=!codex;$$('input,select,textarea',el).forEach(i=>i.disabled=!codex)}
  f.elements.base_url.required=!codex;$('#codex-info').hidden=!codex;
  $('#provider-description').textContent=codex?'复用本机官方 Codex 的 ChatGPT 登录，生成内容使用你的 Codex 额度，无需 API Key。':'配置保存在本机。生成时，提取的论文文本会发送到所填 API 服务。';
  $('#test-settings').textContent=codex?'测试 Codex 调用':'测试连接';
  if(codex){$('#codex-login-state').textContent='正在检查本机登录…';try{const status=await api('/codex/status');if($('#settings-form')?.elements.api_style.value==='codex')$('#codex-login-state').textContent=status.message}catch(e){if($('#codex-login-state'))$('#codex-login-state').textContent=e.message}}
}
function settingStatus(text,error){const el=$('#settings-status');el.textContent=text;el.classList.toggle('error-text',error);el.classList.toggle('success-text',!error)}
function readSettings(){
  const f=$('#settings-form');const value={};
  for(const name of ['base_url','model','api_style','api_key','proxy','codex_path','codex_effort','auth_mode','endpoint_mode','token_field'])value[name]=f.elements[name].value.trim();
  for(const name of ['timeout','max_tokens','batch_size','context_chars','retries','temperature'])value[name]=Number(f.elements[name].value);
  for(const name of ['json_mode','send_temperature','clear_api_key','clear_extra_headers'])value[name]=f.elements[name].checked;
  if(value.api_style==='codex'){value.api_key='';value.clear_api_key=false;value.extra_body=state.settings?.extra_body||{}}
  else try{value.extra_body=JSON.parse(f.elements.extra_body.value||'{}')}catch{throw Error('额外请求参数不是有效 JSON')}
  if(!value.extra_body||Array.isArray(value.extra_body)||typeof value.extra_body!=='object')throw Error('额外参数必须是 JSON 对象');
  value.extra_headers=null;
  if(value.api_style==='codex')value.clear_extra_headers=false;
  else if(f.elements.extra_headers.value.trim()){
    try{value.extra_headers=JSON.parse(f.elements.extra_headers.value)}catch{throw Error('自定义请求头不是有效 JSON')}
    if(!value.extra_headers||Array.isArray(value.extra_headers)||typeof value.extra_headers!=='object'||Object.values(value.extra_headers).some(v=>typeof v!=='string'))throw Error('请求头必须是字符串值的 JSON 对象');
  }
  return value;
}

async function loadPaper(id){
  state.selected=id;nav('workspace');renderLibrary();
  $('#content').innerHTML='<p class="empty-state">正在打开论文…</p>';
  try{const data=await api('/papers/'+id);if(state.selected!==id)return;state.data=data;state.tab='progress';state.paragraph=null;state.filter='';state.reviewOnly=false;renderPaper()}catch(e){$('#content').innerHTML=`<p class="job-error">${E(e.message)}</p>`}
}
function renderPaper(){
  const d=state.data;if(!d)return;const m=d.meta;
  const ready=m.export_ready,active=busy(m);
  $('#content').innerHTML=`<section class="paper-workspace"><div class="paper-heading"><div class="paper-title"><h1 lang="en">${E(m.title)}</h1><p>${m.pages} 页 · ${d.parsed.paragraphs.length} 段正文 · ${d.parsed.assets.length} 项图表 · ${d.parsed.references.length} 条参考文献</p></div><a class="source-link" target="_blank" rel="noopener" href="/api/papers/${m.id}/source">查看原始 PDF ↗</a></div><div class="paper-actions">${active?`<button class="button secondary" data-action="pause" ${m.state==='pausing'?'disabled':''}>${m.state==='pausing'?'等待当前请求结束':'暂停生成'}</button>`:`<button class="button primary" data-action="generate">${m.state==='completed'?'检查并继续':m.completed?'继续生成':'开始生成'}</button>`}<button class="button secondary" data-action="export" ${active?'disabled':''}>更新 HTML</button>${ready?`<a class="button secondary" href="/api/papers/${m.id}/html" target="_blank" rel="noopener">预览成品 ↗</a><a class="button secondary" href="/api/papers/${m.id}/html?download=1">下载 HTML</a>`:''}${status(m)}</div><nav class="paper-tabs" aria-label="论文工作区">${[['progress','生成进度'],['notes','段落校对'],['assets','图表'],['outline','论证总览']].map(([k,v])=>`<button data-tab="${k}" class="${state.tab===k?'active':''}">${v}</button>`).join('')}</nav><div id="paper-tab-content"></div></section>`;
  renderTab();
}
function renderTab(){
  $$('.paper-tabs button').forEach(b=>b.classList.toggle('active',b.dataset.tab===state.tab));
  if(state.tab==='notes')renderNotes();else if(state.tab==='assets')renderAssets();else if(state.tab==='outline')renderOutline();else renderProgress();
}
function renderProgress(){
  const d=state.data,m=d.meta;const done=m.completed||0,total=m.total||1,pct=Math.round(done/total*100);
  const stages=[['outline','全文论证骨架'],['paragraphs','段落翻译与批注'],['assets','图表说明'],['export','核对与离线打包']];const idx=stages.findIndex(([s])=>s===m.stage);
  $('#paper-tab-content').innerHTML=`${m.error?`<div class="job-error"><strong>需要处理</strong><br>${E(m.error)}<br><a href="#settings">检查模型设置</a> 后，可继续生成。</div>`:''}<div class="progress-layout"><section class="progress-main"><h2>${E(labels[m.state])}</h2><p class="progress-message">${E(m.message)}</p><div class="progress-numbers"><span>${done} / ${m.total} 段已完成</span><span>${pct}%</span></div><div class="progress-track" role="progressbar" aria-label="段落生成进度" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${pct}"><span style="width:100%;transform:scaleX(${pct/100})"></span></div><ol class="stage-list">${stages.map(([key,title],i)=>`<li class="${m.state==='completed'||idx>i?'done':idx===i?'active':''}"><b>${i+1}</b>${title}</li>`).join('')}</ol><div class="parse-stats">已经提取 ${d.parsed.sections.length} 个章节、${d.parsed.paragraphs.length} 个正文段落与 ${d.parsed.assets.length} 项图表。${m.tokens?`<br>累计 ${m.tokens.calls} 次模型响应 · 输入 ${m.tokens.input.toLocaleString()} / 输出 ${m.tokens.output.toLocaleString()} tokens`:''}</div>${d.review?.length?`<p class="review-note">${d.review.length} 项核对线索，可在“段落校对”中查看。</p>`:''}${d.parsed.warnings.length?`<details class="warnings"><summary>解析核对提示（${d.parsed.warnings.length} 项）</summary><ul>${d.parsed.warnings.map(w=>`<li>${E(w)}</li>`).join('')}</ul></details>`:''}</section><section class="log-panel"><h2>任务记录</h2><ul class="log-list">${(m.events||[]).slice().reverse().map(e=>`<li><time>${E(e.time.slice(11,19))}</time><span>${E(e.message)}</span></li>`).join('')}</ul></section></div>`;
}
function renderAssets(){
  const d=state.data;if(!d.parsed.assets.length){$('#paper-tab-content').innerHTML='<p class="empty-state">尚未识别到带图题的图表。原始 PDF 始终保留，可打开核对。</p>';return}
  $('#paper-tab-content').innerHTML=`<div class="asset-grid">${d.parsed.assets.map(a=>`<article class="asset-item"><a target="_blank" rel="noopener" href="/api/papers/${d.meta.id}/assets/${a.id}"><img src="/api/papers/${d.meta.id}/assets/${a.id}" alt="${E(a.label)}，第 ${a.page} 页" loading="lazy"></a><h3>${E(a.label)} · 第 ${a.page} 页</h3><p class="asset-source">${E(a.en)}</p><p>${E(a.zh||'等待模型生成中文说明')}</p>${a.critique?`<p><strong>论证审视：</strong>${E(a.critique)}</p>`:''}</article>`).join('')}</div>`;
}
function renderOutline(){
  const o=state.data.outline;if(!o){$('#paper-tab-content').innerHTML='<p class="empty-state">开始生成后，会先在这里建立全文论证骨架。</p>';return}
  $('#paper-tab-content').innerHTML=`<div class="outline-core">${E(o.core_claim)}</div><div class="outline-chain">${o.chain.map(i=>`<article><h3>${E(i.stage)}</h3><p>${E(i.text)}</p></article>`).join('')}</div><div class="outline-evaluation"><article><h3>论证最强处</h3><p>${E(o.strongest.text)}</p></article><article><h3>论证最弱处</h3><p>${E(o.weakest.text)}</p></article></div><p class="outline-boundary"><strong>证据边界：</strong>${E(o.evidence_boundary)}</p>`;
}

function renderNotes(){
  const d=state.data;$('#paper-tab-content').innerHTML=`${busy()?'<p class="review-note">生成期间可以阅读原文；暂停后可编辑批注。</p>':''}<div class="editor-toolbar"><input type="search" id="paragraph-filter" aria-label="查找段落" placeholder="搜索英文、译文或批注" value="${E(state.filter)}"><label><input type="checkbox" id="review-filter" ${state.reviewOnly?'checked':''}> 只看有核对提示的段落</label></div><div class="editor-layout"><div class="paragraph-list" id="paragraph-list"></div><div class="editor-content" id="editor-content"></div></div>`;
  $('#paragraph-filter').addEventListener('input',e=>{captureDraft();state.filter=e.target.value;renderParagraphList()});
  $('#review-filter').addEventListener('change',e=>{captureDraft();state.reviewOnly=e.target.checked;renderParagraphList()});renderParagraphList();
}
function filteredParagraphs(){
  const d=state.data,q=state.filter.trim().toLowerCase();return d.parsed.paragraphs.filter(p=>{const a=d.notes[p.id]||{};const match=!q||(p.en+' '+(a.zh||'')+' '+(a.critique||'')).toLowerCase().includes(q);return match&&(!state.reviewOnly||(a.review_flags?.length||a.warnings?.length))});
}
function renderParagraphList(){
  const items=filteredParagraphs();if(!items.some(p=>p.id===state.paragraph))state.paragraph=items[0]?.id||null;
  $('#paragraph-list').innerHTML=items.map(p=>`<button class="paragraph-button ${state.paragraph===p.id?'active':''}" data-paragraph="${p.id}"><strong>${p.id} · 第 ${p.pages.join('、')} 页 ${state.data.notes[p.id]?'':'· 待生成'}</strong><span>${E(state.data.notes[p.id]?.function||p.en)}</span></button>`).join('')||'<p class="field-hint">没有匹配段落。</p>';renderEditor();
}
function draftKey(){return state.selected+':'+state.paragraph}
function renderEditor(){
  const p=state.data.parsed.paragraphs.find(p=>p.id===state.paragraph);if(!p){$('#editor-content').innerHTML='';return}
  const a=state.drafts.get(draftKey())||state.data.notes[p.id]||{id:p.id,zh:'',function:'',logic:'',critique:'',tone:'method',highlights:[],support_quotes:[]};
  const flags=[...(a.review_flags||[]),...(a.warnings||[])];
  $('#editor-content').innerHTML=`<div class="editor-source"><div class="source-meta"><span>${p.id} · 原文第 ${p.pages.join('、')} 页</span><span>英文原文固定保留</span></div><p id="english-preview" lang="en"></p></div>${flags.length?`<div class="editor-hints">${flags.map(w=>`<p>${E(w)}</p>`).join('')}</div>`:''}<form id="annotation-form"><fieldset ${busy()?'disabled':''} style="border:0;padding:0;margin:0"><div class="annotation-form"><label class="full">中文译文<textarea name="zh" rows="7" required>${E(a.zh)}</textarea></label><label>段落功能<input name="function" value="${E(a.function)}" required></label><label>批注颜色<select name="tone">${Object.entries(tones).map(([k,v])=>`<option value="${k}" ${k===a.tone?'selected':''}>${v}</option>`).join('')}</select></label><label class="full">逻辑角色<textarea name="logic" rows="3" required>${E(a.logic)}</textarea></label><label class="full">论证技巧或潜在漏洞<textarea name="critique" rows="4" required>${E(a.critique)}</textarea></label><div class="highlight-editor"><div class="highlight-heading"><h3>英文高亮片段</h3><button type="button" class="text-button" id="add-highlight">添加片段</button></div><div id="highlight-rows">${(a.highlights||[]).map(highlightRow).join('')}</div><small>粘贴原文中的连续片段；保存时会检查精确匹配和重叠。</small></div></div><div class="editor-actions"><button class="button primary" type="submit">保存本段修改</button><button class="button secondary" type="button" data-action="regenerate">用模型重做此段</button><span id="editor-save-status">${a.edited?'已人工修改':state.drafts.has(draftKey())?'有未保存修改':''}</span></div></fieldset></form>`;
  paintEnglish(p.en,a.highlights||[]);
  const form=$('#annotation-form');form.addEventListener('input',()=>{form.dataset.dirty='true';captureDraft();$('#editor-save-status').textContent='有未保存修改';paintEnglish(p.en,readEditor().highlights)});
  form.addEventListener('submit',saveParagraph);
  $('#add-highlight').addEventListener('click',()=>{if($$('.highlight-row').length>=8)return toast('每段最多 8 个高亮片段');$('#highlight-rows').insertAdjacentHTML('beforeend',highlightRow({category:'thesis',quote:''}));form.dataset.dirty='true';captureDraft()});
}
function highlightRow(h){return `<div class="highlight-row"><select aria-label="高亮类别">${Object.entries(tones).map(([k,v])=>`<option value="${k}" ${h.category===k?'selected':''}>${v}</option>`).join('')}</select><textarea rows="2" aria-label="英文原文片段">${E(h.quote)}</textarea><button type="button" data-remove-highlight aria-label="移除此高亮">×</button></div>`}
function readEditor(){const f=$('#annotation-form');if(!f)return null;const old=state.data.notes[state.paragraph]||{};return {...old,id:state.paragraph,zh:f.elements.zh.value,function:f.elements.function.value,logic:f.elements.logic.value,critique:f.elements.critique.value,tone:f.elements.tone.value,highlights:$$('.highlight-row',f).map(r=>({category:$('select',r).value,quote:$('textarea',r).value})).filter(h=>h.quote.trim()),support_quotes:old.support_quotes||[]}}
function captureDraft(){if($('#annotation-form')?.dataset.dirty==='true'){const a=readEditor();state.drafts.set(draftKey(),a)}}
function paintEnglish(text,highlights){
  const el=$('#english-preview');if(!el)return;el.replaceChildren();let end=0;const intervals=[];
  for(const h of highlights){const start=text.indexOf(h.quote);if(h.quote&&start>=0&&!intervals.some(x=>start<x.end&&start+h.quote.length>x.start))intervals.push({start,end:start+h.quote.length,category:h.category})}
  for(const i of intervals.sort((a,b)=>a.start-b.start)){el.append(document.createTextNode(text.slice(end,i.start)));const mark=document.createElement('mark');mark.className=i.category;mark.textContent=text.slice(i.start,i.end);el.append(mark);end=i.end}el.append(document.createTextNode(text.slice(end)));
}
async function saveParagraph(e){
  e.preventDefault();const b=$('#annotation-form button[type=submit]');b.disabled=true;
  try{const value=await api(`/papers/${state.selected}/paragraphs/${state.paragraph}`,{method:'PUT',body:readEditor()});state.data.notes[state.paragraph]=value;state.drafts.delete(draftKey());state.data.meta.export_ready=false;renderPaper();$('#editor-save-status').textContent='已保存，更新 HTML 后生效';toast('本段修改已保存');await refreshLibrary()}catch(err){toast(err.message,true)}finally{if(b.isConnected)b.disabled=false}
}

async function action(name,button){
  if(!state.selected)return;
  if(button)button.disabled=true;
  try{
    if(name==='generate'||name==='regenerate'){
      if(!configured()){toast('请先完成并保存模型设置',true);location.hash='settings';return}
      const opts=name==='regenerate'?{paragraph_ids:[state.paragraph]}:{};
      if(name==='regenerate')state.drafts.delete(draftKey());
      await api(`/papers/${state.selected}/generate`,{method:'POST',body:opts});state.tab='progress';
    }else if(name==='pause')await api(`/papers/${state.selected}/pause`,{method:'POST'});
    else if(name==='export'){await api(`/papers/${state.selected}/export`,{method:'POST'});toast('HTML 已更新，可以预览或下载')}
    state.data=await api('/papers/'+state.selected);renderPaper();await refreshLibrary();
  }catch(e){toast(e.message,true)}finally{if(button&&button.isConnected)button.disabled=false}
}

async function route(){
  const hash=location.hash.slice(1)||'workspace';
  if(hash==='settings')settingsPage();else if(hash==='help'){state.selected=null;state.data=null;nav('help');renderLibrary();template('#help-template')}
  else if(/^paper\/[a-f0-9]{32}$/.test(hash))await loadPaper(hash.slice(6));else welcome();
}
document.addEventListener('click',async e=>{
  const paper=e.target.closest('[data-paper]');if(paper){captureDraft();location.hash='paper/'+paper.dataset.paper;return}
  const tab=e.target.closest('[data-tab]');if(tab){captureDraft();state.tab=tab.dataset.tab;try{state.data=await api('/papers/'+state.selected)}catch(err){toast(err.message,true)}renderTab();return}
  const p=e.target.closest('[data-paragraph]');if(p){captureDraft();state.paragraph=p.dataset.paragraph;renderParagraphList();return}
  const remove=e.target.closest('[data-remove-highlight]');if(remove){remove.closest('.highlight-row').remove();$('#annotation-form').dataset.dirty='true';captureDraft();const p=state.data.parsed.paragraphs.find(p=>p.id===state.paragraph);paintEnglish(p.en,readEditor().highlights);return}
  const b=e.target.closest('[data-action]');if(b)await action(b.dataset.action,b);
});
$('#import-small').addEventListener('click',()=>$('#file-input').click());
$('#file-input').addEventListener('change',e=>importPDF(e.target.files[0]));
window.addEventListener('hashchange',()=>{captureDraft();route()});
let polling=false;
setInterval(async()=>{
  if(polling||state.importing)return;polling=true;
  try{
    await refreshLibrary();const m=state.papers.find(p=>p.id===state.selected);
    if(m&&state.data){const previous=state.data.meta;const stateChanged=m.state!==previous.state;const changed=stateChanged||m.updated_at!==previous.updated_at||m.completed!==previous.completed||m.export_ready!==previous.export_ready;state.data.meta=m;if(changed&&(state.tab!=='notes'||stateChanged)){captureDraft();state.data=await api('/papers/'+state.selected);renderPaper()}}
    $('#connection-state').textContent='本机运行';
  }catch{$('#connection-state').textContent='服务未连接'}finally{polling=false}
},2200);
(async()=>{try{[state.settings,state.papers]=await Promise.all([api('/settings'),api('/papers')]);renderLibrary();await route()}catch(e){$('#content').innerHTML=`<p class="job-error">${E(e.message)}<br>请重新启动 High_SC 后刷新页面。</p>`}})();
