// Start image_composer_server.py first. Real API/state with a fixed image model.
const {chromium}=require('playwright'),fs=require('fs'),assert=require('assert/strict');
(async()=>{const browser=await chromium.launch({headless:true,args:['--no-sandbox']});try{
 const page=await browser.newPage({viewport:{width:1512,height:982}}),origin='http://127.0.0.1:30132',errors=[];page.on('pageerror',e=>errors.push(e.message));page.on('dialog',d=>d.accept());
 const headers={Authorization:'Bearer fixture'},request=async(path,method='GET',data)=>{const r=await page.request.fetch(origin+'/creative/api'+path,{headers,method,data});assert(r.ok(),await r.text());return r.json()};
 const identity=await(await page.request.get(origin+'/acceptance/identity')).json();assert.equal(identity.fixture,'image-composer-fixed-model');
 let p=await request('/projects','POST',{message:'商品、人物与场景的组合输入测试',aspect:'16:9'}),url='/projects/'+p.id;const ids=[];
 for(const color of ['red','blue','green']){const r=await page.request.post(origin+'/creative/api'+url+'/canvas/assets?kind=image&revision='+p.revision,{headers,data:fs.readFileSync(identity.fixtures+'/'+color+'.png')});assert(r.ok());const data=await r.json();p=data.project;ids.push(data.asset.id)}
 p=await request(url+'/canvas','PUT',{revision:p.revision,nodes:ids.map((asset,i)=>({id:'n'+i,asset,kind:'image',role:['product','person','scene'][i],label:['商品图','人物图','场景图'][i],text:'',x:i*310,y:30})),edges:[]});
 await page.addInitScript(()=>sessionStorage.setItem('h3_api_key','fixture'));await page.route('**/creative/api/model-status',r=>r.fulfill({json:{models:[]}}));
 await page.goto(origin+'/creative?project='+p.id+'&view=canvas');await page.waitForSelector('.node-image-model',{state:'attached'});
 await page.locator('#canvasAddMenu>summary').click();await page.getByRole('button',{name:'组合参考生成',exact:true}).click();await page.waitForSelector('#imageComposer');
 for(const aid of ids)await page.locator('#composeImageChoices [data-asset="'+aid+'"]').click();
 assert(await page.locator('#composeImagePreview').isDisabled());assert((await page.locator('#composeImageMessage').textContent()).includes('只接受文字'));
 await page.locator('#composeImageModel').selectOption('hunyuan-image-v2.0-general-edit');await page.locator('#composeImagePrompt').fill('把商品穿在人物身上，放到参考场景中');
 await page.locator('#composeImageInputs article').nth(2).getByRole('button',{name:'图片提前'}).click();
 assert.deepEqual(await page.locator('#composeImageInputs article').evaluateAll(es=>es.map(e=>e.dataset.asset)),[ids[0],ids[2],ids[1]]);
 await page.getByLabel('图 1 保留要求').fill('保留斜向拉链，不照抄图片里的文字');await page.locator('#composeImagePreview').click();await page.waitForSelector('#composeImageConfirm',{state:'visible'});
 assert((await page.locator('#composeImageSummary').textContent()).includes('3 张输入 → 1 张新图'));
 await page.getByLabel('图 2 保留要求').fill('保留空间和光线');assert(await page.locator('#composeImageConfirm').isHidden());
 await page.locator('#composeImagePreview').click();await page.waitForSelector('#composeImageConfirm',{state:'visible'});await page.locator('#composeImageReview summary').click();
 const evidence=process.env.IMAGE_EVIDENCE||'/tmp/image-composer-browser';fs.mkdirSync(evidence,{recursive:true});await page.evaluate(()=>document.fonts.ready);await page.screenshot({path:evidence+'/composer-desktop.png'});
 assert.equal((await(await page.request.get(origin+'/acceptance/identity')).json()).used,0);
 await page.setViewportSize({width:390,height:844});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);assert((await page.locator('#imageComposer').boundingBox()).width<=390);await page.locator('#composeImageConfirm').scrollIntoViewIfNeeded();await page.screenshot({path:evidence+'/composer-mobile.png'});
 await page.locator('#composeImageConfirm').click();await page.waitForSelector('#imageComposer',{state:'detached'});await page.waitForFunction(()=>project.image_task?.state==='completed',{},{timeout:30000});
 p=await request(url);assert.equal(p.canvas.nodes.length,4);assert.equal(p.canvas.edges.length,0);assert(p.canvas.nodes.at(-1).x>620);const aid=p.image_task.asset;
 assert.deepEqual(p.canvas_lineage[aid].sources,[ids[0],ids[2],ids[1]]);assert.deepEqual(p.canvas_lineage[aid].inputs.map(i=>i.role),['product','scene','person']);assert.deepEqual(p.canvas_lineage[aid].adjustments,{angle:'保留原角度',light:'保留原光照'});
 await page.setViewportSize({width:1512,height:982});await page.reload();await page.waitForSelector('.image-input-provenance',{state:'attached'});assert.equal(await page.locator('.canvas-edges>path.derived').count(),3);
 await page.locator('.reference-node:has(.image-input-provenance)').getByRole('button',{name:'编辑素材',exact:true}).click();assert.equal(await page.locator('.image-input-provenance summary').textContent(),'实际图片输入 · 3 张');await page.locator('.image-input-provenance summary').click();assert.equal(await page.locator('.image-compare').count(),1);if(!await page.locator('.generation-options:has(.image-compare)').evaluate(e=>e.open))await page.locator('.generation-options:has(.image-compare)>summary').click();await page.locator('.image-compare summary').click();assert.equal(await page.locator('.image-compare-grid').count(),1);assert.match(await page.locator('.image-compare-adjustments').textContent(),/侧面|视角|光线/);if(await page.locator('#chatToggle').getAttribute('aria-expanded')==='true')await page.locator('#chatToggle').click();await page.locator('#canvasViewMenu>summary').click();await page.getByRole('button',{name:'适应画布',exact:true}).click();await page.screenshot({path:evidence+'/generated-lineage.png'});
 const final=await(await page.request.get(origin+'/acceptance/identity')).json();assert.equal(final.calls.length,1);assert.equal(final.calls[0].references.length,3);assert.equal(final.used,1);assert.equal(final.paid_calls,0);assert.deepEqual(errors,[]);
 fs.writeFileSync(evidence+'/acceptance.json',JSON.stringify({project:p.id,inputs:p.canvas_lineage[aid].inputs,request_count:final.calls.length,platform_fixture_credits:final.used,paid_calls:0,output:aid,edges:p.canvas.edges},null,2));
 console.log('PASS: explicit three-image selection/order/roles, model mismatch guard, preview without debit, changed input re-review, mobile, one submission, retained plan inputs and automatic multi-source lineage. '+evidence);
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exit(1)});
