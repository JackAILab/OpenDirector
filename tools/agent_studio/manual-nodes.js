/* Independent manual nodes share a canvas, not a project-wide generation lock. */
(()=>{
 const cards=new Map();let root='',timer=null,loading=false,adding=false;
 const make=(tag,cls,text)=>{const e=document.createElement(tag);if(cls)e.className=cls;if(text)e.textContent=text;return e};
 // Selection belongs to the current canvas UI, never to generation state.
 function selectManualCard(card){
  document.querySelectorAll('.manual-node-selected').forEach(node=>{if(node!==card)node.classList.remove('manual-node-selected')});
  card?.classList.add('manual-node-selected');
  document.querySelectorAll('[data-manual-editor-toggle]').forEach(button=>button.setAttribute('aria-expanded',String(button.closest('.manual-root-node,.manual-generation-node')===card)));
 }
 function prepareManualSelection(card,head){
  if(!card||!head||head.querySelector('[data-manual-editor-toggle]'))return;
  const initial=!card.dataset.manualComposer;card.dataset.manualComposer='true';
  const toggle=make('button','manual-editor-toggle','编辑');toggle.type='button';toggle.dataset.manualEditorToggle='true';toggle.setAttribute('aria-label','编辑 '+(head.textContent||'生成节点').replace('×','').trim());toggle.setAttribute('aria-expanded',String(card.classList.contains('manual-node-selected')));
  toggle.onclick=()=>{selectManualCard(card);document.dispatchEvent(new CustomEvent('creative-reveal-manual-editor',{detail:{card}}))};head.append(toggle);
  if(initial&&!document.querySelector('.manual-node-selected'))selectManualCard(card);
 }
 document.addEventListener('pointerdown',event=>{
  const card=event.target.closest('.manual-root-node,.manual-generation-node');
  if(card)selectManualCard(card);
  else if(event.target.closest('.manual-root-result'))selectManualCard(document.querySelector('.manual-root-node'));
  else if(event.target.closest('.canvas-viewport,.reference-node'))selectManualCard(null);
 });
 document.addEventListener('focusin',event=>{const card=event.target.closest('.manual-root-node,.manual-generation-node');if(card)selectManualCard(card)});
 document.addEventListener('creative-focus-manual-node',event=>{const card=[...document.querySelectorAll('.manual-generation-node')].find(node=>node.dataset.manualProject===event.detail?.id);if(card)selectManualCard(card)});
 const active=p=>p.image_task?.state==='running'||['running','rendering','planning'].includes(p.state);
 const resumeOnly=p=>p.creation_mode==='video'&&p.film&&!['planned','completed','failed'].includes(p.film.state);
 const phaseText={queued:'排队中',preparing:'准备素材',submitting:'提交中',generating:'生成中',downloading:'保存结果',denoising:'生成画面',encoding:'编码视频',decoding:'解码视频',finalizing:'保存结果'};
 function status(p){const job=p.creation_mode==='image'?p.image_task:p.film;if(!job)return p.state==='planning'?'Director 正在规划':p.creation_mode==='agent'?'等待 Director 方案':'等待生成';if(job.state==='completed')return '已完成';if(job.state==='needs_review'||p.interrupted||['paused','failed'].includes(p.state))return p.state==='paused'?'任务已暂停':p.state==='failed'?'生成失败':'结果待核对';const progress=job.progress||{};return (phaseText[progress.phase||progress.stage||job.state]||'生成中')+(Number.isFinite(progress.percent)?' '+Math.round(progress.percent)+'%':'')}
 function pauseControl(host,p,c=null){
  if(p.creation_mode!=='video'||!p.film||!['running','rendering'].includes(p.state))return;
  const pause=make('button','manual-pause-tracking',p.stop_requested?'等待暂停':'暂停跟进');pause.type='button';pause.disabled=!!p.stop_requested||!!c?.stopPending;pause.title='暂停本地跟进；已提交任务可能继续生成，恢复时只查询原任务';pause.setAttribute('aria-label',c?'暂停跟进节点 '+c.index:'暂停跟进当前视频');
  pause.onclick=async()=>{if(pause.disabled)return;pause.disabled=true;if(c)c.stopPending=true;try{const latest=await api('/projects/'+p.id+'/stop','POST');if(c){c.project=latest;draw({project:latest,node:{index:c.index}})}else if(project?.id===p.id){project=latest;window.draw()}toast('已请求暂停跟进；已提交任务可能继续生成，恢复时查询原任务。')}catch(e){toast(e.message);pause.disabled=false}finally{if(c)c.stopPending=false;refresh()}};host.append(pause);
 }
 function progressMeter(host,p){
  let meter=host.querySelector('.manual-progress-meter');
  if(!active(p)){meter?.remove();return}
  if(!meter){meter=make('div','manual-progress-meter');meter.setAttribute('role','progressbar');meter.setAttribute('aria-label','生成进度');meter.setAttribute('aria-valuemin','0');meter.setAttribute('aria-valuemax','100');meter.append(make('span'));host.append(meter)}
  const job=p.creation_mode==='image'?p.image_task:p.film,percent=job?.progress?.percent,known=Number.isFinite(percent);
  meter.dataset.determinate=String(known);meter.setAttribute('aria-valuetext',status(p));
  if(known){const value=Math.max(0,Math.min(100,percent));meter.setAttribute('aria-valuenow',String(value));meter.firstChild.style.width=value+'%'}else{meter.removeAttribute('aria-valuenow');meter.firstChild.style.removeProperty('width')}
 }
 let referenceEdges=null,edgeFrame=0,edgeObserver=null;
 const svgElement=tag=>document.createElementNS('http://www.w3.org/2000/svg',tag);
 function scheduleReferenceEdges(){if(!edgeFrame)edgeFrame=requestAnimationFrame(drawReferenceEdges)}
 function drawReferenceEdges(){
  edgeFrame=0;const world=document.querySelector('.canvas-world');if(!world)return;
  if(!referenceEdges||!referenceEdges.isConnected){referenceEdges=svgElement('svg');referenceEdges.classList.add('manual-reference-edges');referenceEdges.setAttribute('aria-label','已确认的节点参考关系');referenceEdges.setAttribute('width','1400');referenceEdges.setAttribute('height','1100');world.prepend(referenceEdges);
   edgeObserver?.disconnect();edgeObserver=new MutationObserver(records=>{if(records.some(r=>!referenceEdges.contains(r.target)))scheduleReferenceEdges()});edgeObserver.observe(world,{subtree:true,childList:true,attributes:true,attributeFilter:['style','hidden']});
  }
  const sources=[...world.querySelectorAll('.reference-node')],scale=new DOMMatrixReadOnly(getComputedStyle(world).transform).a||1,origin=world.getBoundingClientRect(),fragment=document.createDocumentFragment(),keptPaths=new Set();
  for(const source of sources)installReferencePort(source);
  const targets=[...cards.values()],main=world.querySelector('.manual-root-node');if(main&&!main.hidden&&['image','video'].includes(project?.creation_mode)){const empty=main.querySelector('.studio-manual-empty-node:not([hidden]) .studio-free-node-preview');targets.push({project,card:main,preview:empty||world.querySelector('.manual-primary-result')||main,index:1})}
  for(const c of targets){
   if(!c.card.isConnected||!c.card.getClientRects().length)continue;
   for(const reference of (c.project.creation_mode==='image'?c.project.image_task?.prepared?.references:c.project.video_inputs?.references)||[]){
    const node=project?.canvas?.nodes.find(n=>n.asset===reference.asset),source=node&&sources.find(e=>e.dataset.nodeId===node.id);if(!source||!source.getClientRects().length||source===c.preview)continue;
    const a=source.getBoundingClientRect(),b=c.preview.getBoundingClientRect(),forward=a.left<b.left,stacked=a.left<b.right&&b.left<a.right;
    const x1=((stacked||forward?a.right:a.left)-origin.left)/scale,y1=(a.top+a.height/2-origin.top)/scale,x2=((!stacked&&forward?b.left:b.right)-origin.left)/scale,y2=(b.top+b.height/2-origin.top)/scale;
    const bend=Math.max(60,Math.abs(x2-x1)*.45)*(forward?1:-1),path=[...referenceEdges.querySelectorAll('path')].find(p=>p.dataset.source===node.id&&p.dataset.target===c.project.id)||svgElement('path');keptPaths.add(path);path.setAttribute('d',`M ${x1} ${y1} C ${stacked?Math.max(x1,x2)+80:x1+bend} ${y1}, ${stacked?Math.max(x1,x2)+80:x2-bend} ${y2}, ${x2} ${y2}`);path.dataset.source=node.id;path.dataset.target=c.project.id;path.classList.toggle('is-running',active(c.project));const title=svgElement('title');title.textContent=(node.label||'图片')+' → '+(c.project.creation_mode==='image'?'图片':'视频')+'节点 '+c.index;path.replaceChildren(title);
    if(c.project.creation_mode==='video'){
     path.classList.add('editable-reference-edge');path.setAttribute('role','button');path.setAttribute('tabindex','0');path.setAttribute('aria-label','管理参考 '+(node.label||'图片')+' → 视频节点 '+c.index);path.setAttribute('aria-disabled',String(active(c.project)||resumeOnly(c.project)));
     const edit=()=>{if(active(c.project)||resumeOnly(c.project)||c.busy){toast('任务尚未结束，暂不能修改参考输入');return}if(c.project.id===project.id)document.dispatchEvent(new CustomEvent('creative-root-reference-manage',{detail:{asset:reference.asset}}));else configureReferences(c,null,reference.asset)};
     path.onpointerdown=e=>e.stopPropagation();path.onclick=e=>{e.stopPropagation();edit()};path.onkeydown=e=>{if(['Enter',' '].includes(e.key)){e.preventDefault();e.stopPropagation();edit()}};
    }
    if(!path.isConnected)fragment.append(path);
    for(const [x,y] of [[x1,y1],[x2,y2]]){const dot=svgElement('circle');dot.setAttribute('cx',x);dot.setAttribute('cy',y);dot.setAttribute('r','4');fragment.append(dot)}
   }
  }
  referenceEdges.querySelectorAll('path').forEach(p=>{if(!keptPaths.has(p))p.remove()});referenceEdges.querySelectorAll('circle').forEach(c=>c.remove());referenceEdges.append(fragment);
 }
 window.addEventListener('resize',scheduleReferenceEdges);
 document.addEventListener('creative-state-change',scheduleReferenceEdges);
 document.addEventListener('creative-fit-canvas',scheduleReferenceEdges);
 const referenceDragType='application/x-visualagent-reference';
 function installReferencePort(source){
  const node=project?.canvas?.nodes.find(n=>n.id===source.dataset.nodeId);if(node?.kind!=='image'||source.querySelector('.manual-reference-port'))return;
  const port=make('button','manual-reference-port','+');port.type='button';port.draggable=true;port.title='拖到图片或视频生成节点，添加参考';port.setAttribute('aria-label','拖动图片参考 '+(node.label||'图片'));
  port.addEventListener('pointerdown',e=>e.stopPropagation());port.ondragstart=e=>{e.stopPropagation();e.dataTransfer.effectAllowed='copy';e.dataTransfer.setData(referenceDragType,JSON.stringify({parent:project.id,asset:node.asset}));document.body.classList.add('dragging-workspace-reference')};
  port.ondragend=()=>{document.body.classList.remove('dragging-workspace-reference');document.querySelectorAll('.manual-reference-drop-target').forEach(e=>e.classList.remove('manual-reference-drop-target'))};
  source.append(port);
 }
 function installResultPort(c){
  const existing=c.preview.querySelector('.manual-result-reference-port');
  if(c.project.creation_mode!=='image'||c.project.image_task?.state!=='completed'||!c.asset||active(c.project)){existing?.remove();return}
  if(existing?.dataset.asset===c.asset)return;existing?.remove();
  const port=make('button','manual-reference-port manual-result-reference-port','+');port.dataset.asset=c.asset;port.type='button';port.draggable=true;port.title='拖到其他生成节点，使用这张图片作为参考';port.setAttribute('aria-label','拖动生成图片 节点 '+c.index);
  port.onpointerdown=e=>e.stopPropagation();port.ondragstart=e=>{e.stopPropagation();e.dataTransfer.effectAllowed='copy';e.dataTransfer.setData(referenceDragType,JSON.stringify({parent:root,child:c.project.id,asset:c.asset}));document.body.classList.add('dragging-workspace-reference')};
  port.ondragend=()=>{document.body.classList.remove('dragging-workspace-reference');document.querySelectorAll('.manual-reference-drop-target').forEach(e=>e.classList.remove('manual-reference-drop-target'))};c.preview.append(port);
 }
 function installReferenceDrop(c){
  const allowed=e=>[...e.dataTransfer.types].includes(referenceDragType)&&!c.referenceImportPending&&!c.busy&&!active(c.project)&&!resumeOnly(c.project)&&c.project.image_task?.state!=='needs_review'&&['image','video'].includes(c.project.creation_mode);
  c.preview.ondragover=e=>{if(!allowed(e))return;e.preventDefault();e.stopPropagation();e.dataTransfer.dropEffect='copy';c.preview.classList.add('manual-reference-drop-target')};
  c.preview.ondragleave=e=>{if(!c.preview.contains(e.relatedTarget))c.preview.classList.remove('manual-reference-drop-target')};
  c.preview.ondrop=async e=>{c.preview.classList.remove('manual-reference-drop-target');document.body.classList.remove('dragging-workspace-reference');if(!allowed(e))return;e.preventDefault();e.stopPropagation();let data;try{data=JSON.parse(e.dataTransfer.getData(referenceDragType))}catch{return}const pid=root;if(data.parent!==pid)return;
   if(data.child){const source=cards.get(data.child);if(!source||source===c||source.project.creation_mode!=='image'||source.project.image_task?.state!=='completed'||source.asset!==data.asset||active(source.project))return;if(hasDrafts()){toast('请先保存当前画布修改，再使用生成结果');return}}
   else if(!project.canvas?.nodes.some(n=>n.kind==='image'&&n.asset===data.asset))return;
   c.referenceImportPending=true;if(!c.isRoot)c.busy=true;
   try{if(data.child){const result=await api('/projects/'+pid+'/manual-nodes/'+encodeURIComponent(data.child)+'/result','POST');if(root!==pid||project?.id!==pid)return;project=result.project;window.draw();if(result.node.asset!==data.asset)throw Error('图片结果已更新，请重新选择参考');}
    if(c.isRoot){document.dispatchEvent(new CustomEvent('creative-root-reference-drop',{detail:{project:pid,asset:data.asset}}));return}
    c.project=await api('/projects/'+pid+'/manual-nodes/'+c.project.id+'/reference','POST',{revision:c.project.revision,asset:data.asset});c.busy=false;if(root===pid&&c.card.isConnected)await configureReferences(c,data.asset)}catch(error){toast(error.message)}finally{c.referenceImportPending=false;if(!c.isRoot)c.busy=false;refresh()}
  };
 }
 const referenceStrips=new Map();
 function clearReferenceStrip(panel){const state=referenceStrips.get(panel);if(!state)return;state.controller.abort();state.urls.forEach(URL.revokeObjectURL);state.strip.remove();referenceStrips.delete(panel)}
 function syncReferenceStrip(c){
  const panel=c.card.querySelector(c.isRoot?'.studio-manual-image-compose':'.manual-node-editor');if(!panel)return;
  const p=c.project,isImage=p.creation_mode==='image',inFlight=isImage&&p.image_task?.state==='running',mode=p.video_inputs?.mode||'text';let draft=null;try{draft=JSON.parse(sessionStorage.getItem('manual-image-draft:'+p.id)||'null')}catch{}
  const selected=isImage?(inFlight?p.image_task?.prepared?.references:draft?.references):p.video_inputs?.references;
  const refs=Array.isArray(selected)?selected.filter(r=>r&&p.canvas_assets?.[r.asset]?.kind==='image'):[];
  if(!refs.length){clearReferenceStrip(panel);return}
  const assetSignature=JSON.stringify([p.id,p.creation_mode,refs.map(r=>r.asset)]),blocked=active(p)||resumeOnly(p)||c.busy||p.image_task?.state==='needs_review';
  const stripLabel=isImage?(inFlight?'本次生成图片参考':'下次生成图片参考'):'视频输入参考图片';
  function updateTile(tile,ref,index){
   const slot=isImage?`图 ${index+1} · ${{product:'商品',person:'人物',scene:'场景',style:'风格',reference:'参考'}[ref.role]||'参考'}`:mode==='first_last'?(index?'尾帧':'首帧'):mode==='first_frame'?'首帧':`参考 ${index+1}`,name=p.canvas?.nodes?.find(n=>n.asset===ref.asset)?.label||'参考图片';
   tile.disabled=!!blocked;tile.title=slot+' · '+name+(tile.classList.contains('preview-unavailable')?' · 预览暂不可用，点击查看参考设置':'');tile.setAttribute('aria-label','编辑'+slot+' '+name);tile.querySelector('.manual-input-reference-slot').textContent=slot;const img=tile.querySelector('img');if(img)img.alt=name;
   tile.onclick=()=>{if(tile.disabled)return;if(c.isRoot)document.dispatchEvent(new CustomEvent(isImage?'creative-root-image-reference-manage':'creative-root-reference-manage',{detail:{asset:ref.asset}}));else configureReferences(c,null,ref.asset)};
  }
  let state=referenceStrips.get(panel);
  if(state?.assetSignature===assetSignature){state.strip.setAttribute('aria-label',stripLabel);state.strip.querySelectorAll('button').forEach((tile,index)=>updateTile(tile,refs[index],index));return}
  const addedStrip=!state;clearReferenceStrip(panel);const strip=make('div','manual-input-reference-strip');strip.setAttribute('aria-label',stripLabel);
  state={strip,assetSignature,controller:new AbortController(),urls:[]};referenceStrips.set(panel,state);panel.querySelector('textarea').before(strip);
  refs.forEach((ref,index)=>{
   const tile=make('button','manual-input-reference'),img=make('img'),badge=make('span','manual-input-reference-slot');tile.type='button';tile.dataset.asset=ref.asset;tile.append(img,badge);strip.append(tile);updateTile(tile,ref,index);
   fetch('/creative/api/projects/'+p.id+'/canvas/assets/'+ref.asset+'/preview',{headers:{Authorization:'Bearer '+key},signal:AbortSignal.any([state.controller.signal,AbortSignal.timeout(15000)])}).then(r=>{if(!r.ok)throw Error();return r.blob()}).then(blob=>{if(state.controller.signal.aborted||!strip.isConnected)return;const url=URL.createObjectURL(blob);state.urls.push(url);img.src=url}).catch(()=>{if(state.controller.signal.aborted)return;tile.classList.add('preview-unavailable');img.remove();tile.prepend(make('span','manual-input-reference-fallback','图片'));tile.title+=' · 预览暂不可用，点击查看参考设置'});
  });
  // Role/order/task-state changes preserve the user's current camera; only a new row adds height.
  requestAnimationFrame(()=>{if(!strip.isConnected)return;if(addedStrip)document.dispatchEvent(new Event('creative-fit-canvas'));else scheduleReferenceEdges()});
 }
 function clear(){for(const panel of referenceStrips.keys())clearReferenceStrip(panel);for(const c of cards.values()){if(c.url)URL.revokeObjectURL(c.url);c.picker?.destroy();c.card.remove()}cards.clear();scheduleReferenceEdges();document.body.classList.remove('manual-node-focus')}
 async function media(c,p){const imageResult=p.creation_mode==='image'||(p.creation_mode==='agent'&&!p.artifact&&p.image_task?.state==='completed');const asset=imageResult?p.image_task?.asset:p.artifact;if(!asset||c.asset===asset)return;c.asset=asset;const suffix=imageResult?'/canvas/assets/'+asset+'/preview':'/media/final';try{const r=await fetch('/creative/api/projects/'+p.id+suffix,{headers:{Authorization:'Bearer '+key}});if(!r.ok)throw Error();const blob=await r.blob();if(!c.card.isConnected)return;if(c.url)URL.revokeObjectURL(c.url);c.url=URL.createObjectURL(blob);const el=make(imageResult?'img':'video');el.src=c.url;if(el.tagName==='VIDEO'){el.controls=true;el.playsInline=true}el.alt='生成结果';c.preview.replaceChildren(el,c.label);progressMeter(c.preview,c.project);installResultPort(c);c.open.hidden=false}catch{c.asset=null;c.label.textContent='结果读取失败，下次同步将重新读取'}}
 function imageContext(c){return {project:()=>c.project,initial:{model:c.model.value,prompt:c.prompt.value},imageModel:()=>c.model.value,locked:()=>c.busy||active(c.project)||c.project.image_task?.state==='needs_review',hasDrafts:()=>false,api,toast,busy:v=>{c.busy=v;c.send.disabled=v||active(c.project)},accepted:p=>{c.project=p;refresh()},preview:async aid=>{const r=await fetch('/creative/api/projects/'+c.project.id+'/canvas/assets/'+aid+'/preview',{headers:{Authorization:'Bearer '+key}});if(!r.ok)throw Error();return URL.createObjectURL(await r.blob())}}}
 function storeImageDraft(c){try{const draft=JSON.parse(sessionStorage.getItem('manual-image-draft:'+c.project.id)||'{}');sessionStorage.setItem('manual-image-draft:'+c.project.id,JSON.stringify({...draft,prompt:c.prompt.value,model:c.model.value}))}catch{}}
 function syncImageDraft(c){try{const draft=JSON.parse(sessionStorage.getItem('manual-image-draft:'+c.project.id)||'null');if(draft){c.prompt.value=draft.prompt;c.model.value=draft.model;c.picker.sync();c.prompt.dispatchEvent(new Event('input'));c.refs.textContent=draft.references?.length?'参考 · '+draft.references.length:'参考'}}catch{}syncReferenceStrip(c)}
 async function configureReferences(c,initialAsset=null,focusAsset=null,initialMode=null){try{if(c.project.creation_mode==='image'){const {openImageComposer}=await import('/creative/image-composer.js');const ctx=imageContext(c);ctx.initial.focusAsset=focusAsset;if(initialAsset){let saved={};try{saved=JSON.parse(sessionStorage.getItem('manual-image-draft:'+c.project.id)||'{}')}catch{}ctx.initial.references=(saved.references||[]).some(r=>r.asset===initialAsset)?saved.references:[...(saved.references||[]),{asset:initialAsset,role:'reference',instruction:''}]}await openImageComposer(ctx);document.getElementById('imageComposer')?.addEventListener('close',()=>syncImageDraft(c),{once:true});return}const {openVideoInputs}=await import('/creative/video-inputs.js');await openVideoInputs({initialAsset,focusAsset,initialMode,project:()=>c.project,draft:{model:c.model.value,duration:Number(c.duration.value),prompt:c.prompt.value},locked:()=>active(c.project)||c.busy,hasDrafts:()=>false,api,toast,busy:v=>{c.busy=v},accepted:p=>{c.project=p;c.model.value=p.model;c.model.dispatchEvent(new Event('change'));c.duration.value=String(p.duration);c.prompt.value=p.direct_prompt||'';refresh()},preview:async aid=>{const r=await fetch('/creative/api/projects/'+c.project.id+'/canvas/assets/'+aid+'/preview',{headers:{Authorization:'Bearer '+key}});if(!r.ok)throw Error();return URL.createObjectURL(await r.blob())}})}catch(e){toast(e.message)}}
 async function references(c){
  if(c.busy||active(c.project)||resumeOnly(c.project))return;
  const pid=root,dialog=make('dialog','manual-reference-dialog'),urls=[],headingText='从当前画布添加'+(c.project.creation_mode==='image'?'图片':'视频')+'参考';dialog.setAttribute('aria-label',headingText);
  const heading=make('div','image-composer-head'),close=make('button','','×');close.type='button';close.setAttribute('aria-label','关闭画布参考');close.onclick=()=>dialog.close();heading.append(make('strong','',headingText),close);
  const choices=make('div','image-composer-choices'),note=make('p','','添加图片后，在参考设置中选择输入模式与图片。保存不会开始生成。'),configure=make('button','','配置已添加参考');configure.type='button';
  const assets=Object.values(project.canvas_assets||{}).filter(a=>a.kind==='image'&&project.canvas?.nodes.some(n=>n.asset===a.id));
  for(const asset of assets){const button=make('button'),img=make('img'),label=project.canvas.nodes.find(n=>n.asset===asset.id)?.label||'画布图片';button.type='button';button.dataset.asset=asset.id;img.alt=label;button.append(img,make('span','',label));choices.append(button);
   fetch('/creative/api/projects/'+pid+'/canvas/assets/'+asset.id+'/preview',{headers:{Authorization:'Bearer '+key}}).then(r=>{if(!r.ok)throw Error();return r.blob()}).then(blob=>{if(!dialog.isConnected)return;const url=URL.createObjectURL(blob);urls.push(url);img.src=url}).catch(()=>{img.alt='图片预览暂不可用'});
   if(c.project.canvas_assets?.[asset.id]){button.disabled=true;button.append(make('small','','已添加'))}
   button.onclick=async()=>{c.busy=true;dialog.querySelectorAll('button').forEach(b=>b.disabled=true);try{c.project=await api('/projects/'+pid+'/manual-nodes/'+c.project.id+'/reference','POST',{revision:c.project.revision,asset:asset.id});button.dataset.added='true';button.append(make('small','','已添加'));note.textContent='图片已添加，点击「配置已添加参考」选择模型输入。'}catch(e){note.textContent=e.message}finally{c.busy=false;dialog.querySelectorAll('button').forEach(b=>b.disabled=!!b.dataset.added||!!c.project.canvas_assets?.[b.dataset.asset]);refresh()}};
  }
  if(!assets.length)choices.append(make('p','','当前画布还没有图片。可先上传图片，或将其他节点的生成结果加入画布。'));
  configure.onclick=()=>{dialog.close();if(root===pid&&c.card.isConnected)configureReferences(c)};
  dialog.append(heading,note,choices,configure);document.body.append(dialog);dialog.addEventListener('cancel',e=>{if(c.busy)e.preventDefault()});dialog.addEventListener('close',()=>{urls.forEach(URL.revokeObjectURL);dialog.remove()});dialog.showModal();
 }
 function moveNode(c,head){
  let drag=null;
  head.style.touchAction='none';head.style.cursor='grab';
  head.onpointerdown=e=>{if(e.button!==0||c.saving||e.target.closest('button,a,input,textarea,select,video'))return;e.preventDefault();e.stopPropagation();const world=c.card.parentElement,scale=new DOMMatrixReadOnly(getComputedStyle(world).transform).a||1;drag={parent:c.isRoot?c.project.id:root,id:e.pointerId,x:e.clientX,y:e.clientY,left:c.card.offsetLeft,top:c.card.offsetTop,scale};c.dragging=true;c.card.dataset.manualMoving='true';head.setPointerCapture(e.pointerId);head.style.cursor='grabbing'};
  head.onpointermove=e=>{if(!drag||e.pointerId!==drag.id)return;document.dispatchEvent(new Event('creative-camera-touched'));c.card.style.left=Math.max(-10000,Math.min(10000,drag.left+(e.clientX-drag.x)/drag.scale))+'px';c.card.style.top=Math.max(-10000,Math.min(10000,drag.top+(e.clientY-drag.y)/drag.scale))+'px'};
  const finish=async e=>{if(!drag||e.pointerId!==drag.id)return;const before=drag;drag=null;c.dragging=false;head.style.cursor='grab';if(head.hasPointerCapture(e.pointerId))head.releasePointerCapture(e.pointerId);if(e.type==='pointercancel'){c.card.style.left=before.left+'px';c.card.style.top=before.top+'px';delete c.card.dataset.manualMoving;return}const x=c.card.offsetLeft,y=c.card.offsetTop;if(x===before.left&&y===before.top){delete c.card.dataset.manualMoving;return}c.saving=true;try{await api('/projects/'+before.parent+'/manual-nodes/'+c.project.id+'/position','PATCH',{x,y});if(c.isRoot){c.card.dataset.manualPlaced='true';if(project?.id===c.project.id)project.manual_position={x,y}}}catch(error){c.card.style.left=before.left+'px';c.card.style.top=before.top+'px';toast('位置未保存：'+error.message)}finally{c.saving=false;delete c.card.dataset.manualMoving}};
  head.onpointerup=finish;head.onpointercancel=finish;
 }
 function emptyVideo(c){
  if(c.project.creation_mode!=='video')return;
  let empty=c.preview.querySelector('.manual-video-empty');
  const idle=!c.project.film&&!c.asset&&!active(c.project);
  if(!idle){empty?.remove();return}
  if(!empty){empty=make('div','manual-video-empty');const icon=make('span','manual-video-empty-icon','▶'),hint=make('small','','尝试：');icon.setAttribute('aria-hidden','true');empty.append(icon,hint);for(const [mode,label]of [['first_frame','首帧生成视频'],['first_last','首尾帧生成视频'],['references','参考图片生成视频']]){const button=make('button','',label);button.type='button';button.dataset.videoStart=mode;button.onclick=()=>configureReferences(c,null,null,mode);empty.append(button)}c.preview.append(empty)}
  const caps=catalog.find(m=>m.id===c.model.value)?.video_input_modes||{};for(const button of empty.querySelectorAll('button')){button.disabled=!(button.dataset.videoStart in caps);button.title=button.disabled?'当前模型尚不支持此模式':''}c.label.hidden=true;
 }
 function draw(item){let c=cards.get(item.project.id);const p=item.project;
  const directorAsset=p.creation_mode==='agent'?(p.state==='completed'&&p.result_artifact===p.artifact?p.result_asset:p.image_task?.state==='completed'?p.image_task.asset:null):null;
  if(directorAsset&&project?.canvas?.nodes.some(n=>n.asset===directorAsset)){if(c){if(c.url)URL.revokeObjectURL(c.url);c.picker?.destroy();c.card.remove();cards.delete(p.id)}return}
  if(p.creation_mode==='agent'&&!p.film&&!p.artifact&&p.image_task?.state!=='completed'){if(c){c.picker?.destroy();c.card.remove();cards.delete(p.id)}return}
  if(!c){const card=make('section','canvas-card manual-generation-node');card.dataset.manualProject=p.id;card.style.left=(item.node.x??(660+(cards.size%3)*580))+'px';card.style.top=(item.node.y??(40+Math.floor(cards.size/3)*620))+'px';
   const head=make('div','manual-node-head',(p.creation_mode==='image'?'图片':'视频')+'节点 '+item.node.index),preview=make('div','manual-node-preview'),label=make('span','manual-node-status','等待生成');label.setAttribute('role','status');preview.append(label);
   const editor=make('div','manual-node-editor'),prompt=make('textarea');prompt.placeholder='描述你想生成的画面内容';prompt.setAttribute('aria-label','节点 '+item.node.index+' 生成要求');let draft={};try{draft=JSON.parse(sessionStorage.getItem('manual-node:'+p.id)||'{}')}catch{}prompt.value=draft.prompt??(p.image_task?.prompt||((p.direct_prompt||'').startsWith('新建')?'':p.direct_prompt)||'');prompt.oninput=()=>saveDraft();
   const note=make('p','manual-node-notice');note.setAttribute('role','status');note.hidden=true;
   const row=make('div','manual-node-options'),model=make('select'),duration=make('select'),cost=make('span'),send=make('button','','↑'),open=make('button','manual-result-edit','在当前画布编辑');open.type='button';open.hidden=true;open.title='把已完成结果加入当前画布的编辑区';open.onclick=()=>document.dispatchEvent(new CustomEvent('creative-import-manual-result',{detail:{child:p.id}}));send.type='button';send.setAttribute('aria-label','生成节点 '+item.node.index);model.setAttribute('aria-label','节点 '+item.node.index+' 模型');duration.setAttribute('aria-label','节点 '+item.node.index+' 时长');
   const models=p.creation_mode==='image'?[...document.querySelectorAll('#imageModelSelect option')].map(o=>({id:o.value,label:o.textContent,disabled:o.disabled})):catalog.map(m=>({...m,disabled:!m.manual_available}));
   models.forEach(m=>{const option=new Option(m.label,m.id);option.disabled=!!m.disabled;model.append(option)});model.value=p.creation_mode==='image'?p.image_model:([ ...model.options].some(o=>o.value===draft.model&&!o.disabled)?draft.model:p.model);
   function prices(){const m=catalog.find(m=>m.id===model.value),previous=duration.value||String(p.duration);duration.replaceChildren(...(m?.manual_durations||[15]).map(n=>new Option(n+' 秒',n)));duration.value=[...duration.options].some(o=>o.value===previous)?previous:[...duration.options].at(-1)?.value;cost.textContent=p.creation_mode==='image'?'1 积分':((m?.credits_per_5s||0)*Math.ceil(Number(duration.value)/5))+' 积分'}
   function saveDraft(){sessionStorage.setItem('manual-node:'+p.id,JSON.stringify({prompt:prompt.value,model:model.value,duration:Number(duration.value)}))}
   model.onchange=()=>{prices();saveDraft();if(c)emptyVideo(c)};duration.onchange=()=>{saveDraft();const m=catalog.find(m=>m.id===model.value);cost.textContent=(m.credits_per_5s*Math.ceil(Number(duration.value)/5))+' 积分'};duration.hidden=p.creation_mode==='image';prices();if(p.creation_mode==='video'&&[...duration.options].some(o=>o.value===String(draft.duration))){duration.value=String(draft.duration);duration.onchange()}
   const refs=make('button','manual-node-reference','参考');refs.type='button';refs.hidden=!['image','video'].includes(p.creation_mode);refs.onclick=()=>references(c);refs.setAttribute('aria-label','节点 '+item.node.index+' 参考图片');const mode=make('button','manual-video-mode','文生视频');mode.type='button';mode.hidden=p.creation_mode!=='video';mode.setAttribute('aria-label','节点 '+item.node.index+' 生成模式');mode.onclick=()=>configureReferences(c);row.append(model,mode,duration,cost,send);const picker=window.installStudioModelPicker(model);const referenceBar=make('div','manual-reference-bar');referenceBar.append(refs);editor.append(referenceBar,prompt,row,note,open);if(p.creation_mode==='agent'){referenceBar.hidden=true;prompt.hidden=true;row.hidden=true;head.textContent='Director · 生成结果';}card.append(head,preview,editor);document.querySelector('.canvas-world').append(card);c={card,preview,label,prompt,model,duration,cost,note,send,open,index:item.node.index,project:p,busy:false,picker,refs,prices,mode};cards.set(p.id,c);installReferenceDrop(c);if(p.creation_mode==='image'){c.prompt.addEventListener('input',()=>storeImageDraft(c));c.model.addEventListener('change',()=>storeImageDraft(c));syncImageDraft(c)}moveNode(c,head);moveNode(c,preview);preview.addEventListener('dragstart',e=>{if(e.target.tagName==='IMG')e.preventDefault()});if(p.creation_mode!=='agent')prepareManualSelection(card,head);requestAnimationFrame(()=>document.dispatchEvent(new Event('creative-fit-canvas')));send.onclick=()=>submit(c);card.addEventListener('pointerdown',()=>document.body.classList.add('manual-node-focus'));}
  c.project=p;c.mode.textContent=({text:'文生视频',first_frame:'首帧生成',first_last:'首尾帧',references:'全能参考'})[p.video_inputs?.mode||p.input_manifest?.mode||'text']||'选择模式';if(p.creation_mode!=='image')c.refs.textContent=p.video_inputs?.references?.length?'参考 · '+p.video_inputs.references.length:'参考';const resume=resumeOnly(p),blocked=active(p)||c.busy||p.image_task?.state==='needs_review';c.send.disabled=blocked;c.refs.disabled=blocked||!!resume;c.mode.disabled=blocked||!!resume;c.model.disabled=blocked||!!resume;c.duration.disabled=blocked||!!resume;c.prompt.readOnly=blocked||!!resume;syncReferenceStrip(c);
  if(resume){if(!c.resume)c.pendingDraft={prompt:c.prompt.value,model:c.model.value,duration:c.duration.value};c.prompt.value=p.direct_prompt||'';c.model.value=p.model;c.prices();c.duration.value=String(p.duration)}else if(c.resume&&c.pendingDraft!==undefined){c.prompt.value=c.pendingDraft.prompt;c.model.value=c.pendingDraft.model;c.prices();c.duration.value=c.pendingDraft.duration;delete c.pendingDraft}c.resume=!!resume;
  const action=resume?(p.film.job_id?'恢复查询节点 ':'重新提交节点 '):'生成节点 ';c.send.setAttribute('aria-label',action+c.index);c.send.title=resume?(p.film.job_id?'只查询原任务，不重新生成':'按原提示词和参数重新提交'):action+c.index;
  c.cost.textContent=resume?(p.film.job_id?'查询原任务':(p.quote?.credits??0)+' 积分'):p.creation_mode==='image'?'1 积分':((catalog.find(m=>m.id===c.model.value)?.credits_per_5s||0)*Math.ceil(Number(c.duration.value)/5))+' 积分';
  c.note.textContent=p.error||p.image_task?.error||(resume?'当前参数属于已提交任务；完成后可编辑新版本':'');c.note.hidden=!c.note.textContent;c.label.textContent=status(p);pauseControl(c.label,p,c);c.label.hidden=!!c.asset&&!active(p)&&!p.error&&!p.interrupted&&!['paused','failed'].includes(p.state);c.picker.sync();c.card.setAttribute('aria-busy',String(active(p)));document.body.classList.toggle('workspace-child-generating',[...cards.values()].some(n=>active(n.project)));media(c,p);progressMeter(c.preview,p);installResultPort(c);emptyVideo(c);scheduleReferenceEdges();
 }
 async function submit(c){if(c.busy||active(c.project))return;const prompt=c.prompt.value.trim();if(prompt.length<2){toast('请填写生成要求');return}c.busy=true;c.send.disabled=true;let p=c.project;try{
  if(p.creation_mode==='image'){const {generateManualImage}=await import('/creative/image-composer.js');c.busy=false;await generateManualImage(imageContext(c));return}
  else{if(!p.film||['planned','completed','failed'].includes(p.film.state))p=await api('/projects/'+p.id+'/manual-prompt','PATCH',{revision:p.revision,prompt,model:c.model.value,duration:Number(c.duration.value)});const budget=await api('/projects/'+p.id+'/budget');if(!budget.sufficient)throw Error('账户积分不足');if(budget.revision!==p.revision||budget.required_credits!==p.quote.credits)throw Error('输入或费用已变化，请核对后重新发送');p=await api('/projects/'+p.id+'/execute','POST',{revision:p.revision,approved_credits:p.quote.credits})}
  c.project=p;c.label.textContent=status(p);toast(resumeOnly(p)&&p.film?.job_id?'正在查询原任务，可继续编辑其他节点':'节点已提交，可继续创建其他节点');
 }catch(e){toast(e.message);try{c.project=await api('/projects/'+p.id)}catch{}}finally{c.busy=false;c.send.disabled=active(c.project);refresh()}}
 let directorImportPending=false;const directorImportFailures=new Set();
 async function syncDirectorResult(items){
  if(directorImportPending||hasDrafts()||active(project))return;
  for(const {project:child} of items){
   if(child.creation_mode!=='agent')continue;
   const asset=child.state==='completed'&&child.result_artifact===child.artifact?child.result_asset:child.image_task?.state==='completed'?child.image_task.asset:null;
   if(!asset||project.canvas?.nodes.some(node=>node.asset===asset))continue;
   const token=root+':'+child.id+':'+asset;if(directorImportFailures.has(token))continue;
   const parent=root;directorImportPending=true;
   try{const result=await api('/projects/'+parent+'/manual-nodes/'+child.id+'/result','POST');if(root===parent&&project?.id===parent){project=result.project;window.draw();document.dispatchEvent(new Event('creative-state-change'))}}
   catch(error){directorImportFailures.add(token);toast('Director 素材同步未完成：'+error.message+'；可在结果节点中重新加入画布')}
   finally{directorImportPending=false}
   break;
  }
 }
 async function refresh(){clearTimeout(timer);const p=typeof project==='undefined'?null:project;if(!p){if(root){clear();root=''}return}if(root!==p.id){clear();root=p.id}if(loading)return;const pid=root;loading=true;try{const r=await api('/projects/'+pid+'/manual-nodes');if(project?.id===pid){for(const item of r.nodes)draw(item);await syncDirectorResult(r.nodes)}}catch{for(const c of cards.values())if(active(c.project))c.label.textContent='同步中断，正在重新连接'}finally{loading=false;if(project?.id===pid)timer=setTimeout(refresh,4000)}}
 function rootStatus(){const preview=document.querySelector('.studio-manual-empty-node .studio-free-node-preview');if(!preview)return;let badge=preview.querySelector('.manual-root-progress');if(project?.creation_mode==='video'&&project.film&&!project.artifact){if(!badge){badge=make('span','manual-node-status manual-root-progress');badge.setAttribute('role','status');preview.append(badge)}badge.replaceChildren(make('span','',status(project)));pauseControl(badge,project);if(project.error)badge.append(make('small','manual-root-error',project.error));if(project.state==='paused'){const resume=make('button','',project.film?.job_id?'恢复查询':'重新提交');resume.type='button';resume.onclick=()=>executeManualVideo();badge.append(resume)}if(active(project)){const detail=make('small','manual-progress-detail',Number.isFinite(project.film?.progress?.percent)?'正在同步生成进度':'正在同步生成状态');detail.title='模型返回百分比后将在此显示实际进度';badge.append(detail)}preview.setAttribute('aria-busy',String(active(project)))}else{badge?.remove();preview.removeAttribute('aria-busy')}progressMeter(preview,project)}
 document.addEventListener('creative-state-change',()=>{if(project?.id!==root)refresh();requestAnimationFrame(rootStatus)});
 document.addEventListener('creative-root-image-draft',e=>{const card=document.querySelector('.manual-root-node');if(card&&e.detail?.project===project?.id)syncReferenceStrip({card,project,isRoot:true,busy})});
 document.addEventListener('creative-manual-view-ready',()=>{
  rootStatus();const card=document.querySelector('.manual-root-node'),head=card?.querySelector('.studio-free-node-label');
  prepareManualSelection(card,head);
  // After delivery the preview lives in a result card; keep an accessible editor handle.
  if(card){let handle=card.querySelector('.manual-delivered-head');if(!handle){handle=make('div','manual-node-head manual-delivered-head','生成参数');card.prepend(handle);prepareManualSelection(card,handle)}handle.hidden=!card.querySelector('.studio-free-node')?.hidden;}
  if(card)syncReferenceStrip({card,project,isRoot:true,busy});
  if(card&&!card.dataset.referenceDrop){card.dataset.referenceDrop='true';installReferenceDrop({isRoot:true,card,preview:card,get project(){return project},get busy(){return busy}})}
  if(!head||card.dataset.dragProject===project.id)return;
  card.dataset.dragProject=project.id;const movable={card,project,isRoot:true};moveNode(movable,head);const preview=card.querySelector('.studio-free-node-preview');if(preview)moveNode(movable,preview);
 });
 document.addEventListener('creative-add-manual-node',async e=>{if(adding||!project||!['image','video'].includes(e.detail?.kind))return;adding=true;const pid=project.id;try{const kind=e.detail.kind,item=await api('/projects/'+pid+'/manual-nodes','POST',{message:'新建'+(kind==='image'?'图片':'视频')+'节点',creation_mode:kind,model:'kling-video-v4_0',image_model:'kling-image-v3_0',duration:15,aspect:project.aspect});if(project?.id!==pid)return;draw(item);document.body.classList.add('manual-node-focus');document.dispatchEvent(new CustomEvent('creative-focus-manual-node',{detail:{id:item.project.id}}));refresh()}catch(e){toast(e.message)}finally{adding=false}});
 document.addEventListener('pointerdown',e=>{if(e.target.closest('.reference-node,.canvas-image-job'))document.body.classList.remove('manual-node-focus')});
 setTimeout(refresh,0);
})();
