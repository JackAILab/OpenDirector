const {clickEditorControl}=require('./editor_controls.cjs');
// Run the isolated edit_suggestions_server.py first. No production project mutations.
const {chromium}=require('playwright'),fs=require('fs'),assert=require('assert/strict');
(async()=>{const origin='http://127.0.0.1:30130',browser=await chromium.launch({headless:true,args:['--no-sandbox']});try{
const p=await browser.newPage({viewport:{width:1512,height:982}}),errors=[];p.on('pageerror',e=>errors.push(e.message));p.on('dialog',d=>d.accept());
const identity=await(await p.request.get(origin+'/acceptance/identity')).json();assert.equal(identity.fixture,'edit-suggestions-fixed-model');
await p.addInitScript(()=>sessionStorage.setItem('h3_api_key','fixture'));
const project=await(await p.request.post(origin+'/creative/api/projects',{headers:{Authorization:'Bearer fixture'},data:{message:'转场与剪辑建议验收',duration:15}})).json();
const evidence=process.env.EDIT_EVIDENCE||'/tmp/edit-suggestions-browser';fs.mkdirSync(evidence,{recursive:true});
await p.goto(origin+'/creative/editor?project='+project.id);await p.waitForFunction(()=>document.getElementById('status').textContent.includes('项目已载入'));
for(const color of ['red','blue']){
 await p.locator('#uploadVideo').click();await p.locator('#file').setInputFiles(identity.fixtures+'/'+color+'.mp4');await p.waitForFunction(()=>document.getElementById('status').textContent.includes('素材已导入'),{},{timeout:60000});
 await p.locator('.source').filter({hasText:color+'.mp4'}).getByText('＋ 画面').click();await p.locator('#end').fill('3');await p.locator('#apply').click();
}
await p.locator('.clip.clips').first().focus();await p.keyboard.press('Enter');await p.locator('#transitionKind').selectOption('dissolve');await p.locator('#transitionDuration').fill('1');await p.locator('#apply').click();
assert.equal(await p.locator('.transitions button').textContent(),'叠化');assert.equal(Number(await p.locator('#scrub').getAttribute('max')),5);
async function seek(t){await p.locator('#scrub').evaluate((e,t)=>{e.value=t;e.dispatchEvent(new Event('input'))},t);await p.waitForFunction(()=>[...document.querySelectorAll('#pictures video:not([hidden])')].every(v=>v.readyState>=2&&!v.seeking));await p.waitForTimeout(150)}
await seek(2.5);await p.waitForFunction(()=>document.querySelectorAll('#pictures video:not([hidden])').length===2);
assert.deepEqual(await p.locator('#pictures video:not([hidden])').evaluateAll(v=>v.map(v=>Number(v.style.opacity))),[1,.5]);
await p.locator('#monitor').screenshot({path:evidence+'/preview-dissolve.png'});
await seek(1.7);await p.locator('#play').click();await p.waitForFunction(()=>Number(document.getElementById('scrub').value)>3.4,{},{timeout:15000});await p.locator('#play').click();
await clickEditorControl(p,'assistant');await p.locator('#editIntent').fill('先蓝后红，转场改成淡黑。');await p.locator('#suggest').click();
await p.waitForFunction(()=>document.getElementById('suggestionStatus').textContent.includes('建议已就绪'),{},{timeout:90000});
assert.equal(await p.locator('.clip.clips').first().textContent(),'red.mp4');assert.equal((await(await p.request.get(origin+'/acceptance/identity')).json()).model_calls,identity.model_calls+1);
await p.screenshot({path:evidence+'/review-proposal.png'});
await p.locator('#applySuggestion').click();await p.waitForFunction(()=>document.getElementById('adviser').hidden);assert.equal(await p.locator('.clip.clips').first().textContent(),'blue.mp4');assert.equal(await p.locator('.transitions button').textContent(),'淡黑');
await p.locator('#undo').click();assert.equal(await p.locator('.clip.clips').first().textContent(),'red.mp4');assert.equal(await p.locator('.transitions button').textContent(),'叠化');
await p.locator('#redo').click();await seek(2.5);await p.waitForFunction(()=>[...document.querySelectorAll('#pictures video:not([hidden])')].every(v=>Number(v.style.opacity)===0));
await p.locator('#monitor').screenshot({path:evidence+'/preview-black-midpoint.png'});await p.screenshot({path:evidence+'/editor-desktop.png'});
await clickEditorControl(p,'save');await p.waitForFunction(()=>document.getElementById('status').textContent.includes('剪辑已保存'));
await p.reload();await p.waitForFunction(()=>document.getElementById('status').textContent.includes('项目已载入'));assert.equal(await p.locator('.transitions button').textContent(),'淡黑');
await clickEditorControl(p,'assistant');assert(await p.locator('#applySuggestion').isDisabled());await p.locator('#closeAdviser').click();
await p.setViewportSize({width:390,height:844});assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);await clickEditorControl(p,'assistant');await p.screenshot({path:evidence+'/editor-mobile.png'});await p.locator('#closeAdviser').click();
await p.setViewportSize({width:1512,height:982});await p.locator('#export').click();await p.waitForFunction(()=>document.getElementById('status').textContent.includes('导出完成'),{},{timeout:180000});
const download=p.waitForEvent('download');await clickEditorControl(p,'download');await(await download).saveAs(evidence+'/fade-black-export.mp4');await p.reload();await p.waitForFunction(()=>!document.getElementById('download').hidden);assert.deepEqual(errors,[]);
console.log('PASS: real imports, overlapping preview/playback, one stub-model proposal, explicit apply, undo/redo, save/reload, stale prevention, mobile, real export. '+evidence);
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exit(1)});
