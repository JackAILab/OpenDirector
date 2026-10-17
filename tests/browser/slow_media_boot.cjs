// A stalled media response must not hide the workspace. No paid generation.
const {chromium}=require('playwright'),fs=require('fs'),assert=require('assert');
(async()=>{const b=await chromium.launch({channel:'chromium',headless:true,args:['--no-sandbox']});try{
 const p=await b.newPage(),base=process.env.TEST_BASE_URL||'http://127.0.0.1:30080',key=JSON.parse(fs.readFileSync(process.env.TEST_API_KEY_FILE)).api_key;
 await p.addInitScript(k=>sessionStorage.setItem('h3_api_key',k),key);
 const r=await p.request.post(base+'/creative/api/projects',{headers:{Authorization:'Bearer '+key},data:{message:'slow media boot fixture',creation_mode:'video'}});assert(r.ok());const fixture=await r.json();
 await p.route('**/creative/api/projects/'+fixture.id,async route=>{const response=await route.fetch(),body=await response.json();body.state='completed';body.artifact='fixture';body.shots=[{id:'s1',start:0,duration:5,state:'completed',title:'视频',caption:'',rationale:'',prompt:'fixture'}];await route.fulfill({response,json:body})});
 let release,requested=false;const stalled=new Promise(resolve=>release=resolve);
 await p.route('**/media/final',async route=>{requested=true;await stalled;await route.abort()});
 await p.route('**/execute',route=>route.abort());
 await p.goto(base+'/creative?project='+fixture.id+'&view=canvas');
 await p.waitForFunction(()=>!document.querySelector('#studioBoot'),{},{timeout:5000});assert(requested);assert.equal(await p.locator('body').evaluate(e=>getComputedStyle(e).visibility),'visible');
 await p.getByRole('button',{name:'打开 Director',exact:true}).click();await p.locator('.workspace-director-frame').waitFor({state:'visible'});
 release();console.log('PASS: stalled media does not block workspace or Director');
 }finally{await b.close()}})().catch(e=>{console.error(String(e.message).split('\n')[0]);process.exitCode=1});
