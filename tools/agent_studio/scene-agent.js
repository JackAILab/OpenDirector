// Scene suggestions remain a separate, reviewable draft until the user adopts them.
export function installSceneAgent(host){
 const $=id=>document.getElementById(id),el=(tag,text)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;return n};
 let job=null,preview=null,pollTimer=null,working=false,networkPending=false,adopted=false;
 const panel=$('sceneAgent'),status=$('agentStatus'),result=$('agentResult');
 function open(value=true,focus=false){host.setPanel(value,focus);controls()}
 function eligible(){const s=host.state();return job?.state==='completed'&&!job.stale&&!adopted&&s.revision===job.revision&&(!s.dirty||preview)&&job.result?.changes?.length>0}
 function controls(){
  $('askScene').disabled=working||!!preview||host.state().busy;$('sceneIntent').disabled=working||!!preview;
  $('previewSuggestion').disabled=working||!!preview||!eligible();$('restoreScene').hidden=!preview;
  $('adoptScene').hidden=!preview;$('adoptScene').disabled=working;
  $('suggestionActions').hidden=!job?.result;
  $('sceneReviewBar').hidden=!preview||!panel.hidden;
 }
 function render(){
  result.replaceChildren();
  if(job?.result){
   result.append(el('p',job.result.summary));
   const details=el('details'),summary=el('summary',`查看 ${job.result.changes.length} 项具体改动`);details.append(summary);
   for(const c of job.result.changes){const row=el('div');row.className='scene-change';row.append(el('strong',c.label),el('pre',JSON.stringify(c.before)+' → '+JSON.stringify(c.after)));details.append(row)}
   result.append(details);
   const notes=el('details');notes.append(el('summary','建议依据'));
   for(const r of job.result.reasons)notes.append(el('p',r.text));result.append(notes);
  }
  controls();
 }
 function finish(next){
  $('toggleAgent').textContent=next.state==='running'?'✦ 助手处理中':next.state==='completed'?'✦ 查看建议':'✦ 场景助手';
  job=next;networkPending=false;working=next.state==='running';host.lock(working);
  if(working){status.textContent='正在查看场景与机位截图，整理可预演的调整…';schedule()}
  else if(next.state==='completed')status.textContent=next.stale?'场景已更新，这份建议仅供查看。':next.result.changes.length?'建议已就绪 · 先预演，再采用为草稿。':'当前场景保持不变，请查看说明。';
  else status.textContent=next.error||'建议未完成，原场景保留。';
  render();
 }
 function schedule(delay=1400){clearTimeout(pollTimer);pollTimer=setTimeout(poll,delay)}
 async function poll(){
  if(!job||!working)return;
  try{finish(await host.api('/suggestions/'+job.id))}
  catch(e){
   // A lost HTTP observation does not mean the model task stopped. Query the same ID.
   if(networkPending&&e.status===404){working=false;host.lock(false);status.textContent='请求未创建，原场景保留；可以重新发起建议。';controls();return}
   status.textContent='连接暂时中断，正在重查同一份建议…';schedule(4000);
  }
 }
 $('toggleAgent').onclick=()=>open(panel.hidden,true);
 $('closeAgent').onclick=()=>open(false,true);
 document.addEventListener('scene-panel-change',controls);
 for(const b of panel.querySelectorAll('[data-intent]'))b.onclick=()=>{$('sceneIntent').value=b.dataset.intent;$('sceneIntent').focus()};
 $('askScene').onclick=async()=>{
  const intent=$('sceneIntent').value.trim();if(!intent||working||preview||host.state().busy)return;
  working=true;adopted=false;job=null;result.replaceChildren();host.lock(true);status.textContent='正在保存场景并准备机位截图…';controls();
  try{
   const input=await host.prepare();job={id:crypto.randomUUID().replaceAll('-',''),state:'running'};
   status.textContent='正在生成场景建议…';
   const body={...input,request_id:job.id,intent};
   try{finish(await host.api('/suggestions','POST',body))}
   catch(e){
    if(e.status&&e.status<500){job=null;throw e}
    networkPending=true;status.textContent='正在核对请求状态…';schedule();
   }
  }catch(e){working=false;host.lock(false);status.textContent=e.message;controls()}
 };
 $('previewSuggestion').onclick=async()=>{
  if(!eligible()||preview||working)return;
  working=true;host.lock(true);controls();
  try{preview=await host.preview(job.result.spec);status.textContent='正在预演建议方案 · 可以播放或选择镜头；原场景尚未改变。'}
  catch(e){host.lock(false);status.textContent=e.message}
  finally{working=false;controls()}
 };
 async function restore(){
  if(!preview||working)return;
  working=true;controls();
  try{await host.restore(preview);preview=null;host.lock(false);status.textContent='已返回原场景，可以再次预演建议。'}
  catch(e){status.textContent=e.message}
  finally{working=false;controls()}
 }
 $('restoreScene').onclick=restore;
 $('restoreSceneFloating').onclick=restore;
 $('adoptScene').onclick=()=>{
  if(!preview||working)return;host.adopt(preview);preview=null;adopted=true;host.lock(false);
  status.textContent='已采用为草稿 · 可撤销，点击“保存场景”后同步。';controls();
 };
 $('adoptSceneFloating').onclick=()=>$('adoptScene').click();
 open(false);
 return {sync:controls,load(next){if(!next)return;job=next;finish(next)},changed(){
  if(adopted&&!host.state().dirty)status.textContent='建议已保存到场景，可以继续调整。';
  if(job?.result&&!preview&&!eligible()&&!adopted)status.textContent='场景已调整，这份建议仅供查看；重新请求可基于当前草稿规划。';controls();
 }};
}
