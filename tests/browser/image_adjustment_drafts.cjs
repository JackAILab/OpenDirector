// Browser UI draft isolation; never submits model generation or writes project data.
const {chromium}=require('playwright'),fs=require('fs'),assert=require('assert');
(async()=>{const b=await chromium.launch({channel:'chromium',headless:true,args:['--no-sandbox']});try{
 const c=await b.newContext({storageState:process.env.TEST_STORAGE_STATE,viewport:{width:1510,height:900}});
 await c.addInitScript(s=>{for(const[k,v]of Object.entries(s))sessionStorage.setItem(k,v)},JSON.parse(fs.readFileSync(process.env.TEST_SESSION_STORAGE)));
 const p=await c.newPage(),writes=[],errors=[];p.on('pageerror',e=>errors.push(e.message));await p.route('**/creative/api/**',r=>{if(!['GET','HEAD'].includes(r.request().method())){writes.push(r.request().method());return r.abort()}return r.continue()});
 const url=(process.env.TEST_BASE_URL||'http://127.0.0.1:30080')+'/creative?project='+process.env.TEST_PROJECT_ID+'&view=canvas';
 const select=async id=>{await p.locator('[data-node-id="'+id+'"] .canvas-card-head').click()};
 const open=async mode=>{await p.getByRole('button',{name:mode,exact:true}).click();return p.getByRole('dialog',{name:mode==='多角度'?'多角度编辑器':'重打光',exact:true})};
 const close=async d=>d.getByRole('button',{name:'关闭调整面板'}).click();
 await p.goto(url);await select(process.env.TEST_NODE_ID);let d=await open('多角度');await d.getByRole('button',{name:'背面视角',exact:true}).click();await d.getByRole('switch').check();await d.getByLabel('附加调整要求').fill('保留主体花纹');await close(d);
 d=await open('重打光');await d.getByRole('button',{name:'暖色侧光',exact:true}).click();await close(d);
 await p.reload();await select(process.env.TEST_NODE_ID);d=await open('多角度');assert.equal(await d.getByLabel('水平环绕').inputValue(),'180');assert.equal(await d.getByLabel('附加调整要求').inputValue(),'保留主体花纹');assert(await d.getByRole('switch').isChecked());await close(d);
 await select(process.env.TEST_OTHER_NODE_ID);d=await open('多角度');assert.equal(await d.getByLabel('水平环绕').inputValue(),'0');assert.equal(await d.getByLabel('附加调整要求').inputValue(),'');await close(d);
 await select(process.env.TEST_NODE_ID);d=await open('重打光');assert.equal(await d.getByLabel('光源方向',{exact:true}).inputValue(),'90');assert.equal(await d.getByLabel('色温').inputValue(),'3200');await close(d);
 d=await open('多角度');assert.equal(await d.getByLabel('水平环绕').inputValue(),'180');await d.getByRole('button',{name:'↶ 重置参数',exact:true}).click();await close(d);d=await open('多角度');assert.equal(await d.getByLabel('水平环绕').inputValue(),'0');await p.keyboard.press('Escape');assert.equal(await p.locator('.image-adjustment-panel').count(),0);assert.equal(await p.evaluate(()=>document.activeElement?.textContent),'多角度');
 assert.deepEqual(writes,[]);assert.deepEqual(errors,[]);console.log('PASS: angle/light and asset isolation, refresh restoration, prompt draft, reset and focus return; zero writes');
 }finally{for(const c of b.contexts())for(const p of c.pages())await p.unrouteAll({behavior:'ignoreErrors'});await b.close()}
})().catch(e=>{console.error(String(e.message).split('\n')[0]);process.exitCode=1});
