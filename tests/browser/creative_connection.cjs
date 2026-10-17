// Failed status reads must not resubmit paid work or discard local drafts.
const {chromium}=require('playwright');
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
(async()=>{
 const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
 try{
  const page=await browser.newPage(),errors=[],writes=[];let unavailable=false;
  const shot=i=>({id:'s'+i,title:'镜头'+i,start:(i-1)*5,duration:5,state:i===1?'generating':'planned',caption:'原字幕',prompt:'原画面',rationale:'展示产品'});
  let p={id:'connection',state:'ready',revision:1,duration:10,aspect:'16:9',provider:'kling',brief:{},messages:[],questions:[],shots:[shot(1),shot(2)],assumptions:[],decisions:[],events:[],quote:{label:'Kling',credits:2}};
  page.on('pageerror',e=>errors.push(e.message));
  await page.addInitScript(()=>sessionStorage.setItem('h3_api_key','synthetic-session'));
  await page.route('http://studio.test/**',async route=>{
   const req=route.request(),u=new URL(req.url());
   if(req.method()!=='GET')writes.push(req.method()+' '+u.pathname);
   if(u.pathname==='/creative')return route.fulfill({contentType:'text/html',body:fs.readFileSync(path.join(__dirname,'../../tools/agent_studio/index.html'),'utf8')});
   if(['/creative/canvas.js','/creative/canvas.css','/creative/workspace.js','/creative/workspace.css'].includes(u.pathname))return route.fulfill({contentType:u.pathname.endsWith('.js')?'text/javascript':'text/css',body:fs.readFileSync(path.join(__dirname,'../../tools/agent_studio',path.basename(u.pathname)),'utf8')});
   if(u.pathname.endsWith('/models'))return route.fulfill({json:{models:[]}});
   if(u.pathname==='/creative/api/projects')return route.fulfill({json:[{id:p.id,state:p.state,title:'联网测试'}]});
   if(u.pathname==='/creative/api/projects/'+p.id)return unavailable?route.abort('connectionrefused'):route.fulfill({json:p});
   return route.fulfill({status:404});
  });
  await page.goto('http://studio.test/creative?view=studio');
  await page.locator('#cameraTrack button').first().click();
  await page.locator('#shotCaption').fill('保留的编辑草稿');
  await page.evaluate(()=>clearTimeout(pollTimer));
  p={...p,state:'running'};await page.evaluate(()=>refreshProjectStatus());
  unavailable=true;
  await page.evaluate(()=>refreshProjectStatus());
  assert.equal(await page.locator('#syncNotice').isVisible(),true);
  assert.match(await page.locator('#syncNotice').innerText(),/不会重新生成/);
  assert.equal(await page.locator('#shotCaption').inputValue(),'保留的编辑草稿');
  unavailable=false;p={...p,state:'paused',error:'已保存进度'};
  await page.evaluate(()=>refreshProjectStatus());
  assert.equal(await page.locator('#syncNotice').isVisible(),false);
  assert.equal(await page.locator('#executeButton').innerText(),'恢复制作');
  assert.equal(await page.locator('#shotCaption').inputValue(),'保留的编辑草稿');
  unavailable=true;await page.evaluate(()=>refreshProjectStatus());
  await page.evaluate(()=>{project={...project,id:'new-project',state:'ready'};draw()});
  assert.equal(await page.locator('#syncNotice').isVisible(),false);
  assert.deepEqual(writes,[]);assert.deepEqual(errors,[]);
  console.log('PASS: failed read visible, automatic read recovery, draft retained, no mutation requests');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
