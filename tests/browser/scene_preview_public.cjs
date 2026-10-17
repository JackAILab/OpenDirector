// Real WebGL/UI interactions. Public mode is read-only; fixture mode also edits local shots.
const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs');
(async()=>{
 const browser=await chromium.launch({channel:'chromium',headless:true,args:['--no-sandbox','--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
 try{
  const publicMode=true,base=publicMode?'https://creative.jackailab.com':'http://127.0.0.1:30134',out='outputs/creative_ui/20261016_scene_preview/'+(publicMode?'public':'fixture');fs.mkdirSync(out,{recursive:true});
  const page=await browser.newPage({viewport:{width:1512,height:982}}),errors=[],writes=[];page.on('pageerror',e=>errors.push(e.message));
  let key='fixture';if(publicMode){assert((await page.request.post(base+'/site/access',{data:{password:fs.readFileSync('/opt/visualstation/creative-runtime/site-access-password.txt','utf8').trim()}})).ok());key=JSON.parse(fs.readFileSync('/var/lib/visualstation-local/public-acceptance-account.json')).api_key}else assert.equal((await(await page.request.get(base+'/acceptance/identity')).json()).fixture,'scene-shots-fixed-director');
  await page.addInitScript(k=>{sessionStorage.setItem('h3_api_key',k);localStorage.setItem('creative-theme','dark')},key);
  page.on('request',r=>{if(r.url().startsWith(base+'/creative/api/')&&!['GET','HEAD','OPTIONS'].includes(r.method()))writes.push(new URL(r.url()).pathname)});
  await page.goto(base+'/creative/scene');await page.waitForFunction(()=>document.querySelector('#banner').textContent.includes('已就绪'),null,{timeout:90000});
  const value=async()=>Number(await page.locator('#scrub').inputValue());
  const exportSpec=async()=>{await page.locator('.export-menu>summary').click();const downloading=page.waitForEvent('download');await page.locator('#exportJSON').click();const d=await downloading,result=JSON.parse(fs.readFileSync(await d.path(),'utf8')).spec;await page.keyboard.press('Escape');return result};
  const original=await exportSpec(),preview=page.locator('#cameraPreview'),button=page.locator('#previewPlay');
  await button.click();await page.waitForFunction(()=>Number(document.querySelector('#scrub').value)>.2);assert.equal(await page.locator('#play').getAttribute('aria-pressed'),'true');
  await button.click();await page.waitForFunction(()=>document.querySelector('#play').getAttribute('aria-pressed')==='false');const stopped=await value();
  await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));assert.equal(await value(),stopped);
  const compact=await preview.boundingBox();await page.locator('#previewExpand').click();await page.waitForFunction(()=>document.fullscreenElement?.id==='cameraPreview');
  await page.waitForFunction(()=>document.querySelector('#previewCanvas').clientWidth===innerWidth);assert.equal(await page.locator('#previewExpand').getAttribute('aria-pressed'),'true');
  const expanded=await preview.boundingBox();assert(expanded.width>compact.width*3);assert.equal(await value(),stopped);
  await button.click();await page.waitForFunction(at=>Number(document.querySelector('#scrub').value)>at+.2,stopped);await button.click();await page.waitForFunction(()=>document.querySelector('#play').getAttribute('aria-pressed')==='false');
  await page.screenshot({path:out+'/expanded.png'});await page.locator('#previewExpand').click();await page.waitForFunction(()=>!document.fullscreenElement);assert.equal((await preview.boundingBox()).width,compact.width);
  await page.locator('#scrub').press('End');await page.keyboard.press('ArrowLeft');await button.click();await page.waitForFunction(()=>document.querySelector('#previewPlay').getAttribute('aria-pressed')==='false'&&Number(document.querySelector('#scrub').value)===10);
  await button.click();await page.waitForFunction(()=>Number(document.querySelector('#scrub').value)>0&&Number(document.querySelector('#scrub').value)<2);await button.click();
  // Browser fixture: a denied native fullscreen must retain a reversible in-page preview.
  await page.evaluate(()=>{document.querySelector('#cameraPreview').requestFullscreen=()=>Promise.reject(new Error('fixture denied'))});
  await page.locator('#previewExpand').click();await page.waitForFunction(()=>document.querySelector('#cameraPreview').classList.contains('is-expanded'));assert(await page.locator('#previewNotice').isVisible());await page.keyboard.press('Escape');await page.waitForFunction(()=>!document.querySelector('#cameraPreview').classList.contains('is-expanded'));
  assert.deepEqual(await exportSpec(),original);await page.screenshot({path:out+'/desktop.png'});
  await page.setViewportSize({width:390,height:844});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);assert(await button.isVisible());assert(await page.locator('#previewExpand').isVisible());
  await page.locator('#previewExpand').click();await page.waitForFunction(()=>document.querySelector('#cameraPreview').classList.contains('is-expanded'));assert.equal((await preview.boundingBox()).width,390);await page.locator('#previewExpand').click();await page.waitForFunction(()=>!document.querySelector('#cameraPreview').classList.contains('is-expanded'));await page.screenshot({path:out+'/mobile.png'});
  assert.deepEqual(errors,[]);assert.deepEqual(writes,[]);fs.writeFileSync(out+'/verification.json',JSON.stringify({passed:true,shared_clock:true,pause_stable:true,native_fullscreen:true,fullscreen_playback:true,denied_fullscreen_recovery:true,end_stops:true,restart:true,export_unchanged:true,mobile:true,errors,writes,paid_calls:0},null,2));console.log('PASS camera preview shared transport, fullscreen playback, recovery, end/restart and unchanged scene');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
