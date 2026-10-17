const {chromium}=require('playwright');
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
(async()=>{
 const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
 try{
  const page=await browser.newPage({viewport:{width:390,height:844}}),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.addInitScript(()=>sessionStorage.setItem('h3_api_key','test-viewer'));
  let mode='gate',saves=0;
  const item={id:'a'.repeat(24),title:'声音叙事案例',source_url:'https://example.org/ad',
   review:{state:'pending',version:0,scores:{},tags:[],note:''}};
  await page.route('http://library.test/**',async route=>{
   const u=new URL(route.request().url());
   if(u.pathname==='/creative/library')return route.fulfill({contentType:'text/html',body:fs.readFileSync(path.join(__dirname,'../../tools/agent_studio/library.html'),'utf8')});
   if(u.pathname.endsWith('.woff2'))return route.fulfill({status:404});
   if(u.pathname==='/site/access'){mode='busy';return route.fulfill({json:{ok:true}})}
   if(u.pathname==='/creative/api/library'){
    if(mode==='gate')return route.fulfill({status:403,json:{detail:'site access required'}});
    if(mode==='busy')return route.fulfill({status:503,json:{detail:'资料库正在更新，请稍后重新加载。'}});
    if(mode==='html')return route.fulfill({status:502,contentType:'text/html',body:'<h1>private upstream detail</h1>'});
    return route.fulfill({json:{total:1,items:[item],facets:{industry:[],ad_type:[]}}});
   }
   if(u.pathname.endsWith('/status'))return route.fulfill({json:{total:1,playable:0,review_queue:{state:'ready',total_pending:0}}});
   if(u.pathname.endsWith('/review')){
    saves++;
    if(saves===1)return route.fulfill({status:503,json:{detail:'资料库正忙，本次标注未保存。填写内容仍在当前页面，请稍后再保存。'}});
    const submitted=route.request().postDataJSON();
    assert.equal(submitted.note,'我喜欢第 8 秒开始的声音反转');
    assert.equal(submitted.version,0);assert.equal(submitted.state,'selected');
    item.review={...submitted,version:1};return route.fulfill({json:item});
   }
   if(u.pathname.endsWith('/analysis'))return route.fulfill({json:{state:'pending',analysis:null}});
   throw Error('Unexpected endpoint '+u.pathname);
  });
  await page.goto('http://library.test/creative/library');
  await page.locator('#gate').waitFor();assert(await page.locator('#loadFailure').isHidden());
  await page.locator('#password').fill('example');await page.locator('#gate button').click();
  await page.locator('#loadFailure').waitFor();
  assert.match(await page.locator('#loadFailureMessage').textContent(),/正在更新/);
  assert(await page.locator('#app').isHidden());
  assert.equal(saves,0);
  mode='html';await page.locator('#retryLoad').click();
  await page.waitForFunction(()=>document.querySelector('#loadFailureMessage').textContent.includes('服务暂时'));
  assert(!await page.locator('body').textContent().then(t=>t.includes('private upstream')));
  mode='ready';await page.locator('#retryLoad').click();await page.locator('.card').waitFor();
  assert(await page.locator('#loadFailure').isHidden());assert(await page.locator('#gate').isHidden());
  await page.locator('.card').click();await page.locator('#inspector textarea').fill('我喜欢第 8 秒开始的声音反转');
  await page.locator('.choices button').filter({hasText:'我的精选'}).click();
  const save=page.getByRole('button',{name:'保存我的标注',exact:true});
  await save.click();await page.waitForFunction(()=>document.querySelector('#inspector .error')?.textContent.includes('未保存'));
  assert.equal(saves,1);assert.equal(await page.locator('#inspector textarea').inputValue(),'我喜欢第 8 秒开始的声音反转');
  assert.equal(await page.locator('.choices .chosen').textContent(),'我的精选');
  assert(await save.isEnabled());
  await save.click();await page.waitForFunction(()=>document.querySelector('#notice').textContent.includes('标注已保存'));
  assert.equal(saves,2);assert.equal(item.review.version,1);
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  assert.deepEqual(errors,[]);
  console.log('PASS gate → busy → manual recovery, safe server errors, retained draft, explicit save retry, mobile');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
