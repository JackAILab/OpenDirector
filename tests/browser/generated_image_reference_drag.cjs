// Completed-image state fixture with real owned image files and target input preview/save.
const {chromium}=require('playwright'),fs=require('fs'),assert=require('assert');
(async()=>{const browser=await chromium.launch({channel:'chromium',headless:true,args:['--no-sandbox']});try{
 const page=await browser.newPage({viewport:{width:1510,height:900}}),base=process.env.TEST_BASE_URL||'http://127.0.0.1:30080',key=JSON.parse(fs.readFileSync(process.env.TEST_API_KEY_FILE)).api_key,headers={Authorization:'Bearer '+key};const errors=[];page.on('pageerror',e=>errors.push(e.message));await page.addInitScript(k=>sessionStorage.setItem('h3_api_key',k),key);
 let p=await(await page.request.post(base+'/creative/api/projects',{headers,data:{message:'generated result reference fixture',creation_mode:'image'}})).json();
 const png=await page.evaluate(()=>{const c=document.createElement('canvas');c.width=320;c.height=180;const x=c.getContext('2d');x.fillStyle='#6699bb';x.fillRect(0,0,320,180);return c.toDataURL().split(',')[1]});
 const uploaded=await(await page.request.post(base+'/creative/api/projects/'+p.id+'/canvas/assets?kind=image&revision='+p.revision,{headers,data:Buffer.from(png,'base64')})).json();p=uploaded.project;const aid=uploaded.asset.id;
 p=await(await page.request.put(base+'/creative/api/projects/'+p.id+'/canvas',{headers,data:{revision:p.revision,nodes:[{id:'fixture_image',kind:'image',asset:aid,label:'图片',role:'reference',text:'',x:40,y:700}],edges:[]}})).json();
 const source=await(await page.request.post(base+'/creative/api/projects/'+p.id+'/manual-nodes',{headers,data:{message:'completed image fixture',creation_mode:'image',image_model:'kling-image-v3_0'}})).json();
 source.project=await(await page.request.post(base+'/creative/api/projects/'+p.id+'/manual-nodes/'+source.project.id+'/reference',{headers,data:{revision:source.project.revision,asset:aid}})).json();
 const target=await(await page.request.post(base+'/creative/api/projects/'+p.id+'/manual-nodes',{headers,data:{message:'使用生成图片制作视频',creation_mode:'video',model:'kling-video-v4_0',duration:5}})).json();
 source.project.image_task={state:'completed',asset:aid};
 await page.route('**/creative/api/projects/'+p.id+'/manual-nodes',async r=>{const response=await r.fetch(),data=await response.json();data.nodes=data.nodes.map(n=>n.project.id===source.project.id?{...n,project:source.project}:n);await r.fulfill({response,json:data})});
 let imported=0,generated=0;
 await page.route('**/creative/api/projects/'+p.id+'/manual-nodes/'+source.project.id+'/result',async r=>{imported++;const parent=await(await page.request.get(base+'/creative/api/projects/'+p.id,{headers})).json();await r.fulfill({json:{project:parent,node:parent.canvas.nodes[0]}})});
 await page.route('**/creative/api/projects/*/execute',r=>{generated++;return r.abort()});
 await page.goto(base+'/creative?project='+p.id+'&view=canvas');
 const port=page.getByRole('button',{name:'拖动生成图片 节点 2',exact:true}),dest=page.locator('[data-manual-project="'+target.project.id+'"] .manual-node-preview');await port.waitFor();
 await port.dragTo(dest);await page.locator('#videoInputDialog').waitFor({timeout:10000});
 assert.equal(imported,1);assert.equal(generated,0);
 assert((await(await page.request.get(base+'/creative/api/projects/'+target.project.id,{headers})).json()).canvas_assets[aid]);
 assert.equal(await page.locator('#videoInputRows article').count(),1);assert.equal(await page.locator('#videoInputRows article').getAttribute('data-asset'),aid);
 await page.locator('#videoInputPreview').click();await page.locator('#videoInputSave').click();await page.locator('#videoInputDialog').waitFor({state:'detached'});
 const saved=await(await page.request.get(base+'/creative/api/projects/'+target.project.id,{headers})).json();assert.equal(saved.video_inputs.references[0].asset,aid);assert.equal(generated,0);
 assert.deepEqual(errors,[]);
 console.log('PASS: generated-image output drag imports source and opens target reference configuration without generation');
}finally{await browser.close()}})().catch(e=>{console.error(String(e.message).split('\n')[0]);process.exitCode=1});
