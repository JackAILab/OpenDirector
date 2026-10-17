const {clickEditorControl}=require('./editor_controls.cjs');
// Isolated media and real HyperFrames render; no model calls.
// EDIT_SPEECH_FIXTURE=1 EDIT_ACCEPTANCE_PORT=30131 python3 tests/browser/edit_suggestions_server.py
const {chromium}=require('playwright'),fs=require('fs'),path=require('path'),assert=require('assert/strict');
(async()=>{const origin='http://127.0.0.1:30131',browser=await chromium.launch({headless:true,args:['--no-sandbox']});try{
const p=await browser.newPage({viewport:{width:1512,height:982}}),errors=[];p.on('pageerror',e=>errors.push(e.message));p.on('dialog',d=>d.accept());
const identity=await(await p.request.get(origin+'/acceptance/identity')).json();assert.equal(identity.fixture,'edit-speech-fixed-model');
const evidence=process.env.EDIT_EVIDENCE||'/tmp/edit-caption-browser';fs.mkdirSync(evidence,{recursive:true});
const headers={Authorization:'Bearer fixture'};await p.addInitScript(()=>sessionStorage.setItem('h3_api_key','fixture'));
const project=await(await p.request.post(origin+'/creative/api/projects',{headers,data:{message:'字幕校对与样式验收',duration:15}})).json(),api=origin+'/creative/api/projects/'+project.id+'/edit';
await p.goto(origin+'/creative/editor?project='+project.id);await p.waitForFunction(()=>document.getElementById('status').textContent.includes('项目已载入'));
await clickEditorControl(p,'editorMediaToggle');await p.locator('#uploadVideo').click();await p.locator('#file').setInputFiles(identity.fixtures+'/red.mp4');await p.waitForFunction(()=>document.getElementById('status').textContent.includes('素材已导入'),{},{timeout:60000});await p.getByText('＋ 画面',{exact:true}).click();
async function addCaption(text,start,end,track){await p.locator('#addCaption').click();await p.locator('#text').fill(text);await p.locator('#start').fill(String(start));await p.locator('#end').fill(String(end));await p.locator('#captionTrack').selectOption(String(track));await p.locator('#apply').click()}
await addCaption('夜色里，自有轮廓',.3,1.4,0);await addCaption('Turn the ordinary into your own.',1.5,2.8,0);await addCaption('HIDDEN <script>window.injected=true</script>',.3,2.8,1);
assert.equal(await p.locator('.caption-list-item').count(),3);
await p.locator('#captionTrackSwitches [data-track="1"]').click();
await p.locator('.caption-list-item').filter({hasText:'夜色里'}).click();await p.locator('#captionPreset').selectOption('accent');await p.locator('#captionMotion').selectOption('rise');await p.locator('#apply').click();await p.locator('#styleTrack').click();
await p.locator('.caption-list-item').filter({hasText:'Turn the ordinary'}).click();assert.equal(await p.locator('#captionMotion').inputValue(),'rise');
await p.locator('#undo').click();assert.equal(await p.locator('#captionMotion').inputValue(),'none');await p.locator('#redo').click();assert.equal(await p.locator('#captionMotion').inputValue(),'rise');
await p.locator('.caption-list-item').filter({hasText:'夜色里'}).click();
async function seek(t){await p.locator('#scrub').evaluate((e,t)=>{e.value=t;e.dispatchEvent(new Event('input'))},t);await p.waitForFunction(()=>[...document.querySelectorAll('#pictures video:not([hidden])')].every(v=>v.readyState>=2&&!v.seeking))}
await seek(.39);assert.equal(await p.locator('.subtitle').count(),1);const alpha=Number(await p.locator('.caption-effect').evaluate(e=>e.style.opacity));assert(Math.abs(alpha-.75)<.001);await p.locator('#monitor').screenshot({path:evidence+'/rise-preview.png'});
await seek(.8);await p.screenshot({path:evidence+'/caption-workspace.png'});assert.equal(await p.evaluate(()=>window.injected),undefined);
await p.locator('#playCaption').click();await p.waitForFunction(()=>document.getElementById('play').textContent==='▶'&&Math.abs(Number(document.getElementById('scrub').value)-1.4)<.02,{},{timeout:15000});
await clickEditorControl(p,'save');await p.waitForFunction(()=>document.getElementById('status').textContent.includes('剪辑已保存'));await p.reload();await p.waitForFunction(()=>document.getElementById('status').textContent.includes('项目已载入'));
await clickEditorControl(p,'editorMediaToggle');await p.locator('#captionsTab').click();const saved=await(await p.request.get(api,{headers})).json();assert.deepEqual(saved.spec.caption_visibility,[true,false,true]);assert.equal(saved.spec.captions.length,3);assert.equal(saved.spec.captions[1].appearance.motion,'rise');
await p.setViewportSize({width:390,height:844});await p.locator('.caption-list-item').filter({hasText:'夜色里'}).click();assert.equal(await p.locator('#settings').getAttribute('aria-expanded'),'true');assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);await p.screenshot({path:evidence+'/caption-mobile.png'});await clickEditorControl(p,'settings');
await p.setViewportSize({width:1512,height:982});await p.locator('#export').click();await p.waitForFunction(()=>!document.getElementById('download').hidden,{},{timeout:180000});const download=p.waitForEvent('download');await clickEditorControl(p,'download');await(await download).saveAs(evidence+'/caption-motion.mp4');
const result=await(await p.request.get(api,{headers})).json(),folder=path.join(path.dirname(identity.fixtures),'edits',project.id,result.export.id);
const html=fs.readFileSync(path.join(folder,'index.html'),'utf8');assert(!html.includes('HIDDEN'));assert(!html.includes('window.injected'));assert(html.includes('夜色里，自有轮廓'));
// Seek the actual exported GSAP timeline backward and forward; the shared preview calculation must agree.
const render=await browser.newPage({viewport:{width:1280,height:720}});await render.goto('file://'+path.join(folder,'index.html'));await render.evaluate(()=>document.fonts.ready);
for(const time of [.39,.8,1.35,.34,1.57,2.75,1.6]){
 const values=await render.evaluate(({time,captions})=>{window.__timelines.edit.seek(time,false);return captions.slice(0,2).filter(c=>time>=c.start&&time<c.end).map(c=>{const i=captions.indexOf(c),el=document.querySelector('#caption-'+i+' .caption-effect');return {actual:{opacity:Number(gsap.getProperty(el,'opacity')),y:Number(gsap.getProperty(el,'y'))},expected:EditCaptions.pose(c,time,1280,720)}})},{time,captions:result.spec.captions});
 values.forEach(v=>{assert(Math.abs(v.actual.opacity-v.expected.opacity)<.002);assert(Math.abs(v.actual.y-v.expected.y)<.002)});
}
// Static captions must also pass contrast and render without a padding animation.
const staticSpec=structuredClone(result.spec);staticSpec.captions.forEach(c=>c.appearance.motion='none');
assert.equal((await p.request.put(api,{headers,data:{revision:result.revision,spec:staticSpec}})).status(),200);
const savedStatic=await(await p.request.get(api,{headers})).json();
assert.equal((await p.request.post(api+'/export',{headers,data:{revision:savedStatic.revision}})).status(),200);
let staticResult;for(let i=0;i<180;i++){staticResult=await(await p.request.get(api,{headers})).json();if(staticResult.export.state!=='running')break;await new Promise(resolve=>setTimeout(resolve,1000))}
assert.equal(staticResult.export.state,'completed',JSON.stringify(staticResult.export));
fs.writeFileSync(evidence+'/static-captions.mp4',await(await p.request.get(api+'/media',{headers})).body());
assert.deepEqual(errors,[]);const finalIdentity=await(await p.request.get(origin+'/acceptance/identity')).json();assert.equal(finalIdentity.model_calls,0);assert.equal(finalIdentity.speech_calls,0);
fs.writeFileSync(evidence+'/acceptance.json',JSON.stringify({project:project.id,export:result.export.id,folder,spec:result.spec,qa:result.export.qa,static_export:staticResult.export,model_calls:0},null,2));
console.log('PASS: caption list, hidden text retained, style/undo, phrase playback, save/reload, mobile, literal text safety, motion/static real renders and GSAP seek parity. '+evidence);
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exit(1)});
