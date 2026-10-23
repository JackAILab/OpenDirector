/* Compact, reference-first workspace; selections are server-validated. */
(()=>{
 Object.assign(events,{model_changed:'视频模型已切换，请重新规划',image_requested:'已确认参考图生成',image_completed:'参考图已加入画布',image_reframed:'裁剪版本已加入画布',image_needs_review:'图片结果待核对，未自动重试',canvas_inputs_changed:'参考内容已更新，请重新规划',canvas_layout_saved:'画布布局已保存',canvas_asset_uploaded:'参考素材已上传',scene_render_intent_confirmed:'3D 渲染准备已确认，可继续核对生成'});
 const make=(tag,text,cls)=>{const e=document.createElement(tag);if(text)e.textContent=text;if(cls)e.className=cls;return e};
 const action=(text,fn)=>{const b=make('button',text);b.type='button';b.onclick=fn;return b};
 const bar=document.querySelector('.projectbar');if(!bar)return;bar.classList.add('compact');
 const filmDialog=make('dialog');filmDialog.id='filmPromptDialog';
 const filmMeta=make('p',null,'muted'),filmBrief=make('section',null,'film-review-brief'),filmBeats=make('div');filmBeats.id='filmReviewBeats';
 filmBrief.setAttribute('aria-label','广告方向与待确认信息');
 const filmText=make('textarea');filmText.readOnly=true;filmText.rows=12;filmText.setAttribute('aria-label','一次提交的完整提示词');
 const rawPrompt=make('details'),rawLabel=make('summary','查看实际提交的完整提示词');rawPrompt.append(rawLabel,filmText);
 const filmActions=make('div',null,'row');filmActions.append(action('复制整片提示词',async()=>{try{await navigator.clipboard.writeText(filmText.value);toast('已复制实际提交的完整提示词')}catch(e){rawPrompt.open=true;filmText.focus();filmText.select();toast('请复制已选中的整片提示词')}}),action('关闭',()=>filmDialog.close()));
 filmDialog.append(make('h2','整片拍摄方案'),filmMeta,filmBrief,make('p','逐段审阅画面、声音和旁白。全部时码作为一次请求生成完整音视频；字幕后期叠加。实际节奏、商品外观和发音仍需审阅。'),filmBeats,rawPrompt,filmActions);document.body.append(filmDialog);
 function openFilmReview(event){
  const requestedShot=event?.detail?.shot;
  const chaptered=project?.generation_mode==='chaptered_native';rawLabel.textContent=chaptered?'查看完整分章拍摄方案':'查看实际提交的完整提示词';
  filmDialog.querySelector(':scope > p:not(.muted)')?.replaceChildren(document.createTextNode(chaptered?'每15秒生成一章；Agent 自动绑定商品与上一章衔接图，再保留音轨剪辑和叠加字幕。实际外观、转场和声音仍需审阅。':'逐段审阅画面、声音和旁白。全部时码作为一次请求生成完整音视频；字幕后期叠加。实际节奏、商品外观和发音仍需审阅。'));
  if(hasDrafts()){toast('请先保存分镜修改，确保提示词与当前版本一致');return}
  filmText.value=project?.production_prompt||'先请导演生成广告方案。';
  filmMeta.textContent=project?`版本 ${project.revision} · ${project.duration} 秒 · ${project.quote?.label||project.model} · ${project.generation_mode==='chaptered_native'?project.duration/15+' 次章节生成与自动剪辑':'1 次整片生成'}`:'尚未形成拍摄方案';
  filmBrief.replaceChildren(make('h3','这支广告要表达什么'));
  const facts=make('dl');
  for(const [key,label] of [['product','商品'],['audience','受众'],['message','核心主张'],['style','拍摄方向'],['cta','行动号召']])facts.append(make('dt',label),make('dd',project?.brief?.[key]||'待补充'));
  filmBrief.append(facts);
  const pending=[...(project?.questions||[]).map(q=>q.question),...(project?.assumptions||[])];
  if(pending.length){
   const assumptions=make('details',null,'film-review-pending');assumptions.open=true;
   assumptions.append(make('summary',`待核对的问题与假设 · ${pending.length} 项`));
   const list=make('ul');for(const value of pending)list.append(make('li',value));assumptions.append(list);
   assumptions.append(action('补充信息给导演',()=>{filmDialog.close();$('message').focus();$('message').scrollIntoView({block:'center'});toast('补充或纠正这些信息，再请导演更新方案')}));filmBrief.append(assumptions);
  }
  filmBeats.replaceChildren();
  for(const [i,s] of (project?.shots||[]).entries()){
   const beat=make('details',null,'film-review-beat');beat.dataset.shot=s.id;beat.open=requestedShot?s.id===requestedShot:i===0;
   beat.append(make('summary',`${s.start}–${s.start+s.duration}s · ${s.title}`));
   for(const [label,value] of [['画面与拍摄',s.prompt],['音乐、音效与旁白',s.audio_prompt],['后期字幕',s.caption||'无字幕'],['创作依据',s.rationale]])beat.append(make('h3',label),make('p',value||'待补充'));
   beat.append(action('修改这段画面与声音',()=>{filmDialog.close();selected=i;document.body.classList.remove('inspector-folded');syncLayout();drawSelection();drawEditor();document.querySelector('.inspector').scrollTop=0;$('shotPrompt').focus()}));filmBeats.append(beat);
  }
  filmDialog.showModal();
  if(requestedShot)requestAnimationFrame(()=>Array.from(filmBeats.children).find(n=>n.dataset.shot===requestedShot)?.scrollIntoView({block:'start'}));
 }
 document.addEventListener('creative-open-film-review',openFilmReview);
 const filmReviewButton=action('整片拍摄方案',openFilmReview);bar.append(filmReviewButton);
 const sceneIntentDialog=make('dialog');sceneIntentDialog.id='sceneIntentDialog';const sceneIntentMeta=make('p',null,'scene-intent-meta'),sceneIntentBody=make('div',null,'scene-intent-body');const sceneIntentActions=make('div',null,'row');const sceneIntentContinue=action('进入生成确认',()=>{sceneIntentDialog.close();document.querySelector('#executeButton')?.click()}),sceneIntentClose=action('稍后确认',()=>sceneIntentDialog.close());sceneIntentContinue.className='primary';sceneIntentActions.append(sceneIntentClose,sceneIntentContinue);sceneIntentDialog.append(make('h2','3D 场景已接入导演画布'),sceneIntentMeta,sceneIntentBody,make('p','场景版本已冻结到本次上下文。生成前仍会重新展示 Skill、视频模型、审批方式和平台积分，由你完成最终确认。'),sceneIntentActions);document.body.append(sceneIntentDialog);
 const sceneIntentButton=action('3D 渲染已核对 · 继续确认',()=>{const i=project?.scene_render_intent;if(!i)return;const lock=i.trajectory_sha256?` · 轨迹锁 ${i.trajectory_sha256.slice(0,12)}`:'';sceneIntentMeta.textContent=`场景修订 ${i.scene_revision} · ${i.scene_hash.slice(0,12)}${lock} · ${i.aspect}`;sceneIntentBody.replaceChildren(make('p',`模型：${i.model}`),make('p',`审批：${i.approval_mode==='auto'?'自动审批':'手动审批'}`),make('p',i.trajectory_sha256?'镜头轨迹已随场景版本冻结。':'旧版本场景未记录轨迹锁，重新保存 3D 场景后可补齐。'),make('p','状态：只保存了渲染意图，尚未提交视频生成。'));sceneIntentDialog.showModal()});sceneIntentButton.id='sceneRenderIntent';sceneIntentButton.className='scene-render-intent';sceneIntentButton.hidden=true;bar.append(sceneIntentButton);
 const sceneReviewButton=action('成片回放核对 ↗',()=>{if(project)location.href='/creative/scene?project='+encodeURIComponent(project.id)+'&review=1'});sceneReviewButton.id='sceneRenderReview';sceneReviewButton.className='scene-render-review';sceneReviewButton.hidden=true;bar.append(sceneReviewButton);
 const projectDetailsButton=action('详情',()=>bar.classList.toggle('compact'));bar.append(projectDetailsButton);
 const inspectorButton=action('展开简报',()=>{document.body.classList.toggle('inspector-folded');localStorage.setItem('studio-inspector',document.body.classList.contains('inspector-folded')?'closed':'open');syncLayout()});bar.append(inspectorButton);
 document.body.classList.toggle('inspector-folded',localStorage.getItem('studio-inspector')!=='open');
 const brief=$('brief'),heading=brief.previousElementSibling,details=make('details'),summary=make('summary','创作简报');heading.replaceWith(details);details.append(summary,brief);
 const workspaceParams=new URLSearchParams(location.search),returnedSceneShot=(workspaceParams.get('scene_shot')||'').slice(0,80),returnedSceneAt=Number(workspaceParams.get('scene_at')),openSettingsRequested=workspaceParams.get('open_settings')==='1';
 const expanded=workspaceParams.get('view')!=='studio';document.body.classList.toggle('canvas-expanded',expanded);
 const canvasToolbar=document.querySelector('.canvas-toolbar');const openCanvas=action(expanded?'返回工作室':'独立画布 ↗',()=>{if(!project){toast('请先创建项目');return}if(hasDrafts()){toast('请先保存或放弃草稿，再打开独立画布');return}const u='/creative?project='+project.id+(expanded?'&view=studio':'&view=canvas');if(expanded)location.href=u;else window.open(u,'visualagent-canvas-'+project.id)});document.querySelector('.canvas-view-actions')?.append(openCanvas);
 let inlineSession=null;
 const inlineEditDialog=make('dialog',null,'inline-editor-dialog');inlineEditDialog.id='inlineEditorDialog';
 const inlineEditHead=make('div',null,'inline-editor-head'),inlineEditTitle=make('strong','智能剪辑 · 当前项目'),inlineEditActions=make('div',null,'inline-editor-actions');
 const inlineEditFrame=document.createElement('iframe');inlineEditFrame.id='inlineEditorFrame';inlineEditFrame.title='内嵌智能剪辑时间轴';inlineEditFrame.loading='lazy';inlineEditFrame.allowFullscreen=true;
 const editorBridge=()=>{try{return inlineEditFrame.contentWindow?.visualagentInlineEditor}catch{return null}};
 const syncInlineButton=()=>{inlineEdit.textContent=inlineSession?'继续剪辑':'智能剪辑';inlineEdit.classList.toggle('has-session',!!inlineSession);inlineEdit.title=inlineSession?'继续 '+inlineSession.title+' · 当前页面保留草稿与位置':'在当前画布上打开时间轴、字幕、音频和导出工作区'};
 const finishInlineEditor=()=>{const closedProject=inlineSession?.pid;inlineSession=null;inlineEditFrame.src='about:blank';inlineEditDialog.close();syncInlineButton();if(project?.id===closedProject)refreshProjectStatus().then(()=>draw()).catch(()=>toast('剪辑已关闭，项目状态暂未同步'))};
 const requestInlineClose=()=>{const bridge=editorBridge();if(bridge){if(bridge.requestClose()===false)inlineEditTitle.textContent='剪辑任务处理中 · 可先收起回画布，完成后再关闭'}else finishInlineEditor()};
 const suspendInlineEditor=()=>{editorBridge()?.suspend();inlineEditDialog.close();syncInlineButton();inlineEdit.focus();toast('剪辑已收起，草稿保留在当前页面；点击「继续剪辑」返回')};
 const inlineEditMinimize=action('收起',suspendInlineEditor);inlineEditMinimize.setAttribute('aria-label','收起剪辑回到画布');
 const inlineEditClose=action('关闭',requestInlineClose);inlineEditClose.setAttribute('aria-label','关闭内嵌剪辑');inlineEditActions.append(inlineEditMinimize,inlineEditClose);inlineEditHead.append(inlineEditTitle,inlineEditActions);inlineEditDialog.append(inlineEditHead,inlineEditFrame);document.body.append(inlineEditDialog);
 inlineEditDialog.addEventListener('cancel',event=>{event.preventDefault();requestInlineClose()});
 const openInlineEditor=(options={})=>{
  const sourceTime=typeof options.sourceTime==='number'&&Number.isFinite(options.sourceTime)&&options.sourceTime>=0&&options.sourceTime<=7200?options.sourceTime:undefined;
  if(inlineSession){inlineEditDialog.showModal();if(options.source&&inlineSession.pid===project?.id){const source=String(options.source).slice(0,80),tool=['retake','speech','assistant','trim','audio'].includes(options.tool)?options.tool:null,bridge=editorBridge();if(bridge?.state().ready){(tool?bridge.openTool(tool,source):bridge.focusSource(source,sourceTime))?.catch(()=>toast('素材暂不可定位，当前剪辑已保留'))}else inlineSession.pending={source,tool,sourceTime}} if(inlineSession.pid!==project?.id)toast('先完成或关闭 '+inlineSession.title+' 的剪辑，再打开当前项目');return true}
  if(!project){toast('请先创建项目');return false}if(busy){toast('当前制作任务处理中，请稍候');return false}if(hasDrafts()){toast('请先保存或放弃草稿，再打开内嵌剪辑');return false}
  const query=new URLSearchParams({project:project.id,embedded:'1'});if(options.source)query.set('source',String(options.source).slice(0,80));if(sourceTime!==undefined)query.set('source_at',String(sourceTime));if(['retake','speech','assistant','trim','audio'].includes(options.tool))query.set('tool',options.tool);if(options.canvasAsset)query.set('canvas_asset',String(options.canvasAsset).slice(0,80));inlineSession={pid:project.id,title:project.brief?.product||'当前项目'};inlineEditTitle.textContent='智能剪辑 · '+inlineSession.title;inlineEditFrame.src='/creative/editor?'+query.toString();syncInlineButton();inlineEditDialog.showModal();return true;
 };
 const inlineEdit=action('智能剪辑',()=>openInlineEditor());inlineEdit.id='inlineEditButton';inlineEdit.className='canvas-inline-edit-button';inlineEdit.setAttribute('aria-label','打开内嵌剪辑');syncInlineButton();if(canvasToolbar)canvasToolbar.append(inlineEdit);
 document.addEventListener('creative-open-inline-edit',event=>{openInlineEditor(event.detail||{})});
 window.addEventListener('message',event=>{
  const data=event.data||{};if(event.origin!==location.origin||event.source!==inlineEditFrame.contentWindow||data.project!==inlineSession?.pid)return;
  if(data.kind==='visualagent-inline-editor-ready'){const pending=inlineSession.pending;delete inlineSession.pending;if(pending){const bridge=editorBridge();(pending.tool?bridge?.openTool(pending.tool,pending.source):bridge?.focusSource(pending.source,pending.sourceTime))?.catch(()=>toast('素材暂不可定位，当前剪辑已保留'))}return}
  if(data.kind==='visualagent-close-inline-editor'){if(editorBridge()?.state().dirty){requestInlineClose();return}finishInlineEditor();return}
  if(data.kind==='visualagent-inline-timeline'){
   if(Number.isFinite(Number(data.at)))inlineEditTitle.textContent=`智能剪辑 · 游标 ${Number(data.at).toFixed(2)}s · ${inlineSession.title}`;
   if(data.project===project?.id)document.dispatchEvent(new CustomEvent('creative-inline-timeline',{detail:data}));
  }
 });
 const smartEdit=action('独立剪辑 ↗',()=>{if(!project){toast('请先创建项目');return}if(busy){toast('当前制作任务处理中，请稍候');return}if(hasDrafts()){toast('请先保存或放弃草稿，再进入智能剪辑');return}location.href='/creative/editor?project='+encodeURIComponent(project.id)});smartEdit.id='canvasEditButton';smartEdit.className='canvas-edit-button';smartEdit.setAttribute('aria-label','打开智能剪辑');smartEdit.title='进入字幕、重拍、转场、音频和全片审阅';document.querySelector('.canvas-view-actions')?.append(smartEdit);
 const canvasModeButton=action(expanded?'退出全屏':'全屏画布',()=>openCanvas.click());canvasModeButton.className='canvas-mode-button';bar.append(canvasModeButton);
 // PenStudio keeps the creation destinations reachable while the canvas is open.
 // Keep this rail additive: it never owns project state or generation requests.
 const launchRail=make('aside',null,'canvas-launch-rail');launchRail.setAttribute('aria-label','创作入口');
 const launchRailToggle=action('展开创作入口',()=>{const expanded=launchRail.classList.toggle('is-expanded');launchRailToggle.textContent=expanded?'收起创作入口':'展开创作入口';launchRailToggle.setAttribute('aria-expanded',String(expanded));launchRailToggle.dataset.icon=expanded?'‹':'›';});launchRailToggle.type='button';launchRailToggle.className='canvas-launch-toggle';launchRailToggle.dataset.icon='›';launchRailToggle.setAttribute('aria-expanded','false');launchRailToggle.title='展开创作入口';launchRail.append(launchRailToggle);
 const homeLink=document.createElement('a');homeLink.href='/creative/discover';homeLink.textContent='首页';homeLink.dataset.icon='⌂';homeLink.className='canvas-launch-home';homeLink.title='首页';launchRail.append(homeLink);
 const launchTitle=make('div','创作入口','canvas-launch-title');launchRail.append(launchTitle);
 const tool=(label,target,icon)=>{const b=action(label,()=>document.getElementById(target)?.click());b.className='canvas-launch-tool';b.dataset.icon=icon;b.title=label;b.setAttribute('aria-label',label);return b};
 // Keep the canvas navigation and the compact bottom dock in sync. These are
 // proxies rather than duplicate stateful controls, so selecting a tool in
 // either place updates the same canvas mode.
 launchRail.append(tool('选择素材','canvasSelectTool','↖'),tool('平移画布','canvasHandTool','✋'));
 const nodeLimitReached=()=>Array.isArray(project?.manual_nodes)&&project.manual_nodes.length>=15;
 const launch=(label,description,fn,disabled=false,icon='•')=>{const b=action(label,()=>{if(!disabled&&nodeLimitReached()&&['视频生成','图片生成'].includes(label)){toast('当前画布已达到 16 个生成节点上限，请新建画布继续创作');return}fn()});b.className='canvas-launch-action';b.dataset.icon=icon;b.disabled=disabled;b.title=disabled?description:label;b.append(make('small',description));return b};
 launchRail.append(
   launch('新建项目','从 Director 开始一段新创作',()=>document.getElementById('newButton')?.click(),false,'＋'),
   // Route the rail through the same node-creation handlers as the canvas
   // dock. Opening the generic add menu here used to make these two entries
   // look clickable while doing nothing until a second click.
   launch('视频生成','在当前项目中打开视频创作设置',()=>{
    const direct=document.querySelector('[data-manual-add="video"]');
    if(direct){direct.click();return}
    document.querySelector('#canvasAddMenu summary')?.click();
   },false,'▣'),
   launch('图片生成','打开画布添加菜单中的图片入口',()=>{
    const direct=document.querySelector('[data-manual-add="image"]');
    if(direct){direct.click();return}
    document.querySelector('#canvasAddMenu summary')?.click();
   },false,'▧'),
   launch('音频生成','音频模型尚未接入当前项目',()=>{},true,'◒'),
   launch('剧本生成','剧本 Skill 尚未接入当前项目',()=>{},true,'T'),
   launch('智能剪辑','在当前画布打开多轨剪辑',()=>inlineEdit.click(),false,'✂'),
   launch('3D-BOX','布置场景、灯光与镜头轨迹',()=>{if(!project){toast('请先创建项目');return}if(busy){toast('当前制作任务处理中，请稍候');return}if(hasDrafts()){toast('请先保存或放弃草稿，再进入 3D-BOX');return}location.href='/creative/scene?'+new URLSearchParams({project:project.id,return_view:'canvas'})},false,'◇')
 );
 document.body.append(launchRail);
 const creativeStatus=action('创作配置 · 尚未载入',()=>{const panel=document.querySelector('.creative-settings');if(!panel){toast('创作设置尚在载入，请稍候');return}document.body.classList.remove('chat-collapsed');const toggle=document.querySelector('#chatToggle');if(toggle){toggle.textContent='收起对话';toggle.setAttribute('aria-expanded','true')}panel.open=true;panel.scrollIntoView({block:'nearest'});});creativeStatus.id='creativeStatusButton';creativeStatus.className='creative-status-chip';creativeStatus.setAttribute('aria-label','打开创作设置');bar.append(creativeStatus);if(openSettingsRequested)setTimeout(()=>creativeStatus.click(),0);
 const productionTask=make('details',null,'production-task-card');productionTask.setAttribute('aria-label','制作任务状态');productionTask.open=false;productionTask.id='productionTask';
 const taskSummary=make('summary',null,'production-task-summary'),taskKicker=make('span','制作任务','production-task-kicker'),taskTitle=make('strong','等待任务','production-task-title'),taskProgress=make('span','','production-task-progress');taskSummary.append(taskKicker,taskTitle,taskProgress);
 const taskBody=make('div',null,'production-task-body'),taskContext=make('div',null,'production-task-context'),taskDetail=make('p','','production-task-detail'),taskRecovery=make('ul',null,'production-task-recovery'),taskAudit=make('ul',null,'production-task-audit'),taskObservations=make('details',null,'production-task-observations'),observationSummary=make('summary','创作观察'),observationList=make('ul'),taskSceneReview=make('details',null,'production-scene-review'),sceneReviewSummary=make('summary','镜头级核对'),sceneReviewList=make('ul'),taskImageHistory=make('details',null,'production-task-image-history'),imageHistorySummary=make('summary','图像处理记录'),imageHistoryList=make('ul');
 const layoutDialog=make('dialog',null,'layout-observation-dialog');layoutDialog.id='layoutObservationDialog';const layoutObservationBody=make('div');layoutDialog.append(make('h2','自动排版依据'),layoutObservationBody,action('关闭',()=>layoutDialog.close()));document.body.append(layoutDialog);
 const contextCell=(key,label)=>{const cell=make('span',null,'production-task-context-cell');cell.dataset.context=key;cell.append(make('b',label),make('strong','未载入'));return cell};
 taskContext.append(contextCell('skill','Skill'),contextCell('model','视频'),contextCell('approval','审批'),contextCell('references','参考图'));
 taskObservations.setAttribute('aria-label','参考图、图像处理、3D 场景和智能剪辑观察');taskObservations.append(observationSummary,observationList);taskSceneReview.setAttribute('aria-label','3D 场景镜头级核对');taskSceneReview.append(sceneReviewSummary,sceneReviewList);taskImageHistory.setAttribute('aria-label','最近图像处理记录');taskImageHistory.append(imageHistorySummary,imageHistoryList);taskBody.append(taskContext,taskDetail,taskRecovery,taskAudit,taskObservations,taskSceneReview,taskImageHistory);
 const taskActions=make('div',null,'production-task-actions'),refreshTask=action('刷新状态',async()=>{refreshTask.disabled=true;try{await refreshProjectStatus();schedule()}finally{refreshTask.disabled=false;syncProductionTask()}}),resumeTask=action('重新确认制作',()=>document.querySelector('#executeButton')?.click()),reviewTask=action('打开审阅',()=>document.querySelector('#reviewButton')?.click()),sceneTask=action('查看 3D-BOX ↗',()=>{if(!project){toast('请先创建项目');return}if(busy){toast('当前制作任务处理中，请稍候');return}if(hasDrafts()){toast('请先保存或放弃草稿，再进入 3D-BOX');return}location.href='/creative/scene?project='+encodeURIComponent(project.id)}),editTask=action('进入剪辑 ↗',()=>{if(!project){toast('请先创建项目');return}if(busy){toast('当前制作任务处理中，请稍候');return}if(hasDrafts()){toast('请先保存或放弃草稿，再进入智能剪辑');return}location.href='/creative/editor?project='+encodeURIComponent(project.id)});sceneTask.id='productionSceneButton';sceneTask.title='查看 3D 场景、镜头轨迹和剪辑轨道对齐';editTask.id='productionEditButton';editTask.title='查看剪辑草稿、Agent 建议、字幕、音频和人工审阅';taskActions.append(refreshTask,resumeTask,reviewTask,sceneTask,editTask);
 const taskPanel=make('section',null,'production-task-panel');taskPanel.id='productionTaskPanel';taskPanel.setAttribute('aria-label','制作任务详情');
 const closeTask=action('收起',()=>{productionTask.open=false;taskSummary.focus()});closeTask.setAttribute('aria-label','收起制作任务详情');
 const taskSync=make('p',null,'production-task-sync');
 const taskPanelHead=make('div',null,'production-task-panel-head');taskPanelHead.append(make('strong','制作任务详情'),closeTask);
 taskPanel.append(taskPanelHead,taskSync,taskBody,taskActions);productionTask.append(taskSummary,taskPanel);bar.prepend(productionTask);
 const liveProgress=make('section',null,'canvas-live-progress');liveProgress.setAttribute('aria-label','实时制作进度');liveProgress.hidden=true;
 const liveProgressHead=make('div',null,'canvas-live-progress-head'),liveProgressTitle=make('strong','实时制作'),liveProgressLabel=make('span');liveProgressHead.append(liveProgressTitle,liveProgressLabel);
 const liveProgressList=make('div',null,'canvas-live-progress-list');
 const liveProgressTrack=make('div',null,'canvas-live-progress-track'),liveProgressFill=make('span'),liveProgressCaption=make('small');liveProgressTrack.setAttribute('role','progressbar');liveProgressTrack.append(liveProgressFill);liveProgress.append(liveProgressHead,liveProgressList,liveProgressCaption,liveProgressTrack);document.body.append(liveProgress);
const renderManualProgress=detail=>{const d=detail||{};liveProgress.dataset.manual=d.visible?'true':'false';if(!d.visible){liveProgress.hidden=true;liveProgressList.replaceChildren();liveProgressLabel.textContent='';liveProgressCaption.textContent='';liveProgressTrack.removeAttribute('aria-valuenow');liveProgressTrack.removeAttribute('aria-valuetext');liveProgressTrack.removeAttribute('aria-description');liveProgressFill.style.removeProperty('width');return}liveProgress.hidden=false;liveProgressLabel.textContent=d.label||'节点制作中';liveProgressCaption.textContent=d.caption||'正在同步节点进度';liveProgressCaption.setAttribute('aria-label',liveProgressCaption.textContent);const rows=Array.isArray(d.entries)&&d.entries.length?d.entries:[d];liveProgressList.replaceChildren(...rows.slice(0,6).map(row=>{const item=make('div',null,'canvas-live-progress-item'),name=make('span','',row.label||'节点制作中'),value=make('b','',Number.isFinite(row.percent)?Math.round(row.percent)+'%':'同步中');item.append(name,value);return item}));liveProgressTrack.setAttribute('aria-label','生成进度：'+(d.label||'节点制作中'));const determinate=rows.length===1&&Number.isFinite(d.percent)&&!d.interrupted;liveProgressTrack.dataset.determinate=String(determinate);if(determinate){const value=Math.max(0,Math.min(100,Number(d.percent)));liveProgressTrack.setAttribute('aria-valuemin','0');liveProgressTrack.setAttribute('aria-valuemax','100');liveProgressTrack.setAttribute('aria-valuenow',String(value));liveProgressTrack.setAttribute('aria-valuetext',d.label||'节点制作中');liveProgressTrack.removeAttribute('aria-description');liveProgressFill.style.width=value+'%'}else{liveProgressTrack.removeAttribute('aria-valuemin');liveProgressTrack.removeAttribute('aria-valuemax');liveProgressTrack.removeAttribute('aria-valuenow');liveProgressTrack.removeAttribute('aria-valuetext');liveProgressTrack.setAttribute('aria-description',d.label||'节点制作中');liveProgressFill.style.removeProperty('width')}};
 document.addEventListener('creative-manual-progress',event=>renderManualProgress(event.detail));
 const manualProgressVisibilityObserver=new MutationObserver(()=>{if(!document.body.classList.contains('workspace-child-generating'))renderManualProgress({visible:false})});manualProgressVisibilityObserver.observe(document.body,{attributes:true,attributeFilter:['class']});
 taskSummary.setAttribute('aria-controls',taskPanel.id);taskSummary.setAttribute('aria-expanded','false');taskTitle.setAttribute('role','status');taskTitle.setAttribute('aria-live','polite');
 productionTask.addEventListener('toggle',()=>taskSummary.setAttribute('aria-expanded',String(productionTask.open)));
 document.addEventListener('pointerdown',event=>{if(productionTask.open&&!productionTask.contains(event.target))productionTask.open=false});
 document.addEventListener('keydown',event=>{if(event.key==='Escape'&&productionTask.open&&!document.querySelector('dialog[open]')){productionTask.open=false;taskSummary.focus()}});

 const resolutionLabels={callback_observed_awaiting_poll:'已收到回调，等待轮询确认',polling:'供应商处理中',provider_terminal_confirmed:'供应商已结束，正在核对素材',source_checking:'正在检查成片素材',source_verified:'素材检查完成',provider_terminal_failed:'供应商失败，已停止',provider_terminal_uncertain:'结果待核对'};
 function syncProductionTask(){if(!productionTask)return;const retakes=Object.values(project?.edit_retakes||{});const target=project?.film||project?.shots?.find(s=>s.provider_resolution)||retakes.find(s=>s.provider_resolution);const resolution=target?.provider_resolution||'';const poll=target?.provider_poll||{};const recovery=project?.production_recovery_queue||[];const imageTask=project?.image_task||{};const fallback=project?.interrupted?'服务中断，等待恢复查询':imageTask.state==='running'?'参考图生成中':imageTask.state==='completed'?'参考图已加入画布':imageTask.state==='needs_review'?'参考图待核对':({planning:'导演规划中',ready:'等待制作确认',running:'任务运行中',rendering:'正在合成',completed:'成片待审阅',paused:'制作已暂停',failed:'制作失败'}[project?.state]||'等待任务');const label=resolutionLabels[resolution]||fallback;const progress=poll.progress||target?.progress||{},rawPercent=progress.percent,hasPercent=rawPercent!==null&&rawPercent!==''&&Number.isFinite(Number(rawPercent)),numericPercent=hasPercent?Math.max(0,Math.min(100,Number(rawPercent))):null,percent=hasPercent?`${numericPercent}%`:'';
  const stages={queued:'排队中',preparing:'准备画面',generating:'Kling 正在生成',denoising:'生成画面',encoding:'编码视频',decoding:'解码画面',finalizing:'整理成片'};
  const currentLabel=syncFailures?'连接中断 · 正在重连':project?.state==='rendering'?'正在合成成片':project?.state==='completed'?'成片待审阅':project?.state==='paused'?'制作已暂停':project?.state==='failed'?'制作失败':project?.state==='running'&&resolution==='polling'?(stages[progress.stage]||label):label;
  if(taskTitle.textContent!==currentLabel)taskTitle.textContent=currentLabel;
  taskProgress.textContent=syncFailures||project?.state!=='running'?'':percent;taskSync.textContent=syncFailures?'状态暂未同步，正在重试查询。已提交任务不会重复生成。':(lastStatusSync?'上次同步 '+new Date(lastStatusSync).toLocaleTimeString('zh-CN',{hour12:false})+' · 生成期间每 4 秒自动刷新':'等待同步任务状态');productionTask.title=currentLabel+(percent?' · '+percent:'')+' · 点击查看详情';
  const manualVisible=liveProgress.dataset.manual==='true';
  const liveVisible=manualVisible||Boolean(project&&(['running','rendering','paused','planning'].includes(project.state)||project.interrupted||imageTask.state==='running'));
  liveProgress.hidden=!liveVisible;
  if(liveVisible&&!manualVisible){const liveText=currentLabel+(percent?' · '+percent:'');liveProgressLabel.textContent=liveText;liveProgressCaption.textContent=syncFailures?'已提交任务保留，正在重新连接':(hasPercent?'供应商已返回实时百分比':'供应商未返回百分比，显示同步状态');if(Number.isFinite(progress.checked_at)&&progress.checked_at>0)liveProgressCaption.textContent+=' · 模型状态确认 '+new Date(progress.checked_at*1000).toLocaleTimeString('zh-CN',{hour12:false});liveProgressCaption.setAttribute('aria-label',liveProgressCaption.textContent);liveProgressTrack.setAttribute('aria-label','生成进度：'+liveText);const determinate=hasPercent&&!syncFailures;liveProgressTrack.dataset.determinate=String(determinate);if(determinate){liveProgressTrack.setAttribute('aria-valuemin','0');liveProgressTrack.setAttribute('aria-valuemax','100');liveProgressTrack.setAttribute('aria-valuenow',String(numericPercent));liveProgressTrack.setAttribute('aria-valuetext',liveText);liveProgressTrack.removeAttribute('aria-description');liveProgressFill.style.width=numericPercent+'%'}else{liveProgressTrack.removeAttribute('aria-valuemin');liveProgressTrack.removeAttribute('aria-valuemax');liveProgressTrack.removeAttribute('aria-valuenow');liveProgressTrack.removeAttribute('aria-valuetext');liveProgressTrack.setAttribute('aria-description',liveText);liveProgressFill.style.removeProperty('width')}}
  productionTask.classList.toggle('is-running',!project?.interrupted&&(['running','rendering','planning'].includes(project?.state)||imageTask.state==='running'));

  const skill=project?.skill_title||'商品广告导演',version=project?.skill?.version?` · v${project.skill.version}`:'';const model=project?.quote?.label||project?.model||'未选视频模型';const approval=project?.approval_mode==='auto'?'自动':'手动';const refs=project?.canvas?.nodes?.filter(n=>n.kind==='image'||n.kind==='video').length||0;
  taskContext.querySelector('[data-context=skill] strong').textContent=skill+version;taskContext.querySelector('[data-context=model] strong').textContent=model;taskContext.querySelector('[data-context=approval] strong').textContent=approval;taskContext.querySelector('[data-context=references] strong').textContent=refs?`${refs} 个已挂载`:'待添加';
  const nodes=project?.canvas?.nodes||[],events=project?.events||[],lineage=Object.values(project?.canvas_lineage||{}),imageEdits=lineage.filter(item=>['image_edit','image_composite'].includes(item?.kind)).length,layoutSaved=events.some(item=>item?.code==='canvas_layout_saved'),imageAttempts=Array.isArray(project?.image_attempts)?project.image_attempts.filter(Boolean):[];
  const autoLayout=project?.canvas_auto_layout;
  const autoLayoutNode=autoLayout?.node_id&&nodes.find(node=>node.id===autoLayout.node_id);
  const autoLayoutCurrent=Boolean(autoLayoutNode&&Number(autoLayout?.x)===Number(autoLayoutNode.x)&&Number(autoLayout?.y)===Number(autoLayoutNode.y));
  const layoutState=autoLayoutCurrent?`生成结果已自动排版 · ${nodes.length} 个素材`:autoLayoutNode?`已手动调整 · ${nodes.length} 个素材`:layoutSaved?`已保存 · ${nodes.length} 个素材`:nodes.length?'待保存':'待添加';
  const latestTransformObservation=imageAttempts.slice().reverse().map(attempt=>{const draftId=attempt?.transform_draft_id;if(!draftId)return null;const draft=project?.image_transform_drafts?.[draftId];const resultAsset=attempt?.asset||draft?.result_asset;return draft?.result_observation||(resultAsset&&project?.canvas_lineage?.[resultAsset]?.transform_alignment)||null}).find(Boolean);
  const observedImageState={changed_observed:'已生成结果 · 像素变化已观察 · 待人工核对',unchanged:'结果像素未变化 · 需要重新核对',decode_failed:'结果像素观察失败 · 待核对'}[latestTransformObservation?.status]||'';
  const imageState=observedImageState||(imageEdits?`已生成 ${imageEdits} 个调整/合成结果`:imageTask.state==='completed'?'参考图已生成，可继续调整':imageTask.state==='needs_review'?'结果待核对，不会自动重试':imageTask.state==='running'?'参考图生成中':'未记录调整');
  const intent=project?.scene_render_intent,review=project?.scene_render_review,assetIntent=project?.scene_asset_intent,assetQuote=project?.scene_asset_quote;
  const sceneApplications=Array.isArray(project?.scene_timeline_applications)?project.scene_timeline_applications:Object.values(project?.scene_timeline_applications||{}),latestSceneApplication=sceneApplications.filter(item=>item&&typeof item==='object').slice().sort((a,b)=>(Number(a.revision_after)||0)-(Number(b.revision_after)||0)).slice(-1)[0],sceneHash=typeof intent?.scene_hash==='string'?intent.scene_hash:'',timelineSameScene=Boolean(latestSceneApplication?.scene_hash&&sceneHash&&latestSceneApplication.scene_hash===sceneHash),timelineSameRevision=Boolean(latestSceneApplication&&Number(latestSceneApplication.revision_after)===Number(project?.revision)),timelineState=latestSceneApplication?.state==='applied'&&timelineSameScene&&timelineSameRevision?`剪辑轨道已接入 · ${latestSceneApplication.shot_count||latestSceneApplication.shots?.length||0} 个镜头 · 待成片核对`:latestSceneApplication?.state==='applied'&&(!sceneHash||latestSceneApplication.scene_hash!==sceneHash||!timelineSameRevision)?'剪辑轨道已过期 · 请重新生成草稿':latestSceneApplication?.state==='undone'?'轨道草稿已撤销 · 可重新生成':intent?'已冻结场景 · 待生成剪辑轨道草稿':project?.scene3d?'场景已保存 · 待确认渲染':'未接入';
  const reviewShots=Array.isArray(review?.shots)?review.shots:[],reviewDeviationCount=reviewShots.filter(item=>['deviation','unavailable'].includes(item?.status)).length,reviewPendingCount=reviewShots.filter(item=>!['aligned','deviation'].includes(item?.status)).length,renderState=intent?(review?(review.decision==='accepted'?`成片回放已核对 · ${reviewShots.length||'全部'} 个镜头`:`成片回放有偏差 · ${reviewDeviationCount||'部分'} 个镜头待修订${reviewPendingCount?` · ${reviewPendingCount} 个待核对`:''}`):`已冻结修订 ${intent.scene_revision||'—'}`):'';
  const assetState=assetIntent?(assetIntent.stale?'3D 资产草稿已过期 · 请重新保存':`3D 资产草稿 · ${assetIntent.skill_title||assetIntent.skill_id||'商品广告导演'} · ${assetIntent.approval_mode==='auto'?'自动审批':'手动审批'}`):'';
  const assetQuoteState=assetQuote?(assetQuote.stale?'3D 资产报价已过期 · 请重新报价':assetQuote.approval_state==='blocked_provider_unconfigured'?'3D 资产确认已阻止 · 供应商未接入':assetQuote.provider_available===false?'3D 资产报价已核对 · 供应商未接入':'3D 资产报价待确认'):'';
  const sceneState=[assetState,assetQuoteState,renderState,timelineState].filter(Boolean).join(' · ');
  const sceneShotDefinitions=[];let sceneShotCursor=0;for(const item of (Array.isArray(project?.scene3d?.shots)?project.scene3d.shots:[])){const duration=Number(item?.duration)||0;sceneShotDefinitions.push({...item,start:sceneShotCursor,end:sceneShotCursor+duration});sceneShotCursor+=duration}
  const sceneTimelineRows=Array.isArray(latestSceneApplication?.shots)?latestSceneApplication.shots:[],sceneTimelineByShot=new Map(sceneTimelineRows.filter(item=>item?.shot_id).map(item=>[item.shot_id,item])),sceneStatusLabel={not_reviewed:'未核对',aligned:'基本一致',deviation:'存在偏差',unavailable:'无法判断'};
  const sceneReportRows=reviewShots.length?reviewShots.map((item,index)=>{const definition=sceneShotDefinitions.find(shot=>shot.id===item?.shot_id),timeline=sceneTimelineByShot.get(item?.shot_id);return {shotId:item?.shot_id,name:definition?.name||`镜头 ${index+1}`,start:definition?.start,end:definition?.end,review:sceneStatusLabel[item?.status]||'待核对',timeline:timelineState.startsWith('剪辑轨道已接入')?'已接入剪辑':timelineState.startsWith('剪辑轨道已过期')?'剪辑轨道已过期':timeline?'已接入剪辑':'未接入剪辑',note:typeof item?.note==='string'?item.note.trim().replace(/\s+/g,' ').slice(0,96):''}}):sceneTimelineRows.map((item,index)=>({shotId:item?.shot_id,name:item?.name||`镜头 ${index+1}`,start:Number(item?.start),end:Number(item?.end),review:'待回放核对',timeline:timelineState.startsWith('剪辑轨道已接入')?'已接入剪辑':'剪辑轨道已过期',note:''}));
  taskSceneReview.hidden=!sceneReportRows.length;sceneReviewSummary.textContent=sceneReportRows.length?`镜头级核对 · ${sceneReportRows.length} 个`:'镜头级核对';sceneReviewList.replaceChildren(...sceneReportRows.slice(0,12).map(item=>{const li=make('li'),timing=Number.isFinite(item.start)&&Number.isFinite(item.end)?` · ${item.start.toFixed(1)}–${item.end.toFixed(1)}s`:'';const title=make('b',item.name+timing);if(item.shotId&&project?.id){const locate=make('a','定位 ↗');locate.href='/creative/scene?'+new URLSearchParams({project:project.id,scene_shot:item.shotId,scene_at:Number.isFinite(item.start)?item.start.toFixed(2):'0.00'});locate.setAttribute('aria-label',`定位 ${item.name}`);li.append(title,locate)}else li.append(title);li.append(make('span',`${item.review} · ${item.timeline}`));if(item.note)li.title=item.note;return li}));
  const recentLocation=returnedSceneShot&&Number.isFinite(returnedSceneAt)?`最近定位 · ${(sceneReportRows.find(item=>item.shotId===returnedSceneShot)||sceneShotDefinitions.find(item=>item.id===returnedSceneShot))?.name||'镜头'} · 场景 ${Math.max(0,returnedSceneAt).toFixed(2)}s`:'';
  const editSpec=project?.edit||{},clipCount=Array.isArray(editSpec.clips)?editSpec.clips.length:0,retakeCount=Object.keys(project?.edit_retakes||{}).length,versionCount=(project?.edit_versions||[]).length,editExport=project?.edit_export||{},editReview=project?.edit_review||{},reviewCurrent=editReview.revision===project?.revision,suggestions=project?.edit_suggestions||{},latestSuggestion=project?.edit_suggestion_id?suggestions[project.edit_suggestion_id]:null,suggestionCurrent=Boolean(latestSuggestion&&(latestSuggestion.revision==null||latestSuggestion.revision===project?.revision)),suggestionIntent=typeof latestSuggestion?.intent==='string'?latestSuggestion.intent.trim().replace(/\s+/g,' ').slice(0,48):'';
  const editState=editExport.state==='running'?`导出中 · ${clipCount||'当前'} 段画面`:editExport.state==='completed'?'已导出 · 待人工审阅':reviewCurrent&&editReview.decision==='approved'?'人工核对已记录 · 仍需独立审阅':suggestionCurrent&&latestSuggestion?.state==='running'?'Agent 正在分析剪辑目标':suggestionCurrent&&latestSuggestion?.state==='completed'?`Agent 建议已就绪${suggestionIntent?' · '+suggestionIntent:''}`:suggestionCurrent&&latestSuggestion?.state==='failed'?'Agent 建议失败 · 可明确重新请求':latestSuggestion&&!suggestionCurrent?'Agent 建议已过期 · 请重新分析':versionCount?`${versionCount} 个已导出版本`:retakeCount?`${retakeCount} 个重拍任务`:clipCount?`剪辑草稿 · ${clipCount} 段画面`:project?.edit?'已有剪辑草稿':'待进入剪辑';
  observationList.replaceChildren(...[['layout','自动排版',layoutState],['image','图像处理',imageState],['scene','3D 场景',sceneState],['edit','智能剪辑',editState]].map(([key,label,value])=>{const li=make('li');li.dataset.observation=key;li.append(make('b',label),make('span',value));return li}));
  const layoutObservation=project?.canvas_layout_observation,layoutLi=observationList.querySelector('[data-observation=layout]');
  if(layoutObservation&&layoutLi){const review=action('查看依据',()=>{const mode={auto:'自动排版已保持',manual_adjusted:'已保留手动调整',manual:'当前为手动布局',empty:'尚未添加素材'}[layoutObservation.mode]||'布局状态';layoutObservationBody.replaceChildren(make('p',`${mode} · ${layoutObservation.node_count||0} 个素材`),make('p',layoutObservation.reason||'暂无排版说明'),make('p',`碰撞检查：${layoutObservation.collision_count||0} 处 · 边界检查：${layoutObservation.within_bounds?'通过':'需核对'}`),make('p',layoutObservation.training_eligible===false?'仅作创作观察，尚未进入训练或发布。':''));layoutDialog.showModal()});review.className='observation-action';review.setAttribute('aria-label','查看自动排版依据');layoutLi.append(review)}
  observationSummary.textContent=`创作观察 · ${nodes.length||0} 素材`;
  const historyState={running:'生成中',completed:'已完成',needs_review:'待核对',failed:'失败'};imageHistorySummary.textContent=`图像处理记录 · ${imageAttempts.length} 次`;imageHistoryList.replaceChildren(...imageAttempts.slice(-3).reverse().map((attempt,index)=>{const references=attempt.prepared?.references||[],kind=references.length>1?'多图合成':attempt.source_asset||references.length?'原图调整':'参考图生成',state=historyState[attempt.state]||'状态待核对',li=make('li',`${imageAttempts.length-index} · ${kind} · ${state}`);li.dataset.state=attempt.state||'unknown';li.title=references.length?`已记录 ${references.length} 张参考输入`:'未记录额外参考输入';return li}));taskImageHistory.hidden=!imageAttempts.length;
  taskDetail.textContent=target?.provider_callback?'回调观察已写入跨进程审计，当前仍以轮询、下载和技术检查为准。':project?.interrupted?'当前进程未在运行，刷新只会查询已有任务，不会重新提交。':target?'任务状态、素材核验和人工审阅分开记录。':imageTask.state==='running'?'参考图正在生成，完成后会加入画布。':imageTask.state==='completed'?(autoLayoutCurrent?'参考图已加入画布，并已自动排版，可继续核对。':autoLayoutNode?'参考图已加入画布，用户已调整布局，可继续核对。':'参考图已加入画布，可继续核对。'):imageTask.state==='needs_review'?'参考图结果待核对，不会自动重试。':editExport.state==='running'?'剪辑正在导出，完成后仍需人工观看、听音和事实核对。':suggestionCurrent&&latestSuggestion?.state==='completed'?'剪辑建议只读就绪，应用前仍需在剪辑页核对并保存草稿。':'生成前不会创建供应商任务。';taskDetail.textContent+=(recovery.length?` · ${recovery.length} 项待恢复或人工核对`:'')+(recentLocation?` · ${recentLocation}`:'');taskDetail.dataset.sceneReturn=recentLocation;taskRecovery.replaceChildren(...recovery.slice(0,3).map(item=>{const li=make('li',`${item.kind} · ${item.message}`);li.dataset.action=item.action;li.title=item.requires_manual?'需要人工核对':'只读恢复动作，不会重新提交';return li}));taskRecovery.hidden=!recovery.length;taskAudit.replaceChildren(...(project?.provider_callback_audit||[]).slice(0,3).map(item=>{const li=make('li',`${item.received_at?new Date(item.received_at*1000).toLocaleTimeString('zh-CN',{hour12:false}):'--'} · ${item.target} · ${item.status}`);li.title=item.digest||'';return li}));const hasTask=target||recovery.length||project?.interrupted||imageTask.state||clipCount||editExport.state||latestSuggestion?.state;const sceneAvailable=Boolean(project?.scene3d||project?.scene_asset_intent||project?.scene_render_intent||project?.scene_render_review||sceneApplications.length);productionTask.hidden=!project||(!hasTask&&!sceneAvailable&&project.state==='intake');productionTask.dataset.state=resolution||imageTask.state||editExport.state||(suggestionCurrent?latestSuggestion?.state:'')||project?.state||'idle';resumeTask.hidden=!(project?.interrupted||project?.state==='paused');reviewTask.hidden=!(project?.state==='completed'&&project?.artifact);refreshTask.hidden=!project;sceneTask.hidden=!sceneAvailable;sceneTask.disabled=busy||hasDrafts();sceneTask.title=sceneTask.disabled?(hasDrafts()?'请先保存或放弃草稿，再进入 3D-BOX':'当前制作任务处理中，请稍候'):'查看 3D 场景、镜头轨迹和剪辑轨道对齐';editTask.hidden=!project;editTask.disabled=busy||hasDrafts();}
 document.addEventListener('creative-state-change',syncProductionTask);document.addEventListener('creative-status-sync',syncProductionTask);
 function syncCreativeStatus(){const title=project?.skill_title||'商品广告导演',version=project?.skill?.version?` v${project.skill.version}`:'',model=project?.quote?.label||project?.model||'未选视频模型',approval=project?.approval_mode==='auto'?'自动审批':'手动审批';creativeStatus.replaceChildren(make('span',`${title}${version} · `,'creative-status-skill'),make('span',`${model} · ${approval}`));const resolution=project?.film?.provider_resolution||project?.shots?.find(s=>s.provider_resolution)?.provider_resolution;const resolutionLabel={callback_observed_awaiting_poll:'已收到回调，等待轮询确认',polling:'供应商处理中',provider_terminal_confirmed:'供应商已结束，正在核对素材',source_checking:'正在检查成片素材',source_verified:'素材检查完成',provider_terminal_failed:'供应商失败，已停止',provider_terminal_uncertain:'结果待核对'}[resolution]||'';const assetIntent=project?.scene_asset_intent,assetQuote=project?.scene_asset_quote;const assetLabel=assetIntent?`\n3D 资产草稿：${assetIntent.skill_title||assetIntent.skill_id||'未命名 Skill'} · ${assetIntent.stale?'已过期':'已保存'} · ${assetIntent.approval_mode==='auto'?'自动审批':'手动审批'}`:'';const assetQuoteLabel=assetQuote?`\n3D 资产报价：${assetQuote.stale?'已过期':assetQuote.approval_state==='blocked_provider_unconfigured'?'确认已阻止 · 供应商未接入':assetQuote.provider_available===false?'已核对 · 供应商未接入':'待确认'}`:'';creativeStatus.title=`Skill：${title}${version}\n视频模型：${model}\n制作审批：${approval}${assetLabel}${assetQuoteLabel}${resolutionLabel?'\n生产状态：'+resolutionLabel:''}`;creativeStatus.disabled=!project;const intent=project?.scene_render_intent;const lock=intent?.trajectory_sha256?` · 轨迹锁 ${intent.trajectory_sha256.slice(0,12)}`:'';sceneIntentButton.hidden=!intent;sceneIntentButton.disabled=!intent||busy;sceneIntentButton.title=intent?`场景修订 ${intent.scene_revision} · ${intent.scene_hash.slice(0,12)}${lock}\n点击查看并进入生成确认`:'尚未确认 3D 渲染准备';const review=project?.scene_render_review;sceneReviewButton.hidden=!review;sceneReviewButton.disabled=!review||busy;sceneReviewButton.textContent=review?.decision==='accepted'?'成片回放已核对 ↗':'成片回放有偏差 · 查看 ↗';sceneReviewButton.title=review?`成片哈希 ${review.artifact_sha256.slice(0,12)}${review.trajectory_sha256?`\n轨迹锁 ${review.trajectory_sha256.slice(0,12)}`:''}\n${review.note||'已记录成片回放核对结果'}`:'尚未记录成片回放核对'};syncProductionTask()
 function syncLayout(){inspectorButton.textContent=document.body.classList.contains('inspector-folded')?'展开简报':'收起简报'}syncLayout();
 document.querySelector('.timeline').addEventListener('click',e=>{if(e.target.closest('.shot')){document.body.classList.remove('inspector-folded');syncLayout()}});
 const canvasGenerate=action('生成整片视频',()=>document.querySelector('#executeButton')?.click());canvasGenerate.className='primary canvas-generate';if(expanded)document.querySelector('.canvas-output>.canvas-card-head')?.append(canvasGenerate);else document.querySelector('.projectbar')?.append(canvasGenerate);
 const controls=make('div',null,'model-controls'),vlabel=make('label','视频模型'),ilabel=make('label','图片模型');
 const videoSelect=make('select'),imageSelect=make('select');videoSelect.id='videoModelSelect';imageSelect.id='imageModelSelect';videoSelect.setAttribute('aria-label','视频生成模型');imageSelect.setAttribute('aria-label','图片生成模型');vlabel.append(videoSelect);ilabel.append(imageSelect);
 const modelNote=make('p','正在读取模型…','model-note'),generateButton=action('生成参考图',()=>openImage()),modelsButton=action('全部模型与费用',()=>modelDialog.showModal());if(expanded)controls.classList.add('video-node-controls');controls.append(vlabel,modelNote,modelsButton);const controlsHost=expanded?document.querySelector('.canvas-output>.canvas-card-head'):document.querySelector('.compose');if(controlsHost)controlsHost.prepend(controls);
 const imageControls=make('div',null,'image-node-controls'),productGenerate=action('生成商品参考图',()=>openImage());imageControls.append(ilabel,productGenerate);
 const imageStatus=make('p');imageStatus.id='imageStatus';imageControls.append(imageStatus);
 const modelDialog=make('dialog');modelDialog.id='modelDialog';modelDialog.append(make('h2','可选模型'),make('p','视频和参考图分别选择。切换视频模型需要重新规划；只有明确确认生成才扣积分。'));const catalogStatus=make('p',null,'notice');catalogStatus.id='modelServiceNote';const modelList=make('div');const checkStatusButton=action('检查制作服务',()=>checkModelStatus());checkStatusButton.id='checkModelStatus';modelDialog.append(catalogStatus,checkStatusButton,modelList,action('关闭',()=>modelDialog.close()));document.body.append(modelDialog);
 const imageDialog=make('dialog');imageDialog.id='imageDialog';const imageTitle=make('h2','生成一张参考图');imageDialog.append(imageTitle);const imageSummary=make('p'),prompt=make('textarea');
 const imageModel=make('select');imageModel.id='imageDialogModel';imageModel.setAttribute('aria-label','本次图片模型');const imageModelLabel=make('label','本次图片模型');imageModelLabel.append(imageModel);
 const imageSource=make('figure',null,'image-request-source'),imageSourcePreview=make('img'),imageSourceCaption=make('figcaption');imageSource.id='imageRequestSource';imageSourcePreview.alt='本次编辑使用的原图';imageSource.append(imageSourcePreview,imageSourceCaption);imageSource.hidden=true;
 const imageModelNotice=make('p',null,'image-model-notice');imageModelNotice.id='imageModelNotice';imageModelNotice.setAttribute('role','status');prompt.id='imagePrompt';prompt.setAttribute('aria-label','参考图描述');prompt.maxLength=4000;prompt.placeholder='描述商品、材质、场景和光线。文字和字幕会在视频后期添加。';const confirmImage=action('确认生成 · 1 积分',submitImage);confirmImage.className='primary';const imageActions=make('div',null,'row');imageActions.append(action('取消',()=>imageDialog.close()),confirmImage);imageDialog.append(imageSource,imageModelLabel,imageSummary,prompt,imageModelNotice,make('p','生成后加入画布供导演参考；需要约束视频商品外观时，点击该图片上的“设为商品参考”。失败或结果待核对时不会自动重试。'),imageActions);document.body.append(imageDialog);const imageDialogPicker=window.installStudioModelPicker(imageModel);
 let videos=[],images=[],modelsLoaded=false,imageRequest=null,imageSubmitting=false;
 const isLocked=()=>busy||!project||['running','rendering','planning'].includes(project.state)||project.image_task?.state==='running';
 function paintModels(){if(project?.image_task?.state==='running')['sendButton','planButton','executeButton','referenceUploadButton','removeReference','saveShot'].forEach(id=>$(id).disabled=true);if(!modelsLoaded)return;videoSelect.value=project?.model||videos[0]?.id;videoSelect.disabled=isLocked();imageSelect.disabled=isLocked();generateButton.disabled=isLocked();const v=videos.find(m=>m.id===videoSelect.value),i=images.find(m=>m.id===imageSelect.value),credits=v?.credits_per_5s??'费用待读取',capability=v?.single_film?'15 秒有声整片':v?.limitation||'能力待确认';modelNote.textContent=v?`${credits} 积分 / 5 秒 · ${capability}`:'请选择视频模型';generateButton.disabled=isLocked()||!i?.available;openCanvas.disabled=!project;smartEdit.disabled=!project||busy||hasDrafts();smartEdit.title=smartEdit.disabled?(hasDrafts()?'请先保存或放弃草稿，再进入智能剪辑':'请先创建项目'):'进入字幕、重拍、转场、音频和全片审阅';if(canvasGenerate)canvasGenerate.disabled=isLocked()||!project?.shots?.length||!['ready','paused'].includes(project?.state);document.querySelectorAll('.node-image-model').forEach(el=>{el.value=imageSelect.value;el.disabled=isLocked()});document.querySelectorAll('.node-image-generate').forEach(el=>el.disabled=isLocked());
 const t=project?.image_task, imageBusy=t?.state==='running';imageStatus.classList.toggle('is-busy',imageBusy);imageStatus.textContent=t?(imageBusy?'参考图生成中，可离开页面，回来继续查看。':t.state==='completed'?'参考图已加入画布。':t.error||'图片结果待核对，不会自动重试。'):'';document.querySelectorAll('.node-image-generate').forEach(el=>{el.classList.toggle('is-busy',imageBusy);el.textContent=imageBusy?'生成中…':'生成新参考图'});
 }
 videoSelect.onchange=async()=>{const chosen=videoSelect.value;if(!project)return;if(hasDrafts()){toast('请先保存或放弃草稿，再切换模型');paintModels();return}if(!confirm('切换视频模型会保留历史成片，并清除当前待制作方案。需要重新规划和确认预算，是否继续？')){paintModels();return}setBusy(true);try{project=await api('/projects/'+project.id+'/model','PUT',{revision:project.revision,model:chosen});clearMedia();draw();toast('视频模型已切换，请重新出方案。')}catch(e){toast(e.message);await refreshProjectStatus()}finally{setBusy(false)}};
 imageSelect.onchange=()=>{sessionStorage.setItem('creative-image-model',imageSelect.value);paintModels();syncEntry();syncReferenceActions()};
 function imageRequestIssue(){
  const m=images.find(m=>m.id===imageModel.value);
  if(!m?.available)return '请选择一个已接入的图片模型。';
  if(imageRequest?.source_asset&&!['edit','both'].includes(m.mode))return '修改原图需要参考图编辑模型，请在这里选择。';
  if(imageRequest?.source_asset&&(m.min_edit_references||1)>1)return '此模型需要至少两张参考图，请使用组合参考生成。';
  if(m.mode==='edit'&&!imageRequest?.source_asset&&!project?.reference)return '此模型需要参考图，请先在画布上传图片。';
  return '';
 }
 function paintImageRequest(){
  imageDialogPicker.sync();if(!imageRequest)return;const m=images.find(m=>m.id===imageModel.value),issue=imageRequestIssue();imageRequest.model=imageModel.value;
  imageModelNotice.textContent=issue||'将按所选模型生成独立版本，原图保留；确认前不会提交。';
  confirmImage.disabled=imageSubmitting||!!issue;
  imageSummary.textContent=(m?.label||'未选择模型')+' · '+project.aspect+' · 1 张 · 1 平台积分'+(imageRequest.source_asset?' · 使用所选原图':m?.mode==='edit'?' · 使用当前商品参考图':'')+(imageRequest.adjustments.angle!=='保留原角度'?' · '+imageRequest.adjustments.angle:'')+(imageRequest.adjustments.light!=='保留原光照'?' · '+imageRequest.adjustments.light:'')+(imageRequest.transform_draft_id?' · 使用已保存变换草稿':'');
 }
 imageModel.onchange=()=>{if(imageSubmitting)return;paintImageRequest();if(!imageRequestIssue()){imageSelect.value=imageModel.value;imageSelect.onchange()}};
 imageDialog.addEventListener('cancel',event=>{if(imageSubmitting)event.preventDefault()});
 imageDialog.addEventListener('close',()=>{imageRequest=null;imageSourcePreview.removeAttribute('src')});
 function openImage(description='',sourceAsset=null,adjustments=null,transformDraftId=null){
  if(isLocked())return;if(hasDrafts()){toast('请先保存或放弃草稿，再生成参考图');return}
  if(sourceAsset&&project.canvas_assets?.[sourceAsset]?.kind!=='image'){toast('请选择本项目图片');return}
  imageRequest={project:project.id,revision:project.revision,model:imageSelect.value,id:opaqueId(),source_asset:sourceAsset,transform_draft_id:transformDraftId,adjustments:adjustments||{angle:'保留原角度',light:'保留原光照'}};
  imageModel.replaceChildren(...images.map(m=>{const reason=!m.available?'未接入':sourceAsset&&!['edit','both'].includes(m.mode)?'仅文字生成':'';const option=make('option',m.label+(reason?' · '+reason:''));option.value=m.id;option.disabled=!!reason;option.dataset.disabledReason=reason;option.dataset.description=['edit','both'].includes(m.mode)?'支持参考图编辑':'文字生成图片';return option}));imageModel.value=imageSelect.value;
  imageTitle.textContent=sourceAsset?'修改图片':'生成一张参考图';imageSource.hidden=!sourceAsset;
  if(sourceAsset){const node=project.canvas?.nodes.find(n=>n.asset===sourceAsset),card=[...document.querySelectorAll('.reference-node')].find(c=>c.dataset.nodeId===node?.id),src=card?.querySelector('.canvas-card-body>img')?.getAttribute('src');imageSourceCaption.textContent=node?.label||'所选原图';imageSourcePreview.hidden=!src;if(src)imageSourcePreview.src=src;else imageSourcePreview.removeAttribute('src')}
  prompt.placeholder=sourceAsset?'描述想修改的背景、场景或细节，以及需要保留的部分。':'描述商品、材质、场景和光线。';prompt.value=description||(sourceAsset?'':[project.brief.product,project.brief.style].filter(Boolean).join('，'));paintImageRequest();imageDialog.showModal();prompt.focus();
 }
 document.addEventListener('creative-edit-image',event=>{if(event.detail?.asset)openImage('',event.detail.asset)});
 async function submitImage(){if(imageSubmitting)return;if(imageRequestIssue()){toast(imageRequestIssue());return}if(!imageRequest||prompt.value.trim().length<2){toast('请填写具体的参考图描述');return}if(project.id!==imageRequest.project||project.revision!==imageRequest.revision){imageDialog.close();toast('项目已变化，请重新确认');return}imageSubmitting=true;imageDialog.querySelectorAll('button,input,textarea,select').forEach(e=>e.disabled=true);setBusy(true);try{project=await api('/projects/'+project.id+'/images','POST',{revision:imageRequest.revision,model:imageRequest.model,prompt:prompt.value.trim(),request_id:imageRequest.id,approved_credits:1,connect_to_director:!['image','video'].includes(project.creation_mode),...(imageRequest.source_asset?{source_asset:imageRequest.source_asset}:{}),...(imageRequest.transform_draft_id?{transform_draft_id:imageRequest.transform_draft_id}:{}),adjustments:imageRequest.adjustments});imageDialog.close();draw();schedule()}catch(e){toast(e.message+'；请先刷新查看任务，勿重复确认');imageDialog.close();await refreshProjectStatus();schedule()}finally{imageSubmitting=false;imageDialog.querySelectorAll('button,input,textarea,select').forEach(e=>e.disabled=false);paintImageRequest();setBusy(false)}}
 const entry=make('section',null,'canvas-entry');entry.append(make('h3','商品参考'));const productImg=make('img');productImg.alt='视频生成使用的商品参考图';productImg.hidden=true;const entryState=make('p',null,'product-reference-state'),needs=make('div',null,'reference-needs');const upload=action('上传商品参考图',()=>$('referenceFile')?.click());
 const entrySettings=action('参考设置',()=>{});entrySettings.id='productReferenceSettings';
 const entryPanel=make('section',null,'asset-tools-panel product-reference-panel');entryPanel.id='productReferencePanel';entryPanel.setAttribute('popover','auto');entryPanel.setAttribute('aria-label','商品参考设置');
 entrySettings.onclick=null;entrySettings.popoverTargetElement=entryPanel;entrySettings.popoverTargetAction='toggle';entrySettings.setAttribute('aria-controls',entryPanel.id);entrySettings.setAttribute('aria-expanded','false');
 const entryPanelHead=make('div',null,'asset-tools-head'),entryClose=action('关闭',()=>{entryPanel.hidePopover();entrySettings.focus()});entryClose.className='asset-tools-close';entryClose.setAttribute('aria-label','关闭商品参考设置');entryPanelHead.append(make('strong','商品参考设置'),entryClose);
 const reviewReference=action('核对当前商品参考',()=>{entryPanel.hidePopover();document.body.classList.remove('inspector-folded');referencePanel.open=true;syncLayout();referencePanel.scrollIntoView({block:'nearest'})});reviewReference.id='reviewProductReference';
 entryPanel.append(entryPanelHead,imageControls,reviewReference,make('h3','待补充信息'),needs);entryPanel.addEventListener('beforetoggle',event=>entrySettings.setAttribute('aria-expanded',String(event.newState==='open')));
 const entryActions=make('div',null,'product-reference-actions');entryActions.append(upload,entrySettings);entry.append(productImg,entryState,imageStatus,entryActions,entryPanel);document.querySelector('.canvas-world')?.append(entry);
 const canvasHelp=document.querySelector('.canvas-help');if(canvasHelp)canvasHelp.textContent='导演连线帮助理解需求；“视频参考输入”选择实际送入视频模型的图片。保存输入后重新规划。';
 function syncEntry(){entry.hidden=expanded&&!project?.reference&&!project?.reference_needs_review;const src=$('referencePreview').getAttribute('src');productImg.hidden=!src||!!project?.reference_needs_review;if(!src)productImg.removeAttribute('src');if(src&&productImg.getAttribute('src')!==src)productImg.src=src;
  entryState.textContent=project?.reference_needs_review?'商品已变化 · 参考图待核对':project?.video_inputs?'实际输入以“视频参考输入”为准':project?.reference?'已设为商品参考':'上传商品图，锁定商品外观';entry.classList.toggle('reference-pending',!!project?.reference_needs_review);
  const questions=project?.questions||[];needs.textContent=project?(questions.map(q=>'• '+q.question).join('\n')||(project.shots?.length?'拍摄方案已形成，可继续补充或修正。':'• 受众\n• 核心卖点\n• 使用场景与风格')):'先创建一个创作项目';
  upload.textContent=project?.reference?'更换商品图':'上传商品参考图';upload.disabled=isLocked();productGenerate.disabled=isLocked()||!modelsLoaded||!images.find(m=>m.id===imageSelect.value)?.available;reviewReference.hidden=!project?.reference_needs_review;entrySettings.textContent=project?.reference_needs_review?'核对参考':'参考设置';
 }

 if($('referencePreview'))new MutationObserver(syncEntry).observe($('referencePreview'),{attributes:true,attributeFilter:['src']});
 const inputDetails=make('details',null,'timeline-inputs'),inputSummary=make('summary','模型输入与整片提示词'),inputBody=make('div');inputDetails.id='timelineInputs';inputDetails.append(inputSummary,inputBody);document.querySelector('.timeline').prepend(inputDetails);
 const approvalPrompt=make('textarea');approvalPrompt.readOnly=true;approvalPrompt.rows=7;approvalPrompt.setAttribute('aria-label','本次实际提交的完整提示词');const approvalInputs=make('p',null,'input-summary');const soundSummary=$('soundSummary');if(soundSummary)soundSummary.after(approvalInputs,make('h3','完整提示词 · 按时码一次提交'),approvalPrompt);else document.querySelector('#approveDialog')?.append(approvalInputs,make('h3','完整提示词 · 按时码一次提交'),approvalPrompt);
 const referencePanel=make('details',null,'reference-review'),referenceSummary=make('summary','商品参考图');
 const referenceImage=$('referencePreview'),referenceHeading=referenceImage?.previousElementSibling?.previousElementSibling;
 if(referenceHeading)referenceHeading.before(referencePanel);referencePanel.append(referenceSummary);
 let refNode=referenceHeading;while(refNode){const next=refNode.nextElementSibling;referencePanel.append(refNode);if(refNode.tagName==='P'&&refNode.textContent.includes('历史成片保留'))break;refNode=next;}
 const confirmReference=action('确认此图属于当前商品',async()=>{if(isLocked())return;setBusy(true);try{project=await api('/projects/'+project.id+'/reference/confirm','POST',{revision:project.revision,reference_id:project.reference.id});draw();toast('当前商品与参考图关联已确认')}catch(e){toast(e.message)}finally{setBusy(false)}});referencePanel.append(confirmReference);
 // These are current project video inputs, never retrospective message attachments.
 const composerRefs=make('section',null,'studio-composer-references');composerRefs.id='studioComposerReferences';composerRefs.setAttribute('aria-label','当前视频参考');composerRefs.hidden=true;
 const composerRefHead=make('div',null,'studio-composer-reference-head'),composerRefTitle=make('span'),manageRefs=action('管理参考',()=>$('canvasVideoInputs').click()),composerRefList=make('div',null,'studio-composer-reference-list');manageRefs.id='studioManageReferences';composerRefHead.append(composerRefTitle,manageRefs);composerRefs.append(composerRefHead,composerRefList);document.querySelector('.director .compose').prepend(composerRefs);
 let composerRefSignature='',composerRefEpoch=0,composerRefController=null;const composerRefURLs=[];
 function clearComposerRefs(){composerRefEpoch++;composerRefController?.abort();composerRefURLs.splice(0).forEach(URL.revokeObjectURL);composerRefList.replaceChildren()}
 function syncComposerReferences(){
  const p=project,refs=p?.video_inputs?p.video_inputs.references||[]:p?.reference?[{asset:p.reference.source_asset,reference_id:p.reference.id,role:'product'}]:[],mode=p?.video_inputs?.mode;
  const pending=!!(p?.video_inputs_needs_review||p?.reference_needs_review||(p?.video_inputs&&p.video_inputs.model!==p.model));
  manageRefs.disabled=isLocked();composerRefs.hidden=!refs.length;
  const names=refs.map((ref,i)=>p?.canvas?.nodes?.find(n=>n.asset===ref.asset)?.label||(ref.reference_id?'商品参考图':`参考图片 ${i+1}`));
  const signature=JSON.stringify([p?.id,p?.model,mode,refs,names,refs.map(ref=>!!p?.canvas?.nodes?.some(n=>n.asset===ref.asset)),pending]);
  if(signature===composerRefSignature){const legacy=composerRefList.querySelector('[data-legacy-reference]');if(legacy){const src=$('referencePreview').getAttribute('src');if(src)legacy.src=src;else legacy.removeAttribute('src')}return}
  composerRefSignature=signature;clearComposerRefs();if(!refs.length)return;
  const epoch=composerRefEpoch,pid=p.id;composerRefController=new AbortController();const signal=composerRefController.signal;
  composerRefs.dataset.pending=String(pending);composerRefTitle.textContent=pending?'视频参考 · 待核对':`视频参考 · ${({references:'多图参考',first_frame:'首帧',first_last:'首尾帧'})[mode]||'商品参考'} · ${refs.length} 张`;
  refs.forEach((ref,index)=>{
   const inCanvas=!!p.canvas?.nodes?.some(n=>n.asset===ref.asset),name=names[index],slot=mode==='first_last'?(index?'尾帧':'首帧'):mode==='first_frame'?'首帧':String(index+1),role=({product:'商品',person:'人物',scene:'场景',style:'风格',reference:'其他参考'})[ref.role]||'参考';
   const tile=action('',()=>{if(project?.id!==pid)return;if(inCanvas)document.dispatchEvent(new CustomEvent('creative-focus-canvas-asset',{detail:{project:pid,asset:ref.asset}}));else if(!manageRefs.disabled)manageRefs.click();else toast('当前参考保存在项目中，制作结束后可管理。')});tile.className='studio-composer-reference';tile.setAttribute('aria-label',(inCanvas?'定位参考 ':'查看参考 ')+name);tile.title=`${name} · ${role}${ref.instruction?' · '+ref.instruction:''}`;
   const img=make('img');img.alt=name;img.onerror=()=>{if(epoch===composerRefEpoch){tile.classList.add('preview-unavailable');img.alt='预览暂不可读取'}};const badge=make('span',slot,'studio-composer-reference-slot');tile.append(img,badge);composerRefList.append(tile);
   if(!ref.asset){img.dataset.legacyReference='true';const src=$('referencePreview').getAttribute('src');if(src)img.src=src;return}
   fetch(`/creative/api/projects/${encodeURIComponent(pid)}/canvas/assets/${encodeURIComponent(ref.asset)}/preview`,{headers:{Authorization:'Bearer '+key},signal:AbortSignal.any([signal,AbortSignal.timeout(15000)])}).then(async r=>{if(!r.ok)throw Error('preview');const blob=await r.blob();if(epoch!==composerRefEpoch||signal.aborted)return;const url=URL.createObjectURL(blob);composerRefURLs.push(url);img.src=url}).catch(()=>{if(epoch===composerRefEpoch&&!signal.aborted){tile.classList.add('preview-unavailable');img.alt='预览暂不可读取';tile.title+=' · 缩略图暂不可读取'}});
  });
 }
 if($('referencePreview'))new MutationObserver(syncComposerReferences).observe($('referencePreview'),{attributes:true,attributeFilter:['src']});
 function inputDescription(){const m=project?.input_manifest;if(!m)return '尚未形成输入清单';const images=m.images||[],directorOnly=m.director_only||[];return `${({text:'文字生成',first_frame:'首帧',first_last:'首尾帧',references:'多图软参考'})[m.mode]||'视频输入'} · ${images.length} 张实际图片 · 参考音频：无（声音由提示词生成）。导演辅助参考 ${directorOnly.length} 项。${project?.video_inputs_needs_review?'商品信息已变化，请重新核对视频参考。':''}`}
 function syncInputs(){syncComposerReferences();const p=project;inputSummary.textContent=p?.shots?.length?`整片提示词 · ${p.duration}s · 1 次生成 · ${p.input_manifest?.images?.length||0} 张视频参考 · 查看输入`:'整片提示词与参考输入 · 待规划';inputBody.replaceChildren(make('p',inputDescription()),action('查看完整带时码提示词',openFilmReview));
 for(const beat of p?.input_manifest?.beats||[]){inputBody.append(make('p',`${beat.start}–${beat.end}s：${beat.image_ids?.length?'沿用整片已选择的 '+beat.image_ids.length+' 张图片':'文字生成画面'}；声音来自本段 audio prompt；字幕后期叠加。`));}
 const pending=!!p?.reference_needs_review;referenceSummary.textContent=pending?'商品参考待核对 · 商品已变化或尚未确认':'商品参考 · '+(p?.reference?'当前作品独立保存':'未设置');confirmReference.hidden=!pending;confirmReference.disabled=isLocked();document.body.classList.toggle('reference-pending',pending);
 }
 const showApprove=$('executeButton').onclick;$('executeButton').onclick=()=>{if(project?.video_inputs_needs_review){$('canvasVideoInputs').click();return}if(project?.reference_needs_review){document.body.classList.remove('inspector-folded');referencePanel.open=true;syncLayout();referencePanel.scrollIntoView({block:'nearest'});toast('请核对旧参考是否属于当前商品；不符请移除或更换后重新规划。');return}approvalPrompt.value=project?.production_prompt||'';approvalInputs.textContent=inputDescription();showApprove();approvalPrompt.setSelectionRange(0,0);approvalPrompt.scrollTop=0};
 const conversation=$('conversation'),director=conversation.closest('.director');let conversationProject=null,conversationTouched=false,conversationPinned=true,conversationResizing=false;
 const jumpLatest=action('↓',()=>{conversation.scrollTop=conversation.scrollHeight;conversation.focus({preventScroll:true});syncConversationJump()});jumpLatest.id='conversationJumpLatest';jumpLatest.hidden=true;jumpLatest.setAttribute('aria-label','回到最新消息');jumpLatest.title='回到最新消息';conversation.tabIndex=-1;director.append(jumpLatest);
 function syncConversationJump(){const gap=conversation.scrollHeight-conversation.clientHeight-conversation.scrollTop;jumpLatest.hidden=!project||gap<60||!!document.activeElement?.closest('.director-question-editor');const d=director.getBoundingClientRect(),c=conversation.getBoundingClientRect();jumpLatest.style.bottom=Math.max(12,d.bottom-c.bottom+12)+'px'}
 conversation.addEventListener('scroll',()=>{conversationPinned=conversation.scrollHeight-conversation.clientHeight-conversation.scrollTop<60;syncConversationJump()},{passive:true});
 conversation.addEventListener('focusin',syncConversationJump);conversation.addEventListener('focusout',()=>requestAnimationFrame(syncConversationJump));
 director.addEventListener('pointerdown',()=>conversationTouched=true,{passive:true});conversation.addEventListener('wheel',()=>conversationTouched=true,{passive:true});conversation.addEventListener('keydown',()=>conversationTouched=true);
 document.addEventListener('creative-conversation-layout-start',()=>{conversationTouched=true;conversationResizing=true});
 document.addEventListener('creative-conversation-layout-end',()=>{conversationResizing=false;conversationPinned=conversation.scrollHeight-conversation.clientHeight-conversation.scrollTop<60;syncConversationJump()});
 const settleConversation=()=>{if(!conversationResizing&&(!conversationTouched||conversationPinned))conversation.scrollTop=conversation.scrollHeight;syncConversationJump()};new ResizeObserver(settleConversation).observe(conversation);document.fonts?.ready.then(settleConversation);
 function captureConversation(){
  if(conversationProject!==project?.id)return null;
  const top=conversation.getBoundingClientRect().top,anchor=[...conversation.querySelectorAll('[data-conversation-key]')].find(e=>e.getBoundingClientRect().bottom>top),focused=document.activeElement;
  return {bottom:conversation.scrollHeight-conversation.clientHeight-conversation.scrollTop<60&&!focused.matches('.conversation-execution summary'),top:conversation.scrollTop,anchor:anchor?.dataset.conversationKey,offset:anchor?anchor.getBoundingClientRect().top-top:0,field:conversation.contains(focused)&&focused.matches('textarea')?{label:focused.getAttribute('aria-label'),start:focused.selectionStart,end:focused.selectionEnd}:null,executionFocus:conversation.contains(focused)&&focused.matches('.conversation-execution summary')?focused:null,questionFocus:conversation.contains(focused)&&focused.matches('.question-answer-toggle,.question-answer-done')?{key:focused.closest('.question')?.dataset.conversationKey,selector:focused.matches('.question-answer-toggle')?'.question-answer-toggle':'.question-answer-done'}:null,basis:!!conversation.querySelector('.director-context details[open]')};
 }
 function restoreConversation(saved){
  conversationProject=project?.id;if(!saved)conversationTouched=false;conversationPinned=!saved||saved.bottom;
  if(saved?.basis){const details=conversation.querySelector('.director-context details');if(details)details.open=true}
  if(saved?.field){const field=[...conversation.querySelectorAll('textarea')].find(e=>e.getAttribute('aria-label')===saved.field.label);if(field&&!field.disabled){field.focus({preventScroll:true});field.setSelectionRange(saved.field.start,saved.field.end)}}
  if(saved?.executionFocus?.isConnected)saved.executionFocus.focus({preventScroll:true});
  if(saved?.questionFocus){const card=[...conversation.querySelectorAll(':scope > .question')].find(e=>e.dataset.conversationKey===saved.questionFocus.key),control=card?.querySelector(saved.questionFocus.selector);if(control&&!control.disabled&&control.checkVisibility())control.focus({preventScroll:true})}
  if(!saved||saved.bottom)conversation.scrollTop=conversation.scrollHeight;
  else{const anchor=[...conversation.querySelectorAll('[data-conversation-key]')].find(e=>e.dataset.conversationKey===saved.anchor);conversation.scrollTop=anchor?conversation.scrollTop+anchor.getBoundingClientRect().top-conversation.getBoundingClientRect().top-saved.offset:saved.top}
  syncConversationJump();
 }
 const oldDraw=draw;draw=function(){const saved=captureConversation();oldDraw();paintModels();syncEntry();syncConversationList();syncDirectorContext();syncPromptNode();syncInputs();syncCreativeStatus();restoreConversation(saved)};const oldBusy=setBusy;setBusy=function(value){oldBusy(value);paintModels();syncEntry();syncCreativeStatus();syncComposerReferences();syncReferenceActions()};
 window.addEventListener('focus',()=>{if(project&&!busy&&!hasDrafts())refreshProjectStatus().then(()=>schedule())});
 let modelCatalogLoading=false;
 document.addEventListener('creative-reload-model-catalog',()=>loadModels());
 function modelCatalogState(state){for(const select of [videoSelect,imageSelect])select.dataset.catalogState=state}
 async function loadModels(){if(modelCatalogLoading)return;modelCatalogLoading=true;modelCatalogState('loading');try{const c=await api('/models');videos=c.models;images=c.image_models||[];catalogStatus.textContent=c.status_note||'模型可选表示已接入；尚未核验供应商实时健康、余额与排队情况。';modelList.replaceChildren();for(const [select,items] of [[videoSelect,videos],[imageSelect,images]])select.replaceChildren(...items.map(m=>{const suffix=m.available===false?' · 未接入':m.provider&&!m.single_film?` · ${m.limitation||'能力待确认'}`:'';const o=make('option',m.label+suffix);o.value=m.id;o.dataset.description=m.description||'';o.disabled=m.available===false||!!m.provider&&!m.single_film;return o}));imageSelect.value=sessionStorage.getItem('creative-image-model')||images[0]?.id;for(const m of [...videos,...images]){const card=make('article');const cost=m.provider?`${m.credits_per_5s??'费用待读取'} 平台积分 / 5 秒`: '1 平台积分 / 张';const capability=m.provider?`${m.audio?'原生音频':'静音视频'} · ${m.single_film?'15 秒整片可用':m.limitation||'能力待确认'}`:`${m.mode==='both'?'文字 / 参考图生成':m.mode==='edit'?'编辑当前商品参考图':'文字生成图片'} · ${m.available?'已接入':m.limitation||'当前不可用'}`;const title=make('h3');title.className='model-card-title';title.append(window.studioModelLogo(m.id),make('span',m.label));card.append(title,make('p',m.id),make('p',`${cost} · ${capability}`));card.dataset.model=m.id;card.dataset.available=String(m.available!==false);if(m.available===false)card.classList.add('model-unavailable');const health=make('p',m.service_status==='unchecked'||!m.service_status?'服务状态：实时健康未核验':'服务状态：'+({healthy:'最近检查可用',unavailable:'最近检查不可用'}[m.service_status]||'实时健康未核验'),'muted');health.classList.add('model-health');card.append(health);modelList.append(card)}modelsLoaded=true;decorateImages();paintModels();syncEntry();syncReferenceActions();modelCatalogState('ready')}catch(e){modelCatalogState('error');modelNote.textContent='模型列表读取失败';modelNote.append(action('重新读取',()=>loadModels()))}finally{modelCatalogLoading=false}}
 async function checkModelStatus(){
  checkStatusButton.disabled=true;checkStatusButton.textContent='正在检查…';
  try{const result=await api('/model-status');catalogStatus.textContent=result.status_note;
   const labels={reachable:'制作服务已连通',busy:'服务已连通 · 正在处理任务',unavailable:'制作服务暂不可达',unconfigured:'尚未配置制作服务'};
   for(const m of result.models){const card=[...modelList.children].find(c=>c.dataset.model===m.id);if(!card)continue;
    const time=m.checked_at?new Date(m.checked_at*1000).toLocaleTimeString():'';
    card.querySelector('.model-health').textContent=`${labels[m.service_status]||'服务状态未核验'}${time?' · '+time:''} · 供应商授权与余额未核验`;
   }
  }catch(e){catalogStatus.textContent='服务检查失败，请稍后重试。未发起任何生成。'}
  finally{checkStatusButton.disabled=false;checkStatusButton.textContent='重新检查制作服务'}
 }
 // Reference answers are executable actions, not just interview option text.
 const referenceQuestion=q=>/参考图|商品图|产品图|截图|logo|品牌色|素材/i.test(q?.question||'');
 const asksForImage=text=>/^(?:请|直接|先|就|那|帮我|替我|你|给我|让agent|agent|来|吧|，|,|\s)*(?:生成|生|画|做|设计)(?:一[个张幅份套]|个|张)?(?:参考图|概念图|图片|图|logo|标志)?(?:出来|就行|吧|即可|。|！|!|\s)*$/i.test(text.trim());
 const directorImageReferences=()=> (project?.video_inputs?.references||[]).map(({asset,role,instruction})=>({asset,role,instruction:instruction||''}));
 function directorImageLimitation(model,refs){
  if(!model?.available)return '图片模型暂不可用';
  if(!refs.length&&model.mode==='edit')return '此图片模型需要参考图，请先上传';
  if(refs.length&&model.mode==='text')return '此模型仅支持文字生图，请选择支持参考图的模型';
  if(refs.length>Math.min(3,model.max_references??(model.mode==='edit'?1:0)))return '已绑定参考图超过图片模型上限，请先调整参考输入';
  if(refs.length&&refs.length<(model.min_edit_references||1))return '此图片模型需要更多参考图';
  return '';
 }
 function generateQuestionReference(question,produce=false){
  if(!project||isLocked()||hasDrafts())return toast('请先完成当前处理或保存画布草稿');
  const model=images.find(m=>m.id===imageSelect.value);
  const references=directorImageReferences(),limitation=directorImageLimitation(model,references);
  if(limitation)return toast(limitation);
  const context=[answerText(),$('message').value.trim()].filter(Boolean).join('\n\n');
  if(context.length>5000)return toast('回答内容过长，请精简后再生成');
  let videoCredits;
  if(produce){
   videoCredits=(videos.find(m=>m.id===project.model)?.credits_per_5s||0)*(project.duration/5);
   if(project.approval_mode!=='auto'||!videoCredits)return toast('请开启自动审批并读取视频模型费用');
   if(!confirm(`授权本次连续制作：1 张概念参考图（${model.label}，1 积分）＋1 支 ${project.duration} 秒广告（${project.quote?.label||project.model}，${videoCredits} 积分），总上限 ${1+videoCredits} 积分。Agent 将按现有回答和合理假设规划，自动绑定参考并制作。失败停止，不自动重试或换模型。`))return;
  }
  const brief=Object.values(project.brief||{}).filter(v=>typeof v==='string').join('；');
  const request=`为广告制作一张丰富、清晰的概念视觉参考图。创作背景：${brief||project.messages?.find(m=>m.role==='user')?.content||'商品广告'}。当前需要：${question?.question||'广告视觉方向'}。用户补充：${context}。这是一张新创作的概念参考，不是实际品牌Logo或真实应用截图；表现人物、场景、材质、色彩和光线，屏幕留空，不绘制可读界面、标识或文字，文字将在后期制作。`.slice(0,4000);
  document.dispatchEvent(new CustomEvent('creative-compose-image',{detail:{direct:true,director_reference:true,model:model.id,prompt:request,references,director_context:context,...(produce?{director_video_credits:videoCredits}:{}),answerKeys:(project.questions||[]).map(answerKey),message:$('message').value}}));
 }
 window.handleDirectorReferenceIntent=()=>{
  if(project?.creation_mode!=='agent')return false;
  const q=(project.questions||[]).find(q=>referenceQuestion(q)&&asksForImage(answers.get(answerKey(q))||''));
  const message=$('message').value.trim(),current=(project.questions||[]).find(referenceQuestion);
  if(q||(asksForImage(message)&&(current||/参考图|概念图|图片|logo/i.test(message)))){generateQuestionReference(q||current);return true}
  return false;
 };
 function openDirectorUpload(question=null){
  if(!project||isLocked()||hasDrafts())return toast('请先完成当前处理或保存画布草稿');
  const pid=project.id,dialog=make('dialog');dialog.id='directorReferenceUpload';
  const label=make('label','图片用途'),role=make('select');role.setAttribute('aria-label','上传图片用途');
  for(const [value,text]of Object.entries({product:'商品 / 品牌 / 应用截图',person:'人物',scene:'场景',style:'视觉风格'})){const o=make('option',text);o.value=value;role.append(o)}label.append(role);
  const file=make('input');file.type='file';file.accept='image/png,image/jpeg,image/webp';file.multiple=true;file.setAttribute('aria-label','选择参考图片');
  const state=make('p','选择图片后会加入画布，并绑定到视频参考输入。');state.setAttribute('role','status');
  let uploading=false,pending=[];
  const close=action('关闭',()=>dialog.close()),retry=action('重新绑定已上传的图片',()=>bind());retry.hidden=true;
  const bind=async()=>{if(uploading||!pending.length)return;uploading=true;setBusy(true);file.disabled=close.disabled=role.disabled=retry.disabled=true;try{
   if(project?.id!==pid)throw Error('项目已切换，请回到原项目核对图片');
   project=await api('/projects/'+pid+'/director-references','POST',{revision:project.revision,references:pending});
   if(question)answers.set(answerKey(question),'参考图已上传并绑定视频输入，请使用当前参考继续创作');
   pending=[];clearMedia();draw();dialog.close();toast('参考图已加入画布并绑定视频输入；其他回答已保留。');
  }catch(e){state.textContent=e.message+'。文件已保存，可在画布素材中找到；调整参考设置后可重新绑定。';retry.hidden=false}
  finally{uploading=false;file.disabled=close.disabled=role.disabled=retry.disabled=false;setBusy(false)}};
  file.onchange=async()=>{const files=[...file.files];if(!files.length)return;if(files.length>6){state.textContent='一次最多选择六张图片';file.value='';return}if(uploading||pending.length)return;
   uploading=true;setBusy(true);file.disabled=close.disabled=role.disabled=true;
   try{for(const [i,item]of files.entries()){
    if(project?.id!==pid)throw Error('项目已切换');state.textContent=`正在上传 ${i+1}/${files.length}…`;
    const response=await fetch(`/creative/api/projects/${pid}/canvas/assets?kind=image&revision=${project.revision}`,{method:'POST',headers:{Authorization:'Bearer '+key,'Content-Type':item.type},body:item});
    const data=await response.json().catch(()=>({}));if(!response.ok)throw Error(typeof data.detail==='string'?data.detail:'上传未完成');
    if(project?.id!==pid)throw Error('项目已切换，图片保存在原项目');project=data.project;
    pending.push({asset:data.asset.id,role:role.value,instruction:question?question.question.slice(0,240):''});
   }}catch(e){state.textContent=e.message;retry.hidden=!pending.length;return}
   finally{uploading=false;file.disabled=close.disabled=role.disabled=false;file.value='';setBusy(false);draw()}
   await bind();
  };
  dialog.addEventListener('cancel',e=>{if(uploading)e.preventDefault()});dialog.addEventListener('close',()=>dialog.remove());
  dialog.append(make('h3','上传参考图'),label,file,state,retry,close);document.body.append(dialog);dialog.showModal();
 }
 const referenceActions=make('div',null,'director-reference-actions'),referenceImageModel=make('select');referenceImageModel.setAttribute('aria-label','Agent 参考图模型');
 referenceImageModel.onchange=()=>{imageSelect.value=referenceImageModel.value;imageSelect.onchange()};
 const uploadAction=action('上传参考图',()=>openDirectorUpload()),generateAction=action('Agent 生图 · 1 积分',()=>generateQuestionReference((project?.questions||[]).find(referenceQuestion)));
 const produceAction=action('参考图＋成片',()=>generateQuestionReference((project?.questions||[]).find(referenceQuestion),true));
 const imageInputStatus=make('small');imageInputStatus.setAttribute('role','status');
 referenceActions.append(uploadAction,referenceImageModel,generateAction,produceAction,imageInputStatus);$('chatForm').prepend(referenceActions);
 function syncReferenceActions(){referenceActions.hidden=project?.creation_mode!=='agent';
  const refs=directorImageReferences();
  referenceImageModel.replaceChildren(...images.map(m=>{const why=directorImageLimitation(m,refs),o=make('option',m.label+(why?' · 不适用':''));o.value=m.id;o.disabled=!!why;o.title=why;return o}));referenceImageModel.value=imageSelect.value;
  uploadAction.disabled=isLocked();referenceImageModel.disabled=isLocked()||!modelsLoaded;const spec=images.find(m=>m.id===imageSelect.value),limitation=directorImageLimitation(spec,refs);generateAction.disabled=isLocked()||!modelsLoaded||!!limitation;
  imageInputStatus.textContent=modelsLoaded?(limitation|| (refs.length?`生图将使用 ${refs.length} 张已绑定参考`:'未绑定图片，将按文字生成概念参考')):'正在读取图片模型';
  produceAction.hidden=project?.approval_mode!=='auto';produceAction.disabled=generateAction.disabled;
  const cost=(videos.find(m=>m.id===project?.model)?.credits_per_5s||0)*((project?.duration||0)/5);
  produceAction.textContent='参考图＋成片'+(cost?' · '+(1+cost)+' 积分':'');produceAction.disabled||=!cost;
 }
 const openQuestionEditors=new Set(),closedQuestionEditors=new Set();
 function syncQuestionControls(){
  const currentKeys=new Set((project?.questions||[]).map(answerKey));for(const set of [openQuestionEditors,closedQuestionEditors])for(const key of set)if(!currentKeys.has(key))set.delete(key);
  conversation.querySelectorAll(':scope > .question').forEach((card,index)=>{
   const question=project?.questions?.[index],input=card.querySelector('textarea'),choices=card.querySelector('.choices');if(!question||!input||!choices||card.dataset.compactQuestion)return;
   const key=answerKey(question),why=card.querySelector(':scope>p'),editor=make('div',null,'director-question-editor'),toggle=action('',()=>setOpen(editor.hidden,true)),done=action('完成',()=>setOpen(false,true));card.dataset.compactQuestion='true';editor.id='directorQuestionAnswer-'+index;toggle.className='question-answer-toggle';toggle.setAttribute('aria-controls',editor.id);done.className='question-answer-done';
   const syncAnswer=()=>{const value=input.value.trim();toggle.textContent=value||'回答…';toggle.classList.toggle('has-answer',!!value);toggle.setAttribute('aria-label',(value?'修改回答：':'回答：')+question.question);toggle.disabled=input.disabled;done.textContent=referenceQuestion(question)&&asksForImage(value)?'生成参考图 · 1 积分':'完成';};
   done.onclick=()=>{if(referenceQuestion(question)&&asksForImage(input.value))generateQuestionReference(question);else setOpen(false,true)};
   if(referenceQuestion(question)){const actions=make('div',null,'director-reference-actions');actions.append(action('上传参考图',()=>openDirectorUpload(question)),action('Agent 生成概念参考 · 1 积分',()=>generateQuestionReference(question)));editor.append(actions);
    [...choices.children].forEach(b=>{if(/^(?:只)?上传/.test(b.textContent))b.onclick=()=>openDirectorUpload(question)});
   }
   function setOpen(open,focus=false){if(focus){if(open)closedQuestionEditors.delete(key);else closedQuestionEditors.add(key)}editor.hidden=!open;toggle.setAttribute('aria-expanded',String(open));if(open)openQuestionEditors.add(key);else openQuestionEditors.delete(key);if(focus){if(open){input.focus({preventScroll:true});input.setSelectionRange(input.value.length,input.value.length);input.scrollIntoView({block:'nearest'})}else toggle.focus({preventScroll:true})}syncConversationJump()}
   if(why)editor.append(why);editor.append(choices,input,done);card.append(toggle,editor);syncAnswer();setOpen(openQuestionEditors.has(key)||(!input.value.trim()&&!closedQuestionEditors.has(key)));
   input.addEventListener('input',syncAnswer);choices.addEventListener('click',e=>{if(e.target.closest('button')){syncAnswer();setOpen(false,true)}});editor.addEventListener('keydown',e=>{if(e.key==='Escape'){e.preventDefault();e.stopPropagation();setOpen(false,true)}});
  });
 }
 function syncDirectorContext(){
  const conversation=$('conversation');conversation.querySelector('.director-context')?.remove();
  syncReferenceActions();if(!project)return;
  syncQuestionControls();
  const box=make('section',null,'director-context');box.setAttribute('aria-label','本轮导演创作依据');
  const progress=make('p',null,'director-question-progress');progress.setAttribute('role','status');
  const updateProgress=()=>{const total=(project.questions||[]).length,filled=(project.questions||[]).filter(q=>(answers.get(answerKey(q))||'').trim()).length;
   progress.textContent=total?`已询问 · ${total} 项 · ${filled} 项已答`:'整片方案已形成 · 可在时间轴修改画面与声音';
   if(project.state==='completed'&&project.artifact)progress.hidden=true;
   else if(project.state==='planning')progress.textContent='导演正在整理需求与拍摄方案';
   else if(!total&&!project.shots?.length)progress.textContent='补充商品事实与投放目标，导演将整理关键问题';
  };box.append(progress);updateProgress();
  const deliveries=project.workspace_deliveries||[];
  if(deliveries.length){const section=make('section',null,'director-workspace-delivery'),pending=deliveries.filter(item=>item.state==='pending').length,failed=deliveries.filter(item=>item.state==='needs_review').length;
   section.setAttribute('aria-label','Agent 素材回传主画布');section.append(make('p',`主画布素材：${deliveries.filter(item=>item.state==='delivered').length} 项已同步${pending?' · '+pending+' 项等待同步':''}${failed?' · '+failed+' 项待处理':''}`));
   if(pending)section.append(make('small','服务器会继续同步已生成素材，可以关闭此页面。'));
   if(failed){section.append(make('p','请检查主画布空间与来源素材。已生成文件保留在当前项目。'));const retry=action('重新同步素材',async()=>{retry.disabled=true;try{project=await api('/projects/'+project.id+'/workspace-delivery/retry','POST',{revision:project.revision});draw();schedule()}catch(e){toast(e.message)}finally{retry.disabled=false}});retry.disabled=isLocked();section.append(retry)}
   box.append(section);
  }
  const liveInputs=project.video_inputs,liveRefs=liveInputs?.references||[],liveManifest=project.input_manifest;
  if(liveInputs||liveManifest){
   const live=make('section',null,'director-live-inputs');live.setAttribute('aria-label','当前画布实际输入');
   const mode=liveInputs?.mode||liveManifest?.mode||'text';
   const modeLabel=({text:'文字生成',first_frame:'首帧',first_last:'首尾帧',references:'多图参考'})[mode]||'视频输入';
   const images=liveManifest?.images?.length||liveRefs.length;
   const state=project.video_inputs_needs_review||project.reference_needs_review?'待核对':'已同步';
   const source=liveInputs?.source_project?' · 已绑定视频节点':'';
   live.append(make('strong','当前画布实际输入'),make('p',`${modeLabel} · ${images} 张图片 · ${state}${source}`));
   if(liveRefs.length)live.append(make('p',`参考节点已绑定 ${liveRefs.length} 项，生成时将使用这些输入。`));
   box.append(live);
  }
  const decisions=project.decisions||[],assumptions=project.assumptions||[];
  if(decisions.length||assumptions.length){const detail=make('details'),summary=make('summary',`本轮创作依据 · ${decisions.length} 项决策${assumptions.length?' · '+assumptions.length+' 项假设待确认':''}`);detail.append(summary);
   for(const d of decisions){const item=make('div',null,'director-basis');item.append(make('strong',d.title),make('p',d.reason));detail.append(item)}
   if(assumptions.length){detail.append(make('strong','待确认的假设'));for(const a of assumptions)detail.append(make('p',a,'director-assumption'));detail.append(make('p','若假设不符，请在下方纠正，导演会更新方案。'))}
   box.append(detail);
  }
  const firstQuestion=conversation.querySelector(':scope > .question');
  if(firstQuestion)firstQuestion.before(box);else{const result=conversation.querySelector('.conversation-film-receipt');if(result)result.before(box);else conversation.append(box)}
  conversation.oninput=updateProgress;conversation.onclick=updateProgress;
 }
 document.addEventListener('creative-director-context',()=>syncDirectorContext());
 // Message context is a server-recorded snapshot, never inferred from today's inputs.
 const historyPreviewDialog=make('dialog',null,'message-reference-dialog');historyPreviewDialog.id='messageReferenceDialog';
 const historyPreviewTitle=make('strong'),historyPreviewState=make('p'),historyPreviewImage=make('img');historyPreviewImage.alt='历史参考';
 const historyPreviewHead=make('div',null,'message-reference-head');historyPreviewHead.append(historyPreviewTitle,action('关闭',()=>historyPreviewDialog.close()));historyPreviewDialog.append(historyPreviewHead,historyPreviewState,historyPreviewImage);document.body.append(historyPreviewDialog);
 let historyPreviewProject=null,historyPreviewController=new AbortController(),historyPreviewToken=0;const historyPreviewCache=new Map(),historyPreviewTasks=new WeakMap();
 const historyPreviewObserver=new IntersectionObserver(entries=>{for(const item of entries)if(item.isIntersecting){historyPreviewObserver.unobserve(item.target);historyPreviewTasks.get(item.target)?.()}},{root:conversation,rootMargin:'80px'});
 historyPreviewDialog.addEventListener('close',()=>{historyPreviewToken++;historyPreviewImage.removeAttribute('src')});
 historyPreviewImage.onerror=()=>{if(historyPreviewDialog.open&&historyPreviewImage.getAttribute('src'))historyPreviewState.textContent='历史参考无法显示。关闭后可重新打开重试。'};
 function resetHistoryPreviews(){historyPreviewObserver.disconnect();if(historyPreviewProject===project?.id)return;historyPreviewController.abort();historyPreviewController=new AbortController();for(const entry of historyPreviewCache.values())if(entry.url)URL.revokeObjectURL(entry.url);historyPreviewCache.clear();historyPreviewProject=project?.id;historyPreviewToken++;if(historyPreviewDialog.open)historyPreviewDialog.close();historyPreviewImage.removeAttribute('src')}
 function historicalImage(pid,index,slot,ref,retry=false){const cacheKey=JSON.stringify([pid,index,slot,ref]);let entry=historyPreviewCache.get(cacheKey);if(retry&&entry?.failed){historyPreviewCache.delete(cacheKey);entry=null}if(entry)return entry.promise;entry={url:null,failed:false};const signal=historyPreviewController.signal;
  entry.promise=fetch(`/creative/api/projects/${encodeURIComponent(pid)}/messages/${index}/references/${slot}`,{headers:{Authorization:'Bearer '+key},signal:AbortSignal.any([signal,AbortSignal.timeout(15000)])}).then(async response=>{if(!response.ok)throw Error();const blob=await response.blob();if(signal.aborted||historyPreviewProject!==pid)return null;entry.url=URL.createObjectURL(blob);return entry.url}).catch(()=>{entry.failed=true;return null});historyPreviewCache.set(cacheKey,entry);return entry.promise;
 }
 async function openHistoricalReference(pid,index,slot,ref){if(project?.id!==pid)return;const token=++historyPreviewToken;historyPreviewTitle.textContent=ref.label||'历史参考';historyPreviewState.textContent='正在读取发送消息时的参考图…';historyPreviewImage.removeAttribute('src');historyPreviewDialog.showModal();const url=await historicalImage(pid,index,slot,ref,true);if(token!==historyPreviewToken||project?.id!==pid||!historyPreviewDialog.open)return;if(url){historyPreviewImage.src=url;historyPreviewImage.alt=ref.label||'历史参考';historyPreviewState.textContent='发送消息时的视频参考；查看不会更改当前输入。'}else historyPreviewState.textContent='历史参考暂不可读取。关闭后可重新打开重试。'}
 function contextIcon(kind){const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');for(const [name,value] of Object.entries({viewBox:'0 0 24 24',fill:'none',stroke:'currentColor','stroke-width':'1.6','stroke-linecap':'round','stroke-linejoin':'round','aria-hidden':'true'}))svg.setAttribute(name,value);const path=document.createElementNS(svg.namespaceURI,'path');path.setAttribute('d',kind==='model'?'m12 3 9 5v8l-9 5-9-5V8Z M3 8l9 5 9-5M12 13v8':'M6 3h13v18H6Z M3 6h3M3 10h3M3 14h3M3 18h3M10 8h5M10 12h5');svg.append(path);return svg}
 function messageContext(el,index){const snapshot=project?.message_contexts?.[String(index)];if(snapshot?.schema_version!==1||project?.messages?.[index]?.role!=='user')return;const pid=project.id,header=make('div',null,'message-context-tags');header.setAttribute('aria-label','发送时的创作配置');
  for(const [kind,label,detail] of [['skill',snapshot.skill?.title,snapshot.skill?.version?'版本 '+snapshot.skill.version:''],['model',snapshot.model?.label||snapshot.model?.id,'视频模型']])if(label){const tag=make('span',null,'message-context-tag');tag.append(contextIcon(kind),make('span',label));tag.title=label+(detail?' · '+detail:'')+' · 发送时的选择';header.append(tag)}
  if(snapshot.needs_review){const pending=make('span','参考待核对','message-context-pending');pending.title='发送此消息时，参考图尚待核对';header.append(pending)}
  header.title=`发送时：${snapshot.aspect||''} · ${snapshot.duration||''} 秒 · ${snapshot.approval_mode==='auto'?'自动审批':'手动审批'}`;
  const refs=make('div',null,'message-context-references');
  for(const [slot,ref] of (snapshot.references||[]).slice(0,7).entries()){const name=ref.label||'参考图片',chip=action('',()=>openHistoricalReference(pid,index,slot,ref)),img=make('img');chip.className='message-context-reference';chip.setAttribute('aria-label','查看历史参考 '+name);const frame=snapshot.video_input_mode==='first_last'?(slot?'尾帧':'首帧'):snapshot.video_input_mode==='first_frame'?'首帧':`参考 ${slot+1}`;chip.title=frame+' · '+name+' · 发送时的视频参考';img.alt='';img.onerror=()=>{if(img.isConnected){chip.classList.add('preview-unavailable');chip.title+=' · 预览无法显示'}};chip.append(img,make('span',name));refs.append(chip);const load=()=>historicalImage(pid,index,slot,ref).then(url=>{if(!img.isConnected||project?.id!==pid)return;if(url)img.src=url;else{chip.classList.add('preview-unavailable');chip.title+=' · 预览暂不可读取'}});historyPreviewTasks.set(img,load);historyPreviewObserver.observe(img)}
  const body=el.querySelector(':scope>div');if(header.childElementCount)el.insertBefore(header,body);if(refs.childElementCount)el.append(refs);
 }
 // Keep execution history separate: historical messages have no event timestamps.
 const executionLog=make('section',null,'conversation-execution');executionLog.id='conversationExecution';executionLog.setAttribute('aria-label','项目执行记录');
 const executionHistory=make('details',null,'conversation-execution-history'),executionSummary=make('summary'),executionRows=make('div'),executionLive=make('div',null,'conversation-execution-live'),executionLabel=make('span'),executionPercent=make('span'),executionMeter=make('progress'),executionNote=make('small');
 executionHistory.open=false;executionHistory.append(executionSummary,executionRows);executionLive.append(executionLabel,executionPercent,executionMeter,executionNote);executionLog.append(executionHistory,executionLive);executionLive.setAttribute('role','status');executionLive.setAttribute('aria-live','polite');executionMeter.max=100;executionMeter.setAttribute('aria-label','视频服务返回的生成进度');
 let executionProject=null,executionDisclosureTouched=false;const executionEntries=new Map();
 executionSummary.addEventListener('click',()=>{executionDisclosureTouched=true});
 const executionKinds={
  planning_started:['导演开始整理方案','正在根据已经提供的商品信息、参考和要求规划。'],
  questions_ready:['关键问题已整理','导演已返回需要补充的信息，可在对话中回答。'],
  plan_ready:['拍摄方案已形成','画面、声音与时间轴已返回；后续修改会形成新的方案。'],
  planning_failed:['方案整理未完成','本次规划已停止，已经接受的上下文保留。'],
  execution_approved:['本版制作已确认','制作确认已记录；任务是否被视频服务接收，以后续记录为准。'],
  submit_requested:['已请求生成视频','生成请求已开始提交，不表示视频服务已经接收。'],
  generation_accepted:['生成任务已接收','视频服务已返回任务标识，继续查询同一个任务。'],
  provider_callback_received:['已收到任务通知','通知已记录，最终结果仍需查询和素材检查确认。'],
  source_passed:['源视频检查通过','源素材已取得并通过该次技术检查；商品、动作和口播仍需看成片核对。'],
  render_started:['开始合成成片','保留源音视频，按当前方案渲染后期字幕。'],
  technical_passed:['成片技术检查通过','成片已完成技术检查，等待人工审阅；这不代表创意或商品一致性已通过。'],
  execution_stopped:['本次制作已停止','进度已经保留，可打开制作详情查看状态；不会自动重新生成。'],
  stop_requested:['已请求停止后续制作','停止请求已记录，已提交任务的状态仍需继续查询。'],
  paused:['后续制作已暂停','已经保存的结果保留。'],
  human_approved:['已记录人工确认','这次人工审阅已记录；独立审阅和训练资格仍按原有规则检查。'],
  changes_requested:['已收到修改意见','修改意见已保存，可继续调整。']
 };
 function syncExecutionState(){
  const state=project?.state,active=['planning','running','rendering'].includes(state),imageRunning=project?.image_task?.state==='running';
  if(!executionDisclosureTouched)executionHistory.open=false;
  executionLive.hidden=!project||(!active&&!imageRunning&&!syncFailures&&!project.interrupted&&!['completed','failed','planning_failed','paused'].includes(state));
  if(state==='completed'&&project.artifact&&!imageRunning&&!syncFailures&&!project.interrupted)executionLive.hidden=true;
  const title=project?.interrupted?'服务中断，等待恢复查询':imageRunning?'参考图生成中':state==='planning_failed'?'方案整理未完成':taskTitle.textContent;
  const label=syncFailures?'连接中断 · 正在重连':title;if(executionLabel.textContent!==label)executionLabel.textContent=label;
  const target=project?.film||project?.shots?.find(s=>s.provider_resolution),value=(target?.provider_poll?.progress||target?.progress||{}).percent;
  const percent=state==='running'&&target?.provider_resolution==='polling'&&!imageRunning&&!syncFailures&&!project?.interrupted&&Number.isFinite(value)&&value>=0&&value<=100?value:null;
  // A provider often reports a task id before it reports a numeric percentage.
  // Keep the progress surface visible and use the native indeterminate state
  // instead of making a submitted production look idle.
  const showProgress=!syncFailures&&!project?.interrupted&&(active||imageRunning);
  const percentage=percent===null?(showProgress?'同步中':''):percent+'%';if(executionPercent.textContent!==percentage)executionPercent.textContent=percentage;
  executionMeter.hidden=!showProgress;
  if(percent!==null){executionMeter.value=percent;executionMeter.setAttribute('aria-valuetext',percentage)}else{executionMeter.removeAttribute('value');executionMeter.removeAttribute('aria-valuenow');executionMeter.setAttribute('aria-valuetext','供应商未返回百分比，正在同步状态')}
  executionLive.classList.toggle('is-running',!syncFailures&&!project?.interrupted&&(active||imageRunning));
  const note=syncFailures?'状态暂未同步；正在查询原任务，不会重复生成。':project?.interrupted?'等待恢复原任务的查询，当前没有新的生成请求。':percent!==null?'视频服务返回的进度':active||imageRunning?'状态会自动刷新':'当前项目状态';if(executionNote.textContent!==note)executionNote.textContent=note;
  executionLog.hidden=!project||(!executionEntries.size&&executionLive.hidden);
 }
 function syncExecutionLog(){
  if(executionProject!==project?.id){executionProject=project?.id;executionEntries.clear();executionRows.replaceChildren();executionDisclosureTouched=false;executionHistory.open=false}
  const keys=new Set();for(const [index,event] of (project?.events||[]).entries()){
   const definition=Object.hasOwn(executionKinds,event.code)?executionKinds[event.code]:null;if(!definition)continue;
   const id=String(event.seq??index)+':'+event.code;keys.add(id);let row=executionEntries.get(id);
   if(!row){row=make('details',null,'conversation-execution-row');row.dataset.conversationKey='execution:'+id;row.dataset.eventCode=event.code;const summary=make('summary'),icon=make('span','↳','execution-icon'),title=make('span',definition[0]),time=make('time');icon.setAttribute('aria-hidden','true');summary.append(icon,title,time);row.append(summary,make('p',definition[1]));executionEntries.set(id,row);executionRows.append(row)}
   const date=new Date(event.time*1000),valid=Number.isFinite(event.time)&&event.time>0&&!Number.isNaN(date.getTime()),time=row.querySelector('time');time.textContent=valid?date.toLocaleTimeString('zh-CN',{hour12:false}):'';if(valid){time.dateTime=date.toISOString();time.title=date.toLocaleString('zh-CN')}else{time.removeAttribute('datetime');time.removeAttribute('title')}
  }
  for(const [id,row] of executionEntries)if(!keys.has(id)){row.remove();executionEntries.delete(id)}
  executionSummary.textContent='执行记录 · '+executionEntries.size;executionSummary.title='本项目已记录的操作，按发生顺序显示';executionHistory.hidden=!executionEntries.size;
  syncExecutionState();
  // Keep the live execution surface at the top of the Director conversation,
  // where it remains visible while the detailed event history grows below it.
  conversation.prepend(executionLog);
 }

 // A view-only completion receipt uses the current artifact and the existing player.
 const filmReceipt=make('section',null,'conversation-film-receipt');filmReceipt.id='conversationFilmReceipt';filmReceipt.setAttribute('aria-label','本次生成结果');
 const receiptTitle=make('strong','成片已生成'),receiptBody=make('div',null,'conversation-film-body'),receiptThumb=action('',()=>openReceiptFilm()),receiptPoster=make('canvas'),receiptPlaceholder=make('span','▷'),receiptInfo=make('div'),receiptMeta=make('p'),receiptStatus=make('p'),receiptNote=make('p',null,'conversation-film-note'),receiptActions=make('div',null,'conversation-film-actions');
 receiptThumb.className='conversation-film-thumbnail';receiptThumb.setAttribute('aria-label','查看生成成片');receiptPoster.hidden=true;receiptThumb.append(receiptPlaceholder,receiptPoster);receiptInfo.append(receiptMeta,receiptStatus);receiptBody.append(receiptThumb,receiptInfo);
 const receiptWatch=action('查看成片',()=>openReceiptFilm()),receiptEdit=action('智能剪辑',()=>{if(receiptCurrent())openInlineEditor()}),receiptReview=action('审阅成片',()=>{if(receiptCurrent()&&!$('reviewButton').disabled)$('reviewButton').click()});receiptActions.append(receiptWatch,receiptEdit,receiptReview);filmReceipt.append(receiptTitle,receiptBody,receiptNote,receiptActions);
 let receiptArtifact='',receiptProject='',receiptPainted=false,receiptDecoder=null,receiptTimer=null;
 function clearReceiptPoster(){clearTimeout(receiptTimer);if(receiptDecoder){receiptDecoder.onloadedmetadata=receiptDecoder.onseeked=receiptDecoder.onerror=null;receiptDecoder.pause();receiptDecoder.removeAttribute('src');receiptDecoder.load();receiptDecoder=null}receiptPainted=false;receiptPoster.hidden=true;receiptPlaceholder.hidden=false}
 function receiptCurrent(){return project?.state==='completed'&&!!project.artifact&&project.id===receiptProject&&project.artifact===receiptArtifact}
 function openReceiptFilm(){if(receiptCurrent())document.dispatchEvent(new CustomEvent('creative-view-current-film',{detail:{project:receiptProject,artifact:receiptArtifact}}))}
 function updateReceiptMedia(){
  if(!receiptCurrent())return;const player=$('video'),ready=player.readyState>=1&&!player.error;
  receiptMeta.textContent=[project.quote?.label||'视频',ready?`${player.videoWidth} × ${player.videoHeight}`:'',ready&&Number.isFinite(player.duration)?`${player.duration.toFixed(1)} 秒`:''].filter(Boolean).join(' · ');
  if(!receiptPainted&&!receiptDecoder&&ready&&player.getAttribute('src')){
   const artifact=receiptArtifact,pid=receiptProject,source=player.getAttribute('src'),decoder=document.createElement('video');receiptDecoder=decoder;decoder.muted=true;decoder.preload='auto';
   const current=()=>receiptDecoder===decoder&&receiptCurrent()&&receiptArtifact===artifact&&receiptProject===pid&&player.getAttribute('src')===source;
   const finish=()=>{if(receiptDecoder===decoder){clearTimeout(receiptTimer);receiptDecoder=null}decoder.onloadedmetadata=decoder.onseeked=decoder.onerror=null;decoder.pause();decoder.removeAttribute('src');decoder.load()};
   const capture=()=>{if(!current()){finish();return}try{receiptPoster.width=120;receiptPoster.height=Math.max(1,Math.round(120*decoder.videoHeight/decoder.videoWidth));receiptPoster.getContext('2d').drawImage(decoder,0,0,receiptPoster.width,receiptPoster.height);receiptPoster.hidden=false;receiptPlaceholder.hidden=true;receiptPainted=true}catch{}finish()};
   decoder.onloadedmetadata=()=>{if(current())decoder.currentTime=Math.min(.2,decoder.duration/2)};decoder.onseeked=capture;decoder.onerror=finish;receiptTimer=setTimeout(finish,8000);decoder.src=source;
  }
 }
 function syncFilmReceipt(){
  if(project?.state!=='completed'||!project.artifact){filmReceipt.remove();clearReceiptPoster();receiptProject='';receiptArtifact='';return}
  if(receiptProject!==project.id||receiptArtifact!==project.artifact){clearReceiptPoster();receiptProject=project.id;receiptArtifact=project.artifact}
  filmReceipt.dataset.conversationKey='result:'+project.artifact;receiptStatus.textContent=statusLabel(project.state,project.qa?.human);receiptNote.textContent=project.qa?.human==='approved'?'你已确认这一版可用。':'核对商品细节、动作与声音，确认后可继续剪辑或下载。';
  receiptEdit.disabled=busy||hasDrafts();receiptReview.disabled=$('reviewButton').disabled;conversation.append(filmReceipt);updateReceiptMedia();
 }
 for(const event of ['loadeddata','loadedmetadata','seeked'])$('video').addEventListener(event,()=>{updateReceiptMedia();settleConversation()});
 document.addEventListener('creative-status-sync',syncExecutionState);
 function syncConversationList(){
  // Keep the full conversation in chronological order; keys anchor reading across polling redraws.
  resetHistoryPreviews();conversation.querySelectorAll(':scope > .bubble').forEach((el,index)=>{el.dataset.conversationKey='message:'+index;messageContext(el,index)});
  conversation.querySelectorAll(':scope > .question').forEach((el,index)=>el.dataset.conversationKey='question:'+(project?.questions?.[index]?.id||index));
  syncExecutionLog();syncFilmReceipt();
 }
 const promptNode=make('section',null,'canvas-card compiled-prompt-node');promptNode.id='compiledPromptNode';
 const promptHead=make('div',null,'canvas-card-head');promptHead.append(make('strong','拍摄方案'));
 const promptBody=make('div',null,'canvas-card-body'),promptState=make('p',null,'prompt-state'),promptContent=make('p',null,'prompt-brief');promptContent.setAttribute('aria-label','拍摄方案摘要');
 const expandPrompt=action('查看完整提示词',()=>{openFilmReview();if(filmDialog.open){rawPrompt.open=true;filmText.scrollIntoView({block:'nearest'});filmText.focus()}});
 promptBody.append(promptState,promptContent,expandPrompt,action('修改分镜与声音',()=>{if(!project?.shots.length){$('message').focus();toast('补充要求后请导演生成分镜');return}document.body.classList.remove('inspector-folded');syncLayout();document.querySelector('.inspector').scrollTop=0;drawEditor();$('shotPrompt').focus()}));
 promptNode.append(promptHead,promptBody);document.querySelector('.canvas-world').append(promptNode);
 function syncPromptNode(){
  promptNode.hidden=expanded;
  const planned=!!project?.production_prompt&&!['intake','planning','planning_failed'].includes(project.state);
  promptState.textContent=planned?`${project.duration} 秒 · ${project.aspect} · ${project.shots?.length||0} 个节拍${hasDrafts()?' · 有未保存修改':''}`:'等待导演整理方案';
  promptContent.textContent=planned?([project.brief?.message,...(project.shots||[]).map(s=>s.title)].filter(Boolean).join(' · ')||'画面、声音与节奏已整理，可查看完整拍摄方案。'):[project?.brief?.product,project?.brief?.message].filter(Boolean).join(' · ')||'添加商品与创作要求，和导演一起完成拍摄方案。';

 }
 // Deterministic reframing uses the owned source and saves a separate canvas asset.
 const reframeDialog=make('dialog',null,'image-reframe-dialog');reframeDialog.id='imageReframeDialog';
 const reframeTitle=make('h2','裁剪图片'),reframeStage=make('div',null,'image-reframe-stage'),reframeCanvas=make('canvas'),reframeInfo=make('p',null,'image-reframe-info'),reframeControls=make('div',null,'image-reframe-controls'),reframeStatus=make('p',null,'image-reframe-status');
 reframeCanvas.setAttribute('aria-label','裁剪结果预览');reframeStage.append(reframeCanvas);reframeStatus.setAttribute('role','status');
 const reframeRatio=make('select');reframeRatio.setAttribute('aria-label','裁剪比例');for(const [value,title] of [['original','原比例'],['1','1:1'],['0.5625','9:16'],['1.7777777777777777','16:9'],['0.75','3:4'],['1.3333333333333333','4:3']]){const o=make('option',title);o.value=value;reframeRatio.append(o)}
 const cropRange=(label,min,max,value)=>{const wrap=make('label',label),input=make('input');input.type='range';input.min=min;input.max=max;input.value=value;input.setAttribute('aria-label',label);wrap.append(input);reframeControls.append(wrap);return input};
 reframeControls.append(make('label','画幅'));reframeControls.append(reframeRatio);const cropZoom=cropRange('裁剪放大',100,400,100),cropX=cropRange('水平位置',0,100,50),cropY=cropRange('垂直位置',0,100,50);
 let cropSession=null,cropImage=null,cropRotation=0,cropMirror=false,cropSaving=false,cropLoad=0,cropRequest=null;
 const cropRotate=action('旋转 90°',()=>{cropRotation=(cropRotation+90)%360;paintCrop()}),cropFlip=action('水平镜像',()=>{cropMirror=!cropMirror;cropFlip.setAttribute('aria-pressed',String(cropMirror));paintCrop()}),cropReset=action('重置',()=>{cropRotation=0;cropMirror=false;cropFlip.setAttribute('aria-pressed','false');reframeRatio.value='original';cropZoom.value=100;cropX.value=cropY.value=50;paintCrop()});cropFlip.setAttribute('aria-pressed','false');
 const cropActions=make('div',null,'row'),cropClose=action('取消',()=>reframeDialog.close()),cropSave=action('另存到画布',async()=>{
  if(!cropSession||!cropImage||cropSaving)return;if(project?.id!==cropSession.project||project.revision!==cropSession.revision||hasDrafts()||isLocked()){reframeStatus.textContent='项目已变化，请重新打开裁剪。';return}
  const crop=calculateCrop(),params={asset:cropSession.asset,crop,rotation:cropRotation,mirror:cropMirror},signature=JSON.stringify(params);if(cropRequest?.signature!==signature)cropRequest={signature,id:opaqueId()};
  cropSaving=true;setBusy(true);setCropDisabled(true);reframeStatus.textContent='正在另存裁剪结果…';
  try{const r=await api('/projects/'+cropSession.project+'/image-reframe','POST',{...params,revision:cropSession.revision,request_id:cropRequest.id});if(project?.id===cropSession.project){project=r.project;clearMedia();draw();schedule()}reframeDialog.close();toast('裁剪版本已加入画布，原图已保留')}
  catch(e){reframeStatus.textContent=e.message+'；未确认保存成功时，可用相同参数重试。'}finally{cropSaving=false;setBusy(false);setCropDisabled(false)}
 });cropSave.className='primary';cropActions.append(cropClose,cropSave);const cropTransforms=make('div',null,'row');cropTransforms.append(cropRotate,cropFlip,cropReset);
 reframeDialog.append(reframeTitle,make('p','裁剪、旋转与镜像不消耗生成积分；另存新素材，保留原图。'),reframeStage,reframeInfo,cropTransforms,reframeControls,reframeStatus,cropActions);document.body.append(reframeDialog);
 function setCropDisabled(value){reframeDialog.querySelectorAll('button,input,select').forEach(e=>e.disabled=value);cropSave.disabled=value||!cropImage;cropClose.disabled=cropSaving}
 function calculateCrop(){const w=cropRotation%180?cropImage.height:cropImage.width,h=cropRotation%180?cropImage.width:cropImage.height,r=reframeRatio.value==='original'?w/h:Number(reframeRatio.value),zoom=Number(cropZoom.value)/100;const cw=Math.min(w,h*r)/zoom,ch=Math.min(h,w/r)/zoom;return [(w-cw)*Number(cropX.value)/100/w,(h-ch)*Number(cropY.value)/100/h,cw/w,ch/h]}
 function paintCrop(){if(!cropImage)return;const iw=cropImage.width,ih=cropImage.height,w=cropRotation%180?ih:iw,h=cropRotation%180?iw:ih,oriented=document.createElement('canvas');oriented.width=w;oriented.height=h;const c=oriented.getContext('2d');c.translate(w/2,h/2);c.scale(cropMirror?-1:1,1);c.rotate(cropRotation*Math.PI/180);c.drawImage(cropImage,-iw/2,-ih/2);
  const [x,y,cw,ch]=calculateCrop(),left=Math.round(x*w),top=Math.round(y*h),width=Math.round((x+cw)*w)-left,height=Math.round((y+ch)*h)-top,scale=Math.min(1,640/Math.max(width,height));reframeCanvas.width=Math.max(1,Math.round(width*scale));reframeCanvas.height=Math.max(1,Math.round(height*scale));reframeCanvas.getContext('2d').drawImage(oriented,left,top,width,height,0,0,reframeCanvas.width,reframeCanvas.height);reframeInfo.textContent=`${width} × ${height} 像素 · 顺时针 ${cropRotation}°${cropMirror?' · 已镜像':''}`;cropSave.disabled=cropSaving||width<16||height<16;reframeStatus.textContent=width<16||height<16?'裁剪结果的宽和高至少需要 16 像素':'预览未保存';
 }
 for(const input of [reframeRatio,cropZoom,cropX,cropY])input.oninput=paintCrop;
 reframeDialog.addEventListener('cancel',e=>{if(cropSaving)e.preventDefault()});reframeDialog.addEventListener('close',()=>{cropLoad++;cropSession=null;cropImage=null;cropRequest=null});
 document.addEventListener('creative-reframe-image',async event=>{const asset=event.detail?.asset;if(isLocked()||hasDrafts()){toast('请先完成当前任务并保存画布草稿');return}if(project?.canvas_assets?.[asset]?.kind!=='image'){toast('请选择本项目图片');return}const ticket=++cropLoad;cropSession={project:project.id,revision:project.revision,asset};cropImage=null;cropRequest=null;reframeStatus.textContent='正在读取原图…';reframeCanvas.width=reframeCanvas.height=1;reframeInfo.textContent='';reframeDialog.showModal();setCropDisabled(true);
  try{const r=await fetch(`/creative/api/projects/${cropSession.project}/canvas/assets/${asset}/preview`,{headers:{Authorization:'Bearer '+key},signal:AbortSignal.timeout(15000)});if(!r.ok)throw Error('无法读取原图');const url=URL.createObjectURL(await r.blob());try{const img=new Image();img.src=url;await img.decode();if(ticket!==cropLoad||!reframeDialog.open)return;cropImage=img;setCropDisabled(false);cropReset.click()}finally{URL.revokeObjectURL(url)}}catch(e){if(ticket===cropLoad){reframeStatus.textContent=e.message;setCropDisabled(false)}}
 });

 // Grid slicing is deterministic; keep the source and save independent image nodes.
 const gridDialog=make('dialog',null,'image-reframe-dialog'),gridStage=make('div',null,'image-reframe-stage'),gridCanvas=make('canvas'),gridStatus=make('p'),gridSelect=make('select'),gridActions=make('div',null,'row');
 gridCanvas.setAttribute('aria-label','宫格切分预览');gridStatus.setAttribute('role','status');gridSelect.setAttribute('aria-label','宫格排列');
 for(const [v,t] of [['2x2','2 行 × 2 列 · 4 张'],['2x3','2 行 × 3 列 · 6 张'],['3x3','3 行 × 3 列 · 9 张']]){const o=make('option',t);o.value=v;gridSelect.append(o)}
 let gridSession=null,gridImage=null,gridSaving=false,gridLoad=0,gridRequest=null;
 const gridClose=action('取消',()=>gridDialog.close()),gridSave=action('切分并加入画布',async()=>{
  if(!gridSession||!gridImage||gridSaving)return;
  if(project?.id!==gridSession.project||project.revision!==gridSession.revision||hasDrafts()||isLocked()){gridStatus.textContent='项目已变化，请重新打开宫格切分';return}
  const [rows,columns]=gridSelect.value.split('x').map(Number),params={asset:gridSession.asset,rows,columns},signature=JSON.stringify(params);
  if(gridRequest?.signature!==signature)gridRequest={signature,id:opaqueId()};
  gridSaving=true;setBusy(true);gridSave.disabled=gridSelect.disabled=gridClose.disabled=true;gridStatus.textContent='正在切分并保存图片…';
  try{const r=await api('/projects/'+gridSession.project+'/image-grid','POST',{...params,revision:gridSession.revision,request_id:gridRequest.id});if(project?.id===gridSession.project){project=r.project;clearMedia();draw();schedule()}gridDialog.close();toast(`已新增 ${rows*columns} 张宫格图片，保留原图与来源连接`)}
  catch(e){gridStatus.textContent=e.message+'；未确认成功时可用相同参数重试。'}finally{gridSaving=false;setBusy(false);gridSelect.disabled=gridClose.disabled=false;gridSave.disabled=!gridImage}
 });gridSave.className='primary';gridStage.append(gridCanvas);gridActions.append(gridClose,gridSave);gridDialog.append(make('h2','宫格切分'),make('p','把原图均匀切成独立图片，从左到右、从上到下编号。不调用生成模型，不消耗积分，原图保留。'),gridSelect,gridStage,gridStatus,gridActions);document.body.append(gridDialog);
 function paintGrid(){if(!gridImage)return;const [rows,columns]=gridSelect.value.split('x').map(Number),w=gridImage.naturalWidth,h=gridImage.naturalHeight,scale=Math.min(1,640/Math.max(w,h));gridCanvas.width=Math.round(w*scale);gridCanvas.height=Math.round(h*scale);const c=gridCanvas.getContext('2d');c.drawImage(gridImage,0,0,gridCanvas.width,gridCanvas.height);c.strokeStyle='#15d4ec';c.lineWidth=2;c.beginPath();for(let col=1;col<columns;col++){const x=Math.floor(col*w/columns)*scale;c.moveTo(x,0);c.lineTo(x,gridCanvas.height)}for(let row=1;row<rows;row++){const y=Math.floor(row*h/rows)*scale;c.moveTo(0,y);c.lineTo(gridCanvas.width,y)}c.stroke();for(let row=0;row<rows;row++)for(let col=0;col<columns;col++){const x=col*gridCanvas.width/columns+6,y=row*gridCanvas.height/rows+6;c.fillStyle='#111c';c.fillRect(x,y,40,23);c.fillStyle='white';c.font='14px sans-serif';c.fillText(`${row+1}-${col+1}`,x+6,y+16)}
  const count=rows*columns,capacity=Math.min(32-Object.keys(project.canvas_assets||{}).length,16-(project.canvas?.nodes||[]).length),small=w/columns<16||h/rows<16;gridSave.disabled=gridSaving||small||count>capacity;gridStatus.textContent=small?'每个宫格至少需要 16 × 16 像素':count>capacity?`当前最多还可加入 ${Math.max(0,capacity)} 张图片，请选择较少宫格或先整理画布`:`将新增 ${count} 张图片，每张约 ${Math.floor(w/columns)} × ${Math.floor(h/rows)} 像素`;
 }
 gridSelect.onchange=paintGrid;gridDialog.addEventListener('cancel',e=>{if(gridSaving)e.preventDefault()});gridDialog.addEventListener('close',()=>{gridLoad++;gridSession=gridImage=gridRequest=null});
 document.addEventListener('creative-grid-image',async event=>{const asset=event.detail?.asset;if(isLocked()||hasDrafts()){toast('请先完成当前任务并保存画布草稿');return}if(!project?.canvas_capabilities?.image_grid||project.canvas_assets?.[asset]?.kind!=='image')return;const ticket=++gridLoad;gridSession={project:project.id,revision:project.revision,asset};gridImage=gridRequest=null;gridSelect.value='2x2';gridSave.disabled=true;gridCanvas.width=gridCanvas.height=1;gridStatus.textContent='正在读取原图…';gridDialog.showModal();
  try{const r=await fetch(`/creative/api/projects/${gridSession.project}/canvas/assets/${asset}/source`,{headers:{Authorization:'Bearer '+key},signal:AbortSignal.timeout(30000)});if(!r.ok)throw Error('无法读取原图');const url=URL.createObjectURL(await r.blob());try{const img=new Image();img.src=url;await img.decode();if(ticket!==gridLoad||!gridDialog.open)return;gridImage=img;paintGrid()}finally{URL.revokeObjectURL(url)}}catch(e){if(ticket===gridLoad)gridStatus.textContent=e.message}
 });

 function decorateImages(){
  // Keep node-level image controls available while the catalog is loading or
  // temporarily unavailable; the model selector is upgraded when the catalog
  // arrives, but editing entry points must not disappear with it.
  const activeDraft=asset=>Object.values(project?.image_transform_drafts||{}).find(d=>d?.asset===asset&&d.state==='applied');
  const previewImage=(img,angle,light)=>{if(!img)return;const transform={
    '保留原角度':'none','正面平视':'perspective(700px) scale(1.02)','侧面 45 度':'perspective(700px) rotateY(-14deg) rotateZ(-1deg) scale(1.04)','俯视特写':'perspective(700px) rotateX(7deg) scale(1.08) translateY(-3%)','低机位仰视':'perspective(700px) rotateX(-7deg) scale(1.08) translateY(3%)'}[angle]||'none';const filter={
    '保留原光照':'none','窗边柔光':'brightness(1.08) contrast(.95)','暖色侧光':'sepia(.15) saturate(1.12) brightness(1.04)','冷色轮廓光':'hue-rotate(190deg) saturate(1.08) brightness(1.02)','影棚柔光':'contrast(.9) brightness(1.08) saturate(.96)'}[light]||'none';img.style.transform=transform;img.style.filter=filter;img.dataset.previewAngle=angle;img.dataset.previewLight=light};
  document.querySelectorAll('.reference-node').forEach(card=>{
   if(!card.querySelector('img')||card.querySelector('.node-image-controls'))return;
   // Video-reference cards also contain a thumbnail; only images offer image generation.
   if(card.dataset.kind!=='image'&&!/图片|image/i.test(card.textContent))return;
   const box=make('div',null,'node-image-controls'),label=make('label','生成 / 编辑模型'),select=make('select',null,'node-image-model'),modelControl=make('span',null,'image-adjustment-model-control'),modelLogo=make('span',null,'studio-provider-logo');label.title='同一模型用于生成图片、局部修改、多角度与重打光';select.setAttribute('aria-label','此图片节点的生成与编辑模型');modelControl.append(modelLogo,select);
   const imageModels=images.length?images:[{id:imageSelect.value||'kling-image-3',label:'图片模型',available:true}];
   for(const m of imageModels){const o=make('option',m.label);o.value=m.id;o.disabled=!m.available;select.append(o)}
   const syncNodeModelLogo=()=>{const logo=window.studioModelLogo?.(select.value);modelControl.querySelector('.studio-provider-logo')?.remove();if(logo){logo.setAttribute('aria-hidden','true');modelControl.prepend(logo)}};select.value=imageSelect.value;select.onchange=()=>{imageSelect.value=select.value;imageSelect.onchange();syncNodeModelLogo()};label.append(modelControl);syncNodeModelLogo();
   const transforms=make('details',null,'image-transforms');transforms.append(make('summary','调整角度与光照'));
   const angle=make('select'),light=make('select');angle.setAttribute('aria-label','图像角度');light.setAttribute('aria-label','图像光照');
   for(const value of ['保留原角度','正面平视','侧面 45 度','俯视特写','低机位仰视'])angle.append(make('option',value));
   for(const value of ['保留原光照','窗边柔光','暖色侧光','冷色轮廓光','影棚柔光'])light.append(make('option',value));
   const node=project.canvas?.nodes.find(n=>n.id===card.dataset.nodeId),draft=activeDraft(node?.asset),target=card.querySelector('.canvas-card-body>img'),status=make('p',null,'image-transform-status');angle.value=draft?.angle||'保留原角度';light.value=draft?.light||'保留原光照';
   const result= draft?.result_asset&&project.canvas_assets?.[draft.result_asset],resultLineage=result&&project.canvas_lineage?.[draft.result_asset],resultAligned=Boolean(resultLineage?.sources?.includes(node?.asset)&&resultLineage?.adjustments?.angle===draft?.angle&&resultLineage?.adjustments?.light===draft?.light),observation=draft?.result_observation||resultLineage?.transform_alignment;
   const resultStatus=observation?.status==='changed_observed'?'已生成 · 像素变化已观察 · 待人工核对':observation?.status==='unchanged'?'已生成 · 像素未变化 · 需重新核对':observation?.status==='decode_failed'?'已生成 · 像素观察失败 · 待核对':resultAligned?'已生成 · 参数已绑定 · 待像素观察':null;
   const renderPreview=()=>{previewImage(target,angle.value,light.value);const copy=resultStatus||(draft?.result_state==='needs_review'?'已提交生成 · 结果待核对':'已保存草稿 · 等待显式生成 · 可撤销');status.textContent=draft&&draft.angle===angle.value&&draft.light===light.value?copy:'本地预览 · 未保存，不扣积分';};
   const preview=action('预览调整',renderPreview);preview.setAttribute('aria-label','预览调整');
   const save=action('保存变换草稿',async()=>{if(!node?.asset||isLocked())return;save.disabled=true;setBusy(true);try{const base={revision:project.revision,asset:node.asset,angle:angle.value,light:light.value};const checked=await api('/projects/'+project.id+'/image-transforms/preview','POST',base);const result=await api('/projects/'+project.id+'/image-transforms/drafts','POST',{...base,preview_hash:checked.preview_hash,confirm:'save'});project=result.project;clearMedia();draw();schedule();toast('图片变换草稿已保存，可在节点上撤销')}catch(e){status.textContent=e.message}finally{save.disabled=false;setBusy(false)}});save.setAttribute('aria-label','保存变换草稿');
   const undo=action('撤销变换草稿',async()=>{const current=activeDraft(node?.asset);if(!current||isLocked())return;undo.disabled=true;setBusy(true);try{const result=await api('/projects/'+project.id+'/image-transforms/drafts/'+current.id+'/undo','POST',{revision:project.revision});project=result.project;clearMedia();draw();schedule();toast('已撤销图片变换草稿')}catch(e){status.textContent=e.message}finally{undo.disabled=false;setBusy(false)}});undo.setAttribute('aria-label','撤销变换草稿');undo.hidden=!draft;
   angle.onchange=renderPreview;light.onchange=renderPreview;transforms.append(make('label','视角'),angle,make('label','光线'),light,status,preview,save,undo);transforms.addEventListener('toggle',()=>document.dispatchEvent(new Event('creative-node-controls-ready')));card.querySelector('.canvas-card-body').append(transforms);renderPreview();
   const edit=action('生成调整版本',()=>{if(!node?.asset)return;const useDraft=activeDraft(node.asset),matches=useDraft&&useDraft.angle===angle.value&&useDraft.light===light.value;openImage(`保持参考图商品结构、颜色和材质一致。视角：${angle.value}。光照：${light.value}。${card.querySelector('textarea')?.value||''}。不生成文字。`,node.asset,{angle:angle.value,light:light.value},matches?useDraft.id:null)});transforms.append(edit);
   const angleEditor=action('多角度编辑器',()=>node?.asset&&document.dispatchEvent(new CustomEvent('creative-open-image-adjustment',{detail:{asset:node.asset,mode:'angle'}})));angleEditor.setAttribute('aria-label','打开多角度编辑器');
   const lightEditor=action('重打光',()=>node?.asset&&document.dispatchEvent(new CustomEvent('creative-open-image-adjustment',{detail:{asset:node.asset,mode:'light'}})));lightEditor.setAttribute('aria-label','打开重打光编辑器');
   transforms.append(angleEditor,lightEditor);
   const generate=action('生成新参考图',()=>openImage(card.querySelector('textarea')?.value||''));generate.className='node-image-generate';const crop=action('裁剪 / 旋转',()=>document.dispatchEvent(new CustomEvent('creative-reframe-image',{detail:{asset:node?.asset}})));const modify=action('修改图片',()=>openImage(card.querySelector('textarea')?.value||'',node?.asset));box.append(modify,crop,label,generate);card.querySelector('.canvas-card-body').prepend(box);
  });paintModels();document.dispatchEvent(new Event('creative-node-controls-ready'));
 }
 document.addEventListener('creative-canvas-painted',()=>{
  decorateImages();
  // Canvas thumbnails arrive through blob previews after the graph paint.
  // Re-run after those previews settle so image-node editing controls are
  // present in the same render pass users see, without duplicating controls.
  setTimeout(decorateImages,250);
  setTimeout(decorateImages,1000);
 });
 // The first canvas paint can precede workspace listener registration on a
 // cold load; perform an initial pass as well.
 setTimeout(decorateImages,0);
 setTimeout(decorateImages,750);
 function foldInspectorSections(){
  const inspector=document.querySelector('.inspector');if(!inspector||inspector.dataset.sectionsReady)return;
  const source=details.parentElement;const archive=source?.nextElementSibling;if(!source||!archive)return;
  const section=(title,open)=>{const d=make('details',null,'inspector-section');d.open=open;d.append(make('summary',title));return d};
  const current=section('当前目标',true),editable=section('可编辑内容',true),done=section('已完成目标',false);
  const briefBlock=brief.closest('details');if(briefBlock)current.append(briefBlock);
  const decisionHeading=[...source.children].find(e=>e.tagName==='H3'&&e.textContent.trim()==='创作依据');if(decisionHeading)current.append(decisionHeading);
  if($('decisions'))current.append($('decisions'));
  const assumptions=[...source.children].find(e=>e.tagName==='DETAILS'&&e.querySelector('#assumptions'));if(assumptions)current.append(assumptions);
  const reference=source.querySelector('.reference-review');if(reference)editable.append(reference);
  if($('shotEditor'))editable.append($('shotEditor'));
  while(archive.firstElementChild)done.append(archive.firstElementChild);
  source.remove();archive.remove();inspector.replaceChildren(current,editable,done);inspector.dataset.sectionsReady='1';
 }
 syncConversationList();syncDirectorContext();syncPromptNode();syncInputs();restoreConversation(null);
 $('shotEditor').parentElement.prepend($('shotEditor'));
 foldInspectorSections();
 document.querySelector('.timeline').addEventListener('click',e=>{if(e.target.closest('.shot'))document.querySelector('.inspector').scrollTop=0;});

 if(expanded){
  const director=document.querySelector('.director'),head=director.querySelector('.panehead');
  const chatToggle=action('收起对话',()=>{const hidden=document.body.classList.toggle('chat-collapsed');chatToggle.textContent=hidden?'打开对话':'收起对话';chatToggle.setAttribute('aria-expanded',String(!hidden));document.dispatchEvent(new Event('creative-fit-canvas'))});chatToggle.id='chatToggle';chatToggle.setAttribute('aria-expanded','true');bar.append(chatToggle);
  head.append(action('—',()=>chatToggle.click()));head.lastChild.setAttribute('aria-label','收起对话');
  const timelineToggle=action('时间轴',()=>{const visible=document.body.classList.toggle('timeline-open');timelineToggle.setAttribute('aria-expanded',String(visible))});timelineToggle.id='timelineToggle';timelineToggle.setAttribute('aria-expanded','false');canvasToolbar.insertBefore(timelineToggle,inlineEdit);
  const closeInspector=action('关闭详情',()=>{document.body.classList.add('inspector-folded');syncLayout()});closeInspector.className='close-inspector';document.querySelector('.inspector').prepend(closeInspector);
  document.body.classList.add('inspector-folded');syncLayout();
  const priorEditor=drawEditor;drawEditor=function(){priorEditor();if(!document.body.classList.contains('inspector-folded')){const d=$('shotEditor').closest('details');if(d)d.open=true}};
  document.querySelector('.timeline').addEventListener('click',e=>{if(e.target.closest('.shot')){const d=$('shotEditor').closest('details');if(d)d.open=true}});
  head.addEventListener('pointerdown',e=>{if(e.target.closest('button')||innerWidth<=900||document.body.classList.contains('studio-chat-expanded'))return;const r=director.getBoundingClientRect(),x=e.clientX,y=e.clientY;head.setPointerCapture(e.pointerId);head.onpointermove=v=>{director.style.left=Math.max(8,Math.min(innerWidth-r.width-8,r.left+v.clientX-x))+'px';director.style.top=Math.max(Math.min(60,Math.max(8,innerHeight-r.height-8)),Math.min(innerHeight-r.height-8,r.top+v.clientY-y))+'px';director.style.right='auto';director.style.bottom='auto';director.style.height=r.height+'px'};head.onpointerup=head.onpointercancel=()=>{head.onpointermove=null}});
 }
 // Keep primary creation actions visible; project information opens on demand.
 if(expanded){
  const projectMenu=make('details',null,'workspace-project-menu');projectMenu.id='workspaceProjectMenu';
  const menuSummary=make('summary'),menuLabel=make('span','项目','workspace-project-label');
  const title=$('projectTitle'),identity=title.parentElement;
  menuSummary.append(menuLabel,title);menuSummary.setAttribute('aria-label','项目菜单');menuSummary.setAttribute('aria-expanded','false');
  const menuPanel=make('section',null,'workspace-project-panel');menuPanel.id='workspaceProjectPanel';menuPanel.setAttribute('aria-label','项目操作');menuSummary.setAttribute('aria-controls',menuPanel.id);
  identity.className='workspace-project-meta';projectDetailsButton.remove();
  menuPanel.append(identity,filmReviewButton,inspectorButton,canvasModeButton,sceneIntentButton,sceneReviewButton);
  projectMenu.append(menuSummary,menuPanel);bar.prepend(projectMenu);
  projectMenu.addEventListener('toggle',()=>{menuSummary.setAttribute('aria-expanded',String(projectMenu.open));if(projectMenu.open)productionTask.open=false});
  productionTask.addEventListener('toggle',()=>{if(productionTask.open)projectMenu.open=false});
  menuPanel.addEventListener('click',event=>{if(!event.target.closest('button')||event.target.closest('button').disabled)return;projectMenu.open=false;if(!document.querySelector('dialog[open]')&&!document.querySelector('.inspector :focus'))menuSummary.focus()});
  document.addEventListener('pointerdown',event=>{if(projectMenu.open&&!projectMenu.contains(event.target))projectMenu.open=false});
  document.addEventListener('keydown',event=>{if(event.key==='Escape'&&projectMenu.open&&!document.querySelector('dialog[open]')){projectMenu.open=false;menuSummary.focus()}});
 }
 if(key)loadModels();syncEntry();paintModels();syncCreativeStatus();
})();

// Review the saved film beside current product references, without leaving the canvas.
(()=>{
 const dialog=$('reviewDialog');if(!dialog)return;
 const heading=dialog.querySelector('h2'),head=node('div',undefined,'film-comparison-heading'),close=node('button','关闭');close.type='button';close.setAttribute('aria-label','关闭成片审阅');close.onclick=()=>dialog.close();heading.replaceWith(head);head.append(heading,close);
 const section=node('section',undefined,'film-comparison'),meta=node('p',undefined,'muted'),status=node('p');status.id='filmReviewMediaStatus';status.setAttribute('role','status');
 const layout=node('div',undefined,'film-comparison-layout'),references=node('aside',undefined,'film-comparison-references'),stage=node('div',undefined,'film-comparison-stage');
 const player=node('video');player.id='filmReviewVideo';player.controls=true;player.playsInline=true;player.preload='metadata';player.setAttribute('aria-label','当前版本成片');
 const navigation=node('div',undefined,'film-comparison-beats');navigation.setAttribute('aria-label','按方案时段定位成片');
 const clock=node('output','00:00.00'),mark=node('button','在意见中标记当前时间');mark.type='button';mark.id='markFilmReviewTime';
 const tools=node('div',undefined,'film-comparison-tools');tools.append(clock,mark);stage.append(player,status,navigation,tools);layout.append(stage,references);section.append(meta,layout);
 dialog.querySelector('label').before(section);dialog.classList.add('film-review-dialog');
 let target=null,controller=null,epoch=0,objectURLs=[],loaded=false;
 const matches=p=>target&&p?.id===target.id&&p.revision===target.revision&&p.artifact===target.artifact&&p.state==='completed';
 const current=t=>t===epoch&&dialog.open&&matches(project);
 const format=t=>`${String(Math.floor(t/60)).padStart(2,'0')}:${(t%60).toFixed(2).padStart(5,'0')}`;
 function buttons(enabled){mark.disabled=!enabled;$('approveReview').disabled=!enabled;$('requestChanges').disabled=!enabled;navigation.querySelectorAll('button').forEach(b=>b.disabled=!enabled)}
 function release(){controller?.abort();controller=null;player.pause();player.removeAttribute('src');player.load();references.querySelectorAll('img').forEach(img=>img.removeAttribute('src'));objectURLs.forEach(url=>URL.revokeObjectURL(url));objectURLs=[];loaded=false}
 function invalidate(){epoch++;release();buttons(false);status.textContent='作品版本已变化，请关闭后重新打开成片审阅。'}
 function locate(t){if(!loaded)return;player.pause();player.currentTime=Math.max(0,Math.min(t,player.duration||target.duration));clock.textContent=format(player.currentTime)}
 player.addEventListener('timeupdate',()=>{clock.textContent=format(player.currentTime);navigation.querySelectorAll('button').forEach(b=>b.setAttribute('aria-pressed',String(player.currentTime>=Number(b.dataset.start)&&player.currentTime<Number(b.dataset.end))))});
 player.addEventListener('error',()=>{if(dialog.open&&player.getAttribute('src')){loaded=false;buttons(false);status.textContent='成片暂时无法播放，请关闭后重开。审阅意见仍保留在此窗口。'}});
 mark.onclick=()=>{if(!loaded||!matches(project))return;const note=$('reviewNote'),prefix=`【${format(player.currentTime)}】`;if(note.value.length+prefix.length+2>note.maxLength){status.textContent='审阅意见已达到字数上限，请先精简。';return}note.value+=(note.value?'\n':'')+prefix+' ';note.focus()};
 async function fetchBlob(path,t){const r=await fetch('/creative/api/projects/'+target.id+path,{headers:{Authorization:'Bearer '+key},cache:'no-store',signal:AbortSignal.any([controller.signal,AbortSignal.timeout(60000)])});if(!r.ok)throw Error('媒体暂不可用');const blob=await r.blob();if(!current(t))return null;const url=URL.createObjectURL(blob);objectURLs.push(url);return url}
 $('reviewButton').onclick=async()=>{
  if(!project?.artifact||project.state!=='completed')return;
  release();target={id:project.id,revision:project.revision,artifact:project.artifact,duration:project.duration};const t=++epoch;controller=new AbortController();
  $('video').pause();$('reviewNote').value='';$('reviewStatus').textContent='';clock.textContent='00:00.00';status.textContent='正在读取当前成片…';
  meta.textContent=`版本 ${target.revision} · ${target.duration} 秒 · ${project.aspect} · ${project.quote?.label||project.model}`;
  navigation.replaceChildren();
  for(const shot of project.shots||[]){const b=node('button',`${shot.start}–${shot.start+shot.duration}s · ${shot.title}`);b.type='button';b.dataset.start=shot.start;b.dataset.end=shot.start+shot.duration;b.title='定位本方案时段中点；实际剪辑点以成片为准';b.onclick=()=>locate(shot.start+shot.duration/2);navigation.append(b)}
  references.replaceChildren(node('h3','当前商品参考'),node('p','对照轮廓、五金和标识；当前参考不代表历史生成输入记录。','muted'));
  if(project.reference_needs_review||project.video_inputs_needs_review)references.append(node('p','商品信息已变化，参考图待核对。','notice'));
  const selected=project.video_inputs?.references||[];
  const refs=selected.length?selected.slice(0,7).map((r,i)=>({path:'/canvas/assets/'+encodeURIComponent(r.asset)+'/preview',label:`参考 ${i+1} · ${({product:'商品',person:'人物',scene:'场景',style:'风格'})[r.role]||'视频参考'}`})):project.reference?[{path:'/reference?id='+encodeURIComponent(project.reference.id),label:'商品图'}]:[];
  if(!refs.length)references.append(node('p','当前项目没有商品参考图。','muted'));
  dialog.showModal();buttons(false);
  const imageJobs=refs.map(async ref=>{const figure=node('figure'),img=node('img'),caption=node('figcaption',ref.label);img.alt=ref.label;figure.append(img,caption);references.append(figure);try{const url=await fetchBlob(ref.path,t);if(url)img.src=url}catch(e){if(current(t)){img.remove();caption.textContent=ref.label+' · 暂时无法读取'}}});
  try{
   const url=await fetchBlob('/media/final',t);if(!url)return;
   // Recheck after transfer so a remotely replaced film cannot be approved as the old version.
   const latest=await api('/projects/'+target.id);if(!current(t))return;if(!matches(latest)){invalidate();return}
   await new Promise((resolve,reject)=>{const signal=controller.signal;const finish=error=>{clearTimeout(timer);player.removeEventListener('loadedmetadata',ready);player.removeEventListener('error',failed);signal.removeEventListener('abort',aborted);error?reject(error):resolve()};const ready=()=>finish(),failed=()=>finish(Error('成片无法播放')),aborted=()=>finish(Error('已关闭')),timer=setTimeout(()=>finish(Error('成片读取超时')),15000);player.addEventListener('loadedmetadata',ready,{once:true});player.addEventListener('error',failed,{once:true});signal.addEventListener('abort',aborted,{once:true});player.src=url});
   if(!current(t))return;loaded=true;buttons(true);status.textContent='按方案时段定位，或播放完整成片检查动作与声音。定位不代表质量已通过。';
  }catch(e){if(current(t)){buttons(false);status.textContent='成片读取失败，请关闭后重开；没有提交生成或审阅。'}}
  await Promise.allSettled(imageJobs);
 };
 for(const id of ['approveReview','requestChanges']){const save=$(id).onclick;$(id).onclick=async()=>{if(!loaded||!matches(project)){invalidate();return}await save()}}
 dialog.addEventListener('close',()=>{epoch++;release();target=null});
 for(const event of ['creative-state-change','creative-status-sync'])document.addEventListener(event,()=>{if(dialog.open&&!matches(project))invalidate()});
})();
