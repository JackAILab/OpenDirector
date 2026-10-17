// Existing completed media only: selection/navigation must never write or generate.
const {chromium}=require('playwright'),fs=require('fs'),assert=require('assert');
(async()=>{const b=await chromium.launch({channel:'chromium',headless:true,args:['--no-sandbox']});try{
 const c=await b.newContext({viewport:{width:1510,height:900}});await c.addInitScript(s=>{for(const[k,v]of Object.entries(s))sessionStorage.setItem(k,v)},JSON.parse(fs.readFileSync(process.env.TEST_SESSION_STORAGE)));const p=await c.newPage(),writes=[];
 await p.route('**/creative/api/**',r=>{if(!['GET','HEAD'].includes(r.request().method())){writes.push(r.request().method());return r.abort()}return r.continue()});
 for(const id of process.env.TEST_PROJECT_IDS.split(',')){
  await p.goto((process.env.TEST_BASE_URL||'http://127.0.0.1:30080')+'/creative?project='+id+'&view=canvas');
  const result=p.locator('.manual-root-result'),editor=p.locator('.studio-manual-image-compose'),handle=p.locator('.manual-delivered-head');await result.waitFor();await handle.waitFor();
  const original=await editor.locator('textarea').inputValue();
  await p.mouse.click(1000,100);await p.waitForFunction(()=>!document.querySelector('.manual-root-node').classList.contains('manual-node-selected'));
  assert(!await editor.isVisible());assert(await handle.isVisible());
  await handle.getByRole('button').click();assert(await editor.isVisible());assert.equal(await editor.locator('textarea').inputValue(),original);
  const bounds=await editor.boundingBox();assert(bounds.y>=0&&bounds.y+bounds.height<900);
  await p.mouse.click(1000,100);assert(!await editor.isVisible());
  await result.locator('.canvas-card-head strong').click();assert(await editor.isVisible());assert.equal(await editor.locator('textarea').inputValue(),original);
  const position=await p.evaluate(()=>{const r=document.querySelector('.manual-root-result'),n=document.querySelector('.manual-root-node');return {left:r.offsetLeft===n.offsetLeft,gap:n.offsetTop-r.offsetTop-r.offsetHeight}});assert(position.left);assert(position.gap>=10&&position.gap<=14);
  await p.screenshot({path:'/tmp/manual-delivered-'+id+'.png'});
 }
 assert.deepEqual(writes,[]);console.log('PASS completed image/video parameter handle, result selection, aligned layout, preserved prompts; zero writes');
}finally{for(const c of b.contexts())for(const p of c.pages())await p.unrouteAll({behavior:'ignoreErrors'});await b.close()}})().catch(e=>{console.error(String(e.message).split('\n')[0]);process.exitCode=1});
