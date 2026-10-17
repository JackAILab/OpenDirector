// The viewing exercises load on demand; navigation never saves a preference.
const {chromium}=require('playwright');
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
(async()=>{
 const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  let calls=0;
  const candidates=Array.from({length:6},(_,n)=>({id:(n+1).toString(16).padStart(24,'0'),
   focus:'观察点 '+n,title:'候选 <b>'+n+'</b>',brand:'示例品牌',duration:30,
   question:'商品在哪个时刻改变局面？',source_evidence:'官方入围记录'}));
  const item=c=>({...c,source_url:'https://example.org/ad',
   review:{state:'pending',scores:{},tags:[],note:'',version:0}});
  await page.route('http://library.test/**',route=>{
   assert.equal(route.request().method(),'GET');
   const u=new URL(route.request().url());
   if(u.pathname==='/creative/library')return route.fulfill({contentType:'text/html',body:fs.readFileSync(path.join(__dirname,'../../tools/agent_studio/library.html'),'utf8')});
   if(u.pathname.endsWith('.woff2'))return route.fulfill({status:404});
   if(u.pathname.endsWith('/review-starters')){
    calls++;return calls===1?route.fulfill({status:503,json:{detail:'temporarily unavailable'}}):route.fulfill({json:{state:'ready',items:candidates}});
   }
   if(u.pathname.endsWith('/status'))return route.fulfill({json:{total:1,playable:0,review_queue:{state:'ready',total_pending:0}}});
   if(u.pathname==='/creative/api/library')return route.fulfill({json:{total:1,items:[item(candidates[0])],facets:{industry:[],ad_type:[]}}});
   const found=candidates.find(c=>u.pathname==='/creative/api/library/'+c.id);
   assert(found,'unexpected endpoint');return route.fulfill({json:item(found)});
  });
  await page.goto('http://library.test/creative/library');
  await page.locator('.card').waitFor();assert.equal(calls,0);
  const toggle=page.locator('#reviewStarters>summary');
  await toggle.click();await page.waitForFunction(()=>document.querySelector('#starterStatus').textContent.includes('重试'));
  assert.equal(await page.locator('.card').count(),1);
  await toggle.click();await toggle.click();await page.locator('.starter-card').nth(5).waitFor();
  assert.equal(calls,2);
  assert.equal(await page.locator('.starter-card h3').first().textContent(),candidates[0].title);
  assert.equal(await page.locator('.starter-card h3 b').count(),0);
  await toggle.click();await toggle.click();assert.equal(calls,2);
  await page.setViewportSize({width:390,height:844});
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  await page.locator('.starter-card').nth(1).click();
  await page.waitForFunction(()=>document.querySelector('#screen h2')?.textContent==='候选 <b>1</b>');
  assert.equal(new URL(page.url()).searchParams.get('item'),candidates[1].id);
  assert.equal(await page.locator('.choices .chosen').textContent(),'待筛选');
  assert.deepEqual(errors,[]);
  console.log('PASS lazy loading, unavailable/retry, safe text, mobile, correct deep link, no preference writes');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
