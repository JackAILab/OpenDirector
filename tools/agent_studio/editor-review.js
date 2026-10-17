/* Owner-facing full-film checklist. The packet is deterministic; semantic quality remains pending. */
'use strict';
const ReviewUI=(()=>{
 let packet=null,saved=null,ready=false,draft=null,reviewKey='',notice='',loadEpoch=0;
 const key=()=>project?.id+':'+project?.revision;
 const fields=['reviewWatched','reviewHeard','reviewFacts','reviewDecision','reviewNote'];
 function readDraft(){return {human:{full_video_watched:el('reviewWatched').checked,audio_listened:el('reviewHeard').checked,product_facts_checked:el('reviewFacts').checked},decision:el('reviewDecision').value,note:el('reviewNote').value}};
 function openRetakeWindow(window){
  if(working||dirty||reviewKey!==key()){status('请先保存当前剪辑并重新读取审阅窗口。');return}
  const index=spec.clips.findIndex((c,i)=>window.start>=offset(i)-.001&&window.end<=offset(i)+c.end-c.start+.001);
  if(index<0){status('该审阅窗口跨越多个片段，请在时间轴选择其中一段后打开重拍。');return}
  const c=spec.clips[index],at=offset(index),note=el('reviewNote').value;
  selectClip(index);close();RetakeUI.openRange(round(Math.max(c.start,c.start+window.start-at)),round(Math.min(c.end,c.start+window.end-at)),note);
  RetakeUI.message('已带入审阅时间窗和备注；请核对 3–10 秒范围与修改要求，再准备片段。');el('retakeIntent').focus({preventScroll:true});
 }
const labels={source_integrity:'素材摘要',canvas_ratio:'画幅',audio_track:'音轨',caption_timing:'字幕时间',timeline:'时间轴'};
 const el=id=>document.getElementById(id);
 function status(value){el('reviewStatus').textContent=value}
 function currentExport(){
  const candidates=[project?.export,...(project?.edit_versions||[])].filter(Boolean);
  return candidates.find(item=>item.state==='completed'&&item.revision===project?.revision)||null;
 }
 function drawIndependent(){
  const button=el('requestIndependentReview'),label=el('independentReviewStatus');
  if(!button||!label)return;
  const exportJob=currentExport(),request=exportJob&&project?.independent_reviews?.[exportJob.id];
  button.disabled=working||dirty||!!draft||reviewKey!==key()||!exportJob||saved?.decision!=='approved';
  if(!exportJob){label.textContent='完成一次导出并通过技术检查后，可交给另一位审阅者。';return}
  if(request){
   const text={pending_independent_review:'已提交，等待另一位审阅者完整观看和听音。',independent_passed:'独立审阅已通过；仍不会自动获得训练资格。',needs_changes:'独立审阅要求修改，可重新导出后再次申请。',rejected:'独立审阅未通过，可修改后重新导出。'}[request.status]||'已有独立审阅申请。';
   label.textContent=`导出 ${exportJob.id.slice(0,8)} · ${text} training_eligible=false`;
   return;
  }
  label.textContent=saved?.decision==='approved'?'人工核对已完成，可将当前导出提交给另一位审阅者。':'请先将审阅结论设为“人工核对完成”并保存。';
 }
 function draw(){if(!ready)return;const open=!el('reviewPanel').hidden;el('review').setAttribute('aria-expanded',String(open));if(!open)return;
  if(!packet){el('reviewSummary').textContent='打开审阅面板后读取当前剪辑核对项。';return}
  el('reviewSummary').textContent=`${packet.duration.toFixed(2)} 秒 · 技术核对 ${Object.values(packet.technical).filter(v=>v.status==='passed').length}/${Object.keys(packet.technical).length} 项 · 内容与声音仍需人工观看/听音`;
  const list=el('reviewTechnical');list.replaceChildren();Object.entries(packet.technical).forEach(([key,item])=>{const row=document.createElement('div');row.className='review-item '+item.status;const title=document.createElement('strong');title.textContent=(item.status==='passed'?'✓ ':'○ ')+(labels[key]||key);const detail=document.createElement('span');detail.textContent=item.detail;row.append(title,detail);list.append(row)});
  const content=el('reviewContent');content.replaceChildren();(packet.content_tasks||[]).forEach(task=>{const row=document.createElement('div');row.className='review-item pending';const title=document.createElement('strong');title.textContent='○ '+task.label+' · 待审阅';const detail=document.createElement('span');detail.textContent=task.instruction;row.append(title,detail);const windows=document.createElement('div');windows.className='review-windows';(task.windows||[]).forEach(window=>{const button=document.createElement('button');button.type='button';button.className='review-window';button.textContent=`定位 ${Number(window.start).toFixed(2)}–${Number(window.end).toFixed(2)} 秒`;button.title=window.reason||'定位审阅窗口';button.onclick=()=>{if(typeof seek==='function'){stop();seek(Number(window.start));status(`已定位${task.label}：${Number(window.start).toFixed(2)} 秒`)}else status('请先载入剪辑')};const replay=document.createElement('button');replay.type='button';replay.className='review-replay';replay.textContent='回放';replay.setAttribute('aria-label',`回放${task.label} ${Number(window.start).toFixed(2)}–${Number(window.end).toFixed(2)} 秒`);replay.disabled=working;replay.onclick=async()=>{if(working)return;if(await playTimeline(Number(window.start),Number(window.end)))status(`回放${task.label}：${Number(window.start).toFixed(2)}–${Number(window.end).toFixed(2)} 秒`)};const group=document.createElement('div');group.className='review-window-controls';const retake=document.createElement('button');retake.type='button';retake.className='review-replay';retake.textContent='修改这段';retake.setAttribute('aria-label',`修改${task.label} ${Number(window.start).toFixed(2)}–${Number(window.end).toFixed(2)} 秒`);retake.disabled=working||dirty||reviewKey!==key();retake.onclick=()=>openRetakeWindow(window);group.append(button,replay,retake);windows.append(group)});row.append(windows);content.append(row)});
  const values=draft||saved||{},checks=values.human||packet.human||{};el('reviewWatched').checked=!!checks.full_video_watched;el('reviewHeard').checked=!!checks.audio_listened;el('reviewFacts').checked=!!checks.product_facts_checked;el('reviewDecision').value=values.decision||'pending';el('reviewNote').value=values.note||'';for(const id of fields)el(id).disabled=working;el('saveReview').disabled=working||!spec?.clips?.length||reviewKey!==key();status(notice||(reviewKey!==key()?'剪辑版本已更新，请重新打开审阅以读取当前核对项。':draft?'审阅记录有未保存修改。':saved?`已保存：${saved.decision==='approved'?'人工核对完成':saved.decision==='needs_changes'?'需要修改':'待审阅'} · training_eligible=false · 内容语义不会自动标记通过`:'技术结果已读取 · 请选择人工核对结论'));drawIndependent()}

 async function load(){const token=++loadEpoch,requestedKey=key();status('正在读取全片核对项…');try{const result=await request('/edit/review');if(token!==loadEpoch||key()!==requestedKey)return;if(reviewKey!==requestedKey||packet?.document_sha256!==result.packet.document_sha256)draft=null;packet=result.packet;saved=result.saved;reviewKey=requestedKey;notice='';draw()}catch(e){if(token===loadEpoch){notice=e.message;status(notice)}}}
 async function open(){if(!spec?.clips?.length){status('请先加入并保存画面片段');return}document.querySelectorAll('.adviser').forEach(e=>e.hidden=true);el('reviewPanel').hidden=false;ready=true;draw();await load()}
 function close(){loadEpoch++;el('reviewPanel').hidden=true;el('review').setAttribute('aria-expanded','false')}
 async function saveReview(){if(working||dirty||reviewKey!==key()){status(dirty?'请先保存当前剪辑，再记录审阅。':working?'正在处理…':'剪辑版本已更新，请重新打开审阅。');return}const values=readDraft(),payload={revision:project.revision,decision:values.decision,checks:values.human,note:values.note.trim()};draft=values;notice='正在保存审阅记录…';working=true;draw();try{const result=await request('/edit/review','POST',payload);packet=result.packet;saved=result.saved;draft=null;notice=''}catch(e){notice='保存未完成：'+e.message+'；修改已保留，请重试。'}finally{working=false;draw()}}
 async function requestIndependent(){const exportJob=currentExport();if(!exportJob||working)return;if(dirty||draft||reviewKey!==key()){status('请先保存当前剪辑及当前版本的审阅修改。');return}if(saved?.decision!=='approved'){status('请先完成并保存人工核对');return}working=true;draw();try{const result=await request('/edit/review/request','POST',{revision:project.revision,export_id:exportJob.id});project.independent_reviews??={};project.independent_reviews[exportJob.id]=result.request;notice='已提交独立审阅申请 · training_eligible 仍为 false'}catch(e){notice=e.message}finally{working=false;draw()}}
 function init(){ready=true;for(const id of fields)el(id).addEventListener('input',()=>{draft=readDraft();notice='';status('审阅记录有未保存修改。');drawIndependent()});el('review').onclick=open;el('closeReview').onclick=close;el('saveReview').onclick=saveReview;el('requestIndependentReview').onclick=requestIndependent;draw()}
 return {init,draw,open,close};
})();
