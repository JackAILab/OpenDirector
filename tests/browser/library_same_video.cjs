// Exact-file grouping and source navigation; synthetic data, no real writes.
const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
(async()=>{const browser=await chromium.launch({headless:true,args:['--no-sandbox']});try{
 const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[],queries=[];let sourceReads=0;
 page.on('pageerror',e=>errors.push(e.message));await page.addInitScript(()=>sessionStorage.setItem('h3_api_key','fixture'));
 const item={id:'first',title:'原广告 · 来源一',source_name:'官方来源一',source_url:'https://example.org/one',media_url:'/creative/api/library/first/media',duration:15,audio:true,media_status:'local',review:{state:'pending',scores:{},tags:[],note:'',version:0}};
 const second={...item,id:'second',title:'同一个视频 · 来源二',source_url:'https://example.org/two'};
 await page.route('http://library.test/**',route=>{
  const r=route.request(),u=new URL(r.url());assert.equal(r.method(),'GET');
  if(u.pathname==='/creative/library')return route.fulfill({contentType:'text/html',body:fs.readFileSync(path.join(__dirname,'../../tools/agent_studio/library.html'),'utf8')});
  if(u.pathname.endsWith('.woff2')||u.pathname.endsWith('/media'))return route.fulfill({status:404});
  if(u.pathname.endsWith('/status'))return route.fulfill({json:{total:2,playable:2,distinct_playable:1,review_queue:{state:'ready',total_pending:0},can_review:true}});
  if(u.pathname.endsWith('/same-video')){sourceReads++;return route.fulfill(sourceReads===1?{status:503,json:{}}:{json:{total:2,items:[{...item,review_state:'pending'},{...second,review_state:'selected'}]}})}
  if(u.pathname==='/creative/api/library/second')return route.fulfill({json:second});
  assert.equal(u.pathname,'/creative/api/library');queries.push(Object.fromEntries(u.searchParams));
  const grouped=u.searchParams.get('unique_media')==='true';
  return route.fulfill({json:{total:grouped?1:2,items:grouped?[item]:[item,second],facets:{industry:[],ad_type:[]}}});
 });
 await page.goto('http://library.test/creative/library');await page.locator('.card').nth(1).waitFor();
 await page.waitForFunction(()=>document.querySelector('#metricDistinctPlayable').textContent==='1');
 assert.equal(await page.locator('#metricPlayable').textContent(),'2');assert.equal(sourceReads,0);
 await page.locator('#uniqueMedia').check();await page.waitForFunction(()=>document.querySelectorAll('.card').length===1);
 assert.equal(queries.at(-1).unique_media,'true');assert.equal(queries.at(-1).offset,'0');assert(await page.locator('#uniqueMediaNote').isVisible());
 await page.locator('.card').click();assert.equal(sourceReads,0);
 const summary=page.locator('.same-video-sources summary');await summary.click();await page.getByText('来源暂未读取，收起后重新展开可重试。',{exact:true}).waitFor();
 await summary.click();await summary.click();await page.locator('.same-video-sources .history-entry').nth(1).waitFor();
 assert.equal(sourceReads,2);assert.match(await page.locator('.same-video-sources').textContent(),/2 条来源记录使用同一个视频文件/);
 assert.equal(await page.locator('.same-video-sources a').nth(1).getAttribute('href'),'https://example.org/two');
 await page.getByRole('combobox',{name:'画面工艺',exact:true}).selectOption('5');
 const dismissed=new Promise(resolve=>page.once('dialog',async d=>{await d.dismiss();resolve()}));await page.getByRole('button',{name:'查看此来源及标注',exact:true}).click();await dismissed;
 assert.equal(await page.locator('#screen h2').textContent(),item.title);assert.equal(await page.getByRole('combobox',{name:'画面工艺',exact:true}).inputValue(),'5');
 const accepted=new Promise(resolve=>page.once('dialog',async d=>{await d.accept();resolve()}));await page.getByRole('button',{name:'查看此来源及标注',exact:true}).click();await accepted;await page.waitForFunction(()=>document.querySelector('#screen h2').textContent==='同一个视频 · 来源二');
 await page.setViewportSize({width:390,height:844});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 await page.locator('#screen button').first().click();await page.locator('#uniqueMedia').uncheck();await page.locator('.card').nth(1).waitFor();assert.equal(queries.at(-1).unique_media,'false');assert.equal(await page.locator('#uniqueMediaNote').isVisible(),false);
 assert.deepEqual(errors,[]);console.log('PASS exact-file filter, distinct counts, source read retry, separate source navigation, dirty review guard, mobile; no writes');
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exit(1)});
