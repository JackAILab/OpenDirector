const {chromium}=require('playwright'),fs=require('fs'),assert=require('assert');
(async()=>{const browser=await chromium.launch({channel:'chromium',headless:true,args:['--no-sandbox']});try{
 const page=await browser.newPage({viewport:{width:1510,height:900}}),base=process.env.TEST_BASE_URL||'http://127.0.0.1:30080',key=JSON.parse(fs.readFileSync(process.env.TEST_API_KEY_FILE)).api_key,headers={Authorization:'Bearer '+key};
 await page.addInitScript(k=>sessionStorage.setItem('h3_api_key',k),key);
 const p=await(await page.request.post(base+'/creative/api/projects',{headers,data:{message:'reference parent',creation_mode:'video',model:'kling-video-v4_0',duration:5}})).json();
 const png=await page.evaluate(()=>{const c=document.createElement('canvas');c.width=320;c.height=180;const x=c.getContext('2d');x.fillStyle='#6699bb';x.fillRect(0,0,320,180);return c.toDataURL().split(',')[1]});
 const upload=await(await page.request.post(base+'/creative/api/projects/'+p.id+'/canvas/assets?kind=image&revision='+p.revision,{headers,data:Buffer.from(png,'base64')})).json(),aid=upload.asset.id;
 assert((await page.request.put(base+'/creative/api/projects/'+p.id+'/canvas',{headers,data:{revision:upload.project.revision,nodes:[{id:'ref1',kind:'image',asset:aid,label:'场景参考',role:'reference',text:'',x:40,y:40}],edges:[]}})).ok());
 const child={project:p};
 let paid=0;await page.route('**/execute',r=>{paid++;return r.abort()});await page.goto(base+'/creative?project='+p.id+'&view=canvas');
 const port=page.getByRole('button',{name:'拖动图片参考 场景参考',exact:true}),target=page.locator('.manual-root-node .studio-free-node-preview');await port.waitFor();await port.dragTo(target);
 await page.locator('#videoInputDialog').waitFor();assert.equal(await page.locator('#videoInputMode').inputValue(),'references');assert.equal(await page.locator('#videoInputRows article').count(),1);assert.equal(await page.locator('#videoInputRows article').getAttribute('data-asset'),aid);
 assert.equal(await page.locator('.manual-reference-edges path').count(),0);await page.getByRole('button',{name:'关闭视频参考',exact:true}).click();
 let saved=await(await page.request.get(base+'/creative/api/projects/'+child.project.id,{headers})).json();assert(!saved.video_inputs,'Dropping and closing must not confirm model inputs');
 await port.dragTo(target);await page.locator('#videoInputDialog').waitFor();await page.locator('#videoInputPreview').click();await page.locator('#videoInputSave').click();await page.locator('#videoInputDialog').waitFor({state:'detached'});await page.locator('.manual-reference-edges path').waitFor({state:'attached'});
 saved=await(await page.request.get(base+'/creative/api/projects/'+child.project.id,{headers})).json();assert.equal(saved.video_inputs.references[0].asset,aid);assert.equal(saved.duration,5);assert.equal(paid,0);

 const tile=page.locator('.manual-root-node .manual-input-reference');await tile.waitFor();assert.equal(await tile.getAttribute('data-asset'),aid);assert((await tile.innerText()).includes('参考 1'));await page.waitForFunction(()=>document.querySelector('.manual-root-node .manual-input-reference img')?.naturalWidth>0);await tile.click();await page.locator('#videoInputDialog').waitFor();assert.equal(await page.locator('#videoInputRows .reference-input-focus').getAttribute('data-asset'),aid);await page.getByRole('button',{name:'关闭视频参考',exact:true}).click();

 const edge=page.locator('.manual-reference-edges path');
 const point=await edge.evaluate(e=>{const p=e.getPointAtLength(e.getTotalLength()/2),t=e.getScreenCTM();return {x:t.a*p.x+t.c*p.y+t.e,y:t.b*p.x+t.d*p.y+t.f}});await page.mouse.click(point.x,point.y);
 await page.locator('#videoInputDialog').waitFor();assert.equal(await page.locator('#videoInputRows .reference-input-focus').getAttribute('data-asset'),aid);await page.getByRole('button',{name:'关闭视频参考',exact:true}).click();assert.equal(await edge.count(),1);
 await edge.focus();await page.keyboard.press('Enter');await page.locator('#videoInputDialog').waitFor();await page.getByRole('button',{name:'移除视频输入',exact:true}).click();await page.locator('#videoInputMode').selectOption('text');await page.locator('#videoInputPreview').click();await page.locator('#videoInputSave').click();await page.locator('#videoInputDialog').waitFor({state:'detached'});await page.waitForFunction(()=>document.querySelectorAll('.manual-reference-edges path').length===0);
 const detached=await(await page.request.get(base+'/creative/api/projects/'+child.project.id,{headers})).json();assert.equal(detached.video_inputs.references.length,0);assert.equal(await tile.count(),0);assert(detached.canvas_assets[aid]);assert.equal(await page.locator('.reference-node').count(),1);assert.equal(paid,0);
 await page.evaluate(()=>{project.state='running';project.film={state:'generating'};document.dispatchEvent(new Event('creative-state-change'))});await port.dragTo(target);assert.equal(await page.locator('#videoInputDialog').count(),0,'Running root must reject reference drops');
 if(process.env.TEST_SCREENSHOT)await page.screenshot({path:process.env.TEST_SCREENSHOT});
 console.log('PASS: real mouse drag selects root video reference; cancel leaves inputs unchanged; confirmation creates connection; mouse/keyboard manage and remove inputs without deleting assets');
}finally{await browser.close()}})().catch(e=>{console.error(String(e.message).split('\n')[0]);process.exitCode=1});
