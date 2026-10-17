// Read-only playback of review windows in the existing production jacket composition.
const {chromium}=require('playwright'),fs=require('fs'),assert=require('assert/strict');
const {clickEditorControl}=require('./editor_controls.cjs');
(async()=>{const b=await chromium.launch({channel:'chromium',headless:true,args:['--no-sandbox']});try{
 const p=await b.newPage({viewport:{width:1920,height:1080}}),base='https://creative.jackailab.com',id='ddc97d3742fdf0cbdbd28928',out='outputs/creative_ui/20261016_review_feedback';fs.mkdirSync(out,{recursive:true});fs.rmSync(out+'/production-verification.json',{force:true});
 await p.request.post(base+'/site/access',{data:{password:fs.readFileSync('/opt/visualstation/creative-runtime/site-access-password.txt','utf8').trim()}});
 const key=JSON.parse(fs.readFileSync('/var/lib/visualstation-local/public-acceptance-account.json')).api_key;
 await p.addInitScript(k=>{sessionStorage.setItem('h3_api_key',k);localStorage.setItem('creative-theme','dark')},key);
 const read=async suffix=>{const r=await p.request.get(base+'/creative/api/projects/'+id+suffix,{headers:{Authorization:'Bearer '+key}});assert(r.ok());return r.json()};
 const before=await read(''),editBefore=await read('/edit'),reviewBefore=await read('/edit/review'),writes=[],errors=[];
 p.on('request',r=>{if(r.url().includes('/creative/api/')&&!['GET','HEAD','OPTIONS'].includes(r.method()))writes.push(new URL(r.url()).pathname)});p.on('pageerror',e=>errors.push(e.message));
 await p.goto(base+'/creative/editor?project='+id,{waitUntil:'domcontentloaded'});
 await p.waitForFunction(()=>typeof spec!=='undefined'&&spec&&[...document.querySelectorAll('#pictures video')].some(v=>v.readyState>=2));
 await clickEditorControl(p,'review');await p.locator('#reviewContent').getByRole('button',{name:/^回放/}).first().waitFor();
 const windows=reviewBefore.packet.content_tasks.flatMap(task=>task.windows),index=windows.findIndex(w=>w.start>=1.5&&w.end-w.start>1),window=windows[Math.max(0,index)];
 await p.locator('#reviewContent').getByRole('button',{name:/^回放/}).nth(Math.max(0,index)).click();await p.waitForFunction(()=>playing);
 await p.waitForFunction(end=>!playing&&Math.abs(t-end)<.04,window.end,{timeout:25000});
 assert(await p.evaluate(()=>[...pictures.values()].every(v=>v.paused)));assert.equal(await p.evaluate(()=>dirty),false);
 await p.screenshot({path:out+'/production-review.png'});
 assert.deepEqual(await read(''),before);assert.deepEqual(await read('/edit'),editBefore);assert.deepEqual(await read('/edit/review'),reviewBefore);assert.deepEqual(writes,[]);assert.deepEqual(errors,[]);
 fs.writeFileSync(out+'/production-verification.json',JSON.stringify({passed:true,actual_jacket_media:true,window:{start:window.start,end:window.end},stopped_at_window_end:true,project_edit_and_review_unchanged:true,writes,errors,paid_calls:0},null,2));
 console.log('PASS real jacket review window playback; project, edit and review unchanged; no writes');
}finally{await b.close()}})().catch(e=>{console.error(e);process.exitCode=1});
