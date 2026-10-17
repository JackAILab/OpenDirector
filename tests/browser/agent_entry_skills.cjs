// Visible new-project actions only. Selecting a Skill must never submit a task.
const {chromium}=require('playwright'),fs=require('fs'),assert=require('assert');
(async()=>{const browser=await chromium.launch({channel:'chromium',headless:true,args:['--no-sandbox']});try{
 const context=await browser.newContext({storageState:process.env.TEST_STORAGE_STATE,viewport:{width:1510,height:900}});
 if(process.env.TEST_SESSION_STORAGE)await context.addInitScript(s=>{for(const[k,v]of Object.entries(s))sessionStorage.setItem(k,v)},JSON.parse(fs.readFileSync(process.env.TEST_SESSION_STORAGE)));
 const page=await context.newPage(),errors=[],writes=[];page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/creative/api/**',r=>{if(!['GET','HEAD'].includes(r.request().method())){writes.push(r.request().method());return r.abort()}return r.continue()});
 await page.goto((process.env.TEST_BASE_URL||'http://127.0.0.1:30080')+'/creative?new=1&mode=agent');
 const welcome=page.getByRole('region',{name:'开始 Agent 创作'});await welcome.waitFor();
 const cards=welcome.locator('.studio-agent-suggestion:enabled');await cards.nth(1).waitFor();
 await page.locator('#initialBrief').fill('保留我已输入的创作需求');const title=await cards.nth(1).locator('span').first().innerText();await cards.nth(1).click();
 assert.equal(await page.locator('#initialBrief').inputValue(),'保留我已输入的创作需求');assert((await page.locator('#entry-initialSkill').innerText()).includes(title));assert(await page.locator('#initialBrief').evaluate(e=>e===document.activeElement));
 await welcome.getByRole('button',{name:'查看全部 Skill →',exact:true}).click();await page.locator('#studioEntryPicker').waitFor({state:'visible'});await page.locator('#studioEntryPicker').getByRole('button',{name:'关闭',exact:true}).click();
 await page.getByRole('button',{name:'工作流',exact:true}).click();assert(!await welcome.isVisible());await page.getByRole('button',{name:'打开 Director',exact:true}).click();await welcome.waitFor();await page.getByRole('button',{name:'收起 Director',exact:true}).click();assert(!await welcome.isVisible());await page.getByRole('button',{name:'图片生成',exact:true}).first().click();assert(!await welcome.isVisible());assert.equal(await page.locator('body').getAttribute('data-creation-mode'),'image');
 await page.getByRole('button',{name:'故事板',exact:true}).click();await welcome.waitFor();assert.equal(await page.locator('#initialBrief').inputValue(),'保留我已输入的创作需求');
 await page.setViewportSize({width:390,height:844});await page.waitForTimeout(150);await cards.nth(1).click();
 const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth);assert(!overflow,'Entry must not overflow mobile viewport');
 if(process.env.TEST_SCREENSHOT)await page.screenshot({path:process.env.TEST_SCREENSHOT});
 assert.deepEqual(writes,[]);assert.deepEqual(errors,[]);console.log('PASS: real Skill choice preserves prompt, all-Skills picker, manual isolation, mobile fit, zero writes');
 }finally{for(const c of browser.contexts())for(const p of c.pages())await p.unrouteAll({behavior:'ignoreErrors'});await browser.close()}
})().catch(e=>{console.error(String(e.message).split('\n')[0]);process.exitCode=1});
