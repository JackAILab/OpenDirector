const {chromium}=require('playwright'),fs=require('fs'),path=require('path'),assert=require('assert/strict');
(async()=>{const browser=await chromium.launch({headless:true,args:['--no-sandbox']});try{
 const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
 const root=path.resolve(__dirname,'../..');let unlocked=false,adoptions=0,expireAdoption=true,videoReads=0;
 const templates=['coffee','lamp'].map((id,i)=>({id,title:i?'窗边的光':'清晨咖啡',category:i?'家居':'餐饮',product:i?'台灯':'咖啡',scene:'日常',duration:10,aspect:'16:9',model_label:'Kling 2.5',audio:false,storyboard:[{title:'细节',rationale:'展现质感',caption:'早安'}]}));
 templates.push(
  {...templates[0],id:'native',title:'十五秒有声香水',category:'香氛',duration:15,audio:true,model_label:'Kling 3.0',storyboard:[{start:0,end:5,title:'进入夜晚'},{start:5,end:10,title:'商品细节'},{start:10,end:15,title:'留下感受'}]},
  {...templates[0],id:'short-audio',title:'短有声风格参考',category:'参考',duration:10,audio:true},
  {...templates[0],id:'long-silent',title:'长静音风格参考',category:'参考',duration:15,audio:false}
 );
 await page.addInitScript(()=>sessionStorage.setItem('h3_api_key','fixture'));
 await page.route('http://studio.test/**',async route=>{const r=route.request(),u=new URL(r.url());
  if(u.pathname==='/creative/discover')return route.fulfill({contentType:'text/html',body:fs.readFileSync(root+'/tools/agent_studio/discover.html','utf8')});
  if(['/creative/portal.js','/creative/portal.css'].includes(u.pathname))return route.fulfill({contentType:u.pathname.endsWith('.js')?'text/javascript':'text/css',body:fs.readFileSync(root+'/tools/agent_studio/'+path.basename(u.pathname),'utf8')});
  if(u.pathname==='/creative/theme.js')return route.fulfill({contentType:'text/javascript',body:fs.readFileSync(root+'/tools/agent_studio/theme.js','utf8')});
  if(u.pathname==='/creative/theme.css')return route.fulfill({contentType:'text/css',body:fs.readFileSync(root+'/tools/agent_studio/theme.css','utf8')});
  if(u.pathname==='/creative/skills.css')return route.fulfill({contentType:'text/css',body:fs.readFileSync(root+'/tools/agent_studio/skills.css','utf8')});
  if(u.pathname==='/creative/skills.js')return route.fulfill({contentType:'text/javascript',body:fs.readFileSync(root+'/tools/agent_studio/skills.js','utf8')});
  if(u.pathname.startsWith('/creative/')&&/\.(js|css)$/.test(u.pathname)&&fs.existsSync(root+'/tools/agent_studio/'+path.basename(u.pathname)))return route.fulfill({path:root+'/tools/agent_studio/'+path.basename(u.pathname)});
  if(u.pathname.endsWith('.woff2'))return route.fulfill({contentType:'font/woff2',body:fs.readFileSync(root+'/tools/asset_studio/public/fonts/studio-chinese.woff2')});
 if(u.pathname==='/site/access'){unlocked=true;return route.fulfill({json:{ok:true}})}
  if(u.pathname==='/creative/api/models')return route.fulfill({json:{models:[
   {id:'kling-video-v3_0',label:'Kling 3.0',provider:'kling',credits_per_5s:3,audio:true,single_film:true,available:true},
   {id:'kling-video-v3_0_omni',label:'Kling O3',provider:'kling',credits_per_5s:4,audio:true,single_film:true,available:true},
   {id:'MiniMax-H3',label:'MiniMax H3',provider:'minimax-h3',credits_per_5s:1,audio:true,single_film:false,available:false,limitation:'待验证'}
  ],image_models:[{id:'hunyuan-image-v3.0',label:'混元 Image 3.0',available:true,mode:'text',credits:1}],status_note:'synthetic model catalog'}})
  if(u.pathname==='/creative/api/skills')return route.fulfill({json:{skills:[
   {id:'ad-video',title:'商品广告导演',version:1,inputs:['商品参考图或已确认的外观','唯一卖点','受众与投放目的'],references:['商品外观、材质和可见结构'],steps:['核实商品','规划分镜'],checks:['商品外观一致','卖点有画面证据','旁白可听且不过密'],source:'recipe'},
   {id:'template-native',title:'十五秒有声香水',version:1,inputs:['商品参考图或已确认的外观','唯一卖点','受众与投放目的'],references:['商品外观、材质和可见结构'],steps:['核实商品','规划分镜'],checks:['商品外观一致','卖点有画面证据','旁白可听且不过密'],source:'template'}
  ]}})
  if(u.pathname==='/creative/api/skills/mine')return route.fulfill({json:{skills:[],favorites:[]}})
  if(u.pathname==='/creative/api/templates')return route.fulfill(unlocked?{json:{templates}}:{status:403,json:{detail:'gate'}});
  if(u.pathname.endsWith('/video')){videoReads++;return route.fulfill({status:503})}
  if(u.pathname.endsWith('/poster'))return route.fulfill({status:404});
  if(u.pathname.endsWith('/use')){adoptions++;assert.deepEqual(r.postDataJSON(),{product:'我的茶杯',requirements:'保留原产品的杯柄形状',model:'kling-video-v3_0_omni',aspect:'9:16',approval_mode:'manual'});if(expireAdoption){expireAdoption=false;return route.fulfill({status:401,json:{detail:'expired'}})}return route.fulfill({json:{id:'new-owned-project'}})}
  if(u.pathname==='/account')return route.fulfill({body:'synthetic login'});
  if(u.pathname==='/creative')return route.fulfill({body:'workspace'});
  return route.fulfill({status:404});
 });
 await page.goto('http://studio.test/creative/discover?view=agent');assert.equal(await page.evaluate(()=>document.documentElement.dataset.theme),'dark');assert.equal(await page.locator('body').evaluate(e=>getComputedStyle(e).backgroundColor),'rgb(18, 18, 18)');await page.locator('#password').fill('fixture');await page.locator('#gateForm button').click();await page.locator('.sample-gallery>summary').click();await page.locator('.studio-entry-details>summary').click();await page.locator('.template').nth(1).waitFor();await page.waitForFunction(()=>document.querySelectorAll('#entryVideo option').length===3);assert(await page.locator('[data-setting=entrySkill]').isVisible());assert(await page.locator('[data-setting=entryApproval]').isVisible());assert(await page.locator('[data-setting=entryImage]').isVisible());
 // Only actual long, audible samples are featured; loading the page stays silent.
 await page.locator('#featuredFilm').waitFor();assert.equal(await page.locator('#featuredTitle').textContent(),'十五秒有声香水');
 assert.equal(videoReads,0);assert.match(await page.locator('#featuredBeats').innerText(),/10–15s/);
 await page.locator('#soundOnly').check();assert.equal(await page.locator('.template').count(),1);assert.match(await page.locator('.template').innerText(),/十五秒有声香水/);
 await page.locator('#search').fill('不存在的产品');assert.equal(await page.locator('.template').count(),0);
 await page.getByRole('button',{name:'查看全部样片',exact:true}).click();assert.equal(await page.locator('.template').count(),5);assert.equal(await page.locator('#soundOnly').isChecked(),false);
 await page.locator('#featuredPreview').click();await page.locator('#previewDialog').waitFor();assert.match(await page.locator('#previewVideo').getAttribute('src'),/native\/video$/);assert.match(await page.locator('#structure').innerText(),/这个 Skill 如何复用 · v1/);assert.match(await page.locator('#structure').innerText(),/输入契约[\s\S]*商品参考图或已确认的外观/);assert.match(await page.locator('#structure').innerText(),/验收标准[\s\S]*卖点有画面证据/);
 await page.waitForFunction(()=>document.querySelector('#previewStatus').textContent.length>0);assert(videoReads>0);await page.locator('#closePreview').click();assert(await page.locator('#previewVideo').evaluate(v=>v.paused));
 assert.equal(await page.locator('#quickForm').count(),1);assert.equal(await page.locator('.entry-paths > button').count(),3);assert.equal(await page.locator('.entry-paths > a').count(),2);assert.match(await page.locator('.entry-paths > a[href="/creative/scene"]').innerText(),/3D-BOX 场景调度/);assert.equal(await page.locator('.composer').count(),1);await page.locator('#modelCatalog').evaluate(el=>el.open=true);assert.match(await page.locator('#modelStrip').innerText(),/Kling 3\.0/);assert.match(await page.locator('#modelStrip').innerText(),/MiniMax H3/);assert.equal(await page.locator('#entryVideo option').count(),3);assert.equal(await page.locator('#entryImage option').count(),1);
 await page.locator('[data-intent="story"]').click();assert.equal(await page.locator('[data-intent="story"]').getAttribute('aria-pressed'),'true');assert.match(await page.locator('#quickTitle').innerText(),/品牌故事/);assert.match(await page.locator('.entry-paths > a[href="/creative/library"]').innerText(),/广告参考/);
 await page.locator('#search').fill('台灯');assert.equal(await page.locator('.template').count(),1);await page.locator('#search').fill('');await page.locator('#filters').getByRole('button',{name:'餐饮',exact:true}).click();assert.equal(await page.locator('.template').count(),1);
 await page.locator('#filters').getByRole('button',{name:'全部',exact:true}).click();await page.setViewportSize({width:390,height:844});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
 await page.locator('.studio-nav-toggle').click();assert.equal(await page.locator('.studio-nav-toggle').getAttribute('aria-expanded'),'true');await page.locator('[data-portal-nav=agent]').first().click();await page.locator('[data-tab="favorites"]').click();assert.equal(await page.locator('[data-tab="favorites"]').getAttribute('aria-pressed'),'true');assert.equal(await page.locator('.studio-nav-toggle').getAttribute('aria-expanded'),'false');await page.locator('[data-tab="all"]').click();await page.locator('.studio-nav-toggle').click();await page.keyboard.press('Escape');assert.equal(await page.locator('.studio-nav-toggle').getAttribute('aria-expanded'),'false');
 await page.locator('[data-setting=entryVideo]').click();await page.locator('#portalComposerPicker').getByRole('button',{name:/Kling O3/}).click();await page.locator('[data-setting=entryAspect]').click();await page.locator('#portalComposerPicker').getByRole('button',{name:/9:16/}).click();assert.match(await page.locator('#entrySummarySkill').textContent(),/商品广告导演/);assert.equal(await page.locator('#entrySummaryModel').textContent(),'Kling O3');assert.equal(await page.locator('#entrySummaryApproval').textContent(),'手动审批');assert.equal(await page.locator('#entrySummaryAspect').textContent(),'9:16 竖屏');await page.locator('#entrySkillContract').evaluate(e=>e.open=true);assert.match(await page.locator('#entryContractInputs').textContent(),/商品参考图/);assert.match(await page.locator('#entryContractReferences').textContent(),/商品外观/);assert.match(await page.locator('#entryContractChecks').textContent(),/卖点有画面证据/);assert.match(await page.locator('#entryConfigNote').textContent(),/预计 12 平台积分/);
 await page.locator('#quickPrompt').fill('我的茶杯，保留原产品的杯柄形状');
 await page.locator('.card-footer button').first().click();
 assert.equal(await page.locator('#useDialog').count(),0);assert.equal(await page.locator('#entrySkill').inputValue(),'template-native');assert.equal(await page.locator('#entrySkill option:checked').getAttribute('data-version'),'1');assert.equal(await page.locator('#entryVideo').inputValue(),'kling-video-v3_0_omni');assert.equal(await page.locator('#entryAspect').inputValue(),'9:16');assert.equal(await page.locator('#entryApproval').inputValue(),'manual');assert.equal(await page.locator('#quickPrompt').inputValue(),'我的茶杯，保留原产品的杯柄形状');
 await page.locator('#quickForm button[type=submit]').click();await page.waitForURL('**/creative?new=1');assert.equal(adoptions,0);const draft=await page.evaluate(()=>JSON.parse(sessionStorage.getItem('creative_entry_draft')));assert.equal(draft.skill,'template-native');assert.equal(draft.model,'kling-video-v3_0_omni');assert.equal(draft.aspect,'9:16');assert.equal(draft.pending,true);assert.deepEqual(errors,[]);
 console.log('PASS featured audio preview with opt-in playback, duration/audio filtering and empty reset, gallery gate, mobile layout, model/ratio and Skill composer handoff; no generation');
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exit(1)});
