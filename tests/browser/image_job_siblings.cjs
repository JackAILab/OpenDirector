// Replay an already completed owned task as running; never submits generation.
const {chromium}=require('playwright'),fs=require('fs'),assert=require('assert');
(async()=>{const b=await chromium.launch({channel:'chromium',headless:true,args:['--no-sandbox']});try{
 assert(process.env.TEST_PROJECT_ID);const c=await b.newContext({storageState:process.env.TEST_STORAGE_STATE,viewport:{width:1510,height:900}});
 if(process.env.TEST_SESSION_STORAGE)await c.addInitScript(s=>{for(const[k,v]of Object.entries(s))sessionStorage.setItem(k,v)},JSON.parse(fs.readFileSync(process.env.TEST_SESSION_STORAGE)));
 const p=await c.newPage(),base=process.env.TEST_BASE_URL||'http://127.0.0.1:30080';let writes=0;
 await p.route('**/creative/api/**',async r=>{if(!['GET','HEAD'].includes(r.request().method())){writes++;return r.abort()}if(new URL(r.request().url()).pathname==='/creative/api/projects/'+process.env.TEST_PROJECT_ID){const response=await r.fetch(),body=await response.json();assert(body.image_task?.id);body.image_task={...body.image_task,state:'running',progress:{phase:'generating',percent:37}};return r.fulfill({response,json:body})}return r.continue()});
 await p.goto(base+'/creative?project='+process.env.TEST_PROJECT_ID+'&view=canvas');const task=p.locator('[data-system-node="image-job"]');await task.waitFor();await p.locator('.manual-generation-node').first().waitFor();
 await p.waitForFunction(()=>document.querySelectorAll('.manual-generation-node').length>=2);await p.waitForTimeout(700);
 const overlaps=await p.evaluate(()=>{const box=document.querySelector('[data-system-node="image-job"]').getBoundingClientRect();return [...document.querySelectorAll('.reference-node,.manual-generation-node,.manual-root-node')].filter(e=>!e.hidden&&getComputedStyle(e).display!=='none').some(e=>{const r=e.getBoundingClientRect();return box.left<r.right&&box.right>r.left&&box.top<r.bottom&&box.bottom>r.top})});assert(!overlaps,'Task card must avoid reference, root and sibling generators');assert((await task.innerText()).includes('37%'));assert.equal(writes,0);console.log('PASS: image progress avoids existing reference and image/video generators, zero submissions');
 }finally{for(const c of b.contexts())for(const p of c.pages())await p.unrouteAll({behavior:'ignoreErrors'});await b.close()}
})().catch(e=>{console.error(String(e.message).split('\n')[0]);process.exitCode=1});
