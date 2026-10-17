// Uses the live input preview/save API. No generation is authorized.
const {chromium}=require('playwright'),fs=require('fs'),assert=require('assert');
(async()=>{const browser=await chromium.launch({channel:'chromium',headless:true,args:['--no-sandbox']});try{
 const page=await browser.newPage({viewport:{width:1510,height:900}}),base=process.env.TEST_BASE_URL||'http://127.0.0.1:30080';
 const key=JSON.parse(fs.readFileSync(process.env.TEST_API_KEY_FILE)).api_key,headers={Authorization:'Bearer '+key};
 await page.addInitScript(k=>sessionStorage.setItem('h3_api_key',k),key);
 const response=await page.request.post(base+'/creative/api/projects',{headers,data:{message:'manual input duration fixture',creation_mode:'video',model:'kling-video-v4_0',duration:25,aspect:'16:9'}});assert(response.ok());const p=await response.json();
 let paid=0;await page.route('**/execute',r=>{paid++;return r.abort()});
 await page.goto(base+'/creative?project='+p.id+'&view=canvas');
 await page.locator('.studio-manual-image-compose textarea').fill('新的节点提示词');
 await page.getByLabel('视频生成时长',{exact:true}).selectOption('5');
 await page.getByRole('button',{name:'参考 / 编辑',exact:true}).click();await page.locator('#videoInputDialog').waitFor();
 await page.getByRole('button',{name:'关闭视频参考',exact:true}).click();
 const unchanged=await(await page.request.get(base+'/creative/api/projects/'+p.id,{headers})).json();assert.equal(unchanged.duration,25);assert.equal(unchanged.direct_prompt,p.direct_prompt);
 assert.equal(await page.getByLabel('视频生成时长',{exact:true}).inputValue(),'5');assert.equal(await page.locator('.studio-manual-image-compose textarea').inputValue(),'新的节点提示词');
 await page.getByRole('button',{name:'参考 / 编辑',exact:true}).click();
 await page.locator('#videoInputPreview').click();await page.locator('#videoInputSave').waitFor({state:'visible'});
 const summary=await page.locator('#videoInputReview').innerText();assert(summary.includes('5 秒 · 16:9'));assert(!summary.includes('15 秒'));assert(!summary.includes('保留现有方案'));
 assert.equal(await page.locator('#videoInputSave').innerText(),'保存输入 · 返回画布');await page.locator('#videoInputSave').click();await page.locator('#videoInputDialog').waitFor({state:'detached'});
 const saved=await(await page.request.get(base+'/creative/api/projects/'+p.id,{headers})).json();assert.equal(saved.duration,5);assert.equal(saved.direct_prompt,'新的节点提示词');assert.equal(saved.video_inputs.mode,'text');assert.equal(paid,0);
 assert((await page.locator('#toast').innerText()).includes('点击画布发送按钮'));
 console.log('PASS: manual draft input review and save retain selected duration/prompt without planning or generation');
}finally{await browser.close()}})().catch(e=>{console.error(String(e.message).split('\n')[0]);process.exitCode=1});
