// Read-only image task lifecycle on the actual canvas; fixed APIs, no provider calls.
const {chromium}=require('playwright'),fs=require('fs'),path=require('path'),assert=require('assert/strict');
(async()=>{const browser=await chromium.launch({headless:true,args:['--no-sandbox']});try{
 const page=await browser.newPage({viewport:{width:1512,height:982}}),errors=[],writes=[];page.on('pageerror',e=>errors.push(e.message));
 const root=path.resolve(__dirname,'../..'),dir=path.join(root,'tools/agent_studio'),evidence=process.env.JOB_EVIDENCE||'/tmp/canvas-image-job';fs.mkdirSync(evidence,{recursive:true});
 let p={id:'navigation-test',state:'ready',revision:1,duration:15,aspect:'16:9',provider:'kling',model:'kling-video-v3_0_omni',brief:{product:'皮夹克导航验证'},messages:[],questions:[],decisions:[],assumptions:[],events:[],shots:[],canvas:{nodes:[
  {id:'notes',kind:'text',label:'拍摄要求',text:'保留银色拉链',role:'story',x:-500,y:-600},
  {id:'jacket',kind:'image',asset:'a'.repeat(32),label:'黑色夹克',text:'夜景侧光',role:'product',x:800,y:20},
  {id:'street',kind:'video',asset:'b'.repeat(32),label:'城市街景',text:'出门场景',role:'scene',x:2500,y:600},
  {id:'literal',kind:'text',label:'<script>window.injected=true</script>',text:'测试名称按文字显示',role:'style',x:-700,y:500}
 ],edges:[]},canvas_assets:{},quote:{label:'Kling O3',credits:12}};
 const original=JSON.stringify(p.canvas);let failSync=false;await page.addInitScript(()=>sessionStorage.setItem('h3_api_key','fixture'));
 await page.route('http://studio.test/**',route=>{const request=route.request(),u=new URL(request.url());if(request.method()!=='GET'){writes.push(request.method()+' '+u.pathname);return route.fulfill({status:400})}
  if(u.pathname==='/creative')return route.fulfill({contentType:'text/html',body:fs.readFileSync(dir+'/index.html')});
  if(/\.(js|css)$/.test(u.pathname)&&fs.existsSync(dir+'/'+path.basename(u.pathname)))return route.fulfill({contentType:u.pathname.endsWith('.js')?'text/javascript':'text/css',body:fs.readFileSync(dir+'/'+path.basename(u.pathname))});
  if(u.pathname.endsWith('.woff2'))return route.fulfill({contentType:'font/woff2',body:fs.readFileSync(root+'/tools/asset_studio/public/fonts/studio-chinese.woff2')});
  if(u.pathname.endsWith('/models'))return route.fulfill({json:{models:[{id:p.model,label:'Kling O3',provider:'kling',single_film:true,audio:true,available:true,credits_per_5s:4}],image_models:[{id:'hunyuan-image-v2.0-general-edit',label:'混元图片参考编辑',available:true,mode:'edit',credits:1}]}});
  if(u.pathname.endsWith('/skills'))return route.fulfill({json:{skills:[{id:'ad-video',title:'商品广告导演',version:1}]}});
  if(u.pathname.endsWith('/projects'))return route.fulfill({json:[{id:p.id,title:p.brief.product}]});
  if(u.pathname.endsWith('/projects/'+p.id))return failSync?route.fulfill({status:503,json:{detail:'fixture offline'}}):route.fulfill({json:p});
  return route.fulfill({status:404,json:{detail:'fixture'}});
 });

 p.image_task={id:'image-job-1',state:'running',model:'hunyuan-image-v2.0-general-edit',prepared:{references:[{asset:'a'.repeat(32)}]}};
 await page.goto('http://studio.test/creative?view=canvas');await page.locator('.canvas-image-job').waitFor();
 const card=page.locator('.canvas-image-job');assert.equal(await card.getAttribute('data-state'),'running');assert.equal(await card.getAttribute('aria-busy'),'true');assert.match(await card.textContent(),/参考图生成中.*黑色夹克/s);assert.doesNotMatch(await card.textContent(),/\d+%/);assert.equal(await page.locator('[data-image-processing=running]').count(),1);
 assert.equal(await page.evaluate(()=>hasDrafts()),false);assert.equal(JSON.stringify(p.canvas),original);await page.locator('#canvasNavigatorToggle').click();await page.getByRole('searchbox').fill('参考图生成中');await page.waitForFunction(()=>document.querySelectorAll('.canvas-navigator-result').length===1);await page.locator('.canvas-navigator-result').click();await page.screenshot({path:evidence+'/image-job-running.png'});
 await page.locator('#canvasNavigatorToggle').click();await page.getByRole('searchbox').fill('参考图生成中');await page.waitForFunction(()=>document.querySelectorAll('.canvas-navigator-result').length===1);await page.locator('.canvas-navigator-result').click();
 await card.getByRole('button',{name:'黑色夹克',exact:true}).click();await page.locator('#canvasMediaToolbar').waitFor({state:'visible'});assert.match(await page.locator('#canvasMediaToolbar').getAttribute('aria-label'),/黑色夹克/);
 failSync=true;await page.evaluate(()=>refreshProjectStatus());assert.equal(await card.getAttribute('data-state'),'stale');assert.equal(await card.getAttribute('aria-busy'),'false');assert.match(await card.textContent(),/状态同步中断/);assert.equal(await page.locator('[data-image-processing=running]').count(),0);
 failSync=false;await page.evaluate(()=>refreshProjectStatus());assert.equal(await card.getAttribute('data-state'),'running');
 p={...p,revision:2,image_task:{...p.image_task,state:'completed',asset:'c'.repeat(32)},canvas:{...p.canvas,nodes:[...p.canvas.nodes,{id:'result',kind:'image',asset:'c'.repeat(32),label:'生成的夹克场景',role:'scene',x:3000,y:30}]}};
 await page.evaluate(()=>refreshProjectStatus());assert.equal(await card.getAttribute('data-state'),'completed');assert.equal(await page.locator('[data-image-processing]').count(),0);await card.getByRole('button',{name:'定位生成结果',exact:true}).click();await page.waitForFunction(()=>document.querySelector('#canvasMediaToolbar')?.getAttribute('aria-label').includes('生成的夹克场景'));assert.equal(await page.evaluate(()=>hasDrafts()),false);
 // Open the actual task through navigation; completion never writes a new canvas node itself.
 await page.locator('#canvasNavigatorToggle').click();await page.getByRole('searchbox').fill('参考图已加入画布');await page.waitForFunction(()=>document.querySelectorAll('.canvas-navigator-result').length===1);await page.locator('.canvas-navigator-result').click();await page.screenshot({path:evidence+'/image-job-completed.png'});await card.getByRole('button',{name:'收起',exact:true}).click();assert.equal(await card.count(),0);await page.evaluate(()=>draw());assert.equal(await card.count(),0);
 p={...p,revision:3,image_task:{id:'image-job-2',state:'needs_review',model:'hunyuan-image-v3.0',reference_id:'product-reference'}};await page.evaluate(()=>refreshProjectStatus());assert.equal(await card.getAttribute('data-state'),'needs_review');assert.match(await card.textContent(),/不会自动重新生成/);assert.match(await card.textContent(),/本次输入 · 商品参考图/);assert.equal(await card.getByRole('button',{name:'定位生成结果',exact:true}).count(),0);await card.getByRole('button',{name:'查看任务详情',exact:true}).click();assert.equal(await page.locator('#productionTask').evaluate(e=>e.open),true);await page.keyboard.press('Escape');
 // The result disappeared from the canvas: do not point at another image.
 p={...p,image_task:{...p.image_task,state:'completed',asset:'d'.repeat(32)}};await page.evaluate(()=>refreshProjectStatus());assert(await card.getByRole('button',{name:'结果暂不在画布'}).isDisabled());
 await page.setViewportSize({width:390,height:844});await page.locator('#canvasNavigatorToggle').click();await page.getByRole('searchbox').fill('图片已生成');await page.waitForFunction(()=>document.querySelectorAll('.canvas-navigator-result').length===1);await page.locator('.canvas-navigator-result').click();const box=await card.boundingBox(),chat=await page.locator('.director').boundingBox();assert(box.x>=0&&box.x+box.width<=390&&box.y+box.height<chat.y);await page.screenshot({path:evidence+'/image-job-mobile.png'});
 p={...p,id:'another-project',revision:1,image_task:undefined};await page.evaluate(()=>openProject('another-project'));assert.equal(await card.count(),0);
 p={...p,image_task:{id:'old-completed-job',state:'completed',asset:'a'.repeat(32)}};await page.reload();await page.waitForSelector('.reference-node');assert.equal(await card.count(),0,'old completed jobs do not add clutter on project open');
 assert.deepEqual(errors,[]);assert.deepEqual(writes,[]);console.log('PASS image task lifecycle, source binding, disconnection/recovery, completion locate, dismiss, failed/removed result, mobile, project switch; no writes or paid calls');
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exit(1)});
