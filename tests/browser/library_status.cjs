// Synthetic requests only: status must never block viewing or invent counts.
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
(async()=>{
 const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
 try{
  const page=await browser.newPage(),errors=[],pending=[];
  page.on('pageerror',e=>errors.push(e.message));
  const item={id:'synthetic',title:'可立即打开的广告',source_url:'https://example.org/ad',
   review:{state:'pending',scores:{},tags:[],note:'',version:0}};
  await page.route('http://library.test/**',route=>{
   const u=new URL(route.request().url());
   assert.equal(route.request().method(),'GET');
   if(u.pathname==='/creative/library')return route.fulfill({contentType:'text/html',body:fs.readFileSync(path.join(__dirname,'../../tools/agent_studio/library.html'),'utf8')});
   if(u.pathname.endsWith('.woff2'))return route.fulfill({status:404});
   if(u.pathname.endsWith('/status')){pending.push(route);return;}
   assert.equal(u.pathname,'/creative/api/library');
   return route.fulfill({json:{total:1,items:[item],facets:{industry:[],ad_type:['Advertising / Film craft / Direction / Commercial campaigns / Digital platforms / Product demonstrations']}}});
  });
  const status={total:1,playable:0,reviewed:0,selected:0,source_link:null,
   review_queue:{state:'unavailable',analysis_pending:null,semantic_review_pending:null,total_pending:null},
   runs:[{source:'官方来源',state:'running',discovered:12,inserted:3}],
   backups:[{created:1791400000,state:'verified',scope:'metadata'}]};
  const waitPending=async n=>{for(let i=0;i<100&&pending.length<n;i++)await page.waitForTimeout(20);assert.equal(pending.length,n);};
  await page.goto('http://library.test/creative/library');
  await page.locator('.card').waitFor({timeout:2000});
  await waitPending(1);
  await page.locator('.card').click();
  assert.equal(await page.locator('#screen h2').textContent(),item.title);
  await pending.shift().fulfill({json:status});
  await page.waitForFunction(()=>document.querySelector('#operations').textContent.includes('案例与标注'));
  assert.equal(await page.locator('#metricSource').textContent(),'—');
  assert.equal(await page.locator('#metricAnalysisPending').textContent(),'—');
  assert.equal(await page.locator('#metricSelected').textContent(),'0');
  assert.match(await page.locator('#operations').textContent(),/发现 12 · 入库 3/);
  assert.match(await page.locator('#operations').textContent(),/审阅队列暂不可读取/);

  // Metadata receipts must not hide a slower video cache batch or its failures.
  await page.evaluate(()=>{void refreshOperations();});
  await waitPending(1);
  const media={id:'media-batch',source:'本地视频缓存',state:'running',discovered:8,inserted:4,failed:1};
  await pending.shift().fulfill({json:{...status,media_cache:media,runs:[...status.runs,media]}});
  await page.waitForFunction(()=>document.querySelector('#operations').textContent.includes('视频缓存：处理中 · 已缓存 4 / 8 · 已失败 1'));
  assert(!/最近采集：本地视频缓存/.test(await page.locator('#operations').textContent()));
  await page.evaluate(()=>{void refreshOperations();});
  await waitPending(1);
  await pending.shift().fulfill({json:{...status,media_cache:{...media,state:'partial',inserted:7,failed:null}}});
  await page.waitForFunction(()=>document.querySelector('#operations').textContent.includes('视频缓存：部分完成 · 已缓存 7 / 8'));
  assert(!/已失败/.test(await page.locator('#operations').textContent()));

  // A resumed full snapshot can be much older than the latest metadata copy.
  await page.evaluate(()=>{void refreshOperations();});
  await waitPending(1);
  const active={id:'older-full',created:1791200000,state:'verifying',scope:'full',items:3397};
  await pending.shift().fulfill({json:{...status,active_backup:active}});
  await page.waitForFunction(()=>document.querySelector('#operations').textContent.includes('进行中的备份'));
  assert.match(await page.locator('#operations').textContent(),/进行中的备份：正在回读校验 · 案例、学习证据与原始媒体 · 3,397 条来源记录/);
  assert.match(await page.locator('#operations').textContent(),/最近创建的备份：.*案例与标注/);
  await page.evaluate(()=>{void refreshOperations();});
  await waitPending(1);
  await pending.shift().fulfill({json:{...status,active_backup:active,backups:[active]}});
  await page.waitForFunction(()=>!document.querySelector('#operations').textContent.includes('最近创建的备份'));

  // Preparation is active before its exact source count is known.
  await page.evaluate(()=>{void refreshOperations();});
  await waitPending(1);
  await pending.shift().fulfill({json:{...status,active_backup:{...active,state:'preparing',items:null}}});
  await page.waitForFunction(()=>document.querySelector('#operations').textContent.includes('正在准备备份'));
  assert.match(await page.locator('#operations').textContent(),/进行中的备份：正在准备备份 · 案例、学习证据与原始媒体/);
  assert(!/0 条来源记录/.test(await page.locator('#operations').textContent()));

  // Counts are measurements within one phase, never proof of remote success.
  await page.evaluate(()=>{void refreshOperations();});
  await waitPending(1);
  const progress={phase:'learning_evidence',processed_analysis_versions:503,total_analysis_versions:1254,copied_learning_files:6542,observed_at:1791987000,stale:true};
  await pending.shift().fulfill({json:{...status,backups:[],active_backup:{...active,state:'preparing',progress}}});
  await page.waitForFunction(()=>document.querySelector('#operations').textContent.includes('已整理 503 / 1,254 条分析版本'));
  let text=await page.locator('#operations').textContent();
  assert.match(text,/6,542 个学习文件/);assert.match(text,/尚未完成远端校验/);
  assert.match(text,/等待下一次进度上报/);assert(!text.includes('备份校验通过'));
  await page.evaluate(()=>{void refreshOperations();});
  await waitPending(1);
  await pending.shift().fulfill({json:{...status,backups:[],active_backup:{...active,progress:{verified_files:4,total_files:4,verified_learning_files:90,total_learning_files:100,observed_at:1791987000,stale:false}}}});
  await page.waitForFunction(()=>document.querySelector('#operations').textContent.includes('已回读校验 4 / 4 个文件'));
  text=await page.locator('#operations').textContent();
  assert(text.includes('已核验 90 / 100 个学习包内文件'));assert(!text.includes('备份校验通过'));
  assert(!text.includes('已整理 503'));assert(!text.includes('等待下一次进度上报'));

  // Complete two overlapping status reads in reverse order.
  await page.evaluate(()=>{void refreshOperations();void refreshOperations();});
  await waitPending(2);
  const older=pending.shift(),newer=pending.shift();
  await newer.fulfill({json:{...status,total:2,backups:[{...status.backups[0],scope:'metadata+learning'}]}});
  await page.waitForFunction(()=>document.querySelector('#metricTotal').textContent==='2');
  await older.fulfill({json:{...status,total:999}});
  await page.waitForTimeout(150);
  assert.equal(await page.locator('#metricTotal').textContent(),'2');
  assert.match(await page.locator('#operations').textContent(),/案例、标注与学习证据/);

  await page.evaluate(()=>{void refreshOperations();});
  await waitPending(1);
  await pending.shift().fulfill({status:503,json:{detail:'temporarily unavailable'}});
  await page.waitForFunction(()=>document.querySelector('#operations').textContent.includes('数据状态暂时不可读取'));
  assert.equal(await page.locator('#metricTotal').textContent(),'—');
  assert.equal(await page.locator('#screen h2').textContent(),item.title);
  await page.evaluate(()=>{void refreshOperations();});
  await waitPending(1);
  await pending.shift().fulfill({json:{...status,review_queue:{state:'ready',total_pending:0,analysis_pending:0,semantic_review_pending:0}}});
  await page.waitForFunction(()=>document.querySelector('#metricAnalysisPending').textContent==='0');
  assert.match(await page.locator('#operations').textContent(),/待处理审阅：0/);
  assert.match(await page.locator('#operations').textContent(),/统计时间待确认/);
  const observedAt=1791992907;
  const queue={state:'ready',total_pending:12,analysis_pending:8,semantic_review_pending:4,observed_at:observedAt};
  await page.evaluate(()=>{void refreshOperations();});
  await waitPending(1);
  await pending.shift().fulfill({json:{...status,review_queue:queue}});
  await page.waitForFunction(()=>document.querySelector('#metricAnalysisPending').textContent==='8');
  const originalTime=await page.evaluate(value=>new Date(value*1000).toLocaleString(),observedAt);
  assert((await page.locator('#operations').textContent()).includes('统计时间 '+originalTime));
  await page.evaluate(()=>{void refreshOperations();});
  await waitPending(1);
  await pending.shift().fulfill({json:{...status,total:2,review_queue:queue}});
  await page.waitForFunction(()=>document.querySelector('#metricTotal').textContent==='2');
  assert((await page.locator('#operations').textContent()).includes('统计时间 '+originalTime));
  await page.setViewportSize({width:390,height:844});
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth));
  assert.deepEqual(errors,[]);
  console.log('PASS: delayed status does not block cases, unknown vs zero, latest response wins, scope labels, failure and recovery, mobile');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
