// Isolated UI regression: no real credentials, provider calls or paid generation.
const {chromium}=require('playwright'),fs=require('fs'),path=require('path'),assert=require('assert/strict');
(async()=>{const browser=await chromium.launch({headless:true,args:['--no-sandbox']});try{
 const root=path.resolve(__dirname,'../..'),dir=root+'/tools/agent_studio';
 const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.addInitScript(()=>sessionStorage.setItem('h3_api_key','fixture'));
 const aid='a'.repeat(32),model='kling-video-v4_0';let submits=0;
 const p={id:'reconfirm-fixture',revision:1,state:'ready',creation_mode:'agent',generation_mode:'chaptered_native',model,provider:'kling',duration:60,aspect:'16:9',brief:{product:'黑银三风扇显卡'},messages:[],questions:[],decisions:[],assumptions:[],events:[],shots:Array.from({length:12},(_,i)=>({id:'shot_'+i,start:i*5,duration:5,title:'镜头',prompt:'画面',audio_prompt:'声音',caption:'',state:'planned'})),canvas:{nodes:[{id:'ref',kind:'image',asset:aid,label:'显卡'}],edges:[]},canvas_assets:{[aid]:{id:aid,kind:'image'}},quote:{label:'Kling 4.0',credits:48,new_jobs:4},video_inputs_needs_review:true,video_inputs:{mode:'references',references:[{asset:aid,role:'product',instruction:''}]},input_manifest:{mode:'references',images:[{asset:aid}],beats:[]}};
 await page.route('https://studio.test/**',r=>{const u=new URL(r.request().url()),f=dir+'/'+path.basename(u.pathname);
  if(u.pathname==='/creative')return r.fulfill({contentType:'text/html',body:fs.readFileSync(dir+'/index.html')});
  if(/\.(css|js)$/.test(u.pathname)&&fs.existsSync(f))return r.fulfill({contentType:f.endsWith('.js')?'text/javascript':'text/css',body:fs.readFileSync(f)});
  if(u.pathname.endsWith('.woff2'))return r.fulfill({body:fs.readFileSync(root+'/tools/asset_studio/public/fonts/studio-chinese.woff2')});
  if(u.pathname.endsWith('/models'))return r.fulfill({json:{models:[{id:model,label:'Kling 4.0',available:true,single_film:true,video_input_modes:{text:0,references:7}}],image_models:[]}});
  if(u.pathname.endsWith('/skills'))return r.fulfill({json:{skills:[]}});
  if(u.pathname.endsWith('/projects'))return r.fulfill({json:[]});
  if(u.pathname.endsWith('/video-inputs/preview'))return r.fulfill({json:{references:[{...p.video_inputs.references[0],width:960,height:640}],input_hash:'f'.repeat(64),requires_plan:false}});
  if(u.pathname.endsWith('/video-inputs')){p.revision++;p.video_inputs_needs_review=false;return r.fulfill({json:p})}
  if(u.pathname.endsWith('/budget'))return r.fulfill({json:{revision:p.revision,required_credits:48,remaining_credits:null,sufficient:true}});
  if(u.pathname.endsWith('/execute')){submits++;return r.fulfill({status:409,json:{detail:'测试：输入已变化，请重新核对'}})}
  if(u.pathname.endsWith('/projects/'+p.id))return r.fulfill({json:p});return r.fulfill({status:404,json:{detail:'fixture'}});
 });
 await page.goto('https://studio.test/creative?project='+p.id+'&view=storyboard');
 await page.locator('#executeButton').click();await page.locator('#videoInputDialog').waitFor();
 assert.equal(await page.locator('#approveDialog').evaluate(e=>e.open),false);assert.equal(submits,0);
 assert.match(await page.locator('#videoInputDialog').innerText(),/60 秒/);assert.match(await page.locator('#videoInputDialog').innerText(),/黑银三风扇显卡/);
 await page.getByRole('button',{name:'核对视频输入',exact:true}).click();await page.getByRole('button',{name:'确认输入 · 保留方案',exact:true}).click();
 await page.waitForFunction(()=>!document.querySelector('#videoInputDialog'));assert.equal(submits,0);
 await page.locator('#executeButton').click();await page.waitForFunction(()=>!document.querySelector('#confirmExecute').disabled);
 await page.locator('#confirmExecute').click();await page.locator('#approveDialog [role=alert]').filter({hasText:'测试：输入已变化'}).waitFor();
 assert.equal(submits,1);assert.equal(await page.locator('#approveDialog').evaluate(e=>e.open),true);assert.equal(await page.locator('#executionError').evaluate(e=>document.activeElement===e),true);
 assert.deepEqual(errors,[]);console.log('PASS reference preflight preserves plan without generation; 409 visible and focused inside modal');
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exitCode=1});
