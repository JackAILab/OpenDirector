const {clickEditorControl}=require('./editor_controls.cjs');
// EDIT_RETAKE_FIXTURE=1 EDIT_ACCEPTANCE_PORT=30132 python3 tests/browser/edit_suggestions_server.py
// Real source/candidate media, fixed provider output; zero external generation calls.
const {chromium}=require('playwright'),fs=require('fs'),assert=require('assert/strict');
(async()=>{const origin='http://127.0.0.1:30132',browser=await chromium.launch({headless:true,args:['--no-sandbox']});try{
 const p=await browser.newPage({viewport:{width:1512,height:982}}),errors=[];p.on('pageerror',e=>errors.push(e.message));
 const headers={Authorization:'Bearer fixture'},identity=await(await p.request.get(origin+'/acceptance/identity')).json();assert.equal(identity.fixture,'edit-retake-fixed-provider');
 const evidence=process.env.EDIT_EVIDENCE||'/tmp/edit-retake-browser';fs.mkdirSync(evidence,{recursive:true});
 await p.addInitScript(()=>sessionStorage.setItem('h3_api_key','fixture'));
 const project=await(await p.request.post(origin+'/creative/api/projects',{headers,data:{message:'重拍候选验收',duration:15}})).json(),api=origin+'/creative/api/projects/'+project.id+'/edit';
 await p.goto(origin+'/creative/editor?project='+project.id);await p.waitForFunction(()=>document.getElementById('status').textContent.includes('项目已载入'));
 await p.locator('#uploadVideo').click();await p.locator('#file').setInputFiles(identity.fixtures+'/red.mp4');await p.waitForFunction(()=>document.getElementById('status').textContent.includes('素材已导入'),{},{timeout:60000});await p.getByText('＋ 画面',{exact:true}).click();await clickEditorControl(p,'save');await p.waitForFunction(()=>document.getElementById('status').textContent==='剪辑已保存');
 let doc=await(await p.request.get(api,{headers})).json();const source=doc.spec.clips[0].source;
 doc.spec.clips=[{source,start:0,end:3,gain:.4,transition:{kind:'dissolve',duration:.4}},{source,start:0,end:3,gain:.8}];
 doc.spec.captions=[{start:.5,end:1.8,text:'Hello jacket.',word_highlight:true,words:[{text:'Hello',start:0,end:.4},{text:' jacket.',start:.6,end:1.1}]}];
 doc.spec.audio=[{source,start:0,end:2,at:3,gain:.3}];
 assert.equal((await p.request.put(api,{headers,data:{revision:doc.revision,spec:doc.spec}})).status(),200);
 await p.reload();await p.waitForFunction(()=>document.getElementById('status').textContent.includes('项目已载入'));doc=await(await p.request.get(api,{headers})).json();const before=structuredClone(doc.spec);
 await p.locator('#retake').click();await p.locator('#retakeIntent').fill('让背景光更暖，保留衣服细节和人物动作。');await p.locator('#retakePrepare').click();await p.waitForFunction(()=>!document.getElementById('retakeGenerate').hidden&&!document.getElementById('retakeGenerate').disabled,{},{timeout:60000});
 assert((await p.locator('#retakeQuote').textContent()).includes('4 积分'));
 assert.equal((await(await p.request.get(origin+'/acceptance/identity')).json()).retake_calls,identity.retake_calls);
 const prepared=await p.evaluate(()=>structuredClone(RetakeUI.job));const route=api+'/retakes/'+prepared.id;
 assert.equal((await p.request.get(route+'/input',{headers:{Authorization:'Bearer other'}})).status(),404);
 await p.screenshot({path:evidence+'/retake-ready.png'});
 await p.locator('#retakeGenerate').click();await p.waitForFunction(()=>!document.getElementById('retakeApply').hidden&&!document.getElementById('retakeApply').disabled,{},{timeout:60000});
 const completed=await(await p.request.get(route,{headers})).json();assert.equal(completed.state,'completed');assert.equal(completed.qa.semantic,'pending');
 assert.deepEqual((await(await p.request.get(api,{headers})).json()).spec,before);
 assert.equal((await p.request.post(route+'/generate',{headers,data:{revision:prepared.revision,quote_digest:prepared.quote_digest,approved_credits:4}})).status(),200);
 assert.equal((await(await p.request.get(origin+'/acceptance/identity')).json()).retake_calls,identity.retake_calls+1);
 await p.locator('#retakeCandidate').evaluate(async v=>{v.muted=true;await v.play()});await p.waitForFunction(()=>document.getElementById('retakeCandidate').currentTime>.2);await p.locator('#retakeCandidate').evaluate(v=>v.pause());await p.screenshot({path:evidence+'/retake-candidate.png'});
 await p.setViewportSize({width:390,height:844});assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);await p.locator('#retakeApply').scrollIntoViewIfNeeded();await p.screenshot({path:evidence+'/retake-mobile.png'});
 await p.evaluate(()=>document.documentElement.dataset.theme='light');await p.screenshot({path:evidence+'/retake-light.png'});await p.evaluate(()=>document.documentElement.dataset.theme='dark');await p.setViewportSize({width:1512,height:982});
 await p.locator('#retakeApply').click();await p.waitForFunction(()=>document.getElementById('retakePanel').hidden);let draft=await p.evaluate(()=>structuredClone(spec));
 assert.equal(draft.duration,before.duration);assert.deepEqual(draft.captions,before.captions);assert.deepEqual(draft.audio,before.audio);assert.deepEqual(draft.clips[0].transition,before.clips[0].transition);assert.equal(draft.clips[0].gain,.4);assert.equal(draft.clips[0].source,completed.asset);
 await p.locator('#undo').click();assert.deepEqual(await p.evaluate(()=>structuredClone(spec)),before);await p.locator('#redo').click();
 await clickEditorControl(p,'save');await p.waitForFunction(()=>document.getElementById('status').textContent==='剪辑已保存');await p.reload();await p.waitForFunction(()=>document.getElementById('status').textContent.includes('项目已载入'));assert.equal(await p.evaluate(()=>spec.clips[0].source),completed.asset);
 // A candidate from an old timeline can be viewed, but not blindly applied again.
 await p.locator('#retake').click();await p.locator('#retakeHistory').selectOption(prepared.id);await p.waitForFunction(()=>!document.getElementById('retakeApply').hidden);assert(await p.locator('#retakeApply').isDisabled());await p.locator('#closeRetake').click();
 await p.locator('#export').click();await p.waitForFunction(()=>!document.getElementById('download').hidden||document.getElementById('status').textContent.includes('导出未通过'),{},{timeout:180000});
 const result=await(await p.request.get(api,{headers})).json();assert.equal(result.export.state,'completed',JSON.stringify(result.export));
 fs.writeFileSync(evidence+'/retake-edit.mp4',await(await p.request.get(api+'/media',{headers})).body());
 assert.deepEqual(errors,[]);fs.writeFileSync(evidence+'/acceptance.json',JSON.stringify({project:project.id,job:completed,qa:result.export.qa,spec:result.spec,provider:'fixed color fixture, not a generation quality evaluation',paid_calls:false},null,2));
 console.log('PASS: explicit quote, owned video input, one submission, source retention, candidate comparison, mobile/themes, exact timing/audio/captions, undo, stale rejection, reload and real MP4 export. '+evidence);
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exit(1)});
