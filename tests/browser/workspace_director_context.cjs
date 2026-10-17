// Metadata fixture only. Browser opens Director; no planning or generation submission.
const {chromium}=require('playwright'),fs=require('fs'),assert=require('assert');
(async()=>{const browser=await chromium.launch({channel:'chromium',headless:true,args:['--no-sandbox']});try{
const page=await browser.newPage(),base=process.env.TEST_BASE_URL||'http://127.0.0.1:30080',key=JSON.parse(fs.readFileSync(process.env.TEST_API_KEY_FILE)).api_key,headers={Authorization:'Bearer '+key};
await page.addInitScript(k=>sessionStorage.setItem('h3_api_key',k),key);
const created=await page.request.post(base+'/creative/api/projects',{headers,data:{message:'workspace context acceptance fixture',creation_mode:'video'}});assert(created.ok());let project=await created.json();
const note=(id,text)=>({id,kind:'text',label:id,text,x:40,y:id==='selected'?30:300,role:'reference'});
const saved=await page.request.put(base+'/creative/api/projects/'+project.id+'/canvas',{headers,data:{revision:project.revision,nodes:[note('selected','Use warm sunset lighting'),note('unselected','Do not pass this note')],edges:[{source:'selected',target:'director'}]}});assert(saved.ok());
await page.route('**/creative/api/projects/*/execute',r=>r.abort());await page.route('**/creative/api/projects/*/message',r=>r.abort());
await page.goto(base+'/creative?project='+project.id+'&view=canvas');await page.getByRole('button',{name:'打开 Director',exact:true}).click();
const frame=page.frameLocator('.workspace-director-frame');await frame.locator('#message').waitFor({state:'visible'});
await frame.getByRole('button',{name:'selected',exact:true}).waitFor({state:'visible'});
const contexts=await page.frames().find(f=>f.url().includes('embedded=director')).evaluate(()=>project.canvas.nodes.map(n=>n.text));assert.deepEqual(contexts,['Use warm sunset lighting']);
await page.getByRole('button',{name:'故事板',exact:true}).click();await page.waitForFunction(()=>document.body.classList.contains('workspace-director-story'));
assert(!await page.locator('.canvas-toolbar').isVisible());assert(!await page.locator('.studio-agent-orb').isVisible());
if(process.env.TEST_SCREENSHOT)await page.screenshot({path:process.env.TEST_SCREENSHOT});
await frame.getByRole('button',{name:'selected',exact:true}).click();await page.waitForFunction(()=>!document.body.classList.contains('workspace-director-story'));
assert(await page.locator('.canvas-toolbar').isVisible());
const latest=await (await page.request.get(base+'/creative/api/projects/'+project.id,{headers})).json();
assert((await page.request.put(base+'/creative/api/projects/'+project.id+'/canvas',{headers,data:{revision:latest.revision,nodes:latest.canvas.nodes,edges:[]}})).ok());
await frame.getByRole('button',{name:'selected',exact:true}).waitFor({state:'hidden',timeout:15000});
assert.equal(await page.evaluate(()=>project.creation_mode),'video');console.log('PASS: browser Director opens with selected workspace context; manual mode preserved; reference chips navigate and disappear after disconnect');
}finally{await browser.close()}})().catch(e=>{console.error(e.message);process.exitCode=1});
