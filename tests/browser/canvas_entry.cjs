// Public UI is read-only. --fixture creates one temporary project, with providers disabled.
const {chromium}=require('playwright'),fs=require('fs'),assert=require('assert/strict');
(async()=>{
 const fixture=process.argv.includes('--fixture'),base=fixture?'http://127.0.0.1:30129':'https://creative.jackailab.com',out='outputs/creative_ui/20261016_multi_entry';fs.mkdirSync(out,{recursive:true});
 const b=await chromium.launch({channel:'chromium',headless:true,args:['--no-sandbox']});
 try{
 const p=await b.newPage({viewport:{width:1920,height:1080}}),errors=[],writes=[];
 p.on('pageerror',e=>errors.push(e.message));p.on('request',r=>{if(r.url().includes('/creative/api/')&&!['GET','HEAD','OPTIONS'].includes(r.method()))writes.push(new URL(r.url()).pathname)});
 let token='fixture';if(!fixture){assert((await p.request.post(base+'/site/access',{data:{password:fs.readFileSync('/opt/visualstation/creative-runtime/site-access-password.txt','utf8').trim()}})).ok());token=JSON.parse(fs.readFileSync('/var/lib/visualstation-local/public-acceptance-account.json')).api_key}
 await p.addInitScript(k=>{sessionStorage.setItem('h3_api_key',k);localStorage.setItem('creative-theme','dark');sessionStorage.setItem('creative_entry_draft',JSON.stringify({pending:true,prompt:'黑色机车夹克，展示斜向拉链，面向美国观众，15 秒英文口播。',model:'kling-video-v3_0_omni',skill:'ad-video',approval:'manual',aspect:'9:16'}))},token);
 await p.goto(base+'/creative?new=1',{waitUntil:'domcontentloaded'});
 await p.waitForFunction(()=>document.body.classList.contains('studio-new-entry')&&!document.querySelector('#initialSkill').disabled);
 assert.equal(await p.locator('dialog[open]').count(),0);assert.equal(await p.locator('#provider').inputValue(),'kling-video-v3_0_omni');assert.equal(await p.locator('#aspect').inputValue(),'9:16');assert.match(await p.locator('#initialBrief').inputValue(),/斜向拉链/);
 assert(await p.locator('#chatForm').isHidden());assert(await p.locator('.canvas-output').isHidden());assert(await p.locator('#createForm').isVisible());
 await p.locator('#entry-provider').click();const picker=p.locator('#studioEntryPicker');await picker.waitFor();assert(await picker.getByRole('button',{name:/Kling O3/}).isEnabled());assert(await picker.getByRole('button',{name:/Kling 2.5/}).isDisabled());
 const bounds=await picker.boundingBox();assert(bounds.x>=0&&bounds.x+bounds.width<=1920);await p.screenshot({path:out+'/'+(fixture?'fixture':'public')+'-models.png',mask:[p.locator('.studio-canvas-account-actions')]});
 await picker.getByRole('button',{name:/Kling O3/}).click();assert(await picker.isHidden());await p.waitForFunction(()=>document.querySelector('#entry-provider').getAttribute('aria-expanded')==='false');
 await p.locator('#entry-initialSkill').click();await picker.getByRole('searchbox').fill('商品广告导演');await picker.getByRole('button',{name:/商品广告导演/}).click();
 await p.locator('#entry-aspect').click();await picker.getByRole('button',{name:/^16:9/}).click();assert.equal(await p.locator('#aspect').inputValue(),'16:9');await p.locator('#entry-aspect').click();await picker.getByRole('button',{name:/^9:16/}).click();
 const file={name:'jacket-reference.png',mimeType:'image/png',buffer:fs.readFileSync('/root/.codex/attachments/bcf881ef-ec49-4a4b-9a1d-f2191d7bbf53/ref_clothes.png')};
 const choose=p.waitForEvent('filechooser');await p.getByRole('button',{name:'添加商品参考图',exact:true}).click();await(await choose).setFiles(file);await p.locator('.studio-entry-reference img').waitFor();assert.equal(await p.locator('.studio-entry-reference img').evaluate(e=>e.complete&&e.naturalWidth>0),true);
 await p.getByRole('button',{name:'移除待上传参考图'}).click();assert(await p.locator('.studio-entry-reference').isHidden());await p.locator('#initialReference').setInputFiles(file);
 await p.locator('#initialBrief').blur();await p.screenshot({path:out+'/'+(fixture?'fixture':'public')+'-desktop.png',mask:[p.locator('.studio-canvas-account-actions')]});
 await p.setViewportSize({width:390,height:844});await p.locator('#entry-provider').click();const mobile=await picker.boundingBox();assert(mobile.x>=0&&mobile.x+mobile.width<=390&&mobile.y>=0&&mobile.y+mobile.height<=844);await p.screenshot({path:out+'/'+(fixture?'fixture':'public')+'-mobile.png',mask:[p.locator('.studio-canvas-account-actions')]});await p.keyboard.press('Escape');assert(await picker.isHidden());
 await p.evaluate(()=>document.documentElement.dataset.theme='light');await p.screenshot({path:out+'/'+(fixture?'fixture':'public')+'-light.png',mask:[p.locator('.studio-canvas-account-actions')]});
 assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);await p.setViewportSize({width:1920,height:1080});
 if(fixture){
  // A product photo is a soft reference for O3, but is not a matching 9:16 first frame.
  assert.match(await p.locator('.studio-entry-reference-mode').innerText(),/多图软参考/);
  await p.locator('#entry-provider').click();await picker.getByRole('button',{name:/Kling 3.0/}).click();assert.match(await p.locator('.studio-entry-reference-mode').innerText(),/首帧参考/);
  await p.getByRole('button',{name:'发送创作需求',exact:true}).click();await p.waitForFunction(()=>document.querySelector('#toast').textContent.includes('比例与'));assert.equal(writes.length,0);assert(await p.locator('#createForm').isVisible());
  await p.locator('#entry-provider').click();await picker.getByRole('button',{name:/Kling O3/}).click();
  await p.getByRole('button',{name:'发送创作需求',exact:true}).click();await p.waitForFunction(()=>project?.video_inputs&&project.state==='planning_failed',{},{timeout:30000});
  const result=await p.evaluate(()=>({id:project.id,model:project.model,aspect:project.aspect,skill:project.skill_id,approval:project.approval_mode,training:project.training_eligible,message:project.messages[0].content,reference:!!project.reference,inputs:project.video_inputs,manifest:project.input_manifest,canvas:project.canvas,state:project.state}));
  assert.equal(result.model,'kling-video-v3_0_omni');assert.equal(result.aspect,'9:16');assert.equal(result.skill,'ad-video');assert.equal(result.approval,'manual');assert.equal(result.training,false);assert.equal(result.reference,false);assert.match(result.message,/斜向拉链/);assert(await p.locator('#createForm').isHidden());assert(await p.locator('#chatForm').isVisible());
  assert.equal(result.inputs.mode,'references');assert.equal(result.inputs.references.length,1);assert.equal(result.inputs.references[0].role,'product');assert.match(result.inputs.input_hash,/^[a-f0-9]{64}$/);assert.equal(result.manifest.mode,'references');assert.equal(result.manifest.images[0].asset,result.inputs.references[0].asset);assert.equal(result.canvas.nodes[0].asset,result.inputs.references[0].asset);
  const meta=await p.request.get(base+'/creative/api/projects/'+result.id+'/canvas/assets/'+result.inputs.references[0].asset+'/metadata',{headers:{Authorization:'Bearer fixture'}});assert(meta.ok());const dimensions=await meta.json();assert.equal(dimensions.width,585);assert.equal(dimensions.height,407);
  assert.equal(writes.filter(x=>x==='/creative/api/projects').length,1);assert(writes.some(x=>x.endsWith('/canvas/assets')));assert(writes.some(x=>x.endsWith('/video-inputs')));assert(writes.some(x=>x.endsWith('/message')));assert(!writes.some(x=>x.endsWith('/execute')));
  await p.screenshot({path:out+'/fixture-bound-input.png',mask:[p.locator('.studio-canvas-account-actions')]});
  // Binding failure preserves the uploaded product and stops before any interview or generation.
  const writesBefore=writes.length;await p.goto(base+'/creative?new=1',{waitUntil:'domcontentloaded'});await p.waitForFunction(()=>document.body.classList.contains('studio-new-entry')&&!document.querySelector('#initialSkill').disabled);await p.locator('#initialReference').setInputFiles(file);
  await p.route('**/video-inputs/preview',r=>r.fulfill({status:503,contentType:'application/json',body:'{"detail":"输入核对暂时不可用"}'}));
  await p.getByRole('button',{name:'发送创作需求',exact:true}).click();await p.waitForFunction(()=>document.querySelector('#toast').textContent.includes('已上传的参考图保留'));
  assert.equal(await p.evaluate(()=>project.state),'intake');assert.equal(await p.evaluate(()=>Object.keys(project.canvas_assets).length),1);assert.equal(await p.evaluate(()=>project.canvas.nodes.length),1);assert.equal(await p.evaluate(()=>!!project.video_inputs),false);
  const failureWrites=writes.slice(writesBefore);assert.equal(failureWrites.filter(x=>x==='/creative/api/projects').length,1);assert(!failureWrites.some(x=>/\/(message|execute)$/.test(x)));
  await p.unroute('**/video-inputs/preview');await p.locator('#canvasVideoInputs').click();await p.locator('#videoInputDialog').waitFor();assert.equal(await p.locator('#videoInputChoices button').count(),1);await p.screenshot({path:out+'/fixture-recovery-input.png',mask:[p.locator('.studio-canvas-account-actions')]});await p.locator('#videoInputMode').selectOption('references');await p.locator('#videoInputChoices button').click();await p.locator('#videoInputPreview').click();await p.locator('#videoInputSave').click();await p.waitForFunction(()=>project?.video_inputs?.mode==='references');assert.equal(await p.evaluate(()=>Object.keys(project.canvas_assets).length),1);assert(!writes.slice(writesBefore).some(x=>/\/(message|execute)$/.test(x)));
  fs.writeFileSync(out+'/fixture-verification.json',JSON.stringify({passed:true,ui_created:true,selected_settings:true,actual_product_image:true,source_dimensions:[585,407],video_aspect:'9:16',input_mode:'references',hash_bound:true,first_frame_mismatch_stops_before_create:true,binding_failure_preserves_image:true,manual_binding_recovery:true,no_text_fallback:true,provider_disabled:true,paid_calls:0,errors},null,2));
 }else{
  // A failed catalogue load is recoverable from the initial composer itself.
  let fail=true;await p.route('**/creative/api/skills',r=>fail?(fail=false,r.fulfill({status:503,contentType:'application/json',body:'{"detail":"catalogue test"}'})):r.continue());
  await p.reload({waitUntil:'domcontentloaded'});await p.locator('#entry-initialSkill').click();await picker.getByRole('button',{name:'重新读取 Skill'}).click();await p.waitForFunction(()=>!document.querySelector('#initialSkill').disabled);await picker.getByRole('button',{name:/商品广告导演/}).click();await p.unroute('**/creative/api/skills');
  await p.goto(base+'/creative?project=ddc97d3742fdf0cbdbd28928&view=canvas',{waitUntil:'domcontentloaded'});await p.waitForFunction(()=>project?.id==='ddc97d3742fdf0cbdbd28928');assert(await p.locator('#createForm').isHidden());assert(await p.locator('#chatForm').isVisible());
  assert.deepEqual(writes,[]);fs.writeFileSync(out+'/public-verification.json',JSON.stringify({passed:true,no_modal:true,preserved_handoff:true,model_skill_aspect_controls:true,reference_preview_remove:true,mobile:true,light:true,catalogue_manual_recovery:true,existing_project_preserved:true,writes,paid_calls:0,errors},null,2));
 }
 assert.deepEqual(errors,[]);console.log('PASS '+(fixture?'temporary real project creation/upload, director provider disabled':'public initial composer/read-only, recovery and existing project')+'; zero paid calls');
 }finally{await b.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
