const {chromium}=require('playwright'),fs=require('fs'),assert=require('assert');
(async()=>{const browser=await chromium.launch({channel:'chromium',headless:true,args:['--no-sandbox']});try{
 const page=await browser.newPage({viewport:{width:1510,height:900}}),base=process.env.TEST_BASE_URL||'http://127.0.0.1:30080',key=JSON.parse(fs.readFileSync(process.env.TEST_API_KEY_FILE)).api_key,headers={Authorization:'Bearer '+key};
 await page.addInitScript(k=>sessionStorage.setItem('h3_api_key',k),key);
 const p=await(await page.request.post(base+'/creative/api/projects',{headers,data:{message:'reference parent',creation_mode:'image'}})).json();
 const png=await page.evaluate(()=>{const c=document.createElement('canvas');c.width=320;c.height=180;const x=c.getContext('2d');x.fillStyle='#6699bb';x.fillRect(0,0,320,180);return c.toDataURL().split(',')[1]});
 const upload=await(await page.request.post(base+'/creative/api/projects/'+p.id+'/canvas/assets?kind=image&revision='+p.revision,{headers,data:Buffer.from(png,'base64')})).json(),aid=upload.asset.id;
 assert((await page.request.put(base+'/creative/api/projects/'+p.id+'/canvas',{headers,data:{revision:upload.project.revision,nodes:[{id:'ref1',kind:'image',asset:aid,label:'场景参考',role:'reference',text:'',x:40,y:40}],edges:[]}})).ok());
 const child=await(await page.request.post(base+'/creative/api/projects/'+p.id+'/manual-nodes',{headers,data:{message:'参考场景生成视频',creation_mode:'video',model:'kling-video-v4_0',duration:5}})).json();
 let paid=0;await page.route('**/execute',r=>{paid++;return r.abort()});await page.goto(base+'/creative?project='+p.id+'&view=canvas');
 await page.getByRole('button',{name:'节点 2 参考图片',exact:true}).click();const chooser=page.getByRole('dialog',{name:'从当前画布添加视频参考'});
 await chooser.locator('[data-asset="'+aid+'"]').click();await page.waitForFunction(()=>document.querySelector('.manual-reference-dialog [data-added=true]'));
 assert.equal(await page.locator('.manual-reference-edges path').count(),0,'Copying assets does not establish model inputs');
 await chooser.getByRole('button',{name:'配置已添加参考',exact:true}).click();await page.locator('#videoInputDialog').waitFor();
 await page.locator('#videoInputMode').selectOption('references');await page.locator('#videoInputChoices [data-asset="'+aid+'"]').click();await page.locator('#videoInputPreview').click();await page.locator('#videoInputSave').click();await page.locator('#videoInputDialog').waitFor({state:'detached'});
 const result=await(await page.request.get(base+'/creative/api/projects/'+child.project.id,{headers})).json();assert.equal(result.video_inputs.references[0].asset,aid);assert.equal(result.duration,5);assert.equal(result.direct_prompt,'参考场景生成视频');assert.equal(paid,0);assert(page.url().includes('project='+p.id));
 const tile=page.locator('.manual-generation-node .manual-input-reference');await tile.waitFor();assert.equal(await tile.getAttribute('data-asset'),aid);await page.waitForFunction(()=>document.querySelector('.manual-generation-node .manual-input-reference img')?.naturalWidth>0);await tile.click();await page.locator('#videoInputDialog').waitFor();assert.equal(await page.locator('#videoInputRows .reference-input-focus').getAttribute('data-asset'),aid);await page.getByRole('button',{name:'关闭视频参考',exact:true}).click();
 await page.getByRole('button',{name:'节点 2 参考图片',exact:true}).click();assert(await chooser.locator('[data-asset="'+aid+'"]').isDisabled());
 await chooser.getByRole('button',{name:'关闭画布参考',exact:true}).click();
 const edge=page.locator('.manual-reference-edges path');await edge.waitFor({state:'attached'});assert.equal(await edge.count(),1);assert.equal(await edge.getAttribute('data-source'),'ref1');assert.equal(await edge.getAttribute('data-target'),child.project.id);
 const before=await edge.getAttribute('d'),head=page.locator('.manual-node-head'),rect=await head.boundingBox();await page.mouse.move(rect.x+30,rect.y+5);await page.mouse.down();await page.mouse.move(rect.x+90,rect.y+50,{steps:6});await page.mouse.up();await page.waitForFunction(d=>document.querySelector('.manual-reference-edges path')?.getAttribute('d')!==d,before);
 await page.route('**/creative/api/projects/'+p.id+'/manual-nodes',async r=>{const response=await r.fetch(),body=await response.json();body.nodes[0].project.state='running';body.nodes[0].project.film={state:'generating',progress:{percent:23}};await r.fulfill({response,json:body})});
 await page.waitForFunction(()=>document.querySelector('.manual-reference-edges path')?.classList.contains('is-running'),{},{timeout:10000});
 assert(await tile.isVisible());assert(await tile.isDisabled());await page.emulateMedia({reducedMotion:'reduce'});assert.equal(await edge.evaluate(e=>getComputedStyle(e).animationName),'none');await page.emulateMedia({reducedMotion:'no-preference'});
 if(process.env.TEST_SCREENSHOT)await page.screenshot({path:process.env.TEST_SCREENSHOT});

 console.log('PASS: parent image copied through child reference UI, confirmed as model input, no generation, confirmed-only edges track dragging and task activity');
}finally{for(const c of browser.contexts())for(const p of c.pages())await p.unrouteAll({behavior:"ignoreErrors"});await browser.close()}})().catch(e=>{console.error(String(e.message).split('\n')[0]);process.exitCode=1});
