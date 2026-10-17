const {clickEditorControl}=require('./editor_controls.cjs');
// Isolated real media/export with fixed ASR words; this is interaction evidence, not ASR quality evidence.
// EDIT_SPEECH_FIXTURE=1 EDIT_ACCEPTANCE_PORT=30131 python3 tests/browser/edit_suggestions_server.py
const {chromium}=require('playwright'),fs=require('fs'),assert=require('assert/strict');
(async()=>{const origin='http://127.0.0.1:30131',browser=await chromium.launch({headless:true,args:['--no-sandbox']});try{
const p=await browser.newPage({viewport:{width:1512,height:982}}),errors=[];p.on('pageerror',e=>errors.push(e.message));p.on('dialog',d=>d.accept());
const identity=await(await p.request.get(origin+'/acceptance/identity')).json();assert.equal(identity.fixture,'edit-speech-fixed-model');
const evidence=process.env.EDIT_EVIDENCE||'/tmp/edit-speech-browser';fs.mkdirSync(evidence,{recursive:true});
const headers={Authorization:'Bearer fixture'};await p.addInitScript(()=>sessionStorage.setItem('h3_api_key','fixture'));
const project=await(await p.request.post(origin+'/creative/api/projects',{headers,data:{message:'口播和视频派生验收',duration:15}})).json();
await p.goto(origin+'/creative/editor?project='+project.id);await p.waitForFunction(()=>document.getElementById('status').textContent.includes('项目已载入'));
for(const color of ['red','blue']){
 await p.locator('#uploadVideo').click();await p.locator('#file').setInputFiles(identity.fixtures+'/'+color+'.mp4');await p.waitForFunction(()=>document.getElementById('status').textContent.includes('素材已导入'),{},{timeout:60000});
 await p.locator('.source').filter({hasText:color+'.mp4'}).getByText('＋ 画面').click();
}
await p.locator('#addCaption').click();await p.locator('#text').fill('Original copy');await p.locator('#apply').click();
await p.locator('.source').filter({hasText:'red.mp4'}).getByText('口播',{exact:true}).click();await p.locator('#speechLanguage').selectOption('en');await p.locator('#transcribeSpeech').click();
await p.waitForFunction(()=>document.querySelectorAll('.speech-segment').length===1,{},{timeout:60000});
assert.equal((await(await p.request.get(origin+'/acceptance/identity')).json()).speech_calls,1);
assert.equal(await p.locator('.clip.captions').count(),1);assert.equal(await p.locator('.uncertain-word').count(),1);
await p.screenshot({path:evidence+'/speech-review.png'});await p.locator('#addSpeechCaptions').click();
await p.waitForFunction(()=>document.getElementById('speechPanel').hidden);assert.equal(await p.locator('.clip.captions').count(),2);
assert.equal(await p.locator('.clip.captions').first().textContent(),'Original copy');
await p.locator('#undo').click();assert.equal(await p.locator('.clip.captions').count(),1);await p.locator('#redo').click();
await p.locator('#scrub').evaluate(e=>{e.value=.7;e.dispatchEvent(new Event('input'))});await p.waitForFunction(()=>document.querySelectorAll('#subtitles .subtitle').length===2);
await p.locator('#monitor').screenshot({path:evidence+'/caption-preview.png'});
await clickEditorControl(p,'save');await p.waitForFunction(()=>document.getElementById('status').textContent.includes('剪辑已保存'));
await p.reload();await p.waitForFunction(()=>document.getElementById('status').textContent.includes('项目已载入'));assert.equal(await p.locator('.clip.captions').count(),2);
const doc=await(await p.request.get(origin+'/creative/api/projects/'+project.id+'/edit',{headers})).json();assert.equal(doc.spec.captions[1].track,1);
await p.setViewportSize({width:390,height:844});await p.locator('.source').filter({hasText:'red.mp4'}).getByText('口播',{exact:true}).click();assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);await p.screenshot({path:evidence+'/speech-mobile.png'});await p.locator('#closeSpeech').click();
await p.setViewportSize({width:1512,height:982});await p.locator('#export').click();await p.waitForFunction(()=>!document.getElementById('toCanvas').hidden,{},{timeout:180000});
await p.setViewportSize({width:390,height:844});assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);await p.screenshot({path:evidence+'/export-mobile.png'});
await p.setViewportSize({width:1512,height:982});const download=p.waitForEvent('download');await clickEditorControl(p,'download');await(await download).saveAs(evidence+'/caption-export.mp4');
await clickEditorControl(p,'toCanvas');await p.waitForURL(/view=canvas/);await p.waitForFunction(()=>document.querySelectorAll('.reference-node').length===3);
assert.equal(await p.locator('.clip-provenance').count(),1);const derived=p.locator('.reference-node').filter({has:p.locator('.clip-provenance')});
await derived.getByText('聚焦',{exact:true}).click();await derived.locator('summary').filter({hasText:'来源片段'}).click();await derived.getByText('播放视频',{exact:true}).click();await p.waitForFunction(()=>[...document.querySelectorAll('.reference-node video')].some(v=>v.readyState>=2&&v.currentTime>0));
await p.screenshot({path:evidence+'/canvas-video-lineage.png'});
const current=await(await p.request.get(origin+'/creative/api/projects/'+project.id,{headers})).json();assert.equal(current.canvas.edges.length,0);assert.equal(Object.values(current.canvas_lineage).filter(a=>a.kind==='video_edit')[0].sources.length,2);
fs.writeFileSync(evidence+'/acceptance.json',JSON.stringify({project:project.id,paid_calls:false,ASR:'fixed words for interaction only',clips:doc.spec.clips,captions:doc.spec.captions,lineage:current.canvas_lineage},null,2));
await derived.getByText('打开剪辑 ↗',{exact:true}).click();await p.waitForURL(/creative\/editor\?.*source=canvas_/);await p.waitForFunction(()=>document.querySelector('.source-highlight'));assert.equal(await p.locator('.clip.clips').count(),2);
assert.deepEqual(errors,[]);console.log('PASS: explicit ASR, uncertainty, preserved captions, undo/reload, mobile, real export, video lineage/playback, reopen source. '+evidence);
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exit(1)});
