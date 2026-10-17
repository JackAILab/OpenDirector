// Synthetic interview contract: no live model or paid video requests.
const {chromium}=require('playwright');
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
(async()=>{
 const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
 try{
  const page=await browser.newPage();const errors=[],sent=[],unexpected=[];
  page.on('pageerror',e=>errors.push(e.message));
  const question={id:'q0',question:'你希望吸引谁？',why:'受众决定表达方式',options:['通勤上班族','周末旅行者']};
  let p={id:'interview',state:'intake',revision:1,duration:10,aspect:'16:9',provider:'kling',brief:{},messages:[],questions:[question],shots:[],assumptions:[],decisions:[],events:[]};
  await page.addInitScript(()=>sessionStorage.setItem('h3_api_key','synthetic-session'));
  await page.route('http://studio.test/**',async route=>{
   const req=route.request(),url=new URL(req.url());if(['/creative/canvas.js','/creative/canvas.css','/creative/workspace.js','/creative/workspace.css','/creative/learning.js','/creative/theme.js','/creative/theme.css','/creative/creative-controls.js'].includes(url.pathname))return route.fulfill({contentType:url.pathname.endsWith('.js')?'text/javascript':'text/css',body:fs.readFileSync(path.join(__dirname,'../../tools/agent_studio',path.basename(url.pathname)),'utf8')});
      let data;
   if(url.pathname==='/creative')return route.fulfill({contentType:'text/html',body:fs.readFileSync(path.join(__dirname,'../../tools/agent_studio/index.html'),'utf8')});
   if(url.pathname.endsWith('/models'))data={models:[]};
   else if(url.pathname.endsWith('/me'))return route.fulfill({status:401,json:{detail:'fixture'}});
   else if(url.pathname.endsWith('/skills'))data={skills:[]};
   else if(url.pathname==='/creative/api/projects')data=[{id:p.id,state:p.state,title:'访谈'}];
   else if(url.pathname==='/creative/api/projects/'+p.id)data=p;
   else if(url.pathname.endsWith('/message')){
    const body=req.postDataJSON();sent.push(body);p={...p,revision:p.revision+1,state:'planning_failed',messages:[...p.messages,{role:'user',content:body.text}]};
    return route.fulfill({status:502,json:{detail:'规划失败，上下文已保存'}});
   }else if(url.pathname.endsWith('.woff2'))return route.fulfill({status:404});
   else{unexpected.push(url.pathname);return route.fulfill({status:400,json:{}})}
   return route.fulfill({json:data});
  });
  await page.goto('http://studio.test/creative');
  const opts=page.locator('.question button'),answer=page.locator('.question textarea');
  await opts.first().click();await opts.nth(1).click();
  assert.equal(await answer.inputValue(),'周末旅行者');
  assert.equal(await opts.first().getAttribute('aria-pressed'),'false');
  await answer.fill('周末旅行者，偏好轻便装备');
  await page.evaluate(()=>draw());
  assert.equal(await answer.inputValue(),'周末旅行者，偏好轻便装备');
  await page.locator('#sendButton').click();
  await page.waitForFunction(()=>!document.querySelector('#sendButton').disabled);
  assert.equal(sent.length,1);assert.equal(sent[0].text,'你希望吸引谁？：周末旅行者，偏好轻便装备');
  assert.equal(await answer.inputValue(),'');
  // Retry planning uses the context the server already saved, without duplicating it.
  await page.locator('#planButton').click();
  await page.waitForFunction(()=>!document.querySelector('#planButton').disabled);
  assert.equal(sent.length,2);assert.equal(sent[1].text,'');assert.equal(sent[1].mode,'plan');
  assert.deepEqual(errors,[]);assert.deepEqual(unexpected,[]);
  console.log('PASS: replace choice, custom answer, redraw retention, answer-only send, persisted failure retry without duplicates');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
