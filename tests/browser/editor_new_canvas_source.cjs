// Isolated editor handoff fixture. No account, generation, or edit writes.
const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
(async()=>{const browser=await chromium.launch({channel:'chromium',headless:true,args:['--no-sandbox']});try{
 const page=await browser.newPage(),errors=[],writes=[],dir=path.resolve(__dirname,'../../tools/agent_studio');let reads=0,fail=false;
 const sid='canvas_'+'a'.repeat(32),source={id:sid,kind:'video',duration:5,width:320,height:180,sha256:'b'.repeat(64),has_audio:false};
 const fixture={revision:1,sources:{},spec:{clips:[],captions:[],audio:[],sources:{},width:1280,height:720,fps:30},edit_capabilities:{}};
 page.on('pageerror',e=>errors.push(e.message));await page.addInitScript(()=>sessionStorage.setItem('h3_api_key','fixture'));
 await page.route('https://editor.test/**',async route=>{const r=route.request(),u=new URL(r.url());if(u.pathname==='/credits/activity')return route.fulfill({json:{ok:true}});if(r.method()!=='GET')writes.push(r.method()+' '+u.pathname);
  if(u.pathname==='/creative/editor')return route.fulfill({contentType:'text/html',body:fs.readFileSync(dir+'/editor.html')});
  if(/\.(js|css)$/.test(u.pathname))return route.fulfill({contentType:u.pathname.endsWith('.js')?'text/javascript':'text/css',body:fs.readFileSync(dir+'/'+path.basename(u.pathname))});
  if(u.pathname.endsWith('/edit')&&r.method()==='PUT'){const body=r.postDataJSON();assert.equal(body.revision,fixture.revision);fixture.spec=body.spec;fixture.revision++;return route.fulfill({json:fixture})}
  if(u.pathname.endsWith('/edit')){reads++;return fail?route.fulfill({status:503,json:{detail:'fixture offline'}}):route.fulfill({json:fixture})}
  if(u.pathname.endsWith('/projects/fixture'))return route.fulfill({json:{canvas_assets:{},canvas:{nodes:[]}}});
  return route.fulfill({status:404,json:{detail:'fixture'}});
 });
 await page.goto('https://editor.test/creative/editor?project=fixture&embedded=1');await page.waitForFunction(()=>window.visualagentInlineEditor?.state().ready);
 const original=await page.evaluate(()=>{checkpoint();spec.captions.push({text:'保留我的草稿',start:0,end:1,track:0});return JSON.stringify({spec,past,revision:project.revision})});
 fixture.revision=9;fixture.sources[sid]=source;fixture.spec.captions=[{text:'服务端另一个版本',start:0,end:1,track:0}];
 await page.evaluate(sid=>visualagentInlineEditor.focusSource(sid),sid);
 assert.equal(reads,2);await page.locator('.source-highlight').waitFor();assert.equal(await page.locator('.source-highlight').getAttribute('data-source'),sid);
 assert.equal(await page.evaluate(()=>JSON.stringify({spec,past,revision:project.revision})),original);assert.equal(await page.evaluate(()=>dirty),true);
 await page.evaluate(sid=>visualagentInlineEditor.openTool('assistant',sid),sid);assert.equal(reads,2,'known source reuses catalog');assert.match(await page.locator('#status').textContent(),/Agent 剪辑来源/);
 fail=true;await page.evaluate(()=>visualagentInlineEditor.focusSource('canvas_'+'c'.repeat(32)));assert.match(await page.locator('#status').textContent(),/新增素材暂未读取/);assert.equal(reads,3);assert.equal(await page.evaluate(()=>JSON.stringify({spec,past,revision:project.revision})),original);
 fail=false;await page.reload();await page.waitForFunction(()=>window.visualagentInlineEditor?.state().ready);const preserved=await page.evaluate(()=>{checkpoint();spec.captions[0].text='第二份本地草稿';return JSON.stringify({spec,past})});const next='canvas_'+'d'.repeat(32);fixture.sources[next]={...source,id:next};fixture.revision=10;await page.evaluate(next=>visualagentInlineEditor.focusSource(next),next);assert.equal(await page.evaluate(()=>project.revision),10,'source-only update advances revision safely');assert.equal(await page.evaluate(()=>JSON.stringify({spec,past})),preserved);
 assert.deepEqual(writes,[]);await page.evaluate(()=>save());assert.equal(writes.length,1);assert.equal(await page.evaluate(()=>dirty),false);const afterSave=await page.evaluate(()=>{checkpoint();spec.captions[0].text='保存后的新草稿';return JSON.stringify({spec,past})});const latest='canvas_'+'e'.repeat(32);fixture.sources[latest]={...source,id:latest};fixture.revision++;await page.evaluate(latest=>visualagentInlineEditor.focusSource(latest),latest);assert.equal(await page.evaluate(()=>project.revision),fixture.revision,'saved edit becomes the comparison baseline');assert.equal(await page.evaluate(()=>JSON.stringify({spec,past})),afterSave);assert.deepEqual(errors,[]);console.log('PASS new canvas video available in retained editor; dirty spec, undo and revision preserved; failure visible; save baseline refreshed; only explicit fixture save');
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exitCode=1});
