// End-to-end routing acceptance. Every paid POST is intercepted, never sent.
const { chromium } = require('playwright');
const fs = require('fs');
const assert = require('assert');
const base = process.env.CREATIVE_TEST_URL || 'https://creative.jackailab.com';

async function run(mode) {
  const browser = await chromium.launch({channel:'chromium',headless:true,args:['--no-sandbox']});
  try {
    const page = await browser.newPage({viewport:{width:1440,height:1000}});
    const errors = [], calls = [];
    page.on('pageerror', e => errors.push(e.message));
    page.on('request', r => {
      if (r.method()==='POST' && r.url().endsWith('/message')) errors.push('Unexpected Agent message');
    });
    await page.request.post(base+'/site/access', {data:{password:fs.readFileSync('/opt/visualstation/creative-runtime/site-access-password.txt','utf8').trim()}});
    await page.addInitScript(key => {
      sessionStorage.setItem('h3_api_key',key);
      localStorage.setItem('creative-theme','dark');
      // A saved Agent draft must not hijack a new manual canvas.
      sessionStorage.setItem('creative_quick_prompt','An old Agent draft');
    }, JSON.parse(fs.readFileSync('/var/lib/visualstation-local/public-acceptance-account.json')).api_key);
    await page.route('**/creative/api/projects/*/budget',async route => {
      const response=await route.fetch(), data=await response.json();
      await route.fulfill({response,json:{...data,sufficient:true,remaining_credits:null}});
    });
    await page.route(/\/creative\/api\/projects\/[^/]+\/(images|execute)$/,route => {
      if(route.request().method()!=='POST') return route.continue();
      calls.push({url:route.request().url(),body:route.request().postDataJSON()});
      return route.fulfill({status:409,json:{detail:'验收拦截：未提交付费任务'}});
    });
    let releaseModels;const gate=new Promise(resolve=>releaseModels=resolve);
    const slowModels=async route=>{await gate;await route.continue()};
    await page.route('**/creative/api/models',slowModels);
    await page.goto(base+'/creative?new=1',{waitUntil:'domcontentloaded'});
    assert.equal(await page.locator('body').evaluate(el=>getComputedStyle(el).visibility),'hidden');
    releaseModels();
    await page.waitForFunction(()=>!document.getElementById('studioBoot'));
    await page.unroute('**/creative/api/models',slowModels);
    assert(await page.locator('.studio-canvas-welcome').isVisible());
    assert.equal(await page.locator('.director').isVisible(),false);
    await page.goto(base+'/creative?new=1&tool='+mode,{waitUntil:'domcontentloaded'});
    await page.waitForFunction(()=>document.querySelector('#entryImageModel')?.options.length>=4 && !document.getElementById('studioBoot'));
    const models=await page.locator(mode==='image'?'#entryImageModel':'#provider').evaluate(el=>[...el.options].filter(o=>!o.disabled&&o.value.startsWith('kling-')).map(o=>o.value));
    assert.equal(models.length,mode==='image'?4:7);
    for(const model of models) {
      await page.goto(base+'/creative?new=1&tool='+mode,{waitUntil:'domcontentloaded'});
      await page.waitForFunction(()=>document.querySelector('#entryImageModel')?.options.length>=4 && !document.getElementById('studioBoot'));
      if(mode==='image') {
        await page.locator('.studio-image-model-toggle').click();
        await page.locator('.studio-image-model-menu [data-model="'+model+'"]').click();
      } else {
        await page.locator('#provider').selectOption(model);
        const durations=await page.locator('#duration option').evaluateAll(os=>os.map(o=>o.value));
        await page.locator('#duration').selectOption(durations.at(-1));
      }
      await page.locator('#initialBrief').fill('猫咪和老虎在岩石上嬉闹，写实摄影，清晨柔光');
      const before=calls.length;
      await page.locator('#createButton').click();
      await page.waitForFunction(()=>document.querySelector('#toast')?.textContent.includes('验收拦截'),null,{timeout:30000});
      assert.equal(calls.length,before+1);
      assert.equal(await page.locator('dialog[open]').count(),0);
      assert.equal(await page.locator('.director').isVisible(),false);
      if(mode==='image') assert.equal(calls.at(-1).body.model,model);
      await page.reload();
      await page.waitForSelector('.studio-manual-image-compose:not([hidden])');
      assert.equal(await page.locator('.director').isVisible(),false);
      assert.equal(await page.locator('.studio-manual-image-compose select').first().inputValue(),model);
      console.log(mode,model,'one direct request, no Agent/dialog; reload isolated');
    }
    await page.screenshot({path:'/tmp/manual-direct-'+mode+'.png'});
    assert.deepEqual(errors,[]);
  } finally { await browser.close(); }
}
module.exports={run};
