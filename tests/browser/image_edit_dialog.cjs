// Real isolated API; image generation is fixed pixels, never a paid provider.
const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs'),crypto=require('node:crypto');
(async()=>{const browser=await chromium.launch({headless:true,args:['--no-sandbox']});try{
 const page=await browser.newPage({viewport:{width:1512,height:982}}),base='http://127.0.0.1:30129',errors=[],submits=[],out='/tmp/image-edit-dialog';fs.mkdirSync(out,{recursive:true});
 page.on('pageerror',e=>errors.push(e.message));
 const api=async(path,method='GET',data)=>{const r=await page.request.fetch(base+'/creative/api'+path,{method,data,headers:{Authorization:'Bearer fixture'}});assert(r.ok(),await r.text());return r.json()};
 assert.equal((await(await page.request.get(base+'/acceptance/identity')).json()).fixture,'canvas-lineage-fixed-pixels');
 let p=await api('/projects','POST',{message:'图片编辑窗口验收 · 固定像素',aspect:'16:9'}),path='/projects/'+p.id;
 p=await api(path+'/images','POST',{revision:p.revision,model:'hunyuan-image-v3.0',prompt:'测试原图，固定像素',request_id:crypto.randomBytes(16).toString('hex'),approved_credits:1});
 for(let i=0;i<80&&p.image_task.state==='running';i++){await new Promise(r=>setTimeout(r,100));p=await api(path)}assert.equal(p.image_task.state,'completed');const source=p.image_task.asset;
 await page.addInitScript(()=>{sessionStorage.setItem('h3_api_key','fixture');sessionStorage.setItem('creative-image-model','hunyuan-image-v3.0')});
 await page.route('**/creative/api/models',async r=>{const response=await r.fetch(),data=await response.json();data.image_models.push({id:'unconfigured-test',label:'未接入测试模型',mode:'edit',available:false});await r.fulfill({response,json:data})});
 await page.route('**/creative/api/model-status',r=>r.fulfill({json:{models:[]}}));
 page.on('request',r=>{if(r.method()==='POST'&&r.url().endsWith('/images'))submits.push(r.postDataJSON())});
 await page.goto(base+'/creative?project='+p.id+'&view=canvas');await page.waitForSelector('.reference-node .node-image-controls',{state:'attached'});
 const open=async()=>{await page.locator('.reference-node').first().locator('.canvas-card-body>img').press('Enter');await page.locator('#canvasMediaToolbar [data-media-action=edit]').click();await page.locator('#imageDialog').waitFor({state:'visible'})};
 await open();const confirm=page.locator('#imageDialog').getByRole('button',{name:'确认生成 · 1 积分'});
 assert.equal(await page.locator('#imageDialogModel').inputValue(),'hunyuan-image-v3.0');assert(await confirm.isDisabled());assert.match(await page.locator('#imageModelNotice').textContent(),/编辑模型/);
 assert.equal(await page.locator('#imageDialogModel option[value=unconfigured-test]').evaluate(e=>e.disabled),true);
 assert(await page.locator('#imageRequestSource img').evaluate(i=>i.complete&&i.naturalWidth>0));assert.equal(submits.length,0);
 await page.locator('#imagePrompt').fill('保留商品，将背景改为柔和的暖色影棚。');
 await page.locator('#imageDialogModel').selectOption('hunyuan-image-v2.0-general-edit');assert(await confirm.isEnabled());assert.match(await page.locator('#imagePrompt').inputValue(),/暖色影棚/);
 await page.screenshot({path:out+'/desktop.png'});await page.setViewportSize({width:390,height:844});
 assert(await page.locator('#imageDialog').evaluate(e=>e.scrollWidth<=e.clientWidth+1));await page.screenshot({path:out+'/mobile.png'});
 await page.locator('#imageDialog').getByRole('button',{name:'取消',exact:true}).click();assert.equal(submits.length,0);assert.equal((await api(path)).revision,p.revision);
 await page.setViewportSize({width:1512,height:982});await open();assert.equal(await page.locator('#imageDialogModel').inputValue(),'hunyuan-image-v2.0-general-edit');
 await page.locator('#imagePrompt').fill('像素观察：保留商品，暖色影棚。');
 let release;const gate=new Promise(resolve=>release=resolve);await page.route('**/creative/api/projects/*/images',async r=>{await gate;await r.continue()});
 await confirm.click();assert(await page.locator('#imageDialogModel').isDisabled());assert(await confirm.isDisabled());assert(await page.locator('#imageDialog').getByRole('button',{name:'取消',exact:true}).isDisabled());
 await page.keyboard.press('Escape');assert(await page.locator('#imageDialog').isVisible());release();await page.waitForFunction(()=>!document.getElementById('imageDialog').open);
 assert.equal(submits.length,1);assert.equal(submits[0].source_asset,source);assert.equal(submits[0].model,'hunyuan-image-v2.0-general-edit');
 for(let i=0;i<80;i++){p=await api(path);if(p.image_task.state==='completed')break;await new Promise(r=>setTimeout(r,100))}
 assert.equal(p.image_task.state,'completed');assert.notEqual(p.image_task.asset,source);assert(p.canvas_assets[source]);assert.equal(p.canvas_lineage[p.image_task.asset].sources[0],source);assert.equal(p.canvas_auto_layout.mode,'generated-result');assert.deepEqual(errors,[]);
 console.log('PASS: in-dialog explicit model selection, incompatible/unavailable guard, source preview, prompt preserved, cancel zero writes, mobile, one fixed-model submit, separate result and lineage');
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exitCode=1});
