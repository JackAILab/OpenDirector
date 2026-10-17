// Task status fixtures, real stop ownership/persistence API. No provider jobs created.
const {chromium}=require('playwright'),fs=require('fs'),assert=require('assert');
(async()=>{const b=await chromium.launch({channel:'chromium',headless:true,args:['--no-sandbox']});try{
 const page=await b.newPage({viewport:{width:1510,height:900}}),base=process.env.TEST_BASE_URL||'http://127.0.0.1:30080',key=JSON.parse(fs.readFileSync(process.env.TEST_API_KEY_FILE)).api_key,headers={Authorization:'Bearer '+key};await page.addInitScript(k=>sessionStorage.setItem('h3_api_key',k),key);
 const parent=await(await page.request.post(base+'/creative/api/projects',{headers,data:{message:'pause parent fixture',creation_mode:'video',model:'kling-video-v4_0'}})).json();
 const children=[];for(let i=0;i<2;i++)children.push(await(await page.request.post(base+'/creative/api/projects/'+parent.id+'/manual-nodes',{headers,data:{message:'pause video fixture '+i,creation_mode:'video',model:'kling-video-v4_0',duration:5}})).json());
 for(const child of children){child.project.state='running';child.project.film={state:'generating',job_id:'fixture-only',progress:{stage:'generating',percent:23}}}
 await page.route('**/creative/api/projects/'+parent.id+'/manual-nodes',r=>r.fulfill({json:{nodes:children}}));
 const stopped=[];await page.route('**/creative/api/projects/*/stop',async r=>{const id=r.request().url().split('/').at(-2);const response=await r.fetch();assert(response.ok());stopped.push(id);const child=children.find(c=>c.project.id===id);child.project.stop_requested=true;await r.fulfill({response,json:child.project})});
 let executions=0;await page.route('**/creative/api/projects/*/execute',r=>{executions++;return r.abort()});
 await page.goto(base+'/creative?project='+parent.id+'&view=canvas');
 await page.getByRole('button',{name:'暂停跟进节点 2',exact:true}).click();
 const first=page.locator('[data-manual-project="'+children[0].project.id+'"]');
 await first.getByText('等待暂停',{exact:true}).waitFor();assert(await first.getByRole('button',{name:'暂停跟进节点 2',exact:true}).isDisabled());assert((await first.innerText()).includes('等待暂停'));
 assert(!await page.getByRole('button',{name:'暂停跟进节点 3',exact:true}).isDisabled());assert.deepEqual(stopped,[children[0].project.id]);
 const get=async id=>(await page.request.get(base+'/creative/api/projects/'+id,{headers})).json();
 assert.equal((await get(children[0].project.id)).stop_requested,true);assert(!(await get(children[1].project.id)).stop_requested);assert(!(await get(parent.id)).stop_requested);
 children[0].project.state='paused';await page.waitForFunction(id=>document.querySelector('[data-manual-project="'+id+'"]')?.getAttribute('aria-busy')==='false',children[0].project.id,{timeout:10000});await first.getByRole('button',{name:'恢复查询节点 2',exact:true}).waitFor({timeout:10000});assert.equal(await first.locator('[role=progressbar]').count(),0);assert.equal(executions,0);
 console.log('PASS: per-video pause request persists only to selected node, pending/paused states and original-job recovery shown, no generation');
}finally{await b.close()}})().catch(e=>{console.error(String(e.message).split('\n')[0]);process.exitCode=1});
