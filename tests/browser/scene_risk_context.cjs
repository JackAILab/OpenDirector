// Uses the isolated scene_shots_server.py fixture. No model calls.
const {chromium}=require('playwright'),assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({headless:true,args:['--no-sandbox','--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
 try{
  const page=await browser.newPage({viewport:{width:1512,height:982}}),origin='http://127.0.0.1:30134',errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  const api=async(path,method='GET',data)=>{const r=await page.request.fetch(origin+path,{method,data,headers:{Authorization:'Bearer fixture'}});assert(r.ok(),await r.text());return r.json()};
  assert.equal((await api('/acceptance/identity')).fixture,'scene-shots-fixed-director');
  const project=await api('/creative/api/projects','POST',{message:'风险时码验收',duration:15}),base='/creative/api/projects/'+project.id+'/scene3d';
  const scene=await api(base),spec=scene.spec;
  const bottle=spec.objects.find(item=>item.id==='bottle'),cap=spec.objects.find(item=>item.id==='cap');
  bottle.position=[0,1.4,0];cap.position=[0,1.4,0];
  spec.shots[0].duration=4;spec.shots[0].station_keyframes=[{object_id:'bottle',at:1,position:[0,1.4,0]},{object_id:'bottle',at:2,position:[0,1.4,0]}];
  spec.shots.push({...structuredClone(spec.shots[0]),id:'second',name:'第二镜头'});spec.duration=8;
  await api(base,'PUT',{revision:scene.revision,spec});
  await page.addInitScript(()=>sessionStorage.setItem('h3_api_key','fixture'));
  await page.goto(origin+'/creative/scene?project='+project.id);
  await page.waitForFunction(()=>document.getElementById('banner').textContent.includes('已就绪'),null,{timeout:90000});
  await page.locator('#openTimelineOverlay').click();
  const sample=page.locator('#timelineOverlayRiskSaved button').first();
  await sample.click();
  await page.waitForFunction(()=>document.getElementById('timelineOverlayRiskHint').textContent.includes('两版此时均有命中记录'));
  assert.match(await page.locator('#stationKeyframeRiskPairCard').textContent(),/两版此时均有命中记录/);
  await page.locator('#timelineOverlayRiskSaved button').nth(1).hover();
  assert.match(await page.locator('#timelineOverlayRiskHint').textContent(),/2\.00s/);
  await page.locator('header').hover();
  assert.match(await page.locator('#timelineOverlayRiskHint').textContent(),/已选保存版 · 1\.00s/);
  await page.locator('#toggleInspector').click();
  await page.locator('#shotList button').nth(1).click();
  await page.locator('#openTimelineOverlay').click();
  await page.locator('#timelineOverlayRiskSaved button').first().click();
  assert.equal(await page.locator('#timelineOverlayRiskSaved button').first().getAttribute('data-shot-id'),'second');
  assert.match(await page.locator('#openEditTimeline').getAttribute('data-url'),/scene_shot=second/);
  await page.waitForFunction(()=>Number(document.getElementById('scrub').value)===5.00);
  const before=await api(base);
  await page.screenshot({path:'/tmp/scene-risk-context.png'});
  assert.equal((await api(base)).revision,before.revision);
  assert.deepEqual(errors,[]);
  console.log('PASS: real WebGL page, shared hint/card, equal-risk shot switch, read-only navigation');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
