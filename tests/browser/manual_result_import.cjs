// UI receipt projection with mocked completion/import; backend import has API tests.
const {chromium}=require('playwright'),fs=require('fs'),assert=require('assert');
(async()=>{const b=await chromium.launch({channel:'chromium',headless:true,args:['--no-sandbox']});try{
 const page=await b.newPage({viewport:{width:1510,height:900}}),base=process.env.TEST_BASE_URL||'http://127.0.0.1:30080',key=JSON.parse(fs.readFileSync(process.env.TEST_API_KEY_FILE)).api_key,headers={Authorization:'Bearer '+key};
 await page.addInitScript(k=>sessionStorage.setItem('h3_api_key',k),key);
 const p=await (await page.request.post(base+'/creative/api/projects',{headers,data:{message:'result import fixture',creation_mode:'video',model:'kling-video-v4_0'}})).json();
 const child=await (await page.request.post(base+'/creative/api/projects/'+p.id+'/manual-nodes',{headers,data:{message:'completed image fixture',creation_mode:'image'}})).json();
 const png=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aX1cAAAAASUVORK5CYII=','base64');
 const aid='a'.repeat(32),nid='result_fixture';child.project.image_task={state:'completed',asset:aid};
 await page.route('**/creative/api/projects/'+p.id+'/manual-nodes',r=>r.fulfill({json:{nodes:[child]}}));
 await page.route('**/canvas/assets/'+aid+'/preview',r=>r.fulfill({contentType:'image/png',body:png}));
 let calls=0;await page.route('**/manual-nodes/'+child.project.id+'/result',r=>{calls++;return r.fulfill({json:{project:{...p,revision:p.revision+1,canvas_assets:{[aid]:{id:aid,kind:'image',width:1,height:1}},canvas:{nodes:[{id:nid,kind:'image',asset:aid,label:'生成结果 · 图片',text:'',role:'reference',x:40,y:930}],edges:[]}},node:{id:nid,asset:aid}}})});
 await page.route('**/creative/api/projects/*/execute',r=>r.abort());
 await page.goto(base+'/creative?project='+p.id+'&view=canvas');
 await page.getByRole('button',{name:'在当前画布编辑',exact:true}).click();
 const result=page.locator('[data-node-id="'+nid+'"]');await result.waitFor();assert.equal(calls,1);assert(page.url().includes(p.id));assert(await result.locator('img').first().isVisible());
 await result.locator('.canvas-card-head').click();
 await page.getByRole('button',{name:'多角度',exact:true}).waitFor({state:'visible'});
 if(process.env.TEST_SCREENSHOT)await page.screenshot({path:process.env.TEST_SCREENSHOT});
 console.log('PASS: child result opens on same canvas and exposes image tools');
}finally{await b.close()}})().catch(e=>{console.error(String(e.message).split('\n')[0]);process.exitCode=1});
