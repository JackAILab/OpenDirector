// Real browser UI with mocked task status; never submits paid generation.
const {chromium}=require('playwright'),fs=require('fs'),assert=require('assert');
(async()=>{
 const browser=await chromium.launch({channel:'chromium',headless:true,args:['--no-sandbox']});
 try{
  const page=await browser.newPage({viewport:{width:1510,height:900}}),base=process.env.TEST_BASE_URL||'http://127.0.0.1:30080';
  const key=JSON.parse(fs.readFileSync(process.env.TEST_API_KEY_FILE)).api_key,headers={Authorization:'Bearer '+key},errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.addInitScript(k=>sessionStorage.setItem('h3_api_key',k),key);
  const response=await page.request.post(base+'/creative/api/projects',{headers,data:{message:'progress visibility browser fixture',creation_mode:'video',model:'kling-video-v4_0',duration:25}});
  assert(response.ok());const fixture=await response.json();
  if(process.env.TEST_WITH_REFERENCE){
   const png=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aX1cAAAAASUVORK5CYII=','base64');
   const upload=await page.request.post(base+'/creative/api/projects/'+fixture.id+'/canvas/assets?kind=image&revision='+fixture.revision,{headers,data:png});assert(upload.ok());const asset=await upload.json();
   const saved=await page.request.put(base+'/creative/api/projects/'+fixture.id+'/canvas',{headers,data:{revision:asset.project.revision,nodes:[{id:'reference_note',kind:'text',label:'画面参考',text:'黄昏，柔和的逆光',role:'reference',x:40,y:40},{id:'reference_image',kind:'image',asset:asset.asset.id,label:'参考图片',text:'',role:'reference',x:40,y:240}],edges:[]}});assert(saved.ok());
  }
  assert((await page.request.post(base+'/creative/api/projects/'+fixture.id+'/manual-nodes',{headers,data:{message:'independent video fixture',creation_mode:'video',model:'kling-video-v3_0',duration:5}})).ok());
  await page.route('**/creative/api/projects/*/execute',route=>route.abort());
  await page.route('**/creative/api/projects/'+fixture.id,async route=>{
   if(route.request().method()!=='GET')return route.continue();
   const response=await route.fetch(),body=await response.json();
   body.state='running';body.film={...body.film,state:'running',provider_resolution:'polling',progress:{stage:'generating',percent:37}};
   await route.fulfill({response,json:body});
  });
  await page.goto(base+'/creative?project='+fixture.id+'&view=canvas');
  const progress=page.locator('.manual-root-progress');await progress.waitFor();
  assert((await progress.innerText()).includes('37%'));
  const meter=page.locator('.manual-root-node [role=progressbar]');
  assert.equal(await meter.getAttribute('aria-valuenow'),'37');
  await page.evaluate(()=>{delete project.film.progress.percent;document.dispatchEvent(new Event('creative-state-change'))});
  await page.waitForFunction(()=>document.querySelector('.manual-root-node [role=progressbar]')?.dataset.determinate==='false');
  assert.equal(await meter.getAttribute('aria-valuenow'),null,'Unknown provider progress must not invent a percentage');
  await page.emulateMedia({reducedMotion:'reduce'});
  assert.equal(await meter.locator('span').evaluate(e=>getComputedStyle(e).animationName),'none');
  await page.emulateMedia({reducedMotion:'no-preference'});
  await page.evaluate(()=>{project.film.progress.percent=37;document.dispatchEvent(new Event('creative-state-change'))});

  await page.locator('.manual-generation-node .manual-editor-toggle').click();
  await page.locator('.manual-node-editor textarea').fill('继续编辑另一个视频节点');
  assert(await progress.isVisible(),'Editing another node must not hide root progress');
  assert.equal(await page.locator('.manual-generation-node.manual-node-selected').count(),1);
  assert.equal(await page.locator('.manual-root-node.manual-node-selected').count(),0);
  assert(!await page.locator('.studio-manual-image-compose').isVisible());
  await page.locator('.manual-root-node .manual-editor-toggle:visible').focus();
  await page.keyboard.press('Enter');
  await page.locator('.studio-manual-image-compose textarea').focus();
  assert.equal(await page.locator('.manual-root-node.manual-node-selected').count(),1);
  assert.equal(await page.locator('.manual-generation-node.manual-node-selected').count(),0);
  assert(!await page.locator('.manual-node-editor').isVisible());
  await page.locator('.manual-generation-node .manual-editor-toggle').focus();
  await page.keyboard.press('Enter');
  await page.locator('.manual-node-editor textarea').focus();
  assert.equal(await page.locator('.manual-node-editor textarea').inputValue(),'继续编辑另一个视频节点');
  assert.equal(await page.locator('.manual-node-selected').count(),1);

  assert(!await page.locator('.studio-manual-image-compose').isVisible());
  assert(!await page.locator('.manual-result-edit').isVisible(),'Editing results must remain hidden until a result exists');
  await page.getByRole('button',{name:'打开 Director',exact:true}).click();
  await page.frameLocator('.workspace-director-frame').locator('#message').waitFor({state:'visible'});
  assert(await progress.isVisible());assert.equal(await page.locator('.canvas-film-task').count(),0);assert.equal(await page.locator('.manual-primary-result').count(),0);
  const bounds=await page.evaluate(()=>{const r=document.querySelector('.manual-root-node').getBoundingClientRect(),c=document.querySelector('.manual-generation-node').getBoundingClientRect(),d=document.querySelector('.workspace-director-frame').getBoundingClientRect();return {rootRight:r.right,childLeft:c.left,childRight:c.right,directorLeft:d.left}});
  if(process.env.TEST_WITH_REFERENCE){const separated=await page.evaluate(()=>{const r=document.querySelector('.manual-root-node').getBoundingClientRect();return [...document.querySelectorAll('.reference-node')].every(card=>{const n=card.getBoundingClientRect();return r.bottom<=n.top||r.top>=n.bottom||r.right<=n.left||r.left>=n.right})});assert(separated,'Reference and manual generator must not overlap')}
  assert(bounds.rootRight<=bounds.childLeft);assert(bounds.childRight<=bounds.directorLeft);
  if(process.env.TEST_SCREENSHOT)await page.screenshot({path:process.env.TEST_SCREENSHOT});
  await page.evaluate(()=>{project.state='paused';project.error='视频接口返回 401；已停止，不会自动重新生成。';document.dispatchEvent(new Event('creative-state-change'))});
  await page.waitForFunction(()=>document.querySelector('.manual-root-progress')?.textContent.includes('401'));
  assert(await progress.getByRole('button',{name:'重新提交',exact:true}).isVisible());
  assert.equal(await meter.count(),0,'Paused tasks must stop showing active progress');
  await page.reload();
  await page.locator('.manual-generation-node .manual-editor-toggle').click();
  assert.equal(await page.locator('.manual-node-editor textarea').inputValue(),'继续编辑另一个视频节点');
  assert(!await page.locator('.studio-manual-image-compose').isVisible());
  await page.locator('.manual-root-node .manual-editor-toggle:visible').click();
  const editorBounds=await page.locator('.studio-manual-image-compose').boundingBox();
  assert(editorBounds.y>=0&&editorBounds.y+editorBounds.height<900,'Explicit edit keeps the composer on screen');
  assert.deepEqual(errors,[]);console.log('PASS: progress stays visible while editing another node; Director does not overlap; failure appears inside root node');
 }finally{for(const context of browser.contexts())for(const page of context.pages())await page.unrouteAll({behavior:"ignoreErrors"});await browser.close()}
})().catch(e=>{console.error(String(e.message).split("\n")[0]);process.exitCode=1});
