// Read-only task inspector through the actual production canvas UI.
const {chromium}=require('playwright'),fs=require('fs'),assert=require('assert/strict');
(async()=>{const b=await chromium.launch({channel:'chromium',headless:true,args:['--no-sandbox']});try{
 const p=await b.newPage({viewport:{width:1920,height:1080}}),base='https://creative.jackailab.com',id='ddc97d3742fdf0cbdbd28928',out='outputs/creative_ui/20261016_canvas_task_dock';fs.mkdirSync(out,{recursive:true});
 await p.request.post(base+'/site/access',{data:{password:fs.readFileSync('/opt/visualstation/creative-runtime/site-access-password.txt','utf8').trim()}});
 const key=JSON.parse(fs.readFileSync('/var/lib/visualstation-local/public-acceptance-account.json')).api_key;
 await p.addInitScript(k=>{sessionStorage.setItem('h3_api_key',k);localStorage.setItem('creative-theme','dark')},key);
 const read=async suffix=>{const r=await p.request.get(base+'/creative/api/projects/'+id+suffix,{headers:{Authorization:'Bearer '+key}});assert(r.ok());return r.json()};
 const before=await read(''),editBefore=await read('/edit'),reviewBefore=await read('/edit/review'),writes=[],errors=[];
 p.on('request',r=>{if(r.url().includes('/creative/api/')&&!['GET','HEAD','OPTIONS'].includes(r.method()))writes.push(new URL(r.url()).pathname)});p.on('pageerror',e=>errors.push(e.message));
 await p.goto(base+'/creative?project='+id+'&view=canvas',{waitUntil:'domcontentloaded'});
 await p.waitForFunction(()=>typeof project!=='undefined'&&project?.id&&document.querySelector('#productionTask .production-task-title').textContent==='成片待审阅');
 const task=p.locator('#productionTask'),trigger=task.locator(':scope>summary'),panel=p.locator('#productionTaskPanel');
 assert.equal(await task.evaluate(e=>e.parentElement.classList.contains('canvas-toolbar')),true);assert.equal(await p.locator('.projectbar #productionTask').count(),0);
 assert.match(await trigger.getAttribute('aria-label'),/制作记录与进度.*成片待审阅/);assert.equal(await task.evaluate(e=>e.open),false);await p.screenshot({path:out+'/canvas.png'});
 await trigger.click();await p.waitForFunction(()=>document.querySelector('#productionTaskPanel').matches(':popover-open'));assert.equal(await trigger.getAttribute('aria-expanded'),'true');assert(await panel.innerText().then(t=>t.includes('Kling O3')));assert.equal(await panel.locator('.studio-task-current').innerText(),'成片待审阅');
 const bounds=async()=>{const r=await panel.boundingBox(),a=await trigger.boundingBox(),v=p.viewportSize();assert(r.x>=0&&r.y>=0&&r.x+r.width<=v.width&&r.y+r.height<=v.height);assert(r.y+r.height<=a.y,'inspector must stay above the dock')};await bounds();
 await panel.getByRole('button',{name:'刷新状态',exact:true}).click();await p.waitForFunction(()=>[...document.querySelectorAll('#productionTaskPanel button')].some(e=>e.textContent==='刷新状态'&&!e.disabled));await p.waitForFunction(()=>[...document.querySelectorAll('.reference-node>.canvas-card-body>img')].every(e=>e.complete&&e.naturalWidth>0));await p.screenshot({path:out+'/task-inspector.png'});
 await p.keyboard.press('Escape');await p.waitForFunction(()=>!document.querySelector('#productionTask').open&&!document.querySelector('#productionTaskPanel').matches(':popover-open'));assert(await trigger.evaluate(e=>document.activeElement===e));
 await trigger.click();await p.waitForFunction(()=>document.querySelector('#productionTaskPanel').matches(':popover-open'));await p.mouse.click(600,80);await p.waitForFunction(()=>!document.querySelector('#productionTask').open);await trigger.click();await p.waitForFunction(()=>document.querySelector('#productionTaskPanel').matches(':popover-open'));await panel.getByRole('button',{name:'收起制作任务详情'}).click();await p.waitForFunction(()=>!document.querySelector('#productionTaskPanel').matches(':popover-open'));
 // Existing image/task links set details.open; they must still open the top-layer inspector.
 await task.evaluate(e=>e.open=true);await p.waitForFunction(()=>document.querySelector('#productionTaskPanel').matches(':popover-open'));
 await p.setViewportSize({width:390,height:844});await bounds();assert(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));const dock=await p.locator('.canvas-toolbar').boundingBox();assert(dock.x>=0&&dock.x+dock.width<=390);await p.screenshot({path:out+'/mobile.png'});
 await p.evaluate(()=>document.documentElement.dataset.theme='light');await p.screenshot({path:out+'/mobile-light.png'});await p.keyboard.press('Escape');await trigger.click();await p.waitForFunction(()=>document.querySelector('#productionTaskPanel').matches(':popover-open'));await bounds();await p.keyboard.press('Escape');
 assert.deepEqual(await read(''),before);assert.deepEqual(await read('/edit'),editBefore);assert.deepEqual(await read('/edit/review'),reviewBefore);assert.deepEqual(writes,[]);assert.deepEqual(errors,[]);
 fs.writeFileSync(out+'/verification.json',JSON.stringify({passed:true,task_in_dock:true,account_island_clear:true,actual_status_visible:true,refresh_read_only:true,top_layer_above_dock:true,escape_outside_close:true,programmatic_open:true,mobile:true,light:true,project_edit_and_review_unchanged:true,writes,errors,paid_calls:0},null,2));
 console.log('PASS task dock, actual status, refresh, keyboard/outside close, top layer and mobile; no project writes');
}finally{await b.close()}})().catch(e=>{console.error(e);process.exitCode=1});
