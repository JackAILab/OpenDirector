const {chromium}=require('playwright'),fs=require('fs'),assert=require('assert');
(async()=>{const browser=await chromium.launch({channel:'chromium',headless:true,args:['--no-sandbox']});try{
 const page=await browser.newPage({viewport:{width:1510,height:900}}),base=process.env.TEST_BASE_URL||'http://127.0.0.1:30080',key=JSON.parse(fs.readFileSync(process.env.TEST_API_KEY_FILE)).api_key,headers={Authorization:'Bearer '+key};await page.addInitScript(k=>sessionStorage.setItem('h3_api_key',k),key);
 let p=await(await page.request.post(base+'/creative/api/projects',{headers,data:{message:'image references parent',creation_mode:'image'}})).json();const ids=[];
 for(const color of ['#6699bb','#997755']){const png=await page.evaluate(color=>{const c=document.createElement('canvas');c.width=320;c.height=180;const x=c.getContext('2d');x.fillStyle=color;x.fillRect(0,0,320,180);return c.toDataURL().split(',')[1]},color);const r=await(await page.request.post(base+'/creative/api/projects/'+p.id+'/canvas/assets?kind=image&revision='+p.revision,{headers,data:Buffer.from(png,'base64')})).json();p=r.project;ids.push(r.asset.id)}
 assert((await page.request.put(base+'/creative/api/projects/'+p.id+'/canvas',{headers,data:{revision:p.revision,nodes:ids.map((id,i)=>({id:'ref'+i,kind:'image',asset:id,label:'参考 '+(i+1),role:'reference',text:'',x:40,y:40+i*240})),edges:[]}})).ok());
 const child=await(await page.request.post(base+'/creative/api/projects/'+p.id+'/manual-nodes',{headers,data:{message:'结合两张参考图生成新场景',creation_mode:'image',image_model:'kling-image-v3_0'}})).json();
 let submitted=null;await page.route('**/creative/api/projects/'+child.project.id+'/images',r=>{submitted=r.request().postDataJSON();return r.fulfill({status:409,json:{detail:'测试拦截付费生成'}})});
 await page.goto(base+'/creative?project='+p.id+'&view=canvas');const target=page.locator('.manual-node-preview');
 for(let i=0;i<ids.length;i++){
  await page.getByRole('button',{name:'拖动图片参考 参考 '+(i+1),exact:true}).dragTo(target);await page.locator('#imageComposer').waitFor();
  assert.equal(await page.locator('#composeImageInputs article').count(),i+1);
  await page.getByRole('button',{name:'关闭图像生成',exact:true}).click();await page.waitForFunction(n=>document.querySelector('.manual-node-reference')?.textContent==='参考 · '+n,i+1);
 }
 await page.getByRole('button',{name:'拖动图片参考 参考 1',exact:true}).dragTo(target);await page.locator('#imageComposer').waitFor();assert.equal(await page.locator('#composeImageInputs article').count(),2);
 await page.locator('#composeImagePrompt').fill('保留图一的场景色调，融合图二的材质');await page.locator('#composeImagePreview').click();await page.locator('#composeImageConfirm').waitFor({state:'visible'});assert((await page.locator('#composeImageSummary').innerText()).includes('2 张输入'));
 await page.getByRole('button',{name:'关闭图像生成',exact:true}).click();await page.waitForFunction(()=>document.querySelector('.manual-node-editor textarea')?.value==='保留图一的场景色调，融合图二的材质');assert.equal(await page.locator('.manual-node-editor textarea').inputValue(),'保留图一的场景色调，融合图二的材质');assert.equal(await page.locator('.manual-node-reference').innerText(),'参考 · 2');assert.equal(submitted,null);
 await page.getByRole('button',{name:'生成节点 2',exact:true}).click();await page.waitForTimeout(500);assert(submitted);assert.deepEqual(submitted.references.map(r=>r.asset),ids);assert.equal(submitted.approved_credits,1);assert.equal(submitted.connect_to_director,false);
 console.log('PASS: two workspace images dragged, deduplicated, previewed, retained on close and sent by image child; paid endpoint intercepted');
}finally{await browser.close()}})().catch(e=>{console.error(String(e.message).split('\n')[0]);process.exitCode=1});
