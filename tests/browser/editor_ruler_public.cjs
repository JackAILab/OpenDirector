// Existing production media: browser seeking and view changes only, no project writes.
const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs');
(async()=>{const browser=await chromium.launch({channel:'chromium',headless:true,args:['--no-sandbox']});try{
 const base='https://creative.jackailab.com',id=process.env.EDIT_PROJECT;assert(id,'Set EDIT_PROJECT to an existing acceptance project');
 const out=process.env.EDIT_EVIDENCE||'outputs/creative_ui/20261016_editor_ruler';fs.mkdirSync(out,{recursive:true});
 const page=await browser.newPage({viewport:{width:1512,height:982}}),errors=[],writes=[],results=[];
 page.on('pageerror',e=>errors.push(e.message));const key=JSON.parse(fs.readFileSync('/var/lib/visualstation-local/public-acceptance-account.json')).api_key;
 assert((await page.request.post(base+'/site/access',{data:{password:fs.readFileSync('/opt/visualstation/creative-runtime/site-access-password.txt','utf8').trim()}})).ok());
 const headers={Authorization:'Bearer '+key},read=async suffix=>{const response=await page.request.get(base+'/creative/api/projects/'+id+suffix,{headers});assert(response.ok());return response.json()};
 const before=await read('/edit'),projectBefore=await read('');
 page.on('request',r=>{if(r.url().includes('/creative/api/')&&!['GET','HEAD','OPTIONS'].includes(r.method()))writes.push(r.method()+' '+new URL(r.url()).pathname.replace(id,':project'))});
 await page.addInitScript(key=>{sessionStorage.setItem('h3_api_key',key);localStorage.setItem('creative-theme','dark')},key);
 await page.goto(base+'/creative/editor?project='+id,{waitUntil:'domcontentloaded'});
 await page.waitForFunction(()=>typeof spec!=='undefined'&&spec&&document.querySelector('.tick-major span')&&[...document.querySelectorAll('#pictures video')].some(v=>v.readyState>=2));
 const geometry=()=>page.locator('.ruler').evaluate(track=>{const b=track.getBoundingClientRect();return {width:b.width,step:Number(track.dataset.majorStep),labels:[...track.querySelectorAll('.tick-major span')].map(n=>{const r=n.getBoundingClientRect();return {text:n.textContent,left:r.left-b.left,right:r.right-b.left}})}});
 for(const [name,width,height]of[['desktop',1512,982],['tablet',1024,768],['mobile',390,844]]){
  await page.setViewportSize({width,height});
  for(const zoom of [1,2.5,6]){
   await page.locator('#zoom').evaluate((el,value)=>{el.value=value;el.dispatchEvent(new Event('input',{bubbles:true}))},String(zoom));
   await page.waitForFunction(()=>{const el=document.querySelector('.ruler');return el&&el.clientWidth>0&&el.dataset.majorStep});
   await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
   const data=await geometry();assert(data.labels.length>=2);for(let i=0;i<data.labels.length;i++){const label=data.labels[i];assert(label.left>=0&&label.right<=data.width+1,'labels stay within track');if(i)assert(label.left-data.labels[i-1].right>=8,'time labels have readable gaps')}
   results.push({name,zoom,...data});
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
   if(zoom===1)await page.screenshot({path:out+'/'+name+'.png'});
  }
 }
 assert(results.find(x=>x.name==='mobile'&&x.zoom===1).step>results.find(x=>x.name==='desktop'&&x.zoom===1).step);
 await page.locator('#zoom').evaluate(el=>{el.value='1';el.dispatchEvent(new Event('input',{bubbles:true}))});
 await page.setViewportSize({width:1512,height:982});await page.waitForFunction(()=>Number(document.querySelector('.ruler').dataset.majorStep)===1);
 await page.setViewportSize({width:390,height:844});await page.waitForFunction(()=>Number(document.querySelector('.ruler').dataset.majorStep)===5);
 const resized=await geometry();for(let i=1;i<resized.labels.length;i++)assert(resized.labels[i].left-resized.labels[i-1].right>=8,'resize alone updates label density');
 await page.setViewportSize({width:1512,height:982});await page.waitForFunction(()=>Number(document.querySelector('.ruler').dataset.majorStep)===1);
 const scrub=page.locator('#scrub');await scrub.scrollIntoViewIfNeeded();const bounds=await scrub.boundingBox(),total=await page.evaluate(()=>duration());
 await page.mouse.click(bounds.x+bounds.width*.4,bounds.y+bounds.height/2);await page.waitForFunction(()=>[...pictures.values()].every(v=>!v.seeking));
 const clicked=Number(await scrub.inputValue());assert(Math.abs(clicked-total*.4)<.03,'pointer maps to timeline time');
 await scrub.press('ArrowRight');const stepped=Number(await scrub.inputValue());assert(Math.abs(stepped-clicked-.01)<.001,'native keyboard precision retained');
 await page.waitForFunction(()=>EditTiming.poses(spec.clips,Math.min(t,duration()-.001)).every(p=>{const v=pictures.get(p.index);return v&&!v.seeking&&Math.abs(v.currentTime-p.source)<.04}));
 await page.locator('#play').click();await page.waitForFunction(start=>t>start+.5,stepped);await page.locator('#play').click();
 const paused=await page.evaluate(()=>({playing,t,heads:[...document.querySelectorAll('.playhead')].map(n=>parseFloat(n.style.left)),expected:t/duration()*100}));assert.equal(paused.playing,false);assert(paused.heads.every(p=>Math.abs(p-paused.expected)<.001));
 await scrub.focus();await scrub.press('End');assert(Math.abs(Number(await scrub.inputValue())-total)<.011,'native 0.01-second range reaches the final step');await scrub.press('Home');assert.equal(Number(await scrub.inputValue()),0);
 const after=await read('/edit'),projectAfter=await read('');assert.equal(after.revision,before.revision);assert.deepEqual(after.spec,before.spec);assert.equal(projectAfter.revision,projectBefore.revision);assert.deepEqual(writes,[]);assert.deepEqual(errors,[]);assert.equal(await page.evaluate(()=>dirty),false);
 fs.writeFileSync(out+'/verification.json',JSON.stringify({passed:true,results,resize_observer:true,pointer_seek:true,keyboard_step_seconds:.01,actual_media_seek:true,playback_and_heads:true,endpoints:true,project_unchanged:true,writes,errors,paid_calls:0},null,2));console.log('PASS public ruler: responsive labels, 3 zooms, pointer/keyboard/media clock, unchanged project, zero writes');
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exitCode=1});
