// Read-only projection test: inject a future result's control receipt, never rewrite historical assets.
const {chromium}=require('playwright'),fs=require('fs'),assert=require('assert');
(async()=>{const b=await chromium.launch({channel:'chromium',headless:true,args:['--no-sandbox']});try{
 const c=await b.newContext({storageState:process.env.TEST_STORAGE_STATE,viewport:{width:1510,height:900}});
 if(process.env.TEST_SESSION_STORAGE)await c.addInitScript(s=>{for(const[k,v]of Object.entries(s))sessionStorage.setItem(k,v)},JSON.parse(fs.readFileSync(process.env.TEST_SESSION_STORAGE)));
 const p=await c.newPage(),pid=process.env.TEST_PROJECT_ID,aid=process.env.TEST_ASSET_ID;assert(pid&&aid);let writes=0;
 await p.route('**/creative/api/**',async r=>{if(r.request().method()!=='GET'){writes++;return r.abort()}return r.continue()});
 await p.route('**/creative/api/projects/'+pid,async r=>{const response=await r.fetch(),body=await response.json();assert(body.canvas_lineage[aid]?.sources.length);body.canvas_lineage[aid].control_parameters={kind:'light',preset:'暖色侧光',direction:90,elevation:30,intensity:65,temperature:3200};await r.fulfill({response,json:body})});
 await p.goto((process.env.TEST_BASE_URL||'http://127.0.0.1:30080')+'/creative?project='+pid+'&view=canvas');
 const card=p.locator('[data-node-id="'+process.env.TEST_NODE_ID+'"]');await card.locator('.canvas-card-head').click();await p.getByRole('button',{name:'前后对比',exact:true}).click();
 const dialog=p.locator('#imageComparisonDialog');await dialog.waitFor();const receipt=await dialog.innerText();for(const value of ['生成参数','暖色侧光','90°','30°','65%','3200K'])assert(receipt.includes(value),value);assert(!receipt.includes('保留原光照'));
 await p.waitForFunction(()=>[...document.querySelectorAll('#imageComparisonStage img')].length===2&&[...document.querySelectorAll('#imageComparisonStage img')].every(i=>i.complete&&i.naturalWidth>0),null,{timeout:60000});
 if(process.env.TEST_SCREENSHOT)await p.screenshot({path:process.env.TEST_SCREENSHOT});
 await dialog.getByRole('button',{name:'关闭图片对比',exact:true}).click();assert.equal(writes,0);console.log('PASS: bound numeric parameters visible beside decoded before/after images; zero writes');
}finally{for(const c of b.contexts())for(const p of c.pages())await p.unrouteAll({behavior:'ignoreErrors'});await b.close()}})().catch(e=>{console.error(String(e.message).split('\n')[0]);process.exitCode=1});
