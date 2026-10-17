// Mock provider states; browser must resume the original job without patching inputs.
const {chromium}=require('playwright'),fs=require('fs'),assert=require('assert');
(async()=>{const b=await chromium.launch({channel:'chromium',headless:true,args:['--no-sandbox']});try{
 const page=await b.newPage({viewport:{width:1510,height:900}}),base=process.env.TEST_BASE_URL||'http://127.0.0.1:30080',key=JSON.parse(fs.readFileSync(process.env.TEST_API_KEY_FILE)).api_key,headers={Authorization:'Bearer '+key};
 await page.addInitScript(k=>sessionStorage.setItem('h3_api_key',k),key);
 const p=await (await page.request.post(base+'/creative/api/projects',{headers,data:{message:'recovery parent',creation_mode:'video',model:'kling-video-v4_0'}})).json();
 const child=await (await page.request.post(base+'/creative/api/projects/'+p.id+'/manual-nodes',{headers,data:{message:'原任务提示词',creation_mode:'video',model:'kling-video-v3_0',duration:5}})).json();
 child.project.state='paused';child.project.film={state:'generating',job_id:'fixture-existing-job',progress:{stage:'generating',percent:41}};child.project.error='查询中断，原任务仍在生成';child.project.quote={...child.project.quote,credits:0,new_jobs:0};
 await page.route('**/creative/api/projects/'+p.id+'/manual-nodes',r=>r.fulfill({json:{nodes:[child]}}));
 await page.route('**/creative/api/projects/'+child.project.id+'/budget',r=>r.fulfill({json:{sufficient:true,revision:child.project.revision,required_credits:0}}));
 let patches=0,executions=0;await page.route('**/creative/api/projects/'+child.project.id+'/manual-prompt',r=>{patches++;return r.abort()});
 await page.route('**/creative/api/projects/'+child.project.id+'/execute',r=>{executions++;assert.equal(r.request().postDataJSON().approved_credits,0);child.project.state='running';child.project.error='';return r.fulfill({json:child.project})});
 await page.goto(base+'/creative?project='+p.id+'&view=canvas');const card=page.locator('.manual-generation-node'),prompt=card.locator('textarea');await card.waitFor();
 assert((await card.locator('.manual-node-notice').innerText()).includes('查询中断'));assert(await prompt.evaluate(e=>e.readOnly));assert.equal(await prompt.inputValue(),'原任务提示词');assert(await card.locator('.studio-model-picker-trigger').isDisabled());
 await card.getByRole('button',{name:'恢复查询节点 2',exact:true}).click();await page.waitForFunction(()=>document.querySelector('.manual-generation-node')?.getAttribute('aria-busy')==='true');assert.equal(executions,1);assert.equal(patches,0);assert((await card.locator('.manual-node-status').innerText()).includes('41%'));
 child.project.state='failed';child.project.film.state='failed';child.project.error='生成失败，请修改后重新提交';
 await page.waitForFunction(()=>document.querySelector('.manual-node-editor textarea')?.readOnly===false,{},{timeout:10000});assert((await card.locator('.manual-node-notice').innerText()).includes('生成失败'));assert(!await card.locator('.studio-model-picker-trigger').isDisabled());
 await prompt.fill('修改后的新提示词');await card.getByRole('button',{name:'生成节点 2',exact:true}).click();await page.waitForTimeout(200);assert.equal(patches,1);assert.equal(executions,1);
 console.log('PASS: persistent child errors, immutable resume inputs, original-job query, editable terminal failure');
}finally{await b.close()}})().catch(e=>{console.error(String(e.message).split('\n')[0]);process.exitCode=1});
