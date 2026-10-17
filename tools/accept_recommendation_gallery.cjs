/* Real public acceptance. Requires all twenty films; never submits generation. */
const {chromium}=require('playwright');
const fs=require('fs'),path=require('path'),assert=require('assert/strict');
const root=path.resolve(__dirname,'..'),privateRoot='/var/lib/visualstation-local';
const base='https://creative.jackailab.com';

(async()=>{
 const expected=JSON.parse(fs.readFileSync(path.join(root,'productions/recommendation_20_v1/cases.json'))).cases;
 assert.equal(expected.length,20);
 const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
 try{
  const page=await browser.newPage({viewport:{width:1512,height:1000}}),errors=[],checks=[];
  page.on('pageerror',e=>errors.push(e.message));
  const key=JSON.parse(fs.readFileSync(privateRoot+'/public-acceptance-account.json')).api_key;
  const gate=await page.request.post(base+'/site/access',{data:{password:fs.readFileSync('/opt/visualstation/creative-runtime/site-access-password.txt','utf8').trim()}});
  assert(gate.ok(),'Site access failed');
  const response=await page.request.get(base+'/creative/api/templates');assert(response.ok());
  const templates=(await response.json()).templates;
  assert.deepEqual(templates.map(t=>t.id).sort(),expected.map(t=>t.id).sort(),'The full twenty-film collection is not published');
  await page.addInitScript(key=>sessionStorage.setItem('h3_api_key',key),key);
  const me=await page.request.get(base+'/me',{headers:{Authorization:'Bearer '+key}});assert(me.ok());
  const before=await me.json();
  await page.goto(base+'/',{waitUntil:'domcontentloaded'});
  await page.waitForFunction(()=>document.querySelectorAll('.template').length===20);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  await page.screenshot({path:privateRoot+'/recommendation20-home-desktop.png'});
  for(const category of new Set(templates.map(t=>t.category))){
   await page.locator('#filters').getByRole('button',{name:category,exact:true}).click();
   assert.equal(await page.locator('.template').count(),templates.filter(t=>t.category===category).length);
  }
  await page.locator('#filters').getByRole('button',{name:'全部',exact:true}).click();
  await page.locator('#search').fill(templates[0].title);
  assert(await page.getByRole('button',{name:'预览'+templates[0].title,exact:true}).isVisible());
  await page.locator('#search').fill('');
  const screenshotDir=privateRoot+'/recommendation20-browser-frames';fs.mkdirSync(screenshotDir,{recursive:true});
  for(const t of templates){
   await page.getByRole('button',{name:'预览'+t.title,exact:true}).click();
   await page.waitForFunction(()=>{const v=document.getElementById('previewVideo');return v.readyState>=2&&!v.error},{},{timeout:45000});
   const video=page.locator('#previewVideo');
   const dimensions=await video.evaluate(v=>({width:v.videoWidth,height:v.videoHeight,duration:v.duration}));
   assert(Math.abs(dimensions.duration-10)<.2,t.id+' duration');
   const size={'16:9':[1280,720],'9:16':[720,1280],'1:1':[720,720]}[t.aspect];
   assert.deepEqual([dimensions.width,dimensions.height],size,t.id+' dimensions');
   await video.evaluate(async v=>{v.muted=true;await v.play()});
   await page.waitForFunction(()=>document.getElementById('previewVideo').currentTime>.35,{},{timeout:30000});
   await video.evaluate(v=>new Promise((resolve,reject)=>{
    v.pause();const timer=setTimeout(()=>reject(Error('Video seek timed out')),30000);
    v.addEventListener('seeked',()=>{clearTimeout(timer);resolve()},{once:true});v.currentTime=7;
   }));
   await page.waitForFunction(()=>{const v=document.getElementById('previewVideo');return !v.seeking&&v.readyState>=2&&Math.abs(v.currentTime-7)<.2});
   assert((await page.locator('#previewMeta').innerText()).includes(t.model_label));
   assert((await page.locator('#previewMeta').innerText()).includes(t.audio?'原生音频':'静音'));
   assert.equal(await page.locator('#structure article').count(),2);
   await video.screenshot({path:path.join(screenshotDir,t.id+'.png')});
   checks.push({id:t.id,playback:true,seek:7,...dimensions,audio_flag:t.audio});
   await page.locator('#closePreview').click();
   assert.equal(await video.evaluate(v=>v.paused),true);
  }
  await page.setViewportSize({width:390,height:844});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  await page.screenshot({path:privateRoot+'/recommendation20-home-mobile.png'});
  await page.getByRole('button',{name:'预览'+templates[0].title,exact:true}).click();
  await page.locator('#previewUse').click();
  await page.locator('#product').fill('最终模板验收：我的独立商品');
  await page.locator('#requirements').fill('仅创建参考结构，不规划、不提交视频生成。');
  await page.locator('#useSubmit').click();await page.waitForURL(base+'/creative');
  await page.locator('.reference-node').first().waitFor();
  const projectId=await page.evaluate(()=>sessionStorage.getItem('creative_project'));
  const adoptedResponse=await page.request.get(base+'/creative/api/projects/'+projectId,{headers:{Authorization:'Bearer '+key}});assert(adoptedResponse.ok());
  const adopted=await adoptedResponse.json();
  assert.equal(adopted.source_template,templates[0].id);assert.equal(adopted.state,'intake');
  assert.equal(adopted.shots.length,0);assert(!adopted.run_id);assert(!adopted.artifact);
  assert(adopted.canvas.nodes.some(n=>n.kind==='text'));
  const after=await(await page.request.get(base+'/me',{headers:{Authorization:'Bearer '+key}})).json();
  assert.equal(after.used,before.used);assert.deepEqual(errors,[]);
  fs.writeFileSync(privateRoot+'/recommendation20-browser-acceptance.json',JSON.stringify({
   complete:true,published:20,public:true,checks,search:true,category_filters:true,mobile_no_overflow:true,
   adopted_project:projectId,owned_template_copy:true,credits_unchanged:true,new_generation:false,page_errors:errors
  },null,2));
  console.log('PASS all twenty real public videos, seek, filters, mobile layout and owned template adoption without generation');
 }finally{await browser.close()}
})().catch(e=>{console.error(e.message);process.exit(1)});
