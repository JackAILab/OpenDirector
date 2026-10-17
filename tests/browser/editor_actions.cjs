const {clickEditorControl}=require('./editor_controls.cjs');
// Isolated real media/API fixture; no model calls or paid generation.
const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs');
(async()=>{const browser=await chromium.launch({headless:true,args:['--no-sandbox']});try{
 const page=await browser.newPage({viewport:{width:1512,height:982}}),origin='http://127.0.0.1:30131',headers={Authorization:'Bearer fixture'},errors=[],out='/tmp/editor-actions';fs.mkdirSync(out,{recursive:true});page.on('pageerror',e=>errors.push(e.message));
 const identity=await(await page.request.get(origin+'/acceptance/identity')).json();assert.equal(identity.fixture,'edit-speech-fixed-model');
 const project=await(await page.request.post(origin+'/creative/api/projects',{headers,data:{message:'时间轴操作验收',duration:15}})).json(),api=origin+'/creative/api/projects/'+project.id+'/edit';
 await page.addInitScript(()=>sessionStorage.setItem('h3_api_key','fixture'));await page.goto(origin+'/creative/editor?project='+project.id);await page.waitForFunction(()=>document.getElementById('status').textContent.includes('项目已载入'));
 await page.locator('#editorToolsToggle').click();await clickEditorControl(page,'editorMediaToggle');await page.locator('#uploadVideo').click();await page.locator('#file').setInputFiles(identity.fixtures+'/red.mp4');await page.waitForFunction(()=>document.getElementById('status').textContent.includes('素材已导入'));await page.getByText('＋ 画面',{exact:true}).click();
 // Header is film-first; opening menus never changes the edit document.
 assert.equal(await page.locator('header h1').textContent(),'智能剪辑');assert.equal(await page.locator('header #save').count(),0);assert.equal(await page.locator('.ruler #scrub').count(),1);
 const initialSpec=await page.evaluate(()=>JSON.stringify(spec));await page.locator('#editorToolsToggle').click();await page.keyboard.press('d');assert.equal(await page.evaluate(()=>JSON.stringify(spec)),initialSpec);await page.keyboard.press('Escape');assert.equal(await page.locator('#editorToolsToggle').getAttribute('aria-expanded'),'false');
 await page.locator('#editorExportMenuToggle').click();assert(await page.locator('#save').isVisible());await page.keyboard.press('Escape');assert.equal(await page.evaluate(()=>JSON.stringify(spec)),initialSpec);
 // Pointer and keyboard seek use the existing range, now placed over the ruler.
 const ruler=await page.locator('#scrub').boundingBox();await page.mouse.click(ruler.x+ruler.width*.5,ruler.y+ruler.height/2);await page.waitForFunction(()=>Math.abs(t-1.5)<.03);assert.equal(await page.locator('#clock').textContent(),'00:01 / 00:03');
 await page.locator('#scrub').focus();await page.keyboard.press('ArrowRight');await page.waitForFunction(()=>Math.abs(t-1.51)<.02);assert.match(await page.locator('#scrub').getAttribute('aria-valuetext'),/1.51 秒/);
 await page.locator('#scrub').press('Home');await page.waitForFunction(()=>t===0);
 const state=()=>page.evaluate(()=>({clips:structuredClone(spec.clips),captions:structuredClone(spec.captions),t,dirty}));const blur=()=>page.evaluate(()=>document.activeElement.blur());
 await blur();await page.keyboard.press('d');assert.equal((await state()).clips.length,2);await page.keyboard.press('Control+z');assert.equal((await state()).clips.length,1);await page.keyboard.press('Control+Shift+z');assert.equal((await state()).clips.length,2);
 await page.keyboard.press('Home');
 await page.locator('#clipActions').click();assert(await page.getByRole('menuitem',{name:'在播放位置分割 · S'}).isDisabled());await page.keyboard.press('Escape');await blur();
 await page.keyboard.press('ArrowRight');assert(Math.abs((await state()).t-1/24)<.0001);await page.keyboard.press('Shift+ArrowRight');assert(Math.abs((await state()).t-(1+1/24))<.0001);
 await page.keyboard.press('s');assert.equal((await state()).clips.length,3);await page.keyboard.press('Control+z');assert.equal((await state()).clips.length,2);
 // Right click acts on the clicked clip at the clicked time, not a prior selection.
 const clip=page.locator('.clip.clips').nth(1),rect=await clip.boundingBox();await clip.click({button:'right',position:{x:rect.width/2,y:12}});await page.locator('#clipActionMenu').waitFor({state:'visible'});assert(Math.abs((await state()).t-4.5)<.08);
 await page.screenshot({path:out+'/desktop-menu.png'});await page.getByRole('menuitem',{name:'在播放位置分割 · S'}).click();assert.equal((await state()).clips.length,3);assert(Math.abs((await state()).clips[1].end-1.5)<.08);
 await blur();await page.keyboard.press('Delete');assert.equal((await state()).clips.length,2);await page.keyboard.press('Control+z');assert.equal((await state()).clips.length,3);
 await page.locator('#addCaption').click();await page.locator('#text').fill('sd');await page.keyboard.press('d');await page.keyboard.press('Backspace');assert.equal((await state()).clips.length,3);assert.equal((await state()).captions.length,1);await page.locator('#apply').click();
 await page.locator('#editorToolsToggle').click();await clickEditorControl(page,'settings');await page.locator('.clip.captions').first().press('Shift+F10');await page.locator('#clipActionMenu').waitFor({state:'visible'});assert.equal(await page.getByRole('menuitem',{name:'复制画面 · D'}).count(),0);await page.keyboard.press('End');assert.equal(await page.evaluate(()=>document.activeElement.textContent),'删除片段 · Delete');await page.keyboard.press('Enter');assert.equal((await state()).captions.length,0);
 await blur();await page.keyboard.press('Control+z');assert.equal((await state()).captions.length,1);
 // Save uses the real API; keyboard edits are ignored throughout its pending request.
 let release;const gate=new Promise(resolve=>release=resolve);await page.route(api,async route=>{if(route.request().method()==='PUT')await gate;await route.continue()});
 await page.locator('#editorExportMenuToggle').click();await clickEditorControl(page,'save');await page.waitForFunction(()=>working);assert(await page.locator('#export').isDisabled());const pending=await state();await page.keyboard.press('d');await page.keyboard.press('Delete');assert.deepEqual((await state()).clips,pending.clips);assert.deepEqual((await state()).captions,pending.captions);release();await page.waitForFunction(()=>!working&&!dirty);await page.unroute(api);
 const saved=await(await page.request.get(api,{headers})).json();assert.equal(saved.spec.clips.length,3);assert.equal(saved.spec.captions.length,1);
 await page.setViewportSize({width:390,height:844});await page.locator('#clipActions').click();const menu=await page.locator('#clipActionMenu').boundingBox();assert(menu.x>=0&&menu.x+menu.width<=390&&menu.y>=0&&menu.y+menu.height<=844);await page.screenshot({path:out+'/mobile-menu.png'});await page.keyboard.press('Escape');
 await page.locator('#editorShortcuts').click();assert(await page.locator('#editorShortcutDialog').evaluate(e=>e.scrollWidth<=e.clientWidth+1));await page.screenshot({path:out+'/mobile-shortcuts.png'});await page.keyboard.press('Escape');
 await page.reload();await page.waitForFunction(()=>document.getElementById('status').textContent.includes('项目已载入'));assert.equal((await state()).clips.length,3);assert.equal((await state()).captions.length,1);assert.deepEqual(errors,[]);
 console.log('PASS real API/media: duplicate/split/delete/undo/redo/save, pointer and keyboard context menu, 24fps stepping, input and busy guards, mobile menus, saved reload; no provider calls');
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exitCode=1});
