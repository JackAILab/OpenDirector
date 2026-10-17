const {clickEditorControl}=require('./editor_controls.cjs');
// EDIT_RETAKE_FIXTURE=1 EDIT_ACCEPTANCE_PORT=30133 python3 tests/browser/edit_suggestions_server.py
// Full-film review is deterministic and uses no paid or semantic model call.
const {chromium}=require('playwright'),assert=require('assert/strict');
(async()=>{const b=await chromium.launch({headless:true,args:['--no-sandbox']});try{
 const origin='http://127.0.0.1:30133',p=await b.newPage({viewport:{width:1512,height:982}}),headers={Authorization:'Bearer fixture'};
 const identity=await(await p.request.get(origin+'/acceptance/identity')).json();assert.equal(identity.fixture,'edit-retake-fixed-provider');await p.addInitScript(()=>sessionStorage.setItem('h3_api_key','fixture'));
 const project=await(await p.request.post(origin+'/creative/api/projects',{headers,data:{message:'全片审阅验收',duration:15}})).json();const api=origin+'/creative/api/projects/'+project.id+'/edit';
 await p.goto(origin+'/creative/editor?project='+project.id);await p.waitForFunction(()=>document.getElementById('status').textContent.includes('项目已载入'));
 await p.locator('#creativeContract > summary').click();assert.match(await p.locator('#creativeContractMeta').textContent(),/商品广告导演.*手动审批/);assert.notEqual(await p.locator('#creativeContractInputs').textContent(),'—');assert.match(await p.locator('#creativeContractMapping').textContent(),/待核对/);
 const trackMap=await p.locator('#creativeContractTracks').textContent();assert.match(trackMap,/Skill 节奏/);assert.match(trackMap,/画面轨/);assert.match(trackMap,/字幕轨/);assert.match(trackMap,/声音轨/);assert.match(trackMap,/待加入画面/);assert.match(await p.locator('#creativeContractTrackNote').textContent(),/状态随草稿刷新/);assert.match(await p.locator('#creativeContractMapping').textContent(),/不自动改写/);assert((await p.locator('#creativeTrackPlanRows .creative-track-plan-row').count())>0);assert.match(await p.locator('#creativeTrackPlanSummary').textContent(),/画面/);
 assert((await p.getByRole('button',{name:'定位节拍',exact:true}).count())>0);
 assert.equal(await p.locator('#creativeSkillImpactOpenSettings').textContent(),'回创作设置确认版本');
 await p.locator('#uploadVideo').click();await p.locator('#file').setInputFiles(identity.fixtures+'/red.mp4');await p.waitForFunction(()=>document.getElementById('status').textContent.includes('素材已导入'),{},{timeout:60000});await p.getByText('＋ 画面',{exact:true}).click();await p.getByRole('button',{name:'加入 Skill 节奏轨',exact:true}).click();assert(await p.locator('#tracks .skill-rhythm').count()>0);assert.match(await p.locator('#skillRhythmStatus').textContent(),/可在时间轴拖动调整/);assert.match(await p.locator('#creativeTrackPlanSummary').textContent(),/画面/);await clickEditorControl(p,'save');await p.waitForFunction(()=>document.getElementById('status').textContent==='剪辑已保存');
 assert.match(await p.locator('#creativeContractTracks').textContent(),/画面轨[\s\S]*1 段画面/);
 await clickEditorControl(p,'review');await p.waitForFunction(()=>document.getElementById('reviewSummary').textContent.includes('技术核对'));assert((await p.locator('#reviewTechnical').textContent()).includes('音轨'));
 assert((await p.locator('#reviewContent').textContent()).includes('商品外观与一致性'));await p.locator('.review-window').first().click();assert((await p.locator('#reviewStatus').textContent()).includes('已定位'));
 await p.locator('#reviewDecision').selectOption('needs_changes');await p.locator('#saveReview').click();await p.waitForFunction(()=>document.getElementById('reviewStatus').textContent.includes('已保存'));
 await p.locator('#reviewWatched').check();await p.locator('#reviewHeard').check();await p.locator('#reviewFacts').check();await p.locator('#reviewDecision').selectOption('approved');await p.locator('#saveReview').click();await p.waitForFunction(()=>document.getElementById('reviewStatus').textContent.includes('training_eligible'));
 assert.equal(await p.locator('#requestIndependentReview').isDisabled(),true);assert((await p.locator('#independentReviewStatus').textContent()).includes('导出'));
 const saved=(await(await p.request.get(api+'/review',{headers})).json()).saved;assert.equal(saved.decision,'approved');assert.equal(saved.semantic,'pending');assert.equal(saved.training_eligible,false);
 await p.setViewportSize({width:390,height:844});assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);await p.screenshot({path:'/tmp/edit-review-mobile.png'});
 console.log('PASS: technical packet, explicit human checklist, needs_changes→approved history, semantic pending, training false, mobile layout');
}finally{await b.close()}})().catch(e=>{console.error(e);process.exit(1)});
