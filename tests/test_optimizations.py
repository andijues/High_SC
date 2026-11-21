import copy
import json
from pathlib import Path
from unittest.mock import patch

from test_workflow import WorkflowFixture
from highsc import cache, jobs, storage
from highsc.analysis import SYSTEM, annotate_batch, compact_context, paragraph_batches
from mock_provider import fixture_response


class OptimizationTest(WorkflowFixture):
    def generate(self,pid,**options):
        r=self.client.post(f'/api/papers/{pid}/generate',json=options,headers=self.headers)
        self.assertEqual(r.status_code,200,r.text)
        return self.wait_for(pid,{'completed','failed','paused'})

    def duplicate(self,pid):
        source=(storage.paper_dir(pid)/'source.pdf').read_bytes()
        r=self.client.post('/api/papers',files={'file':('same-paper.pdf',source,'application/pdf')},headers=self.headers)
        self.assertEqual(r.status_code,200,r.text);return r.json()['id']

    def test_exact_reimport_reuses_results_without_model_connection(self):
        self.save_settings();pid=self.upload();first=self.generate(pid)
        calls=len(self.mock.calls);second_id=self.duplicate(pid)
        with patch.object(jobs,'ModelClient',side_effect=AssertionError('Cache reuse must not consult the model')):
            second=self.generate(second_id)
        self.assertEqual(second['meta']['state'],'completed')
        self.assertEqual(second['notes'],first['notes']);self.assertEqual(second['outline'],first['outline'])
        self.assertEqual(second['meta']['optimization']['requests'],0)
        self.assertEqual(second['meta']['optimization']['cache_paragraphs'],2)
        self.assertEqual(len(self.mock.calls),calls)
        packet=(storage.DATA/'cache'/first['meta']['analysis_key']/'analysis.json').read_text(encoding='utf-8')
        self.assertNotIn('integration-test-secret',packet)

    def test_cached_figure_reuses_text_but_keeps_local_image_path(self):
        import pymupdf
        def add_figure(pid):
            folder=storage.paper_dir(pid);parsed=storage.read_json(folder/'parsed.json')
            (folder/'assets').mkdir(exist_ok=True)
            with pymupdf.open(folder/'source.pdf') as pdf:pdf[0].get_pixmap(clip=pymupdf.Rect(0,0,100,100)).save(folder/'assets/test.png')
            parsed['assets']=[{'id':'asset-001','label':'Figure 1','en':'Figure 1. Original test illustration.','source_text':'A test flow.','after':parsed['paragraphs'][0]['id'],'page':1,'rect':[0,0,100,100],'image':'assets/test.png'}]
            storage.atomic_json(folder/'parsed.json',parsed)
        self.save_settings();pid=self.upload();add_figure(pid);first=self.generate(pid)
        self.assertEqual(first['meta']['state'],'completed')
        second_id=self.duplicate(pid);add_figure(second_id);before=len(self.mock.calls);second=self.generate(second_id)
        self.assertEqual(second['meta']['state'],'completed');self.assertEqual(len(self.mock.calls),before)
        self.assertEqual(second['meta']['optimization']['cache_assets'],1)
        self.assertEqual(second['parsed']['assets'][0]['image'],'assets/test.png')

    def test_cache_preserves_existing_review_warnings(self):
        self.save_settings();pid=self.upload()
        def transform(payload,result):
            if payload['task']=='annotate':
                result['annotations'][0]['highlights'].append({'category':'thesis','quote':'A quote absent from the source.'})
            return result
        self.mock.transform=transform;first=self.generate(pid);second=self.generate(self.duplicate(pid))
        self.assertTrue(first['notes'][first['parsed']['paragraphs'][0]['id']]['warnings'])
        self.assertEqual(second['notes'],first['notes'])

    def test_partial_response_saves_good_paragraph_and_retries_only_missing_id(self):
        self.save_settings();pid=self.upload();batches=[]
        def transform(payload,result):
            if payload['task']=='annotate':
                batches.append([p['id'] for p in payload['paragraphs']])
                if len(batches)==1:
                    result['annotations']=result['annotations'][:1]
                    result['annotations'][0]['zh']='首次生成的完整中文译文，必须保留。'
            return result
        self.mock.transform=transform;doc=self.generate(pid)
        self.assertEqual(doc['meta']['state'],'completed')
        self.assertEqual([len(b) for b in batches],[2,1]);self.assertEqual(batches[1],[batches[0][1]])
        self.assertEqual(doc['notes'][batches[0][0]]['zh'],'首次生成的完整中文译文，必须保留。')
        self.assertEqual(doc['meta']['optimization']['repair_paragraphs'],1)

    def test_usage_keeps_reported_cached_and_reasoning_tokens(self):
        self.save_settings();self.mock.usage={'input_tokens':100,'output_tokens':80,'cached_input_tokens':60,'reasoning_output_tokens':50}
        doc=self.generate(self.upload());tokens=doc['meta']['tokens'];calls=tokens['calls']
        self.assertEqual(tokens['input'],100*calls);self.assertEqual(tokens['output'],80*calls)
        self.assertEqual(tokens['cached_input'],60*calls);self.assertEqual(tokens['reasoning_output'],50*calls)
        self.assertEqual(doc['meta']['optimization']['requests'],calls)

    def test_failed_repair_keeps_good_results_for_resume(self):
        self.save_settings();pid=self.upload();good=None
        def transform(payload,result):
            nonlocal good
            if payload['task']=='annotate':
                if good is None:good=payload['paragraphs'][0]['id']
                result['annotations']=[a for a in result['annotations'] if a['id']==good]
            return result
        self.mock.transform=transform;failed=self.generate(pid)
        self.assertEqual(failed['meta']['state'],'failed');self.assertEqual(set(failed['notes']),{good})
        self.assertEqual(failed['meta']['completed'],1)
        self.mock.transform=None;before=len(self.mock.requests);resumed=self.generate(pid)
        self.assertEqual(resumed['meta']['state'],'completed')
        payloads=[json.loads(r['messages'][-1]['content']) for r in self.mock.requests[before:]]
        self.assertEqual(len(payloads),1);self.assertNotIn(good,[p['id'] for p in payloads[0]['paragraphs']])

    def test_cache_identity_separates_models_efforts_providers_and_prompt_revision(self):
        self.save_settings();pid=self.upload();folder=storage.paper_dir(pid)
        parsed=storage.read_json(folder/'parsed.json');config=storage.load_config()
        key=cache.identity(folder,parsed,config,SYSTEM)
        for field,value in [('model','different-model'),('codex_effort','high'),('base_url','https://other.example/v1'),('api_key','different-secret'),('context_chars',96000)]:
            self.assertNotEqual(key,cache.identity(folder,parsed,{**config,field:value},SYSTEM))
        with patch.object(cache,'REVISION','next-analysis-version'):
            self.assertNotEqual(key,cache.identity(folder,parsed,config,SYSTEM))
        self.generate(pid);second=self.duplicate(pid)
        cfg={**self.settings(),'model':'different-model'}
        self.client.put('/api/settings',json=cfg,headers=self.headers)
        before=len(self.mock.calls);doc=self.generate(second)
        self.assertEqual(doc['meta']['state'],'completed');self.assertGreater(len(self.mock.calls),before)

    def test_corrupt_cached_annotation_is_regenerated_in_isolation(self):
        self.save_settings();pid=self.upload();first=self.generate(pid)
        path=cache.path_for(first['meta']['analysis_key']);packet=storage.read_json(path)
        broken=first['parsed']['paragraphs'][0]['id'];packet['notes'][broken]['id']='wrong-id';storage.atomic_json(path,packet)
        second=self.duplicate(pid);before=len(self.mock.requests);doc=self.generate(second)
        self.assertEqual(doc['meta']['state'],'completed');self.assertEqual(doc['meta']['optimization']['cache_paragraphs'],1)
        payloads=[json.loads(r['messages'][-1]['content']) for r in self.mock.requests[before:]]
        self.assertEqual(len(payloads),1);self.assertEqual([p['id'] for p in payloads[0]['paragraphs']],[broken])

    def test_broken_cache_container_is_rebuilt_and_reused_next_time(self):
        self.save_settings();pid=self.upload();first=self.generate(pid);key=first['meta']['analysis_key']
        packet=storage.read_json(cache.path_for(key));packet['notes']=[];storage.atomic_json(cache.path_for(key),packet)
        second=self.generate(self.duplicate(pid));self.assertEqual(second['meta']['state'],'completed')
        before=len(self.mock.calls);third=self.generate(self.duplicate(pid))
        self.assertEqual(third['meta']['state'],'completed');self.assertEqual(third['meta']['optimization']['requests'],0);self.assertEqual(len(self.mock.calls),before)

    def test_manual_edits_are_not_overwritten_or_shared_as_model_results(self):
        self.save_settings();pid=self.upload();first=self.generate(pid);p=first['parsed']['paragraphs'][0]
        edited={**first['notes'][p['id']],'zh':'人工校对的专属版本，应留在原任务中。'}
        self.client.put(f'/api/papers/{pid}/paragraphs/{p["id"]}',json=edited,headers=self.headers).raise_for_status()
        second=self.generate(self.duplicate(pid));self.assertEqual(second['notes'][p['id']]['zh'],first['notes'][p['id']]['zh'])
        original=self.generate(pid);self.assertEqual(original['notes'][p['id']]['zh'],edited['zh'])
        before=len(self.mock.calls);self.generate(pid,paragraph_ids=[p['id']])
        self.assertEqual(len(self.mock.calls)-before,1,'Explicit single-paragraph regeneration must bypass cache')

    def test_outline_generations_are_never_mixed_in_shared_cache(self):
        self.save_settings();pid=self.upload();first=self.generate(pid);key=first['meta']['analysis_key']
        new=copy.deepcopy(first['outline']);new['core_claim']='新版独立论证骨架'
        cache.store(key,outline=new)
        packet=storage.read_json(cache.path_for(key));self.assertEqual(packet['notes'],{});self.assertEqual(packet['assets'],{})
        # Unknown legacy provenance is kept local, rather than declared to be
        # output from the currently selected model/effort.
        folder=storage.paper_dir(pid);meta=storage.read_json(folder/'meta.json');meta.pop('analysis_key');storage.atomic_json(folder/'meta.json',meta)
        self.assertFalse(cache.eligible(folder,first['parsed'],key))

    def test_adaptive_batches_preserve_full_source_and_respect_output_budget(self):
        paragraphs=[{'id':f'p{i}','section_id':'s0','en':'A complete source paragraph. '*4} for i in range(24)]
        cfg={**storage.DEFAULT_CONFIG,'api_style':'codex'}
        groups=list(paragraph_batches(paragraphs,cfg));self.assertEqual([len(g) for g in groups],[8,8,8])
        self.assertEqual([p for g in groups for p in g],paragraphs)
        manual=list(paragraph_batches(paragraphs,{**cfg,'adaptive_batching':False}));self.assertEqual(len(manual),6)
        long={'id':'long','section_id':'s0','en':'x'*15000}
        groups=list(paragraph_batches([long,*paragraphs[:2]],cfg));self.assertEqual(groups[0],[long])
        small=list(paragraph_batches(paragraphs,{**cfg,'api_style':'chat','max_tokens':2048}));self.assertTrue(all(len(g)==1 for g in small))
        extra=list(paragraph_batches(paragraphs,{**cfg,'api_style':'chat','extra_body':{'max_completion_tokens':1024}}));self.assertTrue(all(len(g)==1 for g in extra))

    def test_adaptive_codex_timeout_scales_without_changing_model_or_effort(self):
        from highsc.provider import ModelClient
        cfg={**storage.DEFAULT_CONFIG,'api_style':'codex','model':'gpt-6.1-sol','codex_effort':'xhigh','timeout':180}
        with patch('highsc.codex_client.codex_status',return_value={'chatgpt_login':True}),patch('highsc.codex_client.request',return_value={'ok':True}) as call:
            ModelClient(cfg).request('test',{'task':'annotate','paragraphs':[{} for _ in range(6)]})
            passed=call.call_args.args[0]
            self.assertEqual(passed['timeout'],270);self.assertEqual(passed['model'],'gpt-6.1-sol');self.assertEqual(passed['codex_effort'],'xhigh')
            self.assertEqual(cfg['timeout'],180)

    def test_oversized_response_reduces_later_batch_sizes(self):
        from highsc.analysis import annotate_batch as real_annotate
        from highsc.provider import OutputTooLong
        cfg={**self.settings(),'max_tokens':32768}
        self.client.put('/api/settings',json=cfg,headers=self.headers)
        pid=self.upload();folder=storage.paper_dir(pid);parsed=storage.read_json(folder/'parsed.json')
        sid=parsed['sections'][0]['id']
        parsed['paragraphs']=[{'id':f'p{i:03d}','section_id':sid,'en':'A complete source paragraph for controlled batch recovery.','pages':[1]} for i in range(24)]
        storage.atomic_json(folder/'parsed.json',parsed);sizes=[]
        def limited(client,parsed,outline,batch):
            sizes.append(len(batch))
            if len(batch)>4:raise OutputTooLong('truncated fixture')
            return real_annotate(client,parsed,outline,batch)
        with patch.object(jobs,'annotate_batch',side_effect=limited):doc=self.generate(pid)
        self.assertEqual(doc['meta']['state'],'completed');self.assertEqual(len(doc['notes']),24)
        self.assertEqual(sizes.count(8),1);self.assertTrue(all(n<=4 for n in sizes[1:]))

    def test_compact_context_keeps_global_logic_terms_and_cross_reference_fallback(self):
        sections=[{'id':f's{i}','en':f'{i}. Methods'} for i in range(14)]
        parsed={'sections':sections};batch=[{'id':'p1','section_id':'s6','en':'A local controlled procedure.'}]
        outline={'core_claim':'核心主张','chain':[{'stage':str(i),'text':'完整逻辑'} for i in range(5)],'evidence_boundary':'未证明因果','strongest':{'text':'强处'},'weakest':{'text':'弱处'},'glossary':[{'en':'agent','zh':'智能体'}],'sections':[{'id':s['id'],'zh':'章节','logic':'本章逻辑'*20} for s in sections]}
        compact=compact_context(parsed,outline,batch)
        self.assertEqual([s['id'] for s in compact['sections']],['s5','s6','s7'])
        for k in outline.keys()-{'sections'}:self.assertEqual(compact[k],outline[k])
        self.assertLess(len(json.dumps(compact)),len(json.dumps(outline)))
        self.assertEqual(compact_context(parsed,outline,[{**batch[0],'en':'See Section 3 for the evidence.'}]),outline)
        parsed['sections'][6]['en']='Discussion';self.assertEqual(compact_context(parsed,outline,batch),outline)

    def test_sparse_repairs_keep_intervening_source_as_reference_only(self):
        parsed={'sections':[{'id':'s0','en':'Methods'}],'paragraphs':[{'id':f'p{i}','section_id':'s0','en':f'Original source paragraph {i} remains complete.'} for i in range(5)]}
        payloads=[]
        class Recorder:
            def request(self,system,payload):payloads.append(payload);return fixture_response(payload)
        notes=annotate_batch(Recorder(),parsed,{'sections':[]},[parsed['paragraphs'][0],parsed['paragraphs'][2]])
        self.assertEqual([n['id'] for n in notes],['p0','p2'])
        self.assertEqual(payloads[0]['intervening_context'],[{'id':'p1','text':parsed['paragraphs'][1]['en']}])

    def test_mock_benchmark_fewer_requests_with_identical_visible_annotations(self):
        parsed={'sections':[{'id':f's{i}','en':f'{i}. Procedure'} for i in range(12)],'paragraphs':[{'id':f'p{i}','section_id':'s5','en':'The controlled procedure preserves all source material. '*3} for i in range(24)]}
        outline={'core_claim':'核心论点','chain':[{'stage':str(i),'text':'论证链'} for i in range(5)],'evidence_boundary':'未检验','glossary':[], 'sections':[{'id':s['id'],'logic':'独立章节功能'*50} for s in parsed['sections']]}
        class Recorder:
            def __init__(self):self.calls=0;self.chars=0
            def request(self,system,payload):
                self.calls+=1;self.chars+=len(system)+len(json.dumps(payload,ensure_ascii=False));return fixture_response(payload)
        cfg={**storage.DEFAULT_CONFIG,'api_style':'codex'};baseline=Recorder();optimized=Recorder();old=[];new=[]
        with patch('highsc.analysis.compact_context',return_value=outline):
            for group in paragraph_batches(parsed['paragraphs'],{**cfg,'adaptive_batching':False}):old+=annotate_batch(baseline,parsed,outline,group)
        for group in paragraph_batches(parsed['paragraphs'],cfg):new+=annotate_batch(optimized,parsed,outline,group)
        self.assertEqual(old,new);self.assertEqual((baseline.calls,optimized.calls),(6,3));self.assertLess(optimized.chars,baseline.chars)
        print(f'Engineering fixture: calls {baseline.calls} -> {optimized.calls}; business input characters {baseline.chars} -> {optimized.chars}; identical fixture annotations (not a subscription-credit estimate).')
