// Isolated reference connection UI; every API is intercepted, including saves.
const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
(async()=>{const browser=await chromium.launch({channel:'chromium',headless:true,args:['--no-sandbox']});try{
 const page=await browser.newPage({viewport:{width:1512,height:982}}),dir=path.resolve(__dirname,'../../tools/agent_studio'),errors=[],writes=[];page.on('pageerror',e=>{errors.push(e.message);console.error(e.message)});await page.addInitScript(()=>sessionStorage.setItem('h3_api_key','fixture'));
 const root={id:'fixture',creation_mode:'agent',state:'ready',quote:{label:'模型',credits:4,new_jobs:0},revision:1,model:'available',provider:'kling',generation_mode:'single_native',aspect:'16:9',duration:5,brief:{product:'模型可用性'},messages:[],questions:[],decisions:[],assumptions:[],events:[],shots:[],canvas:{nodes:[],edges:[]}};
 let failSave=true;
 let child={...root,id:'child',creation_mode:'video',state:'ready',direct_prompt:'测试模型不可用',quote:{credits:4}};root.canvas.nodes=[{id:'source',kind:'image',asset:'asset',label:'场景参考',role:'reference',x:40,y:40}];root.canvas_assets={asset:{id:'asset',kind:'image',width:320,height:180}};
 await page.route('https://models.test/**',async route=>{const r=route.request(),u=new URL(r.url());if(u.pathname.includes('/creative/api/')&&r.method()!=='GET')writes.push(u.pathname);
  if(u.pathname.endsWith('/child/reference')){child={...child,revision:child.revision+1,canvas_assets:root.canvas_assets,canvas:root.canvas};return route.fulfill({json:child})}
  if(u.pathname.endsWith('/video-inputs/preview'))return route.fulfill({json:{references:r.postDataJSON().references.map(x=>({...x,width:320,height:180})),input_hash:'fixture'}});
  if(u.pathname.endsWith('/video-inputs')){if(failSave){failSave=false;return route.fulfill({status:503,json:{detail:'保存连接失败'}})}child={...child,revision:child.revision+1,video_inputs:r.postDataJSON()};return route.fulfill({json:child})}
  if(u.pathname==='/me')return route.fulfill({json:{email:'fixture@example.test',remaining:0}});
  if(u.pathname==='/creative')return route.fulfill({contentType:'text/html',body:fs.readFileSync(dir+'/index.html')});
  if(/\.(js|css)$/.test(u.pathname))return route.fulfill({contentType:u.pathname.endsWith('.js')?'text/javascript':'text/css',body:fs.readFileSync(dir+'/'+path.basename(u.pathname))});
  if(u.pathname.endsWith('/models'))return route.fulfill({json:{models:[{id:'offline',provider:'kling',single_film:true,label:'不可用模型',available:false,manual_available:false,manual_durations:[5]},{id:'available',provider:'kling',single_film:true,label:'可用模型',available:true,manual_available:true,manual_durations:[5],credits_per_5s:4,video_input_modes:{text:0,references:3}}],image_models:[]}});
  if(u.pathname.endsWith('/skills'))return route.fulfill({json:{skills:[]}});
  if(u.pathname.endsWith('/projects'))return route.fulfill({json:[root]});
  if(u.pathname.endsWith('/projects/fixture'))return route.fulfill({json:root});
  if(u.pathname.endsWith('/manual-nodes'))return route.fulfill({json:{nodes:[{node:{index:2,x:600,y:50},project:child}]}});
  return route.fulfill({status:404,json:{detail:'fixture'}});
 });

 await page.goto('https://models.test/creative?project=fixture&view=canvas');await page.waitForFunction(()=>document.documentElement.dataset.dataReady==='true');await page.getByRole('button',{name:'工作流',exact:true}).click();
 const port=page.getByRole('button',{name:'拖动图片参考 场景参考',exact:true});await port.waitFor();await port.click();await page.getByRole('button',{name:'视频节点 2',exact:true}).click();await page.locator('#videoInputDialog').waitFor();assert.equal(await page.locator('#videoInputRows article').count(),1);
 await page.getByRole('button',{name:'关闭视频参考',exact:true}).click();assert(!child.video_inputs,'cancel cannot bind inputs');
 await port.dragTo(page.locator('[data-manual-project=child] .manual-node-preview'));await page.locator('#videoInputDialog').waitFor();await page.locator('#videoInputPreview').click();await page.locator('#videoInputSave').click();await page.locator('#videoInputPreview').waitFor();assert(await page.locator('#videoInputReview').isHidden(),'failed save invalidates the old confirmation summary');assert.equal(await page.locator('#videoInputRows article').count(),1,'selected image survives failure');assert(!child.video_inputs);assert.equal(await page.locator('.manual-reference-edges .reference-edge-hit').count(),0,'failed save cannot display a saved connection');await page.locator('#videoInputPreview').click();await page.locator('#videoInputSave').click();await page.locator('#videoInputDialog').waitFor({state:'detached'});
 const edge=page.locator('.manual-reference-edges .reference-edge-hit[data-source=source][data-target=child]');await edge.waitFor({state:'attached'});assert.equal(child.video_inputs.references[0].asset,'asset');
 await page.reload();await edge.waitFor({state:'attached'});assert.equal(await edge.count(),1);assert(!writes.some(x=>x.endsWith('/execute')));assert.deepEqual(errors,[]);console.log('PASS reference target choice, cancel, mouse drag, explicit input save, connection restoration after reload; intercepted APIs only');
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exitCode=1});
