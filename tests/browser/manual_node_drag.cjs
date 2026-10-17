// Browser interaction against metadata nodes; no generation is submitted.
const {chromium}=require('playwright'),fs=require('fs'),assert=require('assert');
(async()=>{const browser=await chromium.launch({channel:'chromium',headless:true,args:['--no-sandbox']});try{
 const page=await browser.newPage({viewport:{width:1510,height:900}}),base=process.env.TEST_BASE_URL||'http://127.0.0.1:30080';
 const key=JSON.parse(fs.readFileSync(process.env.TEST_API_KEY_FILE)).api_key,headers={Authorization:'Bearer '+key};
 await page.addInitScript(k=>sessionStorage.setItem('h3_api_key',k),key);
 const created=await page.request.post(base+'/creative/api/projects',{headers,data:{message:'node drag fixture',creation_mode:'video',model:'kling-video-v4_0'}});assert(created.ok());const parent=await created.json();
 const added=await page.request.post(base+'/creative/api/projects/'+parent.id+'/manual-nodes',{headers,data:{message:'drag this image node',creation_mode:'image'}});assert(added.ok());const child=(await added.json()).project;
 await page.route('**/creative/api/projects/*/execute',route=>route.abort());
 await page.goto(base+'/creative?project='+parent.id+'&view=canvas');const card=page.locator('.manual-generation-node'),head=card.locator('.manual-node-head');await head.waitFor();await page.waitForTimeout(500);
 const rootCard=page.locator('.manual-root-node'),rootHead=rootCard.locator('.studio-free-node-label');await rootHead.waitFor();
 const rootBefore=await rootCard.evaluate(e=>({x:e.offsetLeft,y:e.offsetTop})),rootBox=await rootHead.boundingBox();
 const rootSave=page.waitForResponse(r=>r.request().method()==='PATCH'&&r.url().endsWith('/manual-nodes/'+parent.id+'/position'));
 await page.mouse.move(rootBox.x+70,rootBox.y+rootBox.height/2);await page.mouse.down();await page.mouse.move(rootBox.x+110,rootBox.y+rootBox.height/2+50,{steps:8});await page.mouse.up();assert((await rootSave).ok());
 const rootMoved=await rootCard.evaluate(e=>({x:e.offsetLeft,y:e.offsetTop}));assert(rootMoved.x>rootBefore.x&&rootMoved.y>rootBefore.y);
 await page.evaluate(()=>document.dispatchEvent(new Event('creative-state-change')));
 assert.deepEqual(await rootCard.evaluate(e=>({x:e.offsetLeft,y:e.offsetTop})),rootMoved);
 const original=await card.evaluate(e=>({x:e.offsetLeft,y:e.offsetTop})),box=await head.boundingBox();
 const saved=page.waitForResponse(r=>r.request().method()==='PATCH'&&r.url().endsWith('/position'));
 await page.mouse.move(box.x+80,box.y+box.height/2);await page.mouse.down();await page.mouse.move(box.x+140,box.y+box.height/2+95,{steps:10});await page.mouse.up();assert((await saved).ok());
 const moved=await card.evaluate(e=>({x:e.offsetLeft,y:e.offsetTop}));assert(moved.x>original.x&&moved.y>original.y);
 const nodes=(await (await page.request.get(base+'/creative/api/projects/'+parent.id+'/manual-nodes',{headers})).json()).nodes;
 assert.equal(nodes[0].node.project,child.id);assert.equal(nodes[0].node.x,moved.x);assert.equal(nodes[0].node.y,moved.y);
 await page.reload();await head.waitFor();await rootHead.waitFor();assert.deepEqual(await rootCard.evaluate(e=>({x:e.offsetLeft,y:e.offsetTop})),rootMoved);assert.deepEqual(await card.evaluate(e=>({x:e.offsetLeft,y:e.offsetTop})),moved);
 // A failed save restores the last saved location, without changing generation inputs.
 await page.route('**/position',route=>route.fulfill({status:409,json:{detail:'fixture conflict'}}));
 const b=await head.boundingBox();await page.mouse.move(b.x+60,b.y+b.height/2);await page.mouse.down();await page.mouse.move(b.x+100,b.y+b.height/2+60,{steps:5});await page.mouse.up();
 await page.waitForFunction(pos=>{const c=document.querySelector('.manual-generation-node');return c.offsetLeft===pos.x&&c.offsetTop===pos.y},moved);
 if(process.env.TEST_SCREENSHOT)await page.screenshot({path:process.env.TEST_SCREENSHOT});
 console.log('PASS: root and child drag persist across reload; rejected save restores previous position');
}finally{await browser.close()}})().catch(e=>{console.error(String(e.message).split("\n")[0]);process.exitCode=1});
