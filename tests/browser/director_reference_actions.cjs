// Local UI contract fixture; never accesses a real account or provider.
const {chromium}=require('playwright'),fs=require('fs'),path=require('path'),assert=require('assert/strict');
(async()=>{const browser=await chromium.launch({headless:true,args:['--no-sandbox']});try{
 const root=path.resolve(__dirname,'../..'),dir=root+'/tools/agent_studio',out='/tmp/director-reference-actions';fs.mkdirSync(out,{recursive:true});
 const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[],writes=[];page.on('pageerror',e=>{errors.push(e.message);console.error('PAGE',e.stack)});await page.addInitScript(()=>sessionStorage.setItem('h3_api_key','fixture'));
 const p={id:'reference-flow',revision:1,state:'intake',creation_mode:'agent',model:'kling-video-v4_0',provider:'kling',duration:15,aspect:'16:9',brief:{product:'兴趣匹配应用'},messages:[{role:'user',content:'制作交友应用广告'}],questions:[{id:'brand',question:'请提供 Logo、品牌色和真实应用界面截图',why:'核对外观',options:['上传Logo与完整界面截图','只上传Logo和品牌色','暂不提供']}],decisions:[],assumptions:[],events:[],shots:[],canvas:{nodes:[],edges:[]},canvas_assets:{},quote:{label:'Kling 4.0',credits:12}};
 const aid='a'.repeat(32);let generation=0,planning=0,failPreview=false,videoBudget=null;
 await page.route('https://studio.test/**',r=>{const u=new URL(r.request().url()),f=dir+'/'+path.basename(u.pathname),method=r.request().method();if(method!=='GET')writes.push([method,u.pathname,r.request().postData()]);
 if(u.pathname==='/creative')return r.fulfill({contentType:'text/html',body:fs.readFileSync(dir+'/index.html')});
 if(/\.(css|js)$/.test(u.pathname)&&fs.existsSync(f))return r.fulfill({contentType:f.endsWith('.js')?'text/javascript':'text/css',body:fs.readFileSync(f)});
 if(u.pathname.endsWith('.woff2'))return r.fulfill({contentType:'font/woff2',body:fs.readFileSync(root+'/tools/asset_studio/public/fonts/studio-chinese.woff2')});
 if(u.pathname.endsWith('/models'))return r.fulfill({json:{models:[{id:p.model,label:'Kling 4.0',single_film:true,available:true,credits_per_5s:4}],image_models:[{id:'fixture-image',label:'参考图测试模型',mode:'both',max_references:3,available:true},{id:'fixture-text',label:'纯文字测试模型',mode:'text',max_references:0,available:true}]}});
 if(u.pathname.endsWith('/skills'))return r.fulfill({json:{skills:[]}});
 if(u.pathname.endsWith('/projects'))return r.fulfill({json:[{id:p.id,title:p.brief.product}]});
 if(u.pathname.endsWith('/canvas/assets')){p.revision++;p.canvas_assets[aid]={id:aid,kind:'image'};return r.fulfill({json:{project:p,asset:{id:aid,kind:'image'}}})}
 if(u.pathname.endsWith('/director-references')){const d=r.request().postDataJSON();assert.equal(d.references[0].asset,aid);p.revision++;p.video_inputs={mode:'references',references:d.references};return r.fulfill({json:p})}
 if(u.pathname.endsWith('/images/preview')){const d=r.request().postDataJSON();return failPreview?r.fulfill({status:422,json:{detail:'参考位已满'}}):r.fulfill({json:{credits:1,input_hash:'f'.repeat(64),...(d.director_video_credits?{video_credits:d.director_video_credits,total_credits:1+d.director_video_credits}:{})}})}
 if(u.pathname.endsWith('/images')){generation++;const d=r.request().postDataJSON();assert(d.director_reference&&d.connect_to_director);assert.deepEqual(d.references,p.video_inputs.references);assert.equal(d.approved_credits,1);assert.match(d.director_context,/直接帮我生成一个/);videoBudget=d.director_video_credits??null;if(videoBudget)p.auto_approval={state:'armed',credits:videoBudget};p.revision++;p.image_task={id:d.request_id,state:'running',director_context:d.director_context};return r.fulfill({json:p})}
 if(u.pathname.endsWith('/stop')){p.stop_requested=true;return r.fulfill({json:p})}
 if(u.pathname.endsWith('/message')){planning++;return r.fulfill({status:500,json:{detail:'should route to image action'}})}
 if(u.pathname.endsWith('/projects/'+p.id))return r.fulfill({json:p});return r.fulfill({status:404,json:{detail:'fixture'}})});
 await page.goto('https://studio.test/creative?project=reference-flow&view=storyboard');await page.locator('.question-answer-toggle').waitFor();
 await page.locator('.agent-settings-toggle').click();
 await page.getByRole('button',{name:'上传Logo与完整界面截图',exact:true}).click();
 await page.locator('#directorReferenceUpload').waitFor();
 await page.getByLabel('选择参考图片').setInputFiles({name:'reference.png',mimeType:'image/png',buffer:Buffer.from('fixture bytes')});
 await page.waitForFunction(()=>document.querySelector('#directorReferenceUpload')===null);
 assert.match(await page.locator('.question-answer-toggle').textContent(),/已上传并绑定/);
 assert.equal(await page.getByLabel('Agent 参考图模型').locator('option[value="fixture-text"]').isDisabled(),true);
 assert.match(await page.locator('#chatForm > .director-reference-actions').textContent(),/生图将使用 1 张已绑定参考/);
 await page.locator('.question-answer-toggle').click();await page.locator('.question textarea').fill('直接帮我生成一个');
 await page.getByRole('button',{name:'生成参考图 · 1 积分',exact:true}).click();
 await page.waitForFunction(()=>typeof project!=='undefined'&&project.image_task?.state==='running');
 assert.equal(generation,1);assert.equal(planning,0);assert.equal(await page.locator('.question textarea').inputValue(),'');
 assert.equal(await page.getByRole('button',{name:'Agent 生图 · 1 积分',exact:true}).isDisabled(),true);
 p.image_task={...p.image_task,state:'needs_review'};p.revision++;await page.evaluate(()=>refreshProjectStatus());
 await page.locator('#message').fill('直接帮我生成一个');failPreview=true;await Promise.all([page.waitForResponse(r=>r.url().endsWith('/images/preview')&&r.status()===422),page.locator('#sendButton').click()]);await page.waitForFunction(()=>!busy);assert.equal(generation,1);assert.equal(await page.locator('#message').inputValue(),'直接帮我生成一个');
 failPreview=false;await page.locator('#sendButton').click();await page.waitForFunction(()=>project.image_task?.state==='running');assert.equal(generation,2);assert.equal(planning,0);assert.equal(await page.locator('#message').inputValue(),'');
 assert.equal(videoBudget,null);p.image_task.state='needs_review';p.approval_mode='auto';p.revision++;await page.evaluate(()=>refreshProjectStatus());await page.locator('#message').fill('直接帮我生成一个');
 const produce=page.getByRole('button',{name:'参考图＋成片 · 13 积分',exact:true});
 page.once('dialog',async d=>{assert.match(d.message(),/总上限 13 积分/);await d.dismiss()});await produce.click();assert.equal(generation,2);
 page.once('dialog',async d=>d.accept());await produce.click();await page.waitForFunction(()=>project.image_task?.state==='running');
 assert.equal(generation,3);assert.equal(videoBudget,12);assert.equal(planning,0);
 await page.getByRole('button',{name:'取消后续自动制作',exact:true}).click();await page.waitForFunction(()=>project.stop_requested);
 assert.deepEqual(errors,[]);await page.screenshot({path:out+'/reference-actions.png'});
 console.log('PASS upload/binding, image-only action, combined budget confirmation/cancel, one image submission, stop subsequent video; local fixture only');
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exitCode=1});
