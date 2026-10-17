// Run with Playwright available in NODE_PATH; uses synthetic data, no provider calls.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
(async () => {
  const browser = await chromium.launch({headless:true,args:['--no-sandbox']});
  try {
    const page = await browser.newPage();
    const errors=[];page.on('pageerror',e=>errors.push(e.message));
    let project={id:'draft-test',state:'ready',revision:1,duration:15,generation_mode:'single_native',aspect:'16:9',provider:'kling',
      model:'kling-video-v3_0',brief:{product:'测试咖啡'},messages:[],questions:[],decisions:[],assumptions:[],events:[],
      shots:[1,2,3].map((n)=>({id:'shot_'+n,title:'镜头'+n,caption:'原字幕'+n,prompt:'coffee '+n,audio_prompt:'钢琴与旁白',rationale:'产品展示',start:(n-1)*5,duration:5,state:'planned'})),
      quote:{label:'Kling 3.0',credits:9,new_jobs:1}};
    let writes=0,failSave=false,unexpected=[],executions=[];
    await page.addInitScript(()=>sessionStorage.setItem('h3_api_key','synthetic-session'));
    await page.route('http://studio.test/**',async route=>{
      const req=route.request(),url=new URL(req.url());
      if(url.pathname==='/creative')return route.fulfill({contentType:'text/html',body:fs.readFileSync(path.join(__dirname,'../../tools/agent_studio/index.html'),'utf8')});
      if(['/creative/canvas.js','/creative/canvas.css','/creative/workspace.js','/creative/workspace.css','/creative/learning.js','/creative/theme.js','/creative/theme.css','/creative/creative-controls.js'].includes(url.pathname))return route.fulfill({contentType:url.pathname.endsWith('.js')?'text/javascript':'text/css',body:fs.readFileSync(path.join(__dirname,'../../tools/agent_studio',path.basename(url.pathname)),'utf8')});
      let data;
      if(url.pathname.endsWith('/models'))data={models:[{id:'kling-video-v3_0',provider:'kling',label:'Kling 3.0',credits_per_5s:3,single_film:true,audio:true}]};
      else if(url.pathname.endsWith('/skills'))data={skills:[{id:'ad-video',title:'商品广告导演',version:1}]};
      else if(url.pathname==='/creative/api/projects')data=[{id:project.id,title:'测试咖啡',state:'ready'}];
      else if(url.pathname==='/creative/api/projects/'+project.id)data=project;
      else if(url.pathname.endsWith('/timeline')&&req.method()==='PATCH'){
        writes++;
        if(failSave)return route.fulfill({status:409,json:{detail:'版本发生变化，请重新载入'}});
        project={...project,shots:req.postDataJSON().shots,revision:project.revision+1};data=project;
      }else if(url.pathname.endsWith('/execute')&&req.method()==='POST'){executions.push(req.postDataJSON());data=project;
      }else if(url.pathname.endsWith('.woff2'))return route.fulfill({status:404});
      else {unexpected.push(req.method()+' '+url.pathname);return route.fulfill({status:400,json:{detail:'unexpected'}})}
      return route.fulfill({json:data});
    });
    await page.goto('http://studio.test/creative?view=studio');
  await page.locator('#cameraTrack button').first().click();
    await page.locator('#shotCaption').fill('第一镜头草稿');await page.locator('#shotAudio').fill('新旁白与音乐');
    await page.locator('#cameraTrack button').nth(1).click();
    await page.locator('#shotCaption').fill('第二镜头草稿');
    await page.locator('#cameraTrack button').first().click();
    assert.equal(await page.locator('#shotCaption').inputValue(),'第一镜头草稿');
    // A status refresh must preserve edits just as a timeline selection does.
    await page.evaluate(()=>draw());
    assert.equal(await page.locator('#shotCaption').inputValue(),'第一镜头草稿');
    await page.locator('#executeButton').click();
    assert.equal(await page.locator('#approveDialog').evaluate(el=>el.open),false);
    await page.locator('#planButton').click();
    assert.equal(unexpected.length,0);
    failSave=true;await page.locator('#saveShot').click();
    await page.waitForFunction(()=>!document.querySelector('#saveShot').disabled);
    assert.equal(await page.locator('#shotCaption').inputValue(),'第一镜头草稿');
    failSave=false;await page.locator('#saveShot').click();
    await page.waitForFunction(()=>document.querySelector('#draftNotice').classList.contains('hidden'));
    assert.deepEqual(project.shots.map(s=>s.caption),['第一镜头草稿','第二镜头草稿','原字幕3']);
    assert.equal(writes,2);assert.equal(project.shots[0].audio_prompt,'新旁白与音乐');
    await page.locator('#shotCaption').fill('要放弃的草稿');
    await page.locator('#discardDrafts').click();
    assert.equal(await page.locator('#shotCaption').inputValue(),'第一镜头草稿');
    await page.locator('#executeButton').click();
    assert.equal(await page.locator('#approveDialog').evaluate(el=>el.open),true);
    // A background refresh cannot approve a newer revision than the visible confirmation.
    await page.evaluate(()=>{project={...project,revision:project.revision+1}});
    await page.locator('#confirmExecute').click();
    assert.equal(executions.length,0);
    assert.equal(await page.locator('#approveDialog').evaluate(el=>el.open),false);
    await page.locator('#executeButton').click();
    // Even if a status refresh changes a quote, submit only the budget the user saw.
    await page.evaluate(()=>{project={...project,quote:{...project.quote,credits:18}}});
    await page.locator('#confirmExecute').click();
    await page.waitForFunction(()=>!document.querySelector('#confirmExecute').disabled);
    assert.deepEqual(executions,[{revision:3,approved_credits:9}]);
    assert.deepEqual(unexpected,[]);assert.deepEqual(errors,[]);
    console.log('PASS: cross-shot drafts, refresh preservation, save failure, save all, discard, execution/planning guard, stale approval rejected, reviewed budget preserved; synthetic execution only');
  } finally {await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
