// Browser draft persistence and recovery isolation; no paid generation.
const {chromium}=require('playwright'),fs=require('fs'),assert=require('assert');
(async()=>{const b=await chromium.launch({channel:'chromium',headless:true,args:['--no-sandbox']});try{
 const page=await b.newPage({viewport:{width:1510,height:900}}),base=process.env.TEST_BASE_URL||'http://127.0.0.1:30080',key=JSON.parse(fs.readFileSync(process.env.TEST_API_KEY_FILE)).api_key,headers={Authorization:'Bearer '+key};
 await page.addInitScript(k=>sessionStorage.setItem('h3_api_key',k),key);
 const p=await (await page.request.post(base+'/creative/api/projects',{headers,data:{message:'draft persistence parent',creation_mode:'video',model:'kling-video-v4_0'}})).json();
 const child=await (await page.request.post(base+'/creative/api/projects/'+p.id+'/manual-nodes',{headers,data:{message:'原任务提示词',creation_mode:'video',model:'kling-video-v4_0',duration:25}})).json();
 await page.route('**/creative/api/projects/*/execute',r=>r.abort());
 await page.goto(base+'/creative?project='+p.id+'&view=canvas');
 const card=page.locator('.manual-generation-node'),prompt=card.locator('textarea'),model=card.locator('select').nth(0),duration=card.locator('select').nth(1);await card.waitFor();
 await model.selectOption('kling-video-v3_0',{force:true});await duration.selectOption('5');await prompt.fill('第二个节点的新视频草稿');
 await page.reload();await card.waitFor();
 assert.equal(await prompt.inputValue(),'第二个节点的新视频草稿');assert.equal(await model.inputValue(),'kling-video-v3_0');assert.equal(await duration.inputValue(),'5');
 const stored=await (await page.request.get(base+'/creative/api/projects/'+child.project.id,{headers})).json();assert.equal(stored.model,'kling-video-v4_0');assert.equal(stored.duration,25);
 child.project.state='paused';child.project.film={state:'generating',job_id:'fixture-existing-job',progress:{stage:'generating'}};
 await page.route('**/creative/api/projects/'+p.id+'/manual-nodes',r=>r.fulfill({json:{nodes:[child]}}));
 await page.reload();await card.waitFor();
 assert.equal(await prompt.inputValue(),'原任务提示词');assert.equal(await model.inputValue(),'kling-video-v4_0');assert.equal(await duration.inputValue(),'25');assert(await prompt.evaluate(e=>e.readOnly));
 child.project.state='failed';child.project.film.state='failed';
 await page.waitForFunction(()=>document.querySelector('.manual-node-editor textarea')?.readOnly===false,{},{timeout:10000});
 assert.equal(await prompt.inputValue(),'第二个节点的新视频草稿');assert.equal(await model.inputValue(),'kling-video-v3_0');assert.equal(await duration.inputValue(),'5');
 await prompt.fill('');await page.reload();await card.waitFor();assert.equal(await prompt.inputValue(),'');
 console.log('PASS: draft model/duration/prompt survive reload, server unchanged, pending job uses original inputs, blank draft retained');
}finally{await b.close()}})().catch(e=>{console.error(String(e.message).split('\n')[0]);process.exitCode=1});
