// Real UI gestures only; read the existing jacket project and discard all local edits.
const {chromium}=require('playwright'),fs=require('fs'),assert=require('assert/strict');
(async()=>{
 const browser=await chromium.launch({channel:'chromium',headless:true,args:['--no-sandbox']});
 try{
  const base='https://creative.jackailab.com',id='ddc97d3742fdf0cbdbd28928',out='outputs/creative_ui/20261016_canvas_pan';fs.mkdirSync(out,{recursive:true});
  const page=await browser.newPage({viewport:{width:1920,height:1080}}),errors=[],writes=[];
  page.on('pageerror',e=>errors.push(e.message));
  assert((await page.request.post(base+'/site/access',{data:{password:fs.readFileSync('/opt/visualstation/creative-runtime/site-access-password.txt','utf8').trim()}})).ok());
  const key=JSON.parse(fs.readFileSync('/var/lib/visualstation-local/public-acceptance-account.json')).api_key;
  await page.addInitScript(k=>{sessionStorage.setItem('h3_api_key',k);localStorage.setItem('creative-theme','dark')},key);
  const read=async()=>{const r=await page.request.get(base+'/creative/api/projects/'+id,{headers:{Authorization:'Bearer '+key}});assert(r.ok());return r.json()},before=await read();
  page.on('request',r=>{if(r.url().includes('/creative/api/')&&!['GET','HEAD','OPTIONS'].includes(r.method()))writes.push(new URL(r.url()).pathname)});
  await page.goto(base+'/creative?project='+id+'&view=canvas',{waitUntil:'domcontentloaded'});
  await page.waitForFunction(()=>document.querySelector('#video')?.readyState>=2);
  const viewport=page.locator('.canvas-viewport'),hand=page.locator('#canvasHandTool'),select=page.locator('#canvasSelectTool'),image=page.locator('.reference-node[data-kind=image]>.canvas-card-body>img').first(),head=page.locator('.reference-node[data-kind=image]>.canvas-card-head').first();
  const state=()=>page.evaluate(()=>{const m=new DOMMatrix(getComputedStyle(document.querySelector('.canvas-world')).transform);return{x:m.e,y:m.f,scale:m.a,nodes:[...document.querySelectorAll('.reference-node')].map(n=>({id:n.dataset.nodeId,x:n.style.left,y:n.style.top})),dirty:hasDrafts()}});
  const center=async locator=>{const r=await locator.boundingBox();assert(r);return{x:r.x+r.width/2,y:r.y+r.height/2}};
  const drag=async(locator,dx,dy,{cancel=false}={})=>{const a=await center(locator);await page.mouse.move(a.x,a.y);await page.mouse.down();await page.mouse.move(a.x+dx,a.y+dy,{steps:8});if(cancel)await page.keyboard.press('Escape');await page.mouse.up()};
  const close=(a,b)=>assert(Math.abs(a-b)<1.1,`${a} differs from ${b}`);
  // Hand on image and title pans the viewport, without selecting media or changing nodes.
  await hand.click();assert.equal(await hand.getAttribute('aria-pressed'),'true');let start=await state();
  await drag(image,90,45);let end=await state();close(end.x-start.x,90);close(end.y-start.y,45);assert.deepEqual(end.nodes,start.nodes);assert(!end.dirty);
  start=end;await drag(head,-60,25);end=await state();close(end.x-start.x,-60);close(end.y-start.y,25);assert.deepEqual(end.nodes,start.nodes);assert(!end.dirty);
  await image.dblclick();assert.equal(await page.locator('dialog[open]').count(),0);assert.equal(await page.locator('#canvasInsertMenu').evaluate(e=>e.matches(':popover-open')),false);
  // V and held Space temporarily pan, then restore box selection. Escape restores the view.
  await viewport.focus();await page.keyboard.press('v');assert.equal(await select.getAttribute('aria-pressed'),'true');assert.equal(await hand.getAttribute('aria-pressed'),'false');
  const bounds=await image.boundingBox();await page.mouse.move(bounds.x-15,bounds.y-35);await page.mouse.down();await page.mouse.move(bounds.x+bounds.width+10,bounds.y+bounds.height+10,{steps:8});await page.mouse.up();assert.equal(await page.locator('.canvas-multi-selected').count(),1);
  await viewport.focus();await page.keyboard.down('Space');assert.equal(await hand.getAttribute('aria-pressed'),'true');start=await state();await drag(image,40,-20);end=await state();close(end.x-start.x,40);close(end.y-start.y,-20);assert.deepEqual(end.nodes,start.nodes);assert(!end.dirty);
  await page.keyboard.up('Space');assert.equal(await hand.getAttribute('aria-pressed'),'false');assert.equal(await select.getAttribute('aria-pressed'),'true');assert.equal(await page.locator('.canvas-multi-selected').count(),1);
  await page.keyboard.press('h');start=await state();await drag(head,55,35,{cancel:true});end=await state();close(end.x,start.x);close(end.y,start.y);assert.deepEqual(end.nodes,start.nodes);assert(!end.dirty);
  // Leaving the window releases temporary Space and cancels an unfinished pointer gesture.
  await page.keyboard.press('v');await viewport.focus();await page.keyboard.down('Space');start=await state();const a=await center(image);await page.mouse.move(a.x,a.y);await page.mouse.down();await page.mouse.move(a.x+30,a.y+20);await page.evaluate(()=>window.dispatchEvent(new Event('blur')));await page.mouse.up();await page.keyboard.up('Space');end=await state();close(end.x,start.x);close(end.y,start.y);assert.equal(await hand.getAttribute('aria-pressed'),'false');assert.equal(await select.getAttribute('aria-pressed'),'true');
  // Typing in the actual conversation is never converted to keyboard tools.
  const message=page.locator('#message');await message.fill('');await message.pressSequentially('h v ');assert.equal(await message.inputValue(),'h v ');assert.equal(await hand.getAttribute('aria-pressed'),'false');await message.fill('');
  // Legacy title drag still edits, and its undo returns to the saved graph.
  await select.click();assert.equal(await select.getAttribute('aria-pressed'),'false');await drag(head,24,16);assert((await state()).dirty);await viewport.focus();await page.keyboard.press('Control+z');assert(!(await state()).dirty);
  // Return to normal mode: image double-click still opens the preview.
  await image.dblclick();assert.equal(await page.locator('dialog[open]').count(),1);await page.keyboard.press('Escape');
  await hand.click();assert(await page.locator('#canvasMediaToolbar').isHidden());await page.screenshot({path:out+'/hand-desktop.png'});
  await page.setViewportSize({width:390,height:844});await page.evaluate(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))));
  const toolbar=await page.locator('.canvas-toolbar').boundingBox(),button=await hand.boundingBox();assert(toolbar.x>=0&&toolbar.x+toolbar.width<=390);assert(button.x>=0&&button.x+button.width<=390);await page.screenshot({path:out+'/hand-mobile.png'});
  await hand.click();assert.equal(await hand.getAttribute('aria-pressed'),'false');assert(await page.locator('#canvasMediaToolbar').isVisible());await page.evaluate(()=>document.documentElement.dataset.theme='light');await hand.click();await page.screenshot({path:out+'/hand-light.png'});
  const after=await read();assert.equal(after.revision,before.revision);assert.deepEqual(after.canvas,before.canvas);assert.deepEqual(after.canvas_assets,before.canvas_assets);assert.deepEqual(writes,[]);assert.deepEqual(errors,[]);
  fs.writeFileSync(out+'/public-verification.json',JSON.stringify({passed:true,hand_image_and_title:true,space_restore:true,marquee_preserved:true,tools_hidden_while_panning:true,escape_cancel:true,window_blur:true,typing_preserved:true,node_drag_undo:true,preview_preserved:true,mobile:true,light:true,unchanged:true,writes,errors,paid_calls:0},null,2));
  console.log('PASS public hand/Space navigation, Escape/blur, input isolation, node drag undo, preview and mobile/light; zero writes');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
