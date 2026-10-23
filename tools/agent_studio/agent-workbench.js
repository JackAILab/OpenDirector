/* Agent workspace: public activity, owned media and version-bound plan review. */
(()=>{
 const el=(tag,text,cls)=>{const n=document.createElement(tag);if(text)n.textContent=text;if(cls)n.className=cls;return n};
 const button=(text,fn)=>{const n=el('button',text);n.type='button';n.onclick=fn;return n};
 const shelf=el('aside',null,'agent-materials');shelf.id='agentMaterials';shelf.setAttribute('aria-label','项目素材');
 const head=el('div',null,'agent-materials-head'),title=el('h2','项目素材'),upload=button('＋',()=>document.querySelector('#chatForm > .director-reference-actions button')?.click());upload.setAttribute('aria-label','上传项目参考图');head.append(title,upload);
 const search=el('input');search.type='search';search.placeholder='搜索素材名称';search.setAttribute('aria-label','搜索项目素材');
 const tabs=el('div',null,'agent-material-tabs'),grid=el('div',null,'agent-material-grid'),info=el('p',null,'agent-material-info');
 let filter='all',signature='',pid='',urls=new Map(),controller=null;
 for(const [id,label] of [['all','全部'],['image','图片'],['video','视频'],['bound','已引用']]){const b=button(label,()=>{filter=id;paintShelf(true)});b.dataset.filter=id;tabs.append(b)}
 const manage=button('管理视频参考',()=>$('canvasVideoInputs')?.click());manage.className='agent-material-manage';shelf.append(head,search,tabs,info,manage,grid);document.body.append(shelf);search.oninput=()=>paintShelf(true);
 const preview=el('dialog',null,'agent-media-preview'),previewTitle=el('h2'),previewBody=el('div',null,'agent-preview-body'),previewInfo=el('p'),previewClose=button('关闭预览',()=>preview.close());preview.setAttribute('aria-label','项目素材预览');preview.append(previewTitle,previewBody,previewInfo,previewClose);document.body.append(preview);
 let previewToken=0,previewURL=null,previewController=null;
 function releasePreview(){previewToken++;previewController?.abort();previewBody.querySelector('video')?.pause();previewBody.replaceChildren();if(previewURL)URL.revokeObjectURL(previewURL);previewURL=null}
 preview.addEventListener('close',releasePreview);
 async function showMedia(asset){
  releasePreview();const token=previewToken,projectId=project?.id;previewTitle.textContent=asset.label;previewInfo.textContent=asset.roleLabel+' · '+asset.origin;previewBody.append(el('p','正在读取素材…'));preview.showModal();previewController=new AbortController();
  try{const response=await fetch(`/creative/api/projects/${encodeURIComponent(projectId)}/canvas/assets/${encodeURIComponent(asset.id)}/${asset.kind==='image'?'preview':'source'}`,{headers:{Authorization:'Bearer '+key},signal:previewController.signal});if(!response.ok)throw Error();const blob=await response.blob();if(token!==previewToken||project?.id!==projectId)return;previewURL=URL.createObjectURL(blob);const media=el(asset.kind==='image'?'img':'video');media.src=previewURL;if(asset.kind==='image')media.alt=asset.label;else{media.controls=true;media.playsInline=true}previewBody.replaceChildren(media)}catch{if(token===previewToken){previewBody.replaceChildren(el('p','素材暂时无法读取。'),button('重新读取',()=>showMedia(asset)))}}
 }
 function assets(){const p=project;if(!p)return [];const refs=p.video_inputs?.references||[],nodes=p.canvas?.nodes||[];return Object.entries(p.canvas_assets||{}).filter(([,a])=>['image','video'].includes(a.kind)).map(([id,a])=>{const node=nodes.find(n=>n.asset===id),ref=refs.find(r=>r.asset===id),sources=p.canvas_lineage?.[id]?.sources||a.provenance?.sources||[];return {id,kind:a.kind,label:node?.label||a.filename||'未命名素材',bound:!!ref,roleLabel:ref?({product:'商品参考',person:'人物参考',scene:'场景参考',style:'风格参考'})[ref.role]||'生成参考':'项目素材',origin:sources.length?'由项目素材派生':a.origin==='generated'||/generated|generation|chapter/.test(p.canvas_lineage?.[id]?.kind||a.provenance?.kind||'')?'Agent 生成':'已保存素材'}})}
 async function thumbnail(img,asset,epoch,signal){const id=asset.id;try{let url=urls.get(id);if(!url){const response=await fetch(`/creative/api/projects/${encodeURIComponent(epoch)}/canvas/assets/${encodeURIComponent(id)}/preview`,{headers:{Authorization:'Bearer '+key},signal});if(!response.ok)throw Error();const blob=await response.blob();if(pid!==epoch||signal.aborted)return;url=URL.createObjectURL(blob);urls.set(id,url)}if(pid===epoch&&!signal.aborted)img.src=url}catch{if(img.isConnected&&!signal.aborted){img.alt='缩略图暂不可读取';img.dataset.unavailable='true';img.src='data:image/svg+xml;charset=utf-8,'+encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 220"><rect width="320" height="220" rx="18" fill="#292f31"/><path d="M86 154l37-42 29 28 28-34 54 48" fill="none" stroke="#7c9297" stroke-width="8" stroke-linecap="round" stroke-linejoin="round"/><circle cx="113" cy="83" r="16" fill="#7c9297"/><text x="160" y="192" fill="#b7c8ca" font-family="sans-serif" font-size="15" text-anchor="middle">Preview unavailable</text></svg>');img.closest('button')?.classList.add('preview-unavailable')}}}
 function paintShelf(force=false){
  if(pid!==project?.id){controller?.abort();urls.forEach(URL.revokeObjectURL);urls.clear();pid=project?.id;controller=new AbortController();search.value='';signature='';if(preview.open)preview.close()}
  const all=assets(),task=project?.image_task,active=task?.state==='running',query=search.value.trim().toLowerCase();
  const next=JSON.stringify([pid,all,filter,query,task?.state,task?.id,project?.state]);if(!force&&signature===next)return;signature=next;
  upload.disabled=!!busy||['planning','running','rendering'].includes(project?.state)||active;manage.disabled=upload.disabled;
  for(const b of tabs.children)b.setAttribute('aria-pressed',String(b.dataset.filter===filter));
  info.textContent=`${all.filter(a=>a.kind==='image').length} 张图片 · ${all.filter(a=>a.kind==='video').length} 段视频`;
  grid.replaceChildren();
  if(active&&['all','image'].includes(filter)&&!query){const tile=el('div',null,'agent-material-pending');tile.append(el('span',null,'agent-spinner'),el('strong','参考图生成中'),el('small','完成后自动加入项目'));grid.append(tile)}
  for(const a of all.filter(a=>(filter==='all'||a.kind===filter||filter==='bound'&&a.bound)&&a.label.toLowerCase().includes(query))){const tile=button('',()=>showMedia(a));tile.className='agent-material-tile';tile.setAttribute('aria-label','预览 '+a.label);const img=el('img');img.alt=a.label;tile.append(img,el('strong',a.label),el('small',(a.kind==='video'?'▷ 视频 · ':'')+a.roleLabel));grid.append(tile);thumbnail(img,a,pid,controller.signal)}
  if(!grid.childElementCount)grid.append(el('p',all.length?'没有匹配的素材':'上传参考图，或让 Agent 生成。素材会保留在这里。','agent-material-empty'));
 }
 const activity=el('section',null,'agent-activity');activity.id='agentActivity';activity.setAttribute('aria-label','导演实时进展');
 const activityHead=el('div',null,'agent-activity-head'),activityTitle=el('strong'),phase=el('span');activityHead.append(activityTitle,phase);
 const steps=el('ol',null,'agent-activity-steps'),decisions=el('div',null,'agent-public-decisions');activity.append(activityHead,steps,decisions);
 let activityKey='',decisionOpen=new Set();
 const phaseNames={queued:'等待规划',references:'核对素材与创作要求',composing:'编排画面、声音与文案',validating:'检查分镜与时间结构'};
 function paintActivity(){
  const p=project,a=p?.planning_activity,current=a?.revision===p?.revision?a:null;
  activityTitle.textContent=p?.state==='planning'?'导演正在规划':current?.state==='failed'?'本轮规划未完成':'本轮创作决策';
  phase.textContent=p?.state==='planning'?(phaseNames[current?.steps?.at(-1)?.stage]||'等待导演服务'):p?.state==='planning_failed'?'已停止，保留已有上下文':p?.questions?.length?'等待补充':'方案可检查';
  activity.dataset.running=String(p?.state==='planning');
  const keyValue=JSON.stringify([p?.id,p?.revision,current,p?.decisions,p?.state]);
  if(activityKey!==keyValue){activityKey=keyValue;steps.replaceChildren();for(const [i,s] of (current?.steps||[]).entries()){const last=i===current.steps.length-1;const li=el('li',(last&&p.state==='planning'?'◌ ':last&&current.state==='failed'?'! ':'✓ ')+(phaseNames[s.stage]||s.stage));li.dataset.active=String(last&&p.state==='planning');steps.append(li)}
   decisions.replaceChildren();const values=current?.decisions||p?.decisions||[];
   for(const [i,d] of values.entries()){const detail=el('details'),summary=el('summary',d.title);const id=p.id+':'+p.revision+':'+i;detail.open=decisionOpen.has(id)||i===values.length-1;detail.append(summary,el('p',d.reason));detail.addEventListener('toggle',()=>{if(detail.open)decisionOpen.add(id);else decisionOpen.delete(id)});decisions.append(detail)}
   if(p?.state==='planning'&&!values.length)decisions.append(el('p','正在整理方案；公开决策形成后会显示在这里。','agent-activity-wait'));
   if(current?.state==='failed'&&values.length)decisions.prepend(el('p','以下为未通过完整校验的规划草稿。','notice'));
  }
  const conversation=$('conversation'),questions=conversation.querySelector(':scope > .question'),context=conversation.querySelector('.director-context');
  if(p&&(current||p.state==='planning'||p.decisions?.length)){if(context)context.before(activity);else if(questions)questions.before(activity);else conversation.append(activity)}else activity.remove();
 }
 const planCard=el('section',null,'agent-plan-card');planCard.id='agentPlanReview';
 function shotTable(p){const table=el('table',null,'agent-shot-table'),thead=el('thead'),hr=el('tr');for(const title of ['时段 / 镜头','画面与声音','后期字幕'])hr.append(el('th',title));thead.append(hr);const tbody=el('tbody');for(const s of p?.shots||[]){const row=el('tr'),time=el('td'),description=el('td'),caption=el('td');time.append(el('span',`${s.start}–${s.start+s.duration}s`),el('strong',s.title));const detail=el('details');detail.open=true;detail.append(el('summary','画面'),el('p',s.prompt));description.append(detail,el('small','声音 / 旁白'),el('p',s.audio_prompt||'未指定'));caption.append(el('p',s.caption||'无字幕'));row.append(time,description,caption);tbody.append(row)}table.append(thead,tbody);return table}
 function openPlan(shot){document.dispatchEvent(new CustomEvent('creative-open-film-review',{detail:{shot}}))}
 function paintPlan(){const p=project;if(!p?.shots?.length||p.state==='planning'){planCard.remove();return}planCard.replaceChildren();const top=el('div',null,'agent-plan-top');top.append(el('strong','拍摄与字幕方案'),el('span',`${p.duration} 秒 · ${p.shots.length} 个节拍 · 版本 ${p.revision}`));const captions=el('div',null,'agent-caption-strip');for(const s of p.shots){const chip=button('',()=>openPlan(s.id));chip.append(el('small',`${s.start}–${s.start+s.duration}s`),el('span',s.caption||'无字幕'));captions.append(chip)}planCard.append(top,el('p',p.brief?.message||'逐段核对画面、声音与字幕，再开始制作。'),captions,button('检查全部分镜与字幕',()=>openPlan()));$('conversation').append(planCard)}
 const approval=$('approveDialog'),review=el('section',null,'agent-approval-review');review.setAttribute('aria-label','本次制作分镜和字幕');approval?.querySelector('.row')?.before(review);
 function paintApproval(){if(!project)return;review.replaceChildren();review.append(el('h3','本版参考素材'),el('p','以下为实际视频输入，可点击检查原图。'));const refs=el('div',null,'agent-approval-refs');for(const a of assets().filter(a=>a.bound)){const b=button('',()=>showMedia(a)),img=el('img');img.alt=a.label;b.append(img,el('span',a.label+' · '+a.roleLabel));refs.append(b);thumbnail(img,a,pid,controller.signal)}if(!refs.childElementCount)refs.append(el('p','文字生成，未绑定图片。'));review.append(refs,el('h3','逐段检查画面、声音和字幕'),shotTable(project));const assumptions=project.assumptions||[];if(assumptions.length){const d=el('details');d.append(el('summary',`待核对假设 · ${assumptions.length} 项`));for(const a of assumptions)d.append(el('p',a));review.append(d)}
  const note=approval.querySelector(':scope > .muted');if(note)note.textContent=project.generation_mode==='chaptered_native'?'按15秒章节依次生成并自动剪辑。生成失败会停下，成片仍需检查商品、动作与声音。':'按本版方案提交整片生成，字幕后期叠加。生成失败会停下，成片仍需检查商品、动作与声音。';
 }
 approval?.addEventListener('toggle',()=>{if(approval.open)paintApproval()});
 // Keep the detailed provider prompt available, collapsed behind human-readable review.
 const prompt=approval?.querySelector('textarea');if(prompt){const d=el('details',null,'agent-raw-prompt');d.append(el('summary','查看模型提示词'));prompt.previousElementSibling?.remove();prompt.before(d);d.append(prompt)}
 const form=$('chatForm'),settings=button('时长与参考图设置',()=>{const open=form.classList.toggle('agent-settings-open');settings.setAttribute('aria-expanded',String(open))});settings.className='agent-settings-toggle';settings.setAttribute('aria-expanded','false');form.prepend(settings);
 const production=el('section',null,'agent-production');production.setAttribute('aria-label','Agent 制作进展');
 function paintProduction(){
  const status=form.querySelector('.campaign-status [role=status]');production.replaceChildren();
  settings.textContent=`${project?.duration||15} 秒 · 时长与参考图设置`;
  if(!project?.campaign){production.remove();return}
  production.append(el('strong','Agent 制作进展'));if(status)production.append(status.cloneNode(true));
  const recent=assets().filter(a=>a.kind==='video').slice(-4),results=el('div',null,'agent-result-previews');
  for(const a of recent){const b=button('',()=>showMedia(a)),img=el('img');img.alt=a.label;b.append(img,el('span','▷ '+a.label));results.append(b);thumbnail(img,a,pid,controller.signal)}
  if(recent.length)production.append(results);$('conversation').append(production);
 }
 const oldDraw=draw;draw=function(){const c=$('conversation'),stick=c.scrollHeight-c.scrollTop-c.clientHeight<70;oldDraw();paintShelf();paintActivity();paintPlan();paintProduction();if(stick)c.scrollTop=c.scrollHeight};
 document.addEventListener('creative-status-sync',paintProduction);
 paintShelf();paintActivity();paintPlan();paintProduction();
})();
