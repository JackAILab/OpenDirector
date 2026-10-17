// Entry-to-director flow with synthetic accounts and projects; no live generation.
const {chromium}=require('playwright');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'../..');
const assets=Object.fromEntries(['discover.html','index.html','canvas.js','workspace.js','learning.js','workspace.css','canvas.css'].map(f=>[f,fs.readFileSync(path.join(root,'tools/agent_studio',f))]));
const catalog={models:[
 {id:'kling-video-v3_0',label:'Kling 3.0',provider:'kling',credits_per_5s:3,single_film:true,available:true,audio:true},
 {id:'kling-video-v3_0_omni',label:'Kling O3',provider:'kling',credits_per_5s:4,single_film:true,available:true,audio:true},
 {id:'MiniMax-H3',label:'MiniMax H3',provider:'minimax-h3',credits_per_5s:1,single_film:false,available:false,audio:true,limitation:'整片待验证'}
],image_models:[{id:'hunyuan-image-v3.0',label:'混元 Image 3.0',mode:'text',available:true},{id:'hunyuan-image-v2.0-general-edit',label:'混元 Image 2.0',mode:'edit',available:true},{id:'gpt-image-2',label:'GPT Image 2',mode:'text',available:false,limitation:'待配置'}]};
(async()=>{
 const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
 try{
  async function fixture(auth=true){
   const page=await browser.newPage({viewport:{width:1440,height:900}}),errors=[],writes=[];let project=null,modelsFail=false,galleryFail=false,galleryGate=null;
   page.on('pageerror',e=>errors.push(e.message));
   await page.addInitScript(auth=>{if(auth)sessionStorage.setItem('h3_api_key','synthetic');},auth);
   await page.route('http://entry.test/**',async route=>{
    const req=route.request(),url=new URL(req.url()),u=url.pathname;
    const file=u==='/creative/discover'?'discover.html':u==='/creative'?'index.html':path.basename(u);
    if(assets[file])return route.fulfill({contentType:file.endsWith('.html')?'text/html':file.endsWith('.css')?'text/css':'text/javascript',body:assets[file]});
    if(u.endsWith('.woff2'))return route.fulfill({status:404});
    if(u==='/account')return route.fulfill({contentType:'text/html',body:'Synthetic login return'});
    if(u==='/creative/api/templates'){if(galleryGate)await galleryGate;return route.fulfill(galleryFail?{status:503,json:{}}:{json:{templates:[]}});}
    if(u==='/creative/api/models')return route.fulfill(modelsFail?{status:503,json:{}}:{json:catalog});
    if(u==='/creative/api/learning/mechanisms')return route.fulfill({json:{}});
    if(req.method()!=='GET')writes.push({url:u,body:req.postDataJSON()});
    if(u==='/creative/api/projects'&&req.method()==='POST'){
     const data=req.postDataJSON();project={id:'created',...data,state:'intake',revision:0,generation_mode:'single_native',brief:{product:'测试咖啡'},shots:[],questions:[],messages:[{role:'user',content:data.message}],assumptions:[],decisions:[],events:[],quote:{credits:12,label:'Kling O3',new_jobs:1}};return route.fulfill({json:project});
    }
    if(u==='/creative/api/projects')return route.fulfill({json:[{id:'older-project',title:'旧创作'}]});
    if(u==='/creative/api/projects/created')return route.fulfill({json:project});
    if(u==='/creative/api/projects/created/message'){project={...project,revision:1,state:'intake',questions:[{id:'audience',question:'主要面向谁？',why:'决定场景',options:['上班族','学生']}],decisions:[{title:'清晨场景',reason:'根据用户输入'}]};return route.fulfill({json:project})}
    return route.fulfill({status:404,json:{}});
   });
   return {page,writes,errors,failModels:v=>modelsFail=v,failGallery:v=>galleryFail=v,holdGallery:()=>{let release;galleryGate=new Promise(r=>release=r);return release}};
  }
  const delayed=await fixture(),release=delayed.holdGallery();await delayed.page.goto('http://entry.test/creative/discover',{waitUntil:'domcontentloaded'});
  await delayed.page.locator('#quickPrompt').fill('样片未返回时也能写下广告想法');await delayed.page.waitForFunction(()=>!document.querySelector('#entryVideo').disabled);assert(await delayed.page.locator('#quickForm').isVisible());assert.equal(await delayed.page.locator('#featuredFilm').isVisible(),false);release();await delayed.page.waitForFunction(()=>document.querySelector('#status').textContent==='');assert.match(await delayed.page.locator('#quickPrompt').inputValue(),/样片未返回/);assert.deepEqual(delayed.errors,[]);await delayed.page.close();
  const first=await fixture(),p=first.page;
  await p.goto('http://entry.test/creative/discover');await p.waitForFunction(()=>!document.querySelector('#entryVideo').disabled);
  await p.locator('#quickPrompt').fill('给真实冷萃咖啡拍一支有音乐和旁白的广告。');
  await p.locator('[data-intent=story]').click();assert.match(await p.locator('#quickPrompt').inputValue(),/真实冷萃/);
  await p.locator('#entryVideo').selectOption('kling-video-v3_0_omni');await p.locator('#entryImage').selectOption('hunyuan-image-v2.0-general-edit');await p.locator('#entryAspect').selectOption('9:16');
  await p.reload();await p.waitForFunction(()=>document.querySelector('#entryVideo').value==='kling-video-v3_0_omni');
  assert.match(await p.locator('#quickPrompt').inputValue(),/真实冷萃/);assert.equal(await p.locator('#entryAspect').inputValue(),'9:16');
  assert.equal(await p.locator('#entryVideo option[value="MiniMax-H3"]').getAttribute('disabled'),'');assert.equal(await p.locator('#entryImage option[value="gpt-image-2"]').getAttribute('disabled'),'');
  await p.locator('#quickForm button[type=submit]').click();await p.waitForURL('**/creative?new=1');await p.locator('#newDialog').waitFor();
  assert.equal(await p.locator('#provider').inputValue(),'kling-video-v3_0_omni');assert.equal(await p.locator('#aspect').inputValue(),'9:16');assert.equal(first.writes.length,0);
  await p.reload();await p.locator('#newDialog').waitFor();assert.match(await p.locator('#initialBrief').inputValue(),/真实冷萃/);
  await p.locator('#createButton').click();await p.waitForFunction(()=>document.querySelectorAll('.question').length===1);
  assert.deepEqual(first.writes.map(w=>w.url),['/creative/api/projects','/creative/api/projects/created/message']);
  assert.equal(first.writes[0].body.model,'kling-video-v3_0_omni');assert.equal(first.writes[0].body.duration,15);assert.match(first.writes[0].body.message,/品牌故事/);
  assert.match(first.writes[1].body.request_id,/^[a-f0-9]{32}$/);
  assert.equal(await p.evaluate(()=>sessionStorage.getItem('creative_entry_draft')),null);
  assert.equal(await p.locator('#imageModelSelect').inputValue(),'hunyuan-image-v2.0-general-edit');assert(await p.locator('#videoModelSelect').isVisible());assert.equal(await p.locator('#imageModelSelect').isVisible(),false);await p.locator('#productReferenceSettings').click();assert(await p.locator('#imageModelSelect').isVisible());await p.keyboard.press('Escape');
  // Inspector grouping must retain all live sections after empty and populated redraws.
  for(const id of ['brief','assumptions','decisions','referencePreview','reviews','versions','events'])assert.equal(await p.locator('#'+id).count(),1,id);
  await p.evaluate(()=>draw());assert.match(await p.locator('#brief').textContent(),/测试咖啡/);
  await p.setViewportSize({width:390,height:844});assert(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));assert.deepEqual(first.errors,[]);await p.close();
  const guest=await fixture(false),g=guest.page;await g.goto('http://entry.test/creative/discover');await g.locator('#quickPrompt').fill('手机竖屏广告，保留这段需求。');await g.locator('#entryAspect').selectOption('9:16');await g.locator('#quickForm button[type=submit]').click();await g.waitForURL('**/account?next=creative');
  await g.evaluate(()=>sessionStorage.setItem('h3_api_key','synthetic'));await g.goto('http://entry.test/creative');await g.locator('#newDialog').waitFor();assert.match(await g.locator('#initialBrief').inputValue(),/保留这段/);assert.equal(await g.locator('#aspect').inputValue(),'9:16');assert.equal(guest.writes.length,0);assert.deepEqual(guest.errors,[]);await g.close();
  const retry=await fixture(),r=retry.page;retry.failModels(true);retry.failGallery(true);await r.goto('http://entry.test/creative/discover');await r.locator('#quickPrompt').fill('网络恢复后继续这个创意');await r.locator('#modelCatalog summary').click();await r.getByRole('button',{name:'重新读取',exact:true}).waitFor();retry.failModels(false);retry.failGallery(false);await r.getByRole('button',{name:'重新读取',exact:true}).click();await r.waitForFunction(()=>!document.querySelector('#entryVideo').disabled);await r.getByRole('button',{name:'重新加载样片'}).click();await r.waitForFunction(()=>document.querySelector('#status').textContent==='');assert.match(await r.locator('#quickPrompt').inputValue(),/网络恢复/);
  // A saved unavailable model must not be silently changed to another provider.
  await r.evaluate(()=>sessionStorage.setItem('creative_entry_draft',JSON.stringify({prompt:'保留我的模型选择',model:'retired-model',pending:true,aspect:'16:9'})));await r.goto('http://entry.test/creative');await r.locator('#newDialog').waitFor();assert.equal(await r.locator('#provider').inputValue(),'retired-model');await r.locator('#createButton').click();assert.equal(retry.writes.length,0);assert.deepEqual(retry.errors,[]);await r.close();
  console.log('PASS entry model/ratio/intent handoff, refresh and login draft recovery, real DOM retention, mobile layout, unavailable model guard, read retry; no generation');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
