// Actual browser configuration controls; no provider submission.
const {chromium}=require('playwright'),fs=require('fs'),assert=require('assert');
(async()=>{const b=await chromium.launch({channel:'chromium',headless:true,args:['--no-sandbox']});try{
 const page=await b.newPage({viewport:{width:1510,height:900}}),base=process.env.TEST_BASE_URL||'http://127.0.0.1:30080',key=JSON.parse(fs.readFileSync(process.env.TEST_API_KEY_FILE)).api_key,headers={Authorization:'Bearer '+key};await page.addInitScript(k=>sessionStorage.setItem('h3_api_key',k),key);
 const parent=await(await page.request.post(base+'/creative/api/projects',{headers,data:{message:'video mode controls fixture',creation_mode:'video',model:'kling-video-v4_0',duration:5}})).json();
 await page.request.post(base+'/creative/api/projects/'+parent.id+'/manual-nodes',{headers,data:{message:'independent video',creation_mode:'video',model:'kling-video-v4_0',duration:5}});
 let executions=0;await page.route('**/creative/api/projects/*/execute',r=>{executions++;return r.abort()});
 await page.goto(base+'/creative?project='+parent.id+'&view=canvas');await page.getByRole('textbox',{name:'视频生成要求',exact:true}).waitFor();
 for(const name of ['视频生成模式','节点 2 生成模式']){
  const button=page.getByRole('button',{name,exact:true});assert.equal(await button.innerText(),'文生视频');await button.click();await page.locator('#videoInputDialog').waitFor();
  assert.equal(await page.locator('#videoInputMode').inputValue(),'text');await page.locator('#videoInputMode').selectOption('first_frame');
  await page.getByRole('button',{name:'关闭视频参考',exact:true}).click();assert.equal(await button.innerText(),'文生视频');
 }
 for(const selector of ['.manual-root-node','.manual-generation-node']){
  const root=page.locator(selector);
  for(const mode of ['first_frame','first_last','references']){
   const entry=root.locator('[data-video-start="'+mode+'"]');await entry.waitFor();
   if(await entry.isDisabled())continue;
   await entry.click();await page.locator('#videoInputDialog').waitFor();assert.equal(await page.locator('#videoInputMode').inputValue(),mode);
   assert(await page.locator('#videoInputPreview').isDisabled(),'No images: no valid preview yet');
   await page.getByRole('button',{name:'关闭视频参考',exact:true}).click();
  }
 }
 const boxes=await page.locator('.manual-node-options').evaluate(e=>({row:e.getBoundingClientRect().toJSON(),children:[...e.children].filter(x=>getComputedStyle(x).display!=='none').map(x=>x.getBoundingClientRect().toJSON())}));
 assert(boxes.children.every(r=>r.left>=boxes.row.left-1&&r.right<=boxes.row.right+1),'Parameter controls overflow the node');
 if(process.env.TEST_SCREENSHOT)await page.screenshot({path:process.env.TEST_SCREENSHOT});
 assert.equal(executions,0);console.log('PASS: separate model/mode controls, video labels, cancel preserves confirmed mode, toolbar fits, no generation');
}finally{await b.close()}})().catch(e=>{console.error(String(e.message).split('\n')[0]);process.exitCode=1});
