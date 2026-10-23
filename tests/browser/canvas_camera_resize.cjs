// Actual canvas navigation with fixed APIs; navigation must not mutate or submit anything.
const {chromium}=require('playwright'),fs=require('fs'),path=require('path'),assert=require('assert/strict');
(async()=>{const browser=await chromium.launch({channel:'chromium',headless:true,args:['--no-sandbox']});try{
 const page=await browser.newPage({viewport:{width:1512,height:982}}),errors=[],writes=[];page.on('pageerror',e=>errors.push(e.message));
 const root=path.resolve(__dirname,'../..'),dir=path.join(root,'tools/agent_studio'),evidence=process.env.NAV_EVIDENCE||'/tmp/canvas-navigation';fs.mkdirSync(evidence,{recursive:true});
 const p={id:'navigation-test',state:'ready',revision:1,duration:15,aspect:'16:9',provider:'kling',model:'kling-video-v3_0_omni',brief:{product:'皮夹克导航验证'},messages:[],questions:[],decisions:[],assumptions:[],events:[],shots:[],canvas:{nodes:[
  {id:'notes',kind:'text',label:'拍摄要求',text:'保留银色拉链',role:'story',x:-500,y:-600},
  {id:'jacket',kind:'image',asset:'a'.repeat(32),label:'黑色夹克',text:'夜景侧光',role:'product',x:800,y:20},
  {id:'street',kind:'video',asset:'b'.repeat(32),label:'城市街景',text:'出门场景',role:'scene',x:2500,y:600},
  {id:'literal',kind:'text',label:'<script>window.injected=true</script>',text:'测试名称按文字显示',role:'style',x:-700,y:500}
 ],edges:[]},canvas_assets:{},creation_mode:'agent',quote:{label:'Kling O3',credits:12}};
 const original=JSON.stringify(p.canvas);await page.addInitScript(()=>sessionStorage.setItem('h3_api_key','fixture'));
 await page.route('https://studio.test/**',route=>{const request=route.request(),u=new URL(request.url());if(u.pathname==='/me')return route.fulfill({json:{email:'fixture@example.test',remaining:0}});if(u.pathname.endsWith('/activity'))return route.fulfill({json:{ok:true}});if(request.method()!=='GET'){writes.push(request.method()+' '+u.pathname);return route.fulfill({status:400})}
  if(u.pathname==='/creative')return route.fulfill({contentType:'text/html',body:fs.readFileSync(dir+'/index.html')});
  if(/\.(js|css)$/.test(u.pathname)&&fs.existsSync(dir+'/'+path.basename(u.pathname)))return route.fulfill({contentType:u.pathname.endsWith('.js')?'text/javascript':'text/css',body:fs.readFileSync(dir+'/'+path.basename(u.pathname))});
  if(u.pathname.endsWith('.woff2'))return route.fulfill({contentType:'font/woff2',body:fs.readFileSync(root+'/tools/asset_studio/public/fonts/studio-chinese.woff2')});
  if(u.pathname.endsWith('/models'))return route.fulfill({json:{models:[{id:p.model,label:'Kling O3',provider:'kling',single_film:true,audio:true,available:true,credits_per_5s:4}],image_models:[]}});
  if(u.pathname.endsWith('/skills'))return route.fulfill({json:{skills:[{id:'ad-video',title:'商品广告导演',version:1}]}});
  if(u.pathname.endsWith('/projects'))return route.fulfill({json:[{id:p.id,title:p.brief.product}]});
  if(u.pathname.endsWith('/projects/'+p.id))return route.fulfill({json:p});
  return route.fulfill({status:404,json:{detail:'fixture'}});
 });

 await page.goto('https://studio.test/creative?project=navigation-test&view=canvas');
 await page.waitForSelector('.reference-node',{state:'attached'});await page.waitForFunction(()=>document.documentElement.dataset.dataReady==='true');await page.getByRole('button',{name:'工作流',exact:true}).click();await page.waitForTimeout(500);
 const frame=()=>page.evaluate(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))));
 await frame();
 const transform=()=>page.locator('.canvas-world').evaluate(e=>e.style.transform);
 assert(await page.locator('.agent-materials').isHidden());
 const director=await page.locator('.director').boundingBox();assert(director.width<=420&&director.x>=1000,'workflow Director stays beside canvas');
 await page.mouse.move(600,130);const before=await transform();await page.mouse.wheel(140,80);await page.waitForTimeout(150);await frame();
 const panned=await transform();assert.notEqual(panned,before,'wheel must move canvas');
 await page.setViewportSize({width:1390,height:920});await page.waitForTimeout(150);await frame();assert.equal(await transform(),panned,'resize must preserve manually panned camera');
 await page.mouse.move(600,130);await page.keyboard.down('Control');await page.mouse.wheel(0,-120);await page.keyboard.up('Control');await page.waitForTimeout(150);await frame();
 const zoomed=await transform();assert.notEqual(zoomed,panned,'zoom must change camera');
 await page.setViewportSize({width:1512,height:982});await page.waitForTimeout(150);await frame();assert.equal(await transform(),zoomed,'resize must preserve manually zoomed camera');
 await page.keyboard.press('h');await page.mouse.move(600,400);await page.mouse.down();await page.mouse.move(660,440,{steps:5});await page.mouse.up();await frame();assert.notEqual(await transform(),zoomed,'hand tool drags the exposed canvas');
 const dock=await page.locator('.canvas-toolbar').boundingBox();assert(dock.y>850&&dock.y+dock.height<=982,'workflow controls stay at bottom');const cleanup=page.locator('.canvas-cleanup-old');if(await cleanup.isVisible())assert((await cleanup.boundingBox()).width>65,'cleanup label stays horizontal');
 await page.screenshot({path:evidence+'/workflow-camera.png'});
 await page.getByRole('button',{name:'故事板',exact:true}).click();await frame();assert(await page.locator('.agent-materials').isVisible(),'storyboard retains material shelf');
 await page.getByRole('button',{name:'工作流',exact:true}).click();await frame();assert(await page.locator('.agent-materials').isHidden(),'returning to workflow releases shelf');
 const rail=await page.locator('.canvas-launch-rail').boundingBox();for(const card of await page.locator('.reference-node').all()){const b=await card.boundingBox();assert(b.x>=rail.x+rail.width+8,'fit must leave nodes clear of left tools');}
 assert.deepEqual(errors,[]);assert.deepEqual(writes,[]);assert.equal(JSON.stringify(p.canvas),original);
 console.log('PASS canvas wheel pan and zoom survive viewport resize without writes');
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exit(1)});
