// Real WebGL/UI interactions. Public mode is read-only; fixture mode also edits local shots.
const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs');
(async()=>{
 const browser=await chromium.launch({channel:'chromium',headless:true,args:['--no-sandbox','--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
 try{
  const publicMode=process.env.SCENE_PUBLIC==='1',base=publicMode?'https://creative.jackailab.com':'http://127.0.0.1:30134',out='outputs/creative_ui/20261015_scene_transport/'+(publicMode?'public':'fixture');fs.mkdirSync(out,{recursive:true});
  const page=await browser.newPage({viewport:{width:1512,height:982}}),errors=[],writes=[];page.on('pageerror',e=>errors.push(e.message));
  let key='fixture';if(publicMode){assert((await page.request.post(base+'/site/access',{data:{password:fs.readFileSync('/opt/visualstation/creative-runtime/site-access-password.txt','utf8').trim()}})).ok());key=JSON.parse(fs.readFileSync('/var/lib/visualstation-local/public-acceptance-account.json')).api_key}else assert.equal((await(await page.request.get(base+'/acceptance/identity')).json()).fixture,'scene-shots-fixed-director');
  await page.addInitScript(k=>{sessionStorage.setItem('h3_api_key',k);localStorage.setItem('creative-theme','dark')},key);
  page.on('request',r=>{if(r.url().startsWith(base+'/creative/api/')&&!['GET','HEAD','OPTIONS'].includes(r.method()))writes.push(new URL(r.url()).pathname)});
  await page.goto(base+'/creative/scene');await page.waitForFunction(()=>document.querySelector('#banner').textContent.includes('已就绪'),null,{timeout:90000});
  const value=async()=>Number(await page.locator('#scrub').inputValue());
  const exportSpec=async()=>{await page.locator('.export-menu>summary').click();const downloading=page.waitForEvent('download');await page.locator('#exportJSON').click();const d=await downloading,result=JSON.parse(fs.readFileSync(await d.path(),'utf8')).spec;await page.keyboard.press('Escape');return result};
  const original=await exportSpec();assert.equal(await page.locator('#clock').textContent(),'00:00 / 00:10');assert(await page.locator('#shotTrack').isHidden());
  await page.locator('#cameraMode').click();const box=await page.locator('#scrub').boundingBox();
  await page.mouse.click(box.x+box.width*.2,box.y+box.height/2);await page.waitForFunction(()=>Number(document.querySelector('#scrub').value)>1.9);assert(Math.abs(await value()-2)<.03);
  const first=await page.locator('#viewport>canvas').screenshot();
  await page.mouse.move(box.x+box.width*.2,box.y+box.height/2);await page.mouse.down();await page.mouse.move(box.x+box.width*.7,box.y+box.height/2,{steps:8});await page.mouse.up();assert(Math.abs(await value()-7)<.03);assert(!(await page.locator('#viewport>canvas').screenshot()).equals(first),'seek must change the rendered camera frame');
  const rail=await page.locator('#sceneTimeline').boundingBox(),head=await page.locator('#scenePlayhead').boundingBox();assert(Math.abs(head.x-(rail.x+rail.width*.7))<4);assert.equal(await page.locator('#play').getAttribute('aria-pressed'),'false');
  const rates=[];for(const rate of [.5,2]){
   await page.locator('#scrub').focus();await page.keyboard.press('Home');await page.locator('#playbackRate').selectOption(String(rate));await page.locator('#play').click();
   const samples=await page.evaluate(()=>new Promise(resolve=>{const rows=[];function sample(now){rows.push([now,Number(document.querySelector('#scrub').value)]);if(rows.length===12)resolve(rows);else requestAnimationFrame(sample)}requestAnimationFrame(sample)}));
   await page.locator('#play').click();const elapsed=samples.slice(1).reduce((n,row,i)=>n+Math.min((row[0]-samples[i][0])/1000,.1),0),advanced=samples.at(-1)[1]-samples[0][1];assert(Math.abs(advanced-elapsed*rate)<.04,`speed ${rate}: ${advanced} over ${elapsed}`);rates.push({rate,elapsed,advanced});
  }
  await page.locator('#scrub').focus();await page.keyboard.press('End');await page.waitForFunction(()=>document.querySelector('#clock').textContent==='00:10 / 00:10');assert.equal(await value(),10);await page.keyboard.press('ArrowLeft');assert.equal(await value(),9.99);await page.keyboard.press('Home');assert.equal(await value(),0);
  await page.locator('#scrub').press('End');await page.locator('#play').click();await page.waitForFunction(()=>Number(document.querySelector('#scrub').value)>0&&Number(document.querySelector('#scrub').value)<2);await page.locator('#play').click();
  await page.locator('#scrub').press('End');await page.keyboard.press('ArrowLeft');await page.locator('#play').click();await page.waitForFunction(()=>Number(document.querySelector('#scrub').value)===10&&document.querySelector('#play').getAttribute('aria-pressed')==='false');assert.equal(await value(),10);
  assert.deepEqual(await exportSpec(),original,'preview rate and seeking must not change scene/export duration');
  await page.screenshot({path:out+'/desktop.png'});
  if(!publicMode){
   await page.locator('#inspectorTab-shots').click();await page.locator('#newShot').click();await page.waitForFunction(()=>!document.querySelector('#shotTrack').classList.contains('single-shot'));assert.equal(await page.locator('#scrub').getAttribute('max'),'13');await page.locator('#shotTrack button').nth(1).click();await page.waitForFunction(()=>Math.abs(Number(document.querySelector('#scrub').value)-11.5)<.15);await page.locator('#scenePlaybackSettings>summary').click();await page.locator('#duration').fill('7');await page.locator('#duration').press('Tab');await page.keyboard.press('Escape');await page.waitForFunction(()=>document.querySelector('#sceneRuler .end').textContent==='17s');await page.locator('#scrub').press('End');assert.equal(await value(),17);await page.screenshot({path:out+'/multiple-shots.png'});
  }
  for(const width of [1024,390]){
   await page.setViewportSize({width,height:844});await page.waitForFunction(()=>document.querySelector('#sceneRuler').clientWidth<innerWidth);assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);const labels=await page.locator('#sceneRuler .major').evaluateAll(nodes=>nodes.filter(n=>n.textContent).map(n=>{const r=n.getBoundingClientRect();return {x:r.x,right:r.right}}));for(let i=1;i<labels.length;i++)assert(labels[i].x>=labels[i-1].right,'ruler labels overlap');const label=await page.locator('#scenePlayheadTime').boundingBox();assert(label.x>=0&&label.x+label.width<=width);assert(await page.locator('#playbackRate').isVisible());await page.locator('#scrub').focus();await page.keyboard.press('Home');await page.keyboard.press('ArrowRight');assert.equal(await value(),.01);await page.screenshot({path:out+'/width-'+width+'.png'});
  }
  assert.deepEqual(errors,[]);assert.deepEqual(writes,[]);fs.writeFileSync(out+'/verification.json',JSON.stringify({passed:true,public:publicMode,pointer_seek:true,real_camera_changes:true,rate_measurements:rates,keyboard_seek:true,end_stops:true,restart:true,export_unchanged:true,responsive:true,errors,writes,paid_calls:0},null,2));console.log('PASS scene ruler, real camera seeking, measured playback rates, keyboard bounds, end/restart, unchanged export and responsive labels');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
