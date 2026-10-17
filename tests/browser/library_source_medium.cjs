// Official source types remain distinct from the unreviewed media identity.
const {chromium}=require('playwright');
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
(async()=>{
 const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
 try{
  const page=await browser.newPage({viewport:{width:390,height:844}}),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  const cases=['Music Videos','Personal Work',''].map((section,n)=>({
   id:(n+1).toString(16).padStart(24,'0'),title:'参考作品 '+n,
   source_url:'https://example.org/ad',ad_type:'Berlin Commercial · '+(section?section+' / ':'')+'Craft: Idea',
   media_role:'work_or_case_film_unverified',creative_structure:{section},
   review:{state:'pending',version:0,scores:{},tags:[],note:''}
  }));
  await page.route('http://library.test/**',route=>{
   assert.equal(route.request().method(),'GET');
   const u=new URL(route.request().url());
   if(u.pathname==='/creative/library')return route.fulfill({contentType:'text/html',body:fs.readFileSync(path.join(__dirname,'../../tools/agent_studio/library.html'),'utf8')});
   if(u.pathname.endsWith('.woff2'))return route.fulfill({status:404});
   if(u.pathname.endsWith('/status'))return route.fulfill({json:{total:3,playable:0,review_queue:{state:'ready',total_pending:0}}});
   if(u.pathname==='/creative/api/library')return route.fulfill({json:{total:3,items:cases,facets:{industry:[],ad_type:[]}}});
   const item=cases.find(c=>u.pathname==='/creative/api/library/'+c.id);
   assert(item,'Unexpected endpoint');return route.fulfill({json:item});
  });
  for(const [n,item] of cases.entries()){
   await page.goto('http://library.test/creative/library?item='+item.id);
   const hint=page.locator('.source-medium-hint');await hint.waitFor();
   const value=await hint.textContent();
   assert.match(value,n===0?/来源类别：音乐视频/:n===1?/来源类别：个人作品/:/原广告 \/ 案例说明片/);
   assert.match(value,/待观看确认/);
   assert.equal(await page.locator('.choices .chosen').textContent(),'待筛选');
   assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  }
  assert.deepEqual(errors,[]);
  console.log('PASS official music/personal source hints, unknown fallback, pending review, mobile; no preference writes');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
