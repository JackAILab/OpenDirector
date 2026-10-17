// Login UI checks use intercepted auth responses; no accounts or sessions are changed.
const {chromium}=require('playwright'),assert=require('assert');
(async()=>{const b=await chromium.launch({channel:'chromium',headless:true,args:['--no-sandbox']});try{const p=await b.newPage({viewport:{width:1440,height:1000}}),base='https://creative.jackailab.com',errors=[];p.on('pageerror',e=>errors.push(e.message));
await p.route('**/site/config',r=>r.fulfill({json:{registration:'email_verification'}}));
await p.goto(base+'/creative?new=1');await p.waitForSelector('.studio-login-link');assert.equal(await p.locator('#auth').isVisible(),false);await p.locator('.studio-login-link').click();await p.waitForURL('**/creative/login?*');await p.waitForSelector('#form');assert.equal(new URL(p.url()).searchParams.get('return_to'),'/creative?new=1');
await p.evaluate(()=>document.fonts.ready);await p.screenshot({path:'/tmp/visualagent-login.png'});
await p.route('**/auth/login',r=>r.fulfill({status:401,json:{detail:'Invalid credentials'}}));await p.locator('#email').fill('fixture@example.test');await p.locator('#password').fill('not-a-real-password');await p.locator('#submit').click();await p.getByText('邮箱或密码不正确。',{exact:true}).waitFor();
await p.locator('#register').click();assert(await p.locator('#confirm').isVisible());await p.locator('#verify').click();assert(await p.locator('#code').isVisible());assert.equal(await p.locator('#password').isVisible(),false);
await p.goto(base+'/creative/login?return_to=https%3A%2F%2Fevil.example');assert.equal(await p.locator('#back').getAttribute('href'),'/creative/discover');
await p.goto(base+'/creative/discover');await p.locator('#portalUser').click();await p.waitForURL('**/creative/login?*');assert.equal(await p.locator('dialog').count(),0);
assert.deepEqual(errors,[]);console.log('Guest canvas, top-right login, standalone page, return path, error and verification states: PASS');
}finally{await b.close()}})().catch(e=>{console.error(e);process.exitCode=1});
