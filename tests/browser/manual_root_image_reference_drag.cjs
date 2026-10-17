const {chromium}=require('playwright'),fs=require('fs'),assert=require('assert');
(async()=>{const browser=await chromium.launch({channel:'chromium',headless:true,args:['--no-sandbox']});try{
 const page=await browser.newPage({viewport:{width:1510,height:900}}),base=process.env.TEST_BASE_URL||'http://127.0.0.1:30080',key=JSON.parse(fs.readFileSync(process.env.TEST_API_KEY_FILE)).api_key,headers={Authorization:'Bearer '+key};await page.addInitScript(k=>sessionStorage.setItem('h3_api_key',k),key);
 let p=await(await page.request.post(base+'/creative/api/projects',{headers,data:{message:'image references parent',creation_mode:'image'}})).json();const ids=[];
 for(const color of ['#6699bb','#997755']){const png=await page.evaluate(color=>{const c=document.createElement('canvas');c.width=320;c.height=180;const x=c.getContext('2d');x.fillStyle=color;x.fillRect(0,0,320,180);return c.toDataURL().split(',')[1]},color);const r=await(await page.request.post(base+'/creative/api/projects/'+p.id+'/canvas/assets?kind=image&revision='+p.revision,{headers,data:Buffer.from(png,'base64')})).json();p=r.project;ids.push(r.asset.id)}
 assert((await page.request.put(base+'/creative/api/projects/'+p.id+'/canvas',{headers,data:{revision:p.revision,nodes:ids.map((id,i)=>({id:'ref'+i,kind:'image',asset:id,label:'参考 '+(i+1),role:'reference',text:'',x:40,y:40+i*240})),edges:[]}})).ok());
 const child={project:p};
 let submitted=null;await page.route('**/creative/api/projects/'+child.project.id+'/images',r=>{submitted=r.request().postDataJSON();return r.fulfill({status:409,json:{detail:'测试拦截付费生成'}})});
 await page.goto(base+'/creative?project='+p.id+'&view=canvas');const target=page.locator('.manual-root-node .studio-free-node-preview');
 for(let i=0;i<ids.length;i++){
  await page.getByRole('button',{name:'拖动图片参考 参考 '+(i+1),exact:true}).dragTo(target);await page.locator('#imageComposer').waitFor();
  assert.equal(await page.locator('#composeImageInputs article').count(),i+1);
  await page.getByRole('button',{name:'关闭图像生成',exact:true}).click();await page.locator('#imageComposer').waitFor({state:'detached'});
 }
 await page.getByRole('button',{name:'拖动图片参考 参考 1',exact:true}).dragTo(target);await page.locator('#imageComposer').waitFor();assert.equal(await page.locator('#composeImageInputs article').count(),2);
 await page.locator('#composeImagePrompt').fill('保留图一的场景色调，融合图二的材质');await page.locator('#composeImagePreview').click();await page.locator('#composeImageConfirm').waitFor({state:'visible'});assert((await page.locator('#composeImageSummary').innerText()).includes('2 张输入'));
 await page.getByRole('button',{name:'关闭图像生成',exact:true}).click();await page.waitForFunction(()=>document.querySelector('.studio-manual-image-compose textarea')?.value==='保留图一的场景色调，融合图二的材质');assert.equal(await page.locator('.studio-manual-image-compose textarea').inputValue(),'保留图一的场景色调，融合图二的材质');assert.equal(submitted,null);
 const tiles=page.locator('.manual-root-node .manual-input-reference');assert.equal(await tiles.count(),2);
 await page.mouse.move(600,150);await page.keyboard.down('Control');await page.mouse.wheel(0,100);await page.keyboard.up('Control');await page.waitForTimeout(300);const viewBefore=await page.locator('.canvas-world').evaluate(e=>e.style.transform);
 await page.waitForFunction(()=>[...document.querySelectorAll('.manual-root-node .manual-input-reference img')].every(i=>i.naturalWidth>0));const beforeImages=await tiles.locator('img').evaluateAll(imgs=>imgs.map(i=>i.src));const firstTile=await tiles.first().elementHandle();
 await tiles.nth(1).click();await page.locator('#imageComposer').waitFor();assert.equal(await page.locator('#composeImageInputs .reference-input-focus').getAttribute('data-asset'),ids[1]);
 await page.locator('#composeImageInputs .reference-input-focus select').selectOption('style');await page.getByRole('button',{name:'关闭图像生成',exact:true}).click();await page.waitForFunction(()=>document.querySelectorAll('.manual-root-node .manual-input-reference-slot')[1]?.textContent.includes('风格'));
 await page.waitForTimeout(300);assert.equal(await page.locator('.canvas-world').evaluate(e=>e.style.transform),viewBefore,'Changing reference role must preserve user zoom and pan');
 assert.deepEqual(await tiles.locator('img').evaluateAll(imgs=>imgs.map(i=>i.src)),beforeImages,'Role changes must reuse decoded previews');assert(await firstTile.evaluate(e=>e.isConnected),'Role changes must retain tile elements');
 await page.getByRole('button',{name:'生成图片',exact:true}).click();await page.waitForTimeout(500);assert(submitted);assert.deepEqual(submitted.references.map(r=>r.asset),ids);assert.equal(submitted.approved_credits,1);assert.equal(submitted.connect_to_director,false);
 await page.evaluate(assets=>{project.image_task={state:'running',prepared:{references:assets.map(asset=>({asset,role:'reference'}))}};document.dispatchEvent(new Event('creative-manual-view-ready'))},ids);
 assert.deepEqual(await tiles.locator('img').evaluateAll(imgs=>imgs.map(i=>i.src)),beforeImages,'Running-state labels must reuse previews');assert(await tiles.first().isDisabled());assert.equal(await page.locator('.manual-root-node .manual-input-reference-strip').getAttribute('aria-label'),'本次生成图片参考');
 await page.evaluate(()=>{project.image_task.state='completed';document.dispatchEvent(new Event('creative-manual-view-ready'))});assert(!(await tiles.first().isDisabled()));assert((await tiles.nth(1).innerText()).includes('风格'));assert.deepEqual(await tiles.locator('img').evaluateAll(imgs=>imgs.map(i=>i.src)),beforeImages);
 const viewBeforeRun=await page.locator('.canvas-world').evaluate(e=>e.style.transform);
 await page.evaluate(({id,asset})=>{project.image_task={state:'running',prepared:{references:[{asset,role:'scene'}]}};document.dispatchEvent(new Event('creative-manual-view-ready'))},{id:p.id,asset:ids[0]});
 await page.waitForTimeout(300);assert.equal(await page.locator('.canvas-world').evaluate(e=>e.style.transform),viewBeforeRun,'Frozen running references must preserve camera');
 assert.equal(await tiles.count(),1);assert(await tiles.first().isDisabled());assert.equal(await page.locator('.manual-root-node .manual-input-reference-strip').getAttribute('aria-label'),'本次生成图片参考');
 await page.evaluate(id=>{project.image_task.state='completed';sessionStorage.removeItem('manual-image-draft:'+id);document.dispatchEvent(new Event('creative-manual-view-ready'))},p.id);assert.equal(await tiles.count(),0,'Historical references must not become next draft');
 console.log('PASS: two workspace images dragged, deduplicated, previewed, retained on close and sent by root image node; paid endpoint intercepted');
}finally{for(const c of browser.contexts())for(const p of c.pages())await p.unrouteAll({behavior:"ignoreErrors"});await browser.close()}})().catch(e=>{console.error(String(e.message).split('\n')[0]);process.exitCode=1});
