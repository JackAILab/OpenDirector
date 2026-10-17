// Navigation and sharing never write a reference review. All data are synthetic.
const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
(async()=>{
 const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
 try{
  const context=await browser.newContext({viewport:{width:1440,height:1000}}),page=await context.newPage();
  const ids=['1'.repeat(24),'2'.repeat(24),'3'.repeat(24)],errors=[],reads=[],writes=[];
  const item=id=>({id,title:'案例 '+id[0],source_name:'官方来源',source_url:'https://example.org/'+id,media_status:'source_link',review:{state:'pending',scores:{},tags:[],note:'',version:0}});
  let gated=false,held=null,holdIdentity=null;
  page.on('pageerror',e=>errors.push(e.message));
  await page.addInitScript(()=>{
   sessionStorage.setItem('h3_api_key','fixture');
   Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:async text=>{window.copiedCaseLink=text}}});
  });
  await page.route('http://library.test/**',route=>{
   const request=route.request(),u=new URL(request.url());
   if(request.method()!=='GET'){
    writes.push(u.pathname);assert.equal(u.pathname,'/site/access');gated=false;return route.fulfill({json:{ok:true}});
   }
   if(u.pathname==='/creative/library')return route.fulfill({contentType:'text/html',body:fs.readFileSync(path.join(__dirname,'../../tools/agent_studio/library.html'),'utf8')});
   if(u.pathname.endsWith('.woff2'))return route.fulfill({status:404});
   if(gated)return route.fulfill({status:403,json:{detail:'site access required'}});
   if(u.pathname.endsWith('/status'))return route.fulfill({json:{total:3,can_review:true}});
   if(u.pathname==='/creative/api/library')return route.fulfill({json:{total:2,items:[item(ids[0]),item(ids[2])],facets:{industry:[],ad_type:[]}}});
   const id=u.pathname.split('/').pop();reads.push(id);
   if(id===holdIdentity){held=route;return;}
   return route.fulfill(ids.includes(id)?{json:item(id)}:{status:404,json:{detail:'参考案例不存在'}});
  });
  const openTitle=async id=>{await page.waitForFunction(title=>document.querySelector('#screen h2')?.textContent===title,'案例 '+id[0]);};
  // A shared target need not be on the current page. Unknown query data are stripped.
  await page.goto('http://library.test/creative/library?item='+ids[1]+'&private_note=fixture');await openTitle(ids[1]);
  assert.equal(new URL(page.url()).search,'?item='+ids[1]);
  await page.getByRole('button',{name:'复制案例链接',exact:true}).click();
  assert.equal(await page.evaluate(()=>window.copiedCaseLink),'http://library.test/creative/library?item='+ids[1]);
  await page.reload();await openTitle(ids[1]);
  // Unsaved edits must keep the current link when leaving is canceled.
  await page.locator('.choices button').nth(1).click();
  page.once('dialog',dialog=>dialog.dismiss());await page.getByRole('button',{name:'← 返回案例列表'}).click();
  assert.equal(new URL(page.url()).search,'?item='+ids[1]);assert(await page.locator('#screen').isVisible());
  page.once('dialog',dialog=>dialog.accept());await page.getByRole('button',{name:'← 返回案例列表'}).click();
  assert.equal(new URL(page.url()).search,'');assert(await page.locator('#screen').isHidden());
  await page.locator('.card').first().click();await openTitle(ids[0]);
  await page.getByRole('button',{name:'暂时跳过',exact:true}).click();await openTitle(ids[2]);
  assert.equal(new URL(page.url()).search,'?item='+ids[2]);
  // Clipboard denial has a selectable text fallback, including on mobile.
  await page.evaluate(()=>{navigator.clipboard.writeText=async()=>{throw Error('denied')}});
  await page.setViewportSize({width:390,height:844});await page.getByRole('button',{name:'复制案例链接',exact:true}).click();
  assert.equal(await page.getByRole('textbox',{name:'案例链接',exact:true}).inputValue(),'http://library.test/creative/library?item='+ids[2]);
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  // A delayed clipboard error belongs to the clicked case, not the next player.
  await page.evaluate(()=>{navigator.clipboard.writeText=()=>new Promise((resolve,reject)=>{window.rejectShare=reject})});
  await page.locator('.copy-case-link').click();await page.getByRole('button',{name:'暂时跳过',exact:true}).click();await openTitle(ids[0]);
  await page.evaluate(()=>window.rejectShare(Error('denied')));await page.waitForTimeout(100);
  assert.equal(await page.locator('.case-share-url').count(),0);
  await page.reload();await openTitle(ids[0]);
  assert(await page.locator('#screen').evaluate(screen=>screen.getBoundingClientRect().top<100));
  // Invalid identifiers do not become API paths; missing cases leave browsing usable.
  const before=reads.length;await page.goto('http://library.test/creative/library?item=..%2Fsecret');
  await page.waitForFunction(()=>document.querySelector('#notice').textContent.includes('案例链接无效'));
  assert.equal(reads.length,before);assert(await page.locator('.card').first().isVisible());
  await page.goto('http://library.test/creative/library?item='+'f'.repeat(24));
  await page.waitForFunction(()=>document.querySelector('#notice').textContent.includes('参考案例不存在'));
  assert(await page.locator('.card').first().isVisible());
  // A late deep-link response must not replace a case the viewer selected meanwhile.
  holdIdentity=ids[1];await page.goto('http://library.test/creative/library?item='+ids[1]);
  await page.locator('.card').first().waitFor();
  for(let n=0;!held&&n<100;n++)await page.waitForTimeout(20);assert(held);
  await page.locator('.card').first().click();await openTitle(ids[0]);
  const response=page.waitForResponse(r=>new URL(r.url()).pathname.endsWith('/'+ids[1]));
  holdIdentity=null;await held.fulfill({json:item(ids[1])});await response;await page.waitForTimeout(100);
  assert.equal(await page.locator('#screen h2').textContent(),'案例 1');assert.equal(new URL(page.url()).search,'?item='+ids[0]);
  // A password challenge retains the requested case until access is granted.
  gated=true;await page.goto('http://library.test/creative/library?item='+ids[1]);
  await page.locator('#gate').waitFor();await page.locator('#password').fill('fixture');await page.locator('#gate button').click();await openTitle(ids[1]);
  assert.deepEqual(writes,['/site/access']);assert.deepEqual(errors,[]);
  console.log('PASS: case links, refresh, clean sharing, unsaved edits, next case, mobile clipboard fallback, invalid/missing links, response race, password gate; zero review writes');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
