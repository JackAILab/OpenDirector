// Isolated UI fixture: no user session, real service, or paid provider.
const {chromium}=require('playwright'),fs=require('fs'),path=require('path'),assert=require('assert/strict');
(async()=>{const browser=await chromium.launch({headless:true,args:['--no-sandbox']});try{
 const dir=path.resolve(__dirname,'../../tools/agent_studio'),page=await browser.newPage(),errors=[],writes=[];
 page.on('pageerror',e=>errors.push(e.message));await page.addInitScript(()=>sessionStorage.setItem('h3_api_key','fixture'));
 const aid='a'.repeat(32),parent={id:'delivery-parent',revision:1,state:'ready',creation_mode:'video',model:'kling-video-v4_0',duration:15,aspect:'16:9',brief:{product:'测试'},messages:[],questions:[],decisions:[],assumptions:[],events:[],shots:[],canvas:{nodes:[],edges:[]},canvas_assets:{},quote:{credits:12}};
 // Chapter ready while the final film is still running. There is no final result.
 const child={...structuredClone(parent),id:'delivery-child',creation_mode:'agent',state:'running',workspace_deliveries:[{asset:aid,state:'pending',code:''}]};
 let delivered=false,rootReads=0;
 await page.route('https://studio.test/**',r=>{
  const u=new URL(r.request().url()),file=dir+'/'+path.basename(u.pathname);
  if(r.request().method()!=='GET'){if(u.pathname.startsWith('/creative/api/'))writes.push(u.pathname);return r.fulfill({status:400,json:{detail:'unexpected write'}})}
  if(u.pathname==='/creative')return r.fulfill({contentType:'text/html',body:fs.readFileSync(dir+'/index.html')});
  if(/\.(js|css)$/.test(u.pathname)&&fs.existsSync(file))return r.fulfill({contentType:file.endsWith('.js')?'text/javascript':'text/css',body:fs.readFileSync(file)});
  if(u.pathname.endsWith('/models'))return r.fulfill({json:{models:[{id:parent.model,label:'Kling 4.0',single_film:true,available:true}],image_models:[]}});
  if(u.pathname.endsWith('/skills'))return r.fulfill({json:{skills:[]}});
  if(u.pathname.endsWith('/projects'))return r.fulfill({json:[parent]});
  if(u.pathname.endsWith('/manual-nodes'))return r.fulfill({json:{nodes:[{node:{index:2,project:child.id,x:700,y:40},project:child}]}});
  if(u.pathname.endsWith('/projects/'+parent.id)){
   rootReads++;const value=structuredClone(parent);
   if(delivered){value.revision=2;value.canvas.nodes=[{id:'chapter-result',asset:aid,kind:'image',label:'第一章尾帧',role:'reference',text:'',x:700,y:40}];value.canvas_assets[aid]={id:aid,kind:'image',width:320,height:180}}
   return r.fulfill({json:value});
  }
  return r.fulfill({status:404,json:{detail:'fixture'}});
 });
 await page.goto('https://studio.test/creative?project='+parent.id+'&view=canvas');
 await page.waitForFunction(()=>typeof project!=='undefined'&&project?.id==='delivery-parent');
 await page.waitForTimeout(4300);assert.equal(await page.locator('[data-node-id="chapter-result"]').count(),0);assert.deepEqual(writes,[]);
 const before=rootReads;delivered=true;child.workspace_deliveries[0].state='delivered';
 await page.locator('.reference-node[data-node-id="chapter-result"]').waitFor({timeout:10000});
 assert(rootReads>before);assert.deepEqual(writes,[]);assert.deepEqual(errors,[]);
 console.log('PASS server-delivered chapter appears before final film; pending waits; browser only reads, no import or generation POST');
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exitCode=1});
