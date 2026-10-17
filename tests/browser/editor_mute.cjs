const {clickEditorControl}=require('./editor_controls.cjs');
// Real API/media/export acceptance. Fixed planner fixture, no provider calls.
const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs');
(async()=>{const browser=await chromium.launch({channel:'chromium',headless:true,args:['--no-sandbox']});try{
 const page=await browser.newPage({viewport:{width:1512,height:982}}),origin=process.env.EDIT_ORIGIN||'http://127.0.0.1:30132',headers={Authorization:'Bearer fixture'},errors=[],out=process.env.EDIT_EVIDENCE||'/tmp/editor-mute';fs.mkdirSync(out,{recursive:true});page.on('pageerror',e=>errors.push(e.message));
 assert(await page.evaluate(()=>document.createElement('video').canPlayType('video/mp4; codecs="avc1.42E01E"')),'Browser must support H.264 for real-media acceptance');
 const identity=await(await page.request.get(origin+'/acceptance/identity')).json();assert.equal(identity.fixture,'edit-speech-fixed-model');
 const project=await(await page.request.post(origin+'/creative/api/projects',{headers,data:{message:'音轨静音验收',duration:15}})).json(),api=origin+'/creative/api/projects/'+project.id+'/edit';
 await page.addInitScript(()=>sessionStorage.setItem('h3_api_key','fixture'));await page.goto(origin+'/creative/editor?project='+project.id);await page.waitForFunction(()=>document.getElementById('status').textContent.includes('项目已载入'));
 await clickEditorControl(page,'editorMediaToggle');
 for(const [name,action] of [['red','＋ 画面'],['blue','＋ 音轨']]){await page.locator('#uploadVideo').click();await page.locator('#file').setInputFiles(identity.fixtures+'/'+name+'.mp4');await page.waitForFunction(()=>document.getElementById('status').textContent.includes('素材已导入'));await page.getByText(action,{exact:true}).last().click()}
 await page.locator('.editor-library-close').click();await page.keyboard.press('Escape');
 await page.locator('#addCaption').click();await page.locator('#text').fill('音轨静音验收');await page.locator('#captionMotion').selectOption('fade');await page.locator('#apply').click();await page.keyboard.press('Escape');
 const state=()=>page.evaluate(()=>({clips:structuredClone(spec.clips),audio:structuredClone(spec.audio),playing,dirty,t}));
 const original=await state(),pictureMute=page.locator('.track-mute[data-kind=clips]'),audioMute=page.locator('.track-mute[data-kind=audio]');
 await pictureMute.click();assert.equal((await state()).clips[0].muted,true);assert.equal((await state()).clips[0].gain,original.clips[0].gain);
 await page.waitForFunction(()=>[...pictures.values()].filter(v=>!v.hidden).every(v=>v.volume===0));
 await page.evaluate(()=>document.activeElement.blur());await page.keyboard.press('Control+z');assert(!(await state()).clips[0].muted);
 await pictureMute.click();await page.locator('#play').click();await page.waitForFunction(()=>playing,{},{timeout:18000}).catch(async e=>{console.log(await page.evaluate(()=>({status:document.getElementById('status').textContent,playing,t,epoch,errors:[...pictures.values()].map(v=>({ready:v.readyState,seeking:v.seeking,time:v.currentTime,error:v.error?.message}))})));throw e});await audioMute.click();
 assert.equal((await state()).playing,true);assert.equal((await state()).audio[0].gain,original.audio[0].gain);
 assert.equal(await page.evaluate(()=>sounds.get('placement-0').volume),0);assert.equal(await audioMute.getAttribute('aria-pressed'),'true');
 await audioMute.click();assert.equal((await state()).audio[0].muted,false);assert.equal(await page.evaluate(()=>sounds.get('placement-0').volume),original.audio[0].gain);
 await page.evaluate(()=>stop());
 await clickEditorControl(page,'save');await page.waitForFunction(()=>!working&&!dirty);await page.reload();await page.waitForFunction(()=>document.getElementById('status').textContent.includes('项目已载入'));
 assert.equal((await state()).clips[0].muted,true);assert.equal((await state()).audio[0].muted,false);
 await page.locator('.editor-timeline-resize').focus();for(let i=0;i<6;i++)await page.keyboard.press('ArrowUp');await page.screenshot({path:out+'/track-mute-desktop.png'});
 async function exportFile(name){await page.locator('#export').click();await page.waitForFunction(()=>!working,{},{timeout:180000});assert.equal(await page.locator('#download').isVisible(),true,await page.locator('#status').textContent());const r=await page.request.get(api+'/media',{headers});assert.equal(r.status(),200);fs.writeFileSync(out+'/'+name,await r.body())}
 await exportFile('independent-only.mp4');
 await audioMute.click();await exportFile('all-muted.mp4');
 const saved=await(await page.request.get(api,{headers})).json();assert(saved.spec.clips[0].muted&&saved.spec.audio[0].muted);assert.equal(saved.spec.audio[0].gain,.3);
 await page.setViewportSize({width:390,height:844});await audioMute.scrollIntoViewIfNeeded();const box=await audioMute.boundingBox();assert(box.x>=0&&box.x+box.width<=390);await page.screenshot({path:out+'/track-mute-mobile.png'});
 await audioMute.click();await pictureMute.click();await clickEditorControl(page,'save');await page.waitForFunction(()=>!working&&!dirty);assert.equal((await state()).clips[0].gain,1);assert.equal((await state()).audio[0].gain,.3);assert.deepEqual(errors,[]);
 const end=await(await page.request.get(origin+'/acceptance/identity')).json();assert.equal(end.model_calls,identity.model_calls);assert.equal(end.paid_calls,false);
 console.log('PASS mute: live playback, undo, gain preservation, save/reload, two real exports, mobile controls; no provider calls');
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exitCode=1});
