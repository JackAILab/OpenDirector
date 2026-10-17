// Real view controls, metadata-only projects. No planning or generation.
const {chromium}=require('playwright'),fs=require('fs'),assert=require('assert');
(async()=>{const browser=await chromium.launch({channel:'chromium',headless:true,args:['--no-sandbox']});try{
 const page=await browser.newPage({viewport:{width:1510,height:900}}),base=process.env.TEST_BASE_URL||'http://127.0.0.1:30080';
 const key=JSON.parse(fs.readFileSync(process.env.TEST_API_KEY_FILE)).api_key,headers={Authorization:'Bearer '+key};
 await page.addInitScript(k=>sessionStorage.setItem('h3_api_key',k),key);
 await page.route('**/creative/api/projects/*/execute',r=>r.abort());
 await page.route('**/creative/api/projects/*/message',r=>r.abort());
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 for(const mode of ['video','agent']){
  const response=await page.request.post(base+'/creative/api/projects',{headers,data:{message:'Director view toggle fixture',creation_mode:mode}});assert(response.ok());const fixture=await response.json();
  await page.goto(base+'/creative?project='+fixture.id+'&view=canvas');
  await page.getByRole('button',{name:'工作流',exact:true}).click();
  await page.evaluate(()=>{window.fitEvents=0;document.addEventListener('creative-fit-canvas',()=>window.fitEvents++)});
  if(mode==='video')await page.getByRole('button',{name:'打开 Director',exact:true}).click();
  const panel=page.locator(mode==='video'?'.workspace-director-frame':'.director');await panel.waitFor({state:'visible'});
  const orb=page.locator('.studio-agent-orb');assert.equal(await orb.getAttribute('aria-expanded'),'true');
  await page.getByRole('button',{name:'收起 Director',exact:true}).click();
  await panel.waitFor({state:'hidden'});assert.equal(await orb.getAttribute('aria-expanded'),'false');
  await page.waitForFunction(()=>window.fitEvents>0);
  await page.getByRole('button',{name:'打开 Director',exact:true}).click();await panel.waitFor({state:'visible'});
  await page.getByRole('button',{name:'故事板',exact:true}).click();
  await page.waitForFunction(()=>document.body.classList.contains('studio-agent-session')||document.body.classList.contains('workspace-director-story'));
  assert(!await orb.isVisible());
  await page.getByRole('button',{name:'工作流',exact:true}).click();await orb.waitFor({state:'visible'});
  await page.getByRole('button',{name:'收起 Director',exact:true}).click();await panel.waitFor({state:'hidden'});
  assert.equal(await page.evaluate(()=>project.id),fixture.id);assert.equal(await page.evaluate(()=>project.creation_mode),mode);
 }
 assert.deepEqual(errors,[]);console.log('PASS: manual and Agent Director toggles, storyboard return, fit events, project identity');
}finally{await browser.close()}})().catch(e=>{console.error(String(e.message).split('\n')[0]);process.exitCode=1});
