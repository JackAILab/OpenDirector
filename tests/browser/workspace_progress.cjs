// Read-only UI regression: override project GET states; never submit generation.
const {chromium}=require('playwright'),fs=require('fs'),assert=require('assert');
(async()=>{
 const base=process.env.TEST_BASE_URL||'https://creative.jackailab.com';
 let id=process.env.TEST_PROJECT_ID;const key=JSON.parse(fs.readFileSync(process.env.TEST_API_KEY_FILE)).api_key;
 assert(key,'Provide a test session file');
 const b=await chromium.launch({channel:'chromium',headless:true,args:['--no-sandbox']});
 try{
  const p=await b.newPage({viewport:{width:1440,height:1000}}),errors=[];
  p.on('pageerror',e=>errors.push(e.message));
  await p.addInitScript(k=>sessionStorage.setItem('h3_api_key',k),key);
  if(!id){const created=await p.request.post(base+'/creative/api/projects',{headers:{Authorization:'Bearer '+key},data:{message:'Agent progress browser fixture',creation_mode:'agent'}});assert(created.ok());id=(await created.json()).id}
  const response=await p.request.get(base+'/creative/api/projects/'+id,{headers:{Authorization:'Bearer '+key}});
  assert(response.ok());const original=await response.json();
  const fixture={...original,state:'running',creation_mode:'agent',artifact:null,result_asset:null,
   canvas:{nodes:[],edges:[]},film:{state:'generating',job_id:'test-only',progress:{stage:'generating',percent:37}},shots:[]};
  await p.route('**/creative/api/projects/'+id,route=>route.request().method()==='GET'?route.fulfill({json:fixture}):route.abort());
  await p.route('**/execute',route=>route.abort());
  await p.goto(base+'/creative?project='+id);
  await p.getByRole('button',{name:'工作流',exact:true}).click();
  await p.locator('.canvas-film-task').getByText('生成中 37%',{exact:true}).waitFor();
  assert.equal(await p.locator('.canvas-film-task').getAttribute('aria-busy'),'true');
  const meter=p.locator('.canvas-film-task [role=progressbar]');assert.equal(await meter.getAttribute('aria-valuenow'),'37');
  await p.evaluate(()=>{delete project.film.progress.percent;document.dispatchEvent(new Event('creative-status-sync'))});
  await p.waitForFunction(()=>document.querySelector('.canvas-film-task [role=progressbar]')?.dataset.determinate==='false');
  assert.equal(await meter.getAttribute('aria-valuenow'),null);
  await p.emulateMedia({reducedMotion:'reduce'});assert.equal(await meter.locator('span').evaluate(e=>getComputedStyle(e).animationName),'none');
  await p.emulateMedia({reducedMotion:'no-preference'});
  await p.getByRole('button',{name:'故事板',exact:true}).click();
  assert(await p.evaluate(()=>document.body.classList.contains('studio-agent-session')));
  await p.getByRole('button',{name:'工作流',exact:true}).click();
  fixture.state='paused';fixture.error='测试：查询中断，已有任务保留';
  await p.reload();await p.getByRole('button',{name:'工作流',exact:true}).click();
  await p.getByRole('button',{name:'恢复查询已有任务',exact:true}).waitFor();
  assert.equal(await p.locator('.canvas-film-task').getAttribute('aria-busy'),'false');
  assert.equal(await p.locator('.canvas-film-task [role=progressbar]').count(),0);
  assert(!(await p.locator('.canvas-film-task').innerText()).includes('37%'));
  assert.deepEqual(errors,[]);console.log('Live progress, paused recovery, workflow/storyboard: PASS (no generation)');
 }finally{await b.close()}
})().catch(e=>{console.error(String(e.message).split("\n")[0]);process.exitCode=1});
