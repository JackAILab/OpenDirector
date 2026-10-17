/* Project recipe settings. Selecting a recipe never submits paid work. */
(()=>{
 const el=(tag,text)=>{const n=document.createElement(tag);if(text)n.textContent=text;return n};
 const panel=el('details');panel.className='creative-settings';
 const summary=el('summary','创作设置'),skill=el('select'),version=el('select'),approval=el('select'),note=el('p');
 skill.id='projectSkill';skill.setAttribute('aria-label','当前创作 Skill');version.id='projectSkillVersion';version.setAttribute('aria-label','Skill 版本');approval.id='projectApproval';approval.setAttribute('aria-label','制作审批方式');
 for(const [value,label] of [['manual','手动审批'],['auto','自动审批 · 单次预算']]){const o=el('option',label);o.value=value;approval.append(o)}
 const label=(text,control)=>{const n=el('label',text);n.append(control);return n};
 const apply=el('button','应用设置');apply.type='button';
 panel.append(summary,label('Skill',skill),label('版本',version),label('审批方式',approval),note,apply);
 document.querySelector('.compose')?.prepend(panel);$('initialSkill').disabled=true;
 let loaded=false,catalogError='',records=[],versionKey='',loadingVersion=false,versionRequest=0,projectKey='';
 async function fillVersions(sid,chosen){const ticket=++versionRequest;loadingVersion=true;apply.disabled=true;version.disabled=true;version.replaceChildren();let versions=[];
  try{if(sid.startsWith('custom-'))versions=(await api('/skills/'+sid+'/versions')).versions.map(v=>v.version);else versions=[records.find(s=>s.id===sid)?.version||1];if(ticket!==versionRequest)return;if(chosen&&!versions.includes(chosen))versions.push(chosen);for(const v of versions.sort((a,b)=>b-a)){const o=el('option','v'+v+(v===project?.skill?.version&&sid===project?.skill_id?' · 项目当前':''));o.value=v;version.append(o)}version.value=chosen||versions[0]||1;
  }catch(e){note.textContent=e.message}finally{if(ticket===versionRequest){loadingVersion=false;version.disabled=false;apply.disabled=!loaded||busy||!version.value}}}
 skill.onchange=()=>{versionKey=skill.value;fillVersions(skill.value,null)};
 function sync(){
  const locked=busy||!project||['planning','running','rendering'].includes(project.state)||project.image_task?.state==='running';
  apply.disabled=locked||!loaded||loadingVersion||!version.value;skill.disabled=approval.disabled=version.disabled=locked||loadingVersion;
  if(!project)return;editButton.disabled=false;
  const sid=project.skill_id||'ad-video';if(![...skill.options].some(o=>o.value===sid)){const o=el('option',project.skill_title||sid);o.value=sid;skill.append(o)}
  const nextKey=project.id+':'+project.revision+':'+sid+':'+project.skill?.version;if(nextKey!==projectKey){projectKey=nextKey;skill.value=sid;versionKey=''}
  if(versionKey!==skill.value){versionKey=skill.value;fillVersions(skill.value,project.skill?.version)}
  if(document.activeElement!==approval)approval.value=project.approval_mode||'manual';
  summary.textContent=(project.skill_title||'商品广告导演')+' · v'+(project.skill?.version||1)+' · '+(project.approval_mode==='auto'?'自动审批':'手动审批');
  note.textContent=project.approval_mode==='auto'?'点击“按现有信息出方案”时授权单次预算；方案完成后自动制作。':'审阅方案与费用后，点击生成整片视频。';
 }
 const locked=()=>busy||!project||['planning','running','rendering'].includes(project.state)||project.image_task?.state==='running';
 async function persistSettings(sid,v,mode){
  if(locked()||!loaded||!Number.isInteger(v)||v<1)return false;
  if(hasDrafts()){toast('请先保存画布与时间轴修改');return false}
  const changing=sid!==(project.skill_id||'ad-video')||v!==(project.skill?.version||1);
  if(!changing&&mode===(project.approval_mode||'manual'))return true;
  if(changing&&project.shots.length&&!confirm('更换 Skill 或版本将保留历史成片，重新规划当前方案。继续？'))return false;
  const pid=project.id,revision=project.revision;
  setBusy(true);try{const saved=await api('/projects/'+pid+'/creative-settings','PUT',{revision,skill_id:sid,skill_version:changing?v:null,approval_mode:mode});if(project?.id!==pid)return false;project=saved;versionKey='';clearMedia();draw();panel.open=false;if(panel.matches(':popover-open'))panel.hidePopover();toast('创作设置已保存');return true}catch(e){toast(e.message);throw e}finally{setBusy(false)}
 }
 apply.onclick=async()=>{try{await persistSettings(skill.value,Number(version.value),approval.value)}catch{}};
 const editButton=el('button','打开剪辑 ↗');editButton.type='button';editButton.id='openEditor';editButton.onclick=()=>{if(hasDrafts()){toast('请先保存当前修改');return}if(project)location.href='/creative/editor?project='+project.id};document.querySelector('.monitorbar')?.append(editButton);
 const sceneButton=el('button','3D 场景 ↗');sceneButton.type='button';sceneButton.id='openScene';sceneButton.onclick=()=>{if(hasDrafts()){toast('请先保存当前修改');return}location.href='/creative/scene'+(project?'?project='+project.id:'')};document.querySelector('.monitorbar')?.append(sceneButton);
 const oldDraw=draw;draw=function(){oldDraw();sync()};const oldBusy=setBusy;setBusy=function(v){oldBusy(v);sync()};
 let loadInFlight=false;
 async function load(){if(loadInFlight)return;loadInFlight=true;catalogError='';$('initialSkill').dataset.skillState='loading';try{const data=await api('/skills');records=data.skills;for(const select of [skill,$('initialSkill')]){const current=select.value;select.replaceChildren(...data.skills.map(s=>{const o=el('option',s.title+' · v'+s.version);o.value=s.id;o.dataset.version=s.version;return o}));select.value=current||'ad-video'}const draft=entryDraft();if(draft.skill){const select=$('initialSkill');select.value=draft.skill;let o=select.selectedOptions[0];if(!o){o=el('option','原选 Skill 暂不可读取 · 请重新选择');o.value=draft.skill;o.disabled=true;select.prepend(o);select.value=draft.skill}if(o&&!o.disabled&&draft.skillVersion){o.dataset.version=draft.skillVersion;o.textContent=(records.find(s=>s.id===draft.skill)?.title||draft.skill)+' · v'+draft.skillVersion}}$('initialSkill').onchange=()=>{const o=$('initialSkill').selectedOptions[0],s=records.find(s=>s.id===o?.value);if(s){o.dataset.version=s.version;o.textContent=s.title+' · v'+s.version}};loaded=true;if(picker.matches(':popover-open'))renderChoices();$('initialSkill').disabled=false;$('initialSkill').dataset.skillState='ready';versionKey='';projectKey='';sync()}catch(e){catalogError=e.message||'Skill 读取失败';$('initialSkill').dataset.skillState='error';if(picker.matches(':popover-open'))renderChoices();note.textContent='Skill 读取失败';const retry=el('button','重新读取');retry.type='button';retry.onclick=load;note.append(retry)}finally{loadInFlight=false}}
 // Pickers keep pending choices local until the user explicitly applies them.
 const button=(text,fn)=>{const b=el('button',text);b.type='button';b.onclick=fn;return b};
 const picker=el('section');picker.id='canvasSkillPicker';picker.className='canvas-skill-picker';picker.setAttribute('popover','auto');picker.setAttribute('aria-label','选择创作 Skill');
 const heading=el('div');heading.className='canvas-picker-heading';const close=button('关闭',()=>picker.hidePopover());close.setAttribute('aria-label','关闭 Skill 选择');heading.append(el('strong','选择 Skill'),close);
 const search=el('input');search.type='search';search.placeholder='搜索名称、适用场景或制作方法';search.setAttribute('aria-label','搜索创作 Skill');
 const filters=el('div');filters.className='canvas-skill-filters';filters.setAttribute('role','group');filters.setAttribute('aria-label','Skill 范围');let filter='all';
 for(const [value,text] of [['all','全部'],['reference','广告参考'],['custom','我的']]){const b=button(text,()=>{filter=value;renderChoices()});b.dataset.filter=value;filters.append(b)}
 const count=el('p'),list=el('div'),selected=el('section'),selectedTitle=el('strong'),selectedVersion=el('select'),detail=el('details'),detailBody=el('div'),pickerNote=el('p'),footer=el('footer');
 count.className='canvas-picker-count';count.setAttribute('role','status');list.className='canvas-skill-choices';list.setAttribute('aria-label','可用 Skill');selected.className='canvas-skill-selected';selectedVersion.setAttribute('aria-label','选用 Skill 版本');detail.append(el('summary','查看输入、步骤与检查项'),detailBody);pickerNote.className='canvas-picker-note';pickerNote.setAttribute('role','status');
 const selectRow=el('div');selectRow.className='canvas-skill-selection-row';selectRow.append(selectedTitle,selectedVersion);selected.append(selectRow,detail);const useSkill=button('使用此 Skill',()=>savePicker('skill'));useSkill.className='primary';useSkill.id='applyCanvasSkill';footer.append(button('取消',()=>picker.hidePopover()),useSkill);picker.append(heading,search,filters,count,list,selected,pickerNote,footer);document.body.append(picker);
 const modePicker=el('section');modePicker.id='canvasApprovalPicker';modePicker.className='canvas-approval-picker';modePicker.setAttribute('popover','auto');modePicker.setAttribute('aria-label','选择审批方式');const modeHead=el('div');modeHead.className='canvas-picker-heading';modeHead.append(el('strong','审批方式'),button('关闭',()=>modePicker.hidePopover()));const modeList=el('div');modeList.className='canvas-approval-choices';const modeNote=el('p');modeNote.className='canvas-picker-note';modeNote.setAttribute('role','status');const modeFooter=el('footer'),useMode=button('应用审批方式',()=>savePicker('approval'));useMode.id='applyCanvasApproval';useMode.className='primary';modeFooter.append(button('取消',()=>modePicker.hidePopover()),useMode);modePicker.append(modeHead,modeList,modeNote,modeFooter);document.body.append(modePicker);
 let draft=null,epoch=0,pickerLoading=false,committing=false,detailEpoch=0,versionError='';
 const sameProject=()=>draft&&project?.id===draft.pid&&project.revision===draft.revision;
 const chosenRecord=()=>records.find(r=>r.id===draft?.sid)||(draft?.sid===(project?.skill_id||'ad-video')?{id:draft.sid,title:project.skill_title||'当前 Skill',version:project.skill?.version||1,description:'项目使用的固定版本'}:null);
 const selectionStatus=()=>!sameProject()?'项目已更新，请关闭后重新选择。':locked()?'制作处理中，结束后可以修改。':hasDrafts()?'先保存画布与时间轴修改，再应用设置。':!loaded?'Skill 目录尚未载入。':pickerLoading?'正在读取版本…':'';
 function updatePicker(){
  if(!draft)return;const status=selectionStatus();useSkill.disabled=committing||!!status||!draft.v;useMode.disabled=committing||!!status;selectedVersion.disabled=committing||!!status;
  if(status){pickerNote.textContent=status;modeNote.textContent=status}
  else if(!committing&&!versionError){pickerNote.textContent='选择制作方法不会生成素材；应用后沿用当前模型与审批方式。';modeNote.textContent='仅保存审批偏好，不会立即开始生成。'}
 }
 function renderChoices(){
  for(const b of filters.children)b.setAttribute('aria-pressed',String(b.dataset.filter===filter));const q=search.value.trim().toLocaleLowerCase();
  const items=records.filter(r=>(filter==='all'||r.source===filter)&&(r.title+' '+(r.category||'')+' '+(r.description||'')+' '+(r.applies_to||'')).toLocaleLowerCase().includes(q));
  count.textContent=loaded?items.length+' 个 Skill':'正在载入 Skill…';if(catalogError)count.replaceChildren(el('span','Skill 目录读取失败 '),button('重新读取',load));list.replaceChildren();
  for(const r of items){const b=button('',()=>chooseSkill(r.id));b.className='canvas-skill-choice';b.dataset.skill=r.id;b.setAttribute('aria-pressed',String(r.id===draft?.sid));b.disabled=committing||locked();const visual=el('span');visual.className='canvas-skill-cover';visual.textContent=r.source==='custom'?'◇':'✦';
   const poster=r.reference_case?.id?'/creative/api/library/'+encodeURIComponent(r.reference_case.id)+'/poster':r.template_id?'/creative/api/templates/'+encodeURIComponent(r.template_id)+'/poster':null;
   if(poster){const img=el('img');img.src=poster;img.alt='';img.loading='lazy';img.onerror=()=>img.remove();visual.append(img)}
   const copy=el('span');copy.className='canvas-skill-copy';copy.append(el('strong',r.title),el('small',r.description||r.applies_to||'可复用制作方法'),el('em',(r.category||'创作方法')+' · v'+r.version));const check=el('span',r.id===draft?.sid?'✓':'+');check.className='canvas-picker-check';b.append(visual,copy,check);list.append(b)
  }
  if(!items.length)list.append(el('p',loaded?'没有匹配的 Skill，试试其他关键词或范围。':'Skill 目录正在载入。'));updatePicker();
 }
 function renderDetail(record){detailBody.replaceChildren();for(const [field,title] of [['inputs','需要准备'],['steps','制作步骤'],['checks','检查项']]){if(!record?.[field]?.length)continue;detailBody.append(el('h4',title));const ul=el('ol');for(const value of record[field])ul.append(el('li',value));detailBody.append(ul)}if(!detailBody.childElementCount)detailBody.append(el('p','详细制作方法正在读取，当前选择尚未保存。'))}
 async function loadDetail(sid,v){const ticket=++detailEpoch;const r=chosenRecord();if(!r)return;if(r.version===v)renderDetail(r);else detailBody.replaceChildren(el('p','正在读取所选版本…'));if(r.source!=='custom'&&!r.detail_available)return;
  try{const full=await api('/skills/'+encodeURIComponent(sid)+'?version='+v);if(ticket!==detailEpoch||draft?.sid!==sid||draft?.v!==v||!picker.matches(':popover-open'))return;renderDetail(full)}catch(e){if(ticket===detailEpoch){detailBody.replaceChildren(el('p',e.message),button('重读详情',()=>loadDetail(sid,v)))}}
 }
 async function chooseSkill(sid,pinned=null){
  if(!draft||committing)return;const ticket=++epoch;++detailEpoch;draft.sid=sid;draft.v=null;versionError='';pickerLoading=true;selectedVersion.replaceChildren();const record=chosenRecord();selectedTitle.textContent=record?.title||'当前 Skill';renderDetail(record);renderChoices();
  try{let versions=sid.startsWith('custom-')?(await api('/skills/'+encodeURIComponent(sid)+'/versions')).versions.map(v=>v.version):[record?.version||1];if(ticket!==epoch||!draft)return;if(pinned&&!versions.includes(pinned))versions.push(pinned);versions=[...new Set(versions)].sort((a,b)=>b-a);for(const v of versions){const option=el('option','v'+v+(sid===(project?.skill_id||'ad-video')&&v===(project?.skill?.version||1)?' · 当前':''));option.value=v;selectedVersion.append(option)}draft.v=pinned||versions[0];selectedVersion.value=String(draft.v);loadDetail(sid,draft.v);
  }catch(e){if(ticket===epoch){versionError=e.message;pickerNote.replaceChildren(el('span',e.message),button('重读版本',()=>chooseSkill(sid,pinned)))}}
  finally{if(ticket===epoch){pickerLoading=false;updatePicker()}}
 }
 selectedVersion.onchange=()=>{if(!draft)return;draft.v=Number(selectedVersion.value);loadDetail(draft.sid,draft.v);updatePicker()};search.oninput=renderChoices;
 function renderModes(){modeList.replaceChildren();for(const [value,title,description] of [['manual','手动审批','先审阅方案与费用，由你确认后生成。'],['auto','自动审批','发起方案时确认单次预算，方案就绪后自动制作。']]){const b=button('',()=>{draft.mode=value;renderModes();updatePicker()});b.dataset.mode=value;b.setAttribute('aria-pressed',String(draft?.mode===value));b.disabled=locked()||committing;const symbol=el('span');symbol.className='canvas-approval-symbol';symbol.setAttribute('aria-hidden','true');const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.setAttribute('viewBox','0 0 24 24');svg.setAttribute('fill','none');svg.setAttribute('stroke','currentColor');svg.setAttribute('stroke-width','1.6');const path=document.createElementNS(svg.namespaceURI,'path');path.setAttribute('d',value==='manual'?'M8 13V5a2 2 0 0 1 4 0v7-9a2 2 0 0 1 4 0v9-6a2 2 0 0 1 4 0v9c0 8-10 10-14 4l-4-5c-1-2 1-4 3-2l3 3':'M20 6 9 17l-5-5');svg.append(path);symbol.append(svg);const copy=el('span');copy.append(el('strong',title),el('small',description));b.append(symbol,copy,el('span',draft?.mode===value?'✓':''));modeList.append(b)}}
 function openPicker(kind,suggestedSkill=null){
  if(!project){toast('先创建一个项目，再选择创作设置');return}if(committing)return;
  if(picker.matches(':popover-open'))picker.hidePopover();if(modePicker.matches(':popover-open'))modePicker.hidePopover();
  draft={pid:project.id,revision:project.revision,sid:project.skill_id||'ad-video',v:project.skill?.version||1,mode:project.approval_mode||'manual'};pickerLoading=false;versionError='';
  if(kind==='skill'){search.value='';filter='all';detail.open=false;picker.showPopover();chooseSkill(records.some(r=>r.id===suggestedSkill)?suggestedSkill:draft.sid,records.some(r=>r.id===suggestedSkill)?null:draft.v);search.focus()}else{modePicker.showPopover();renderModes();updatePicker()}
 }
 async function savePicker(kind){
  if(committing||selectionStatus()||!draft?.v)return;committing=true;updatePicker();const pending={...draft};
  try{const saved=await persistSettings(pending.sid,pending.v,pending.mode);if(saved){(kind==='skill'?picker:modePicker).hidePopover();document.getElementById(kind==='skill'?'studioChatSkill':'studioChatApproval')?.focus()}}
  catch(e){(kind==='skill'?pickerNote:modeNote).textContent=e.message}
  finally{committing=false;useSkill.disabled=!!selectionStatus()||!draft?.v;useMode.disabled=!!selectionStatus()}
 }
 for(const [target,trigger] of [[picker,'studioChatSkill'],[modePicker,'studioChatApproval']])target.addEventListener('toggle',()=>{document.getElementById(trigger)?.setAttribute('aria-expanded',String(target.matches(':popover-open')));if(!picker.matches(':popover-open')&&!modePicker.matches(':popover-open')){++epoch;++detailEpoch;draft=null;pickerLoading=false}});
 document.addEventListener('creative-open-skill-picker',e=>openPicker('skill',e.detail?.skill));document.addEventListener('creative-open-approval-picker',()=>openPicker('approval'));
 const originalSync=sync;sync=function(){originalSync();if(draft)updatePicker()};
 document.addEventListener('creative-reload-skills',()=>{if(!loaded)load()});
 load();sync();
})();
