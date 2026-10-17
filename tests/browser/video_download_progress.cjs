// Browser read-only fixture: controlled media chunks, no generation or project writes.
const {chromium}=require('playwright'),fs=require('fs'),assert=require('assert');
(async()=>{const b=await chromium.launch({channel:'chromium',headless:true,args:['--no-sandbox']});try{
 const fixture='/tmp/visualagent-download-progress.mp4';require('child_process').execFileSync(process.env.CREATIVE_FFMPEG||'ffmpeg',['-v','error','-y','-f','lavfi','-i','testsrc2=s=320x180:r=24:d=2','-c:v','libx264','-threads','2','-pix_fmt','yuv420p',fixture]);
 const c=await b.newContext({storageState:process.env.TEST_STORAGE_STATE,viewport:{width:1510,height:900}});
 await c.addInitScript(s=>{for(const[k,v]of Object.entries(s))sessionStorage.setItem(k,v)},JSON.parse(fs.readFileSync(process.env.TEST_SESSION_STORAGE)));
 await c.addInitScript(bytes=>{const original=window.fetch;window.transferMode='known';window.transferAborted=0;window.fetch=async(input,options)=>{
  if(!String(input).endsWith('/source'))return original(input,options);
  const data=Uint8Array.from(bytes),step=Math.ceil(data.length/3);let offset=0,control;
  const body=new ReadableStream({start(controller){control=controller},cancel(){window.transferAborted++}});
  window.transferNext=()=>{if(offset>=data.length){control.close();return}control.enqueue(data.slice(offset,offset+step));offset+=step;if(offset>=data.length)control.close()};
  window.transferFail=()=>control.error(new Error('fixture interrupted'));
  options.signal.addEventListener('abort',()=>{window.transferAborted++;try{control.error(new DOMException('Aborted','AbortError'))}catch{}},{once:true});
  window.transferNext();return new Response(body,{headers:{'content-type':'video/mp4',...(window.transferMode==='known'?{'content-length':String(data.length)}:{})}});
 };},[...fs.readFileSync(fixture)]);
 const p=await c.newPage(),writes=[],errors=[];p.on('pageerror',e=>errors.push(e.message));await p.route('**/creative/api/**',r=>{if(r.request().url().endsWith('/preview-session'))return r.fulfill({status:404,body:'not installed'});if(!['GET','HEAD'].includes(r.request().method())){writes.push(r.request().method());return r.abort()}return r.continue()});
 await p.goto((process.env.TEST_BASE_URL||'http://127.0.0.1:30080')+'/creative?project='+process.env.TEST_PROJECT_ID+'&view=canvas');
 const open=()=>p.locator('.generated-primary-result .canvas-video-preview-button').click(),info=p.locator('.canvas-video-viewer-info');
 await open();await p.waitForFunction(()=>/33%/.test(document.querySelector('.canvas-video-viewer-info').textContent));assert((await info.innerText()).includes('MB'));assert.equal(await p.locator('#canvasVideoViewer video').evaluate(v=>v.readyState),0);
 await p.evaluate(()=>transferNext());await p.waitForFunction(()=>/66%/.test(document.querySelector('.canvas-video-viewer-info').textContent));await p.evaluate(()=>transferNext());await p.waitForFunction(()=>document.querySelector('#canvasVideoViewer video').readyState>=1);await p.locator('#canvasVideoViewer video').evaluate(v=>v.play());await p.waitForFunction(()=>document.querySelector('#canvasVideoViewer video').currentTime>.2);await p.getByRole('button',{name:'关闭视频预览',exact:true}).click();
 await p.evaluate(()=>transferMode='unknown');await open();await p.waitForFunction(()=>/已读取/.test(document.querySelector('.canvas-video-viewer-info').textContent));assert(!(await info.innerText()).includes('%'));const aborted=await p.evaluate(()=>transferAborted);await p.getByRole('button',{name:'关闭视频预览',exact:true}).click();await p.waitForFunction(n=>transferAborted>n,aborted);assert.equal(await p.locator('#canvasVideoViewer video').count(),0);
 await open();await p.waitForFunction(()=>/已读取/.test(document.querySelector('.canvas-video-viewer-info').textContent));await p.evaluate(()=>transferFail());await p.getByRole('button',{name:'重试预览',exact:true}).waitFor();await p.getByRole('button',{name:'重试预览',exact:true}).click();await p.waitForFunction(()=>/已读取/.test(document.querySelector('.canvas-video-viewer-info').textContent));await p.evaluate(()=>{transferNext();transferNext()});await p.waitForFunction(()=>document.querySelector('#canvasVideoViewer video').readyState>=1);assert.deepEqual(writes,[]);assert.deepEqual(errors,[]);console.log('PASS known/unknown download progress, playback, interruption, explicit retry and close cancellation; zero writes');
 }finally{for(const c of b.contexts())for(const p of c.pages())await p.unrouteAll({behavior:'ignoreErrors'});await b.close()}
})().catch(e=>{console.error(String(e.message).split('\n')[0]);process.exitCode=1});
