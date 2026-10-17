// Run against scene_shots_server.py: no provider generation.
const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs');
(async()=>{
 const browser=await chromium.launch({headless:true,args:['--no-sandbox','--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
 try{
  const page=await browser.newPage({viewport:{width:1512,height:982}}),origin='http://127.0.0.1:30134',errors=[],out='outputs/creative_ui/20261015_scene_dock';fs.mkdirSync(out,{recursive:true});
  page.on('pageerror',error=>errors.push(error.message));
  await page.addInitScript(()=>sessionStorage.setItem('h3_api_key','fixture'));
  const identity=await (await page.request.get(origin+'/acceptance/identity')).json();assert.equal(identity.fixture,'scene-shots-fixed-director');
  await page.goto(origin+'/creative/scene');await page.waitForFunction(()=>document.getElementById('banner').textContent.includes('已就绪'),null,{timeout:90000});
  const panels=['sceneInspector','timelineOverlay','sceneAgent'];
  const only=async(id)=>{for(const name of panels){const visible=name===id||(name==='sceneInspector'&&page.viewportSize().width>1100);await page.locator('#'+name).waitFor({state:visible?'visible':'hidden'});assert.equal(await page.locator('#'+name).isVisible(),visible,name)}};
  await only(null);
  const viewport=await page.locator('#viewport').boundingBox();assert.equal(Math.round(viewport.width),1222);assert(viewport.height>=760);
  await page.screenshot({path:out+'/desktop-dark.png'});
  await page.locator('#viewport>canvas').click({position:{x:viewport.width/2,y:320}});
  await only('sceneInspector');
  assert.equal(await page.locator('#inspectorTab-objects').getAttribute('aria-selected'),'true');
  assert(await page.locator('#properties').isVisible());
  await page.locator('#inspectorTab-shots').click();
  // Panels are views over the same document, not separate copies of inputs.
  const writes=[];page.on('request',r=>{if(r.method()!=='GET')writes.push(r.url())});
  await page.locator('#inspectorTab-shots').focus();await page.keyboard.press('ArrowRight');
  assert.equal(await page.evaluate(()=>document.activeElement.id),'inspectorTab-objects');
  assert.equal(await page.locator('#inspectorTab-objects').getAttribute('aria-selected'),'true');
  await page.locator('[data-object-id=bottle]').click();
  await page.locator('#objectName').fill('验收商品');await page.locator('#objectName').press('Tab');
  await page.locator('#inspectorTab-production').click();
  assert(await page.locator('#assetIntent').isVisible());assert.equal(await page.locator('#properties').isVisible(),false);
  await page.screenshot({path:out+'/desktop-production.png'});
  await page.locator('#inspectorTab-production').focus();await page.keyboard.press('ArrowLeft');
  assert.equal(await page.locator('#objectName').inputValue(),'验收商品');
  await page.screenshot({path:out+'/desktop-objects.png'});
  await page.keyboard.press('Home');assert.equal(await page.locator('#inspectorTab-shots').getAttribute('aria-selected'),'true');
  assert.equal(writes.length,0,'tab changes and local field edits do not submit tasks');
  await page.locator('#shotName').fill('入口验收镜头');await page.locator('#shotName').press('Tab');
  await page.locator('#toggleAgent').click();await only('sceneAgent');
  await page.locator('#sceneIntent').fill('保留这段输入，先查看镜头');
  const inspector=await page.locator('#sceneInspector').boundingBox(),agent=await page.locator('#sceneAgent').boundingBox();assert(agent.x+agent.width<=inspector.x,'assistant must not cover docked assets');
  await page.locator('#inspectorTab-objects').click();assert.equal(await page.locator('#objectName').inputValue(),'验收商品');assert(await page.locator('#sceneAgent').isVisible());
  await page.locator('#closeInspector').click();assert(await page.locator('#sceneInspector').isHidden());assert(await page.locator('#sceneAgent').isVisible());assert.equal(Math.round((await page.locator('#viewport').boundingBox()).width),1512);
  await page.locator('#toggleInspector').click();assert(await page.locator('#sceneAgent').isVisible());assert.equal(await page.locator('#objectName').inputValue(),'验收商品');await page.screenshot({path:out+'/desktop-agent-and-assets.png'});

  await page.locator('#openTimelineOverlay').click();await only('timelineOverlay');
  assert.match(await page.locator('#timelineOverlayShots').textContent(),/入口验收镜头/);
  await page.locator('#timelineOverlayEditPath').click();await page.waitForSelector('#pathDialog[open]');
  await page.keyboard.press('Escape');await page.waitForSelector('#pathDialog[open]',{state:'hidden'});await only('timelineOverlay');
  await page.keyboard.press('Escape');await only(null);assert.equal(await page.evaluate(()=>document.activeElement.id),'openTimelineOverlay');
  await page.locator('#toggleAgent').click();assert.equal(await page.locator('#sceneIntent').inputValue(),'保留这段输入，先查看镜头');
  await page.locator('#closeAgent').click();await only(null);assert.equal(await page.evaluate(()=>document.activeElement.id),'toggleAgent');
  await page.locator('#save').click();await page.waitForFunction(()=>document.getElementById('banner').textContent.includes('场景已保存'));
  const pid=new URL(page.url()).searchParams.get('project');assert(pid);
  const getScene=async()=> (await page.request.get(origin+'/creative/api/projects/'+pid+'/scene3d',{headers:{Authorization:'Bearer fixture'}})).json();
  const saved=await getScene();assert.equal(saved.spec.shots[0].name,'入口验收镜头');assert.equal(saved.spec.objects.find(o=>o.id==='bottle').name,'验收商品');
  await page.locator('#themeToggle').click();await page.screenshot({path:out+'/desktop-light.png'});
  await page.setViewportSize({width:390,height:844});await only(null);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  const mobile=await page.locator('#viewport').boundingBox();assert.equal(Math.round(mobile.width),390);assert(mobile.height>530);
  await page.screenshot({path:out+'/mobile-light.png'});
  for(const [button,id] of [['toggleInspector','sceneInspector'],['openTimelineOverlay','timelineOverlay'],['toggleAgent','sceneAgent']]){
   await page.locator('#'+button).click();await only(id);
   const box=await page.locator('#'+id).boundingBox();assert(box.x>=0&&box.x+box.width<=390);assert(box.height>250);
   if(id==='sceneInspector'){
    for(const tab of ['objects','production','shots']){
     await page.locator('#inspectorTab-'+tab).click();
     assert(await page.locator('#inspectorPage-'+tab).evaluate(el=>el.scrollWidth<=el.clientWidth+1));
     await page.screenshot({path:out+'/mobile-'+tab+'.png'});
    }
   }
   assert(await page.locator('#'+id).evaluate(el=>el.scrollWidth<=el.clientWidth+1),id+' overflow');
  }
  await page.screenshot({path:out+'/mobile-agent.png'});
  await page.keyboard.press('Escape');await only(null);
  assert.equal((await getScene()).revision,saved.revision);
  await page.reload();await page.waitForFunction(()=>document.getElementById('banner').textContent.includes('已就绪'));await only(null);
  await page.setViewportSize({width:1512,height:982});await page.waitForFunction(()=>document.body.classList.contains('scene-inspector-docked'));await only(null);assert.equal(await page.locator('#inspectorTab-objects').getAttribute('aria-selected'),'true');assert.deepEqual(errors,[]);
  console.log(JSON.stringify({result:'PASS',desktop_canvas:viewport,mobile_canvas:mobile,desktop_assets_independent:true,mobile_panels_exclusive:true,input_preserved:true,scene_saved:true,inspector_tabs:true,keyboard_tabs:true,object_edit_preserved:true,navigation_read_only:true,screenshots:out}));
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
