// Read-only regression against an existing completed manual video. Never generates.
const {chromium}=require('playwright'),fs=require('fs'),assert=require('assert');
(async()=>{const browser=await chromium.launch({channel:'chromium',headless:true,args:['--no-sandbox']});try{
 const page=await browser.newPage({viewport:{width:1510,height:900}}),base=process.env.TEST_BASE_URL||'http://127.0.0.1:30080';
 const key=JSON.parse(fs.readFileSync(process.env.TEST_API_KEY_FILE)).api_key;
 assert(process.env.TEST_PROJECT_ID,'Set an owned completed manual video project');
 await page.addInitScript(k=>sessionStorage.setItem('h3_api_key',k),key);
 await page.route('**/creative/api/projects/*/execute',r=>r.abort());
 await page.goto(base+'/creative?project='+encodeURIComponent(process.env.TEST_PROJECT_ID)+'&view=canvas');
 await page.locator('.manual-primary-result').waitFor();
 await page.evaluate(()=>{window.completedFixture=structuredClone(project);project={...project,state:'running',artifact:null,result_asset:null,canvas:{nodes:[],edges:[]},revision:project.revision+1};draw()});
 await page.waitForTimeout(500);
 await page.evaluate(()=>{project={...window.completedFixture,revision:project.revision+1};draw()});
 await page.waitForTimeout(2500);
 const assertLayout=async()=>{const boxes=await page.evaluate(()=>{const r=document.querySelector('.manual-primary-result').getBoundingClientRect(),c=document.querySelector('.manual-root-node').getBoundingClientRect();return {resultBottom:r.bottom,composerTop:c.top}});assert(boxes.composerTop>=boxes.resultBottom+5,JSON.stringify(boxes));console.log('LAYOUT',boxes)};
 await assertLayout();
 const play=page.getByRole('button',{name:'播放视频',exact:true});if(await play.count())await play.click({force:true});
 await page.waitForTimeout(2000);await assertLayout();
 await page.evaluate(()=>document.querySelector('.manual-primary-result').style.height='430px');
 await page.waitForTimeout(300);await assertLayout();
 await page.evaluate(()=>document.querySelector('.manual-primary-result').style.removeProperty('height'));
 await page.waitForTimeout(300);await assertLayout();

}finally{await browser.close()}})().catch(e=>{console.error(String(e.message).split('\n')[0]);process.exitCode=1});
