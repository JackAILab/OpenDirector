// Native Range playback of an owned video; grants playback only, never generates.
const {chromium}=require('playwright'),fs=require('fs'),assert=require('assert');
(async()=>{assert(process.env.TEST_PROJECT_ID);const b=await chromium.launch({channel:'chromium',headless:true,args:['--no-sandbox']});try{
 const ctx=await b.newContext({storageState:process.env.TEST_STORAGE_STATE,viewport:{width:1510,height:900}});
 if(process.env.TEST_SESSION_STORAGE)await ctx.addInitScript(s=>{for(const[k,v]of Object.entries(s))sessionStorage.setItem(k,v)},JSON.parse(fs.readFileSync(process.env.TEST_SESSION_STORAGE)));
 if(process.env.TEST_API_KEY_FILE)await ctx.addInitScript(k=>sessionStorage.setItem('h3_api_key',k),JSON.parse(fs.readFileSync(process.env.TEST_API_KEY_FILE)).api_key);
 const p=await ctx.newPage();let submits=0;const ranges=[];p.on('response',r=>{if(r.url().endsWith('/source')&&r.request().headers().range)ranges.push(r.status())});await p.route('**/execute',r=>{submits++;return r.abort()});
 await p.goto((process.env.TEST_BASE_URL||'http://127.0.0.1:30080')+'/creative?project='+process.env.TEST_PROJECT_ID+'&view=canvas');
 const result=p.locator('.generated-primary-result');await result.locator('.canvas-video-preview-button').click();
 const video=p.locator('#canvasVideoViewer video');await p.waitForFunction(()=>document.querySelector('#canvasVideoViewer video')?.readyState>=1,null,{timeout:190000});
 await p.waitForTimeout(500);if(await video.evaluate(v=>v.paused)){await video.focus();await p.keyboard.press('Space')}
 await p.waitForTimeout(2000);const state=await video.evaluate(v=>({duration:v.duration,time:v.currentTime,paused:v.paused,ready:v.readyState}));assert(state.time>1);assert(!state.paused);assert(state.ready>=2);
 assert((await video.getAttribute('src')).startsWith('/creative/api/projects/'));assert(ranges.includes(206),'Native playback must receive a partial response');await video.evaluate(v=>v.currentTime=Math.min(20,v.duration-2));await p.waitForFunction(()=>document.querySelector('#canvasVideoViewer video')?.readyState>=2);console.log('native Range verified', {partialResponses:ranges.filter(s=>s===206).length});await p.getByRole('button',{name:'关闭视频预览',exact:true}).click();assert.equal(await p.locator('#canvasVideoViewer video').count(),0);assert.equal(submits,0);console.log('PASS visible preview and native playback',state);
 }finally{await b.close()}})().catch(e=>{console.error(String(e.message).split('\n')[0]);process.exitCode=1});
