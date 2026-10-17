const {clickEditorControl}=require('./editor_controls.cjs');
// Fixed ASR observations, real owned media and HyperFrames export; no provider calls.
// EDIT_SPEECH_FIXTURE=1 EDIT_ACCEPTANCE_PORT=30131 python3 tests/browser/edit_suggestions_server.py
const {chromium}=require('playwright'),fs=require('fs'),path=require('path'),assert=require('assert/strict');
(async()=>{const origin='http://127.0.0.1:30131',browser=await chromium.launch({headless:true,args:['--no-sandbox']});try{
 const p=await browser.newPage({viewport:{width:1512,height:982}}),errors=[];p.on('pageerror',e=>errors.push(e.message));
 const identity=await(await p.request.get(origin+'/acceptance/identity')).json(),headers={Authorization:'Bearer fixture'};
 assert.equal(identity.fixture,'edit-speech-fixed-model');const evidence=process.env.EDIT_EVIDENCE||'/tmp/edit-word-browser';fs.mkdirSync(evidence,{recursive:true});
 await p.addInitScript(()=>sessionStorage.setItem('h3_api_key','fixture'));
 const project=await(await p.request.post(origin+'/creative/api/projects',{headers,data:{message:'逐词字幕校对验收',duration:15}})).json(),api=origin+'/creative/api/projects/'+project.id+'/edit';
 await p.goto(origin+'/creative/editor?project='+project.id);await p.waitForFunction(()=>document.getElementById('status').textContent.includes('项目已载入'));
 await clickEditorControl(p,'editorMediaToggle');await p.locator('#uploadVideo').click();await p.locator('#file').setInputFiles(identity.fixtures+'/red.mp4');await p.waitForFunction(()=>document.getElementById('status').textContent.includes('素材已导入'),{},{timeout:60000});await p.getByText('＋ 画面',{exact:true}).click();
 await p.getByText('口播',{exact:true}).click();await p.locator('#transcribeSpeech').click();await p.waitForFunction(()=>document.querySelectorAll('.speech-segment').length===1,{},{timeout:60000});await p.locator('#addSpeechCaptions').click();await p.waitForFunction(()=>document.getElementById('speechPanel').hidden);
 await p.locator('.caption-list-item').click();assert(await p.locator('#text').evaluate(e=>e.readOnly));assert(await p.locator('#wordHighlight').isChecked());
 await p.locator('#detachWords').click();await p.locator('#speechCaptions').click();await p.waitForFunction(()=>document.getElementById('status').textContent.includes('旧字幕补齐'));assert.equal(await p.locator('.caption-list-item').count(),1);
 await p.locator('#wordDetails summary').click();assert.equal(await p.locator('.word-row').count(),2);
 await p.getByLabel('第 2 词文字',{exact:true}).fill(' coat.');await p.getByLabel('第 2 词起点',{exact:true}).fill('.65');await p.locator('#apply').click();assert.equal(await p.locator('#text').inputValue(),'Hello coat.');
 await p.locator('#undo').click();assert.equal(await p.locator('#text').inputValue(),'Hello jacket.');await p.locator('#redo').click();
 // Move the whole phrase: relative word timings remain unchanged.
 await p.locator('#start').fill('.75');await p.locator('#end').fill('1.85');await p.locator('#apply').click();assert.equal(await p.getByLabel('第 2 词起点',{exact:true}).inputValue(),'0.65');
 await p.locator('#end').fill('1.4');await p.locator('#apply').click();assert((await p.locator('#status').textContent()).includes('逐词时间'));await p.locator('#end').fill('1.85');
 await p.getByLabel('第 2 词起点',{exact:true}).fill('.3');await p.locator('#apply').click();assert((await p.locator('#status').textContent()).includes('不重叠'));await p.getByLabel('第 2 词起点',{exact:true}).fill('.65');await p.locator('#apply').click();
 async function seek(t){await p.locator('#scrub').evaluate((e,t)=>{e.value=t;e.dispatchEvent(new Event('input'))},t);await p.waitForFunction(()=>[...document.querySelectorAll('#pictures video:not([hidden])')].every(v=>v.readyState>=2&&!v.seeking))}
 async function active(){return p.locator('#subtitles [data-word-index]').evaluateAll(es=>es.flatMap((e,i)=>getComputedStyle(e).backgroundColor==='rgb(247, 219, 116)'?[i]:[]))}
 for(const [time,expected] of [[.8,[0]],[1.2,[]],[1.45,[1]],[1.85,[]],[.8,[0]]]){await seek(time);assert.deepEqual(await active(),expected)}
 await p.locator('#wordHighlight').uncheck();await p.locator('#apply').click();await seek(.8);assert.deepEqual(await active(),[]);await p.locator('#undo').click();await seek(.8);assert.deepEqual(await active(),[0]);
 await p.locator('#detachWords').click();assert.equal(await p.locator('#text').evaluate(e=>e.readOnly),false);await p.locator('#undo').click();assert.equal(await p.locator('.word-row').count(),2);
 await p.getByLabel('回放第 2 词',{exact:true}).click();await p.waitForFunction(()=>document.getElementById('play').textContent==='▶'&&Math.abs(Number(document.getElementById('scrub').value)-1.85)<.02,{},{timeout:15000});
 await clickEditorControl(p,'save');await p.waitForFunction(()=>document.getElementById('status').textContent.includes('剪辑已保存'));
 // Literal markup in aligned words must remain inert in preview and frozen export.
 let doc=await(await p.request.get(api,{headers})).json();assert.equal(doc.spec.captions[0].words[1].start,.65);
 doc.spec.captions.push({start:.3,end:2.8,track:1,text:'逐词 <script>safe</script>',word_highlight:true,words:[{text:'逐词 ',start:0,end:.7},{text:'<script>safe</script>',start:1.1,end:2.3}],appearance:{preset:'accent',size:'small',motion:'rise'}});
 assert.equal((await p.request.put(api,{headers,data:{revision:doc.revision,spec:doc.spec}})).status(),200);
 await p.reload();await p.waitForFunction(()=>document.getElementById('status').textContent.includes('项目已载入'));await clickEditorControl(p,'editorMediaToggle');await p.locator('#captionsTab').click();await p.locator('.caption-list-item').filter({hasText:'Hello coat.'}).click();await p.locator('#wordDetails summary').click();
 await seek(1.45);assert.equal(await p.locator('#subtitles script').count(),0);await p.screenshot({path:evidence+'/word-workspace.png'});
 // The left trim handle clamps at the first spoken word and preserves source-aligned word times.
 const clip=p.locator('.clip.captions').first(),bounds=await clip.boundingBox();await p.mouse.move(bounds.x+3,bounds.y+bounds.height/2);await p.mouse.down();await p.mouse.move(bounds.x+80,bounds.y+bounds.height/2,{steps:5});await p.mouse.up();assert.equal(await p.locator('#start').inputValue(),'0.75');
 await p.setViewportSize({width:390,height:844});await clickEditorControl(p,'settings');await p.locator('.caption-list-item').filter({hasText:'Hello coat.'}).click();assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);assert.equal(await p.evaluate(()=>{const a=document.querySelector('.subtitle')?.getBoundingClientRect(),b=document.querySelector('.inspector').getBoundingClientRect();if(!a)return false;const left=Math.max(a.left,b.left),right=Math.min(a.right,b.right),top=Math.max(a.top,b.top),bottom=Math.min(a.bottom,b.bottom);return left<right&&top<bottom&&!!document.elementFromPoint((left+right)/2,(top+bottom)/2)?.closest('.inspector')}),true);await p.screenshot({path:evidence+'/word-mobile.png'});await clickEditorControl(p,'settings');await p.setViewportSize({width:1512,height:982});
 await p.locator('#export').click();await p.waitForFunction(()=>!document.getElementById('download').hidden||document.getElementById('status').textContent.includes('导出未通过'),{},{timeout:180000});
 const result=await(await p.request.get(api,{headers})).json();assert.equal(result.export.state,'completed',JSON.stringify(result.export));
 fs.writeFileSync(evidence+'/word-captions.mp4',await(await p.request.get(api+'/media',{headers})).body());
 const folder=path.join(path.dirname(identity.fixtures),'edits',project.id,result.export.id),html=fs.readFileSync(path.join(folder,'index.html'),'utf8');assert(!html.includes('<script>safe'));assert(html.includes('&lt;script&gt;safe&lt;/script&gt;'));
 const render=await browser.newPage({viewport:{width:1280,height:720}});await render.goto('file://'+path.join(folder,'index.html'));await render.evaluate(()=>document.fonts.ready);
 for(const time of [0,.3,.75,1.15,1.4,1.85,2.6,1.45,.8,1.2,.3,0]){
  const values=await render.evaluate(({time,captions})=>{window.__timelines.edit.seek(time,false);return captions.map((c,i)=>{const nodes=[...document.querySelectorAll('#caption-'+i+' [data-word-index]')];return {actual:nodes.flatMap((e,j)=>getComputedStyle(e).backgroundColor==='rgb(247, 219, 116)'?[j]:[]),expected:EditCaptions.activeWord(c,time)}})},{time,captions:result.spec.captions});
  for(const v of values)assert.deepEqual(v.actual,v.expected<0?[]:[v.expected],`Seek ${time}`);
 }
 assert.deepEqual(errors,[]);const finalIdentity=await(await p.request.get(origin+'/acceptance/identity')).json();assert.equal(finalIdentity.model_calls,identity.model_calls);assert.equal(finalIdentity.speech_calls,identity.speech_calls+1);
 fs.writeFileSync(evidence+'/acceptance.json',JSON.stringify({project:project.id,folder,qa:result.export.qa,spec:result.spec,ASR:'fixed fixture for interactions, not quality evaluation',paid_calls:false},null,2));
 console.log('PASS: ASR alignment, word correction/timing, highlight/gaps, undo/detach, movement/trim, word playback, mobile, save/reload, inert markup, real MP4 and bidirectional export seek parity. '+evidence);
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exit(1)});
