// Read-only playback of review windows in the existing production jacket composition.
const {chromium}=require('playwright'),fs=require('fs'),assert=require('assert/strict');
const {clickEditorControl}=require('./editor_controls.cjs');
(async()=>{const b=await chromium.launch({channel:'chromium',headless:true,args:['--no-sandbox']});try{
 const p=await b.newPage({viewport:{width:1920,height:1080}}),base='https://creative.jackailab.com',id='ddc97d3742fdf0cbdbd28928',out='outputs/creative_ui/20261016_retake_range';fs.mkdirSync(out,{recursive:true});
 await p.request.post(base+'/site/access',{data:{password:fs.readFileSync('/opt/visualstation/creative-runtime/site-access-password.txt','utf8').trim()}});
 const key=JSON.parse(fs.readFileSync('/var/lib/visualstation-local/public-acceptance-account.json')).api_key;
 await p.addInitScript(k=>{sessionStorage.setItem('h3_api_key',k);localStorage.setItem('creative-theme','dark')},key);
 const read=async suffix=>{const r=await p.request.get(base+'/creative/api/projects/'+id+suffix,{headers:{Authorization:'Bearer '+key}});assert(r.ok());return r.json()};
 const before=await read(''),editBefore=await read('/edit'),reviewBefore=await read('/edit/review'),writes=[],errors=[];
 p.on('request',r=>{if(r.url().includes('/creative/api/')&&!['GET','HEAD','OPTIONS'].includes(r.method()))writes.push(new URL(r.url()).pathname)});p.on('pageerror',e=>errors.push(e.message));
 await p.goto(base+'/creative/editor?project='+id,{waitUntil:'domcontentloaded'});
 await p.waitForFunction(()=>typeof spec!=='undefined'&&spec&&[...document.querySelectorAll('#pictures video')].some(v=>v.readyState>=2));
 const original=await p.evaluate(()=>structuredClone(spec));
 await clickEditorControl(p,'review');await p.locator('.review-replay').first().waitFor();
 await p.locator('#reviewNote').fill('拉链动作需要从敞开到闭合完整呈现，保持夹克结构和人物一致。');
 const button=p.getByRole('button',{name:/^修改.*1\.63–3\.60 秒$/});assert.equal(await button.count(),1);await button.click();
 assert(await p.locator('#reviewPanel').isHidden());assert(await p.locator('#retakePanel').isVisible());assert.match(await p.locator('#retakeIntent').inputValue(),/拉链动作/);assert.equal(await p.locator('#retakeRangeStart').inputValue(),'1.63');assert.equal(await p.locator('#retakeRangeEnd').inputValue(),'3.6');assert(await p.locator('#retakeRangeIsolate').isDisabled());assert(await p.locator('#retakePrepare').isDisabled());
 await p.locator('#retakeRangeEnd').fill('5.63');await p.locator('#retakeRangePlay').click();await p.waitForFunction(()=>playing);await p.waitForFunction(()=>!playing&&Math.abs(t-5.63)<.03,null,{timeout:15000});
 await p.locator('#retakeRangeIsolate').click();const isolated=await p.evaluate(()=>({spec:structuredClone(spec),index:selected.index,length:duration()}));
 assert.equal(isolated.index,1);assert.equal(isolated.spec.clips.length,3);assert.deepEqual(isolated.spec.clips.map(c=>[c.start,c.end]),[[0,1.63],[1.63,5.63],[5.63,original.clips[0].end]]);assert.deepEqual(isolated.spec.captions,original.captions);assert.deepEqual(isolated.spec.audio,original.audio);assert.equal(isolated.length,original.clips[0].end);assert(await p.locator('#retakePrepare').isEnabled());await p.screenshot({path:out+'/production-range.png'});
 await p.locator('#undo').click();assert.deepEqual(await p.evaluate(()=>spec),original);await p.locator('#redo').click();assert.deepEqual(await p.evaluate(()=>spec),isolated.spec);await p.locator('#undo').click();
 await p.setViewportSize({width:390,height:844});await p.locator('#retakeRangeEnd').fill('5');assert(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));await p.screenshot({path:out+'/mobile-range.png'});
 await p.reload();await p.waitForFunction(()=>typeof spec!=='undefined'&&spec);assert.deepEqual(await p.evaluate(()=>spec),original);
 assert.deepEqual(await read(''),before);assert.deepEqual(await read('/edit'),editBefore);assert.deepEqual(await read('/edit/review'),reviewBefore);assert.deepEqual(writes,[]);assert.deepEqual(errors,[]);
 fs.writeFileSync(out+'/production-verification.json',JSON.stringify({passed:true,actual_jacket_media:true,review_note_and_window_handoff:true,explicit_range_selection:true,bounded_playback:true,three_non_destructive_clips:true,captions_audio_duration_preserved:true,undo_redo:true,mobile:true,project_edit_and_review_unchanged:true,writes,errors,paid_calls:0},null,2));
 console.log('PASS actual jacket review → range playback → isolate draft → undo/redo; no saves or generation');
}finally{await b.close()}})().catch(e=>{console.error(e);process.exitCode=1});
