// Isolated module regression; no accounts, provider calls or generation.
const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
(async()=>{const browser=await chromium.launch({channel:'chromium',headless:true,args:['--no-sandbox']});try{
 const page=await browser.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.route('https://adjust.test/**',route=>route.fulfill({contentType:route.request().url().endsWith('.js')?'text/javascript':'text/html',body:route.request().url().endsWith('.js')?fs.readFileSync(path.join(__dirname,'../../tools/agent_studio/image-adjustments.js'),'utf8'):'<select id="imageModelSelect"></select>'}));
 await page.goto('https://adjust.test/');
 await page.evaluate(async()=>{
  window.openAdjustment=(await import('/adjust.js')).openImageAdjustment;
  window.studioModelLogo=()=>document.createElement('span');window.calls=[];
  window.ctx={locked:()=>false,hasDrafts:()=>false,project:()=>({id:'fixture',revision:1}),toast:()=>{},busy:()=>{},accepted:()=>{},api:async(...args)=>{calls.push(args);throw Error('fixture preview rejected')},preview:async()=>URL.createObjectURL(new Blob(['<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20"><rect width="20" height="20" fill="red"/></svg>'],{type:'image/svg+xml'}))};
 });
 for(const mode of ['angle','light']){
  for(const options of ['', '<option value="">请选择</option>', '<option value="image-v2_1">unsupported</option><option value="disabled-model" disabled>offline</option>']){
   await page.evaluate(async({mode,options})=>{document.querySelector('#imageModelSelect').innerHTML=options;await openAdjustment(ctx,'asset',mode)},{mode,options});
   assert(await page.locator('.image-adjustment-send').isDisabled());assert(await page.getByLabel('调整生成模型').isDisabled());assert.match(await page.locator('.image-adjustment-note').innerText(),/暂无可用编辑模型/);
   await page.evaluate(()=>document.querySelector('.image-adjustment-send').onclick());assert.deepEqual(await page.evaluate(()=>calls),[]);
  }
  await page.evaluate(async mode=>{document.querySelector('#imageModelSelect').innerHTML='<option value="kling-image-o1">Kling</option>';await openAdjustment(ctx,'asset',mode)},mode);
  assert(await page.locator('.image-adjustment-send').isEnabled());await page.locator('.image-adjustment-send').click();await page.getByText('fixture preview rejected',{exact:true}).waitFor();
  assert(await page.locator('.image-adjustment-send').isEnabled());assert.equal(await page.evaluate(()=>calls.length),1);assert.equal(await page.evaluate(()=>calls[0][2].model),'kling-image-o1');await page.evaluate(()=>calls=[]);
 }
 assert.deepEqual(errors,[]);console.log('PASS angle/light unavailable models stay disabled; eligible model reaches preview only');
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exitCode=1});
