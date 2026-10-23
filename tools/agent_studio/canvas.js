/* Reference inputs feed the director; the timeline remains the output clock. */
(()=>{
 const center=document.querySelector('.center'),preview=document.querySelector('.previewarea'),timeline=document.querySelector('.timeline');
 const make=(tag,cls,text)=>{const e=document.createElement(tag);e.className=cls||'';if(text)e.textContent=text;return e};
 // Media tools use the same stroke weight as the workspace controls.
 const mediaPaths={trim:'M7 3v18M17 3v18M3 7h18M3 17h18',audio:'M9 18V5l12-2v13M9 5v4l12-2 M9 18a3 3 0 1 1-3-3 3 3 0 0 1 3 3M21 16a3 3 0 1 1-3-3 3 3 0 0 1 3 3',retake:'M4 5h16v14H4Z M8 9h6a3 3 0 1 1-3 3M8 9l3-3M8 9l3 3',speech:'M3 5h18v14H3Z M6 10h5m2 0h5M6 14h12',image:'M3 4h18v16H3Z M3 16l5-5 4 4 3-3 6 6 M15 8h.01',video:'M4 4h16v16H4Z M10 8l6 4-6 4Z',preview:'M8 3H3v5m13-5h5v5M3 16v5h5m13-5v5h-5',compare:'M12 3v18 M8 5H3v14h5m8-14h5v14h-5',edit:'m14 5 5 5M4 20l5-1L21 7l-5-5L4 14Z',region:'M8 3H3v5m13-5h5v5M3 16v5h5m13-5v5h-5 M12 8v8m-4-4h8',crop:'M6 3v15h15M3 6h15v15',light:'M12 7a5 5 0 1 0 0 10 5 5 0 0 0 0-10M12 1v3m0 16v3M1 12h3m16 0h3M4 4l2 2m12 12 2 2M4 20l2-2M18 6l2-2',adjust:'M4 7h16M4 17h16M8 4v6m8 4v6',compose:'M3 3h12v12H3Z M9 19v2h12V9h-2 M9 7v4M7 9h4',product:'m12 3 9 5v8l-9 5-9-5V8Z M3 8l9 5 9-5M12 13v8',play:'m8 4 12 8-12 8Z',pause:'M8 4v16M16 4v16',inline:'M9 8l11 12M9 16 11 4M5 4a4 4 0 1 0 0 8 4 4 0 0 0 0-8M5 12a4 4 0 1 0 0 8 4 4 0 0 0 0-8',editor:'M13 3h8v8M21 3l-12 12M9 3H3v18h18v-6',download:'M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5',review:'M9 12l2 2 4-4M5 3h14v18H5Z',details:'M5 6h.01M12 6h.01M19 6h.01M5 12h.01M12 12h.01M19 12h.01M5 18h.01M12 18h.01M19 18h.01',close:'m6 6 12 12M6 18 18 6'};
 function mediaIcon(name){const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');for(const [key,value] of Object.entries({viewBox:'0 0 24 24',fill:'none',stroke:'currentColor','stroke-width':'1.6','stroke-linecap':'round','stroke-linejoin':'round','aria-hidden':'true'}))svg.setAttribute(key,value);svg.classList.add('canvas-media-icon');const path=document.createElementNS(svg.namespaceURI,'path');path.setAttribute('d',mediaPaths[name]||mediaPaths.details);svg.append(path);return svg}
 function labelMediaAction(button,label,key){button.replaceChildren(mediaIcon(key),make('span','canvas-media-action-label',label));button.setAttribute('aria-label',label);button.title=label}
 const toolbar=make('div','canvas-toolbar'),viewport=make('div','canvas-viewport'),world=make('div','canvas-world');
 viewport.setAttribute('aria-label','参考素材画布');viewport.tabIndex=0;
 const help=make('div','canvas-help','把文字、图片或视频连接给导演，帮助理解风格和场景。视频仅分析采样画面；右侧商品参考图才会直接用于视频生成。');
 const status=make('span','canvas-status','参考素材会自动连接，可随时断开');
 const edges=document.createElementNS('http://www.w3.org/2000/svg','svg');edges.classList.add('canvas-edges');edges.setAttribute('width','1400');edges.setAttribute('height','1100');world.append(edges);
 let filmTaskCard=null;
 const output=make('section','canvas-card canvas-output');const outputHead=make('div','canvas-card-head');outputHead.append(make('strong','','✦ 创作导演 → 成片'));output.append(outputHead,preview);world.append(output);
 const empty=make('div','canvas-empty','从一张商品图、一段喜欢的视频，或者几句想法开始。\n添加后自动连接，不需要先学会搭建流程。');world.append(empty);
 viewport.append(world,make('div','canvas-hint','拖动标题移动素材 · Shift 多选 / 框选 · 拖动空白平移 · Ctrl / ⌘ + 滚轮缩放'));
 center.insertBefore(toolbar,timeline);center.insertBefore(help,timeline);center.insertBefore(viewport,timeline);
 const canvasParams=new URLSearchParams(location.search);let requestedCanvasAsset=(canvasParams.get('canvas_asset')||'').slice(0,80);
 let serverGraphSignature='',graph={nodes:[],edges:[]},pid=null,revision=-1,dirty=false,saving=false,scale=.85,tx=20,ty=20,focus=canvasParams.get('view')==='studio';
 viewport.classList.toggle('canvas-focus',focus);
 const urls=new Map();
 // Specifications describe owned source files, not their 960px preview thumbnails.
 const metadataRequests=new Map();let metadataController=new AbortController();
 function mediaKind(node){const normalize=value=>{const v=String(value||'').toLowerCase();if(v==='image'||v==='img'||v.includes('image')||v.includes('picture'))return'image';if(v==='video'||v==='vid'||v.includes('video')||v.includes('movie'))return'video';if(v==='audio')return'audio';if(v==='text'||v.includes('text'))return'text';return''};const direct=[node?.kind,node?.media_kind,node?.mediaType,node?.type].map(normalize).find(Boolean);if(direct)return direct;const asset=node?.asset&&project?.canvas_assets?.[node.asset];const assetKind=[asset?.kind,asset?.media_kind,asset?.mediaType,asset?.type].map(normalize).find(Boolean);if(assetKind)return assetKind;const hint=[node?.label,node?.title,node?.prompt,node?.text].join(' ').toLowerCase();if(node?.asset&&(hint.includes('图片')||hint.includes('image')||hint.includes('图像')))return'image';return node?.asset?'video':'text'}
 function mediaSpecText(meta){const valid=n=>Number.isInteger(n)&&n>0;const size=valid(meta?.width)&&valid(meta?.height)?`${meta.width} × ${meta.height}`:'';const seconds=Number(meta?.duration),time=Number.isFinite(seconds)&&seconds>0?`${Math.floor(seconds/60)}:${String(Math.floor(seconds%60)).padStart(2,'0')}`:'';return [size,time].filter(Boolean).join(' · ')}
 const sourceAudioTracks=new Map();
 function sourceSpec(aid,label){const ownerPid=pid,cacheKey=ownerPid+'/'+aid;label.textContent='';label.title='正在读取源素材规格';if(!metadataRequests.has(cacheKey)){metadataRequests.set(cacheKey,fetch(`/creative/api/projects/${ownerPid}/canvas/assets/${aid}/metadata`,{headers:{Authorization:'Bearer '+key},signal:metadataController.signal}).then(async response=>{if(!response.ok)throw Error();return response.json()}).catch(()=>null))}metadataRequests.get(cacheKey).then(meta=>{if(pid!==ownerPid||!label.isConnected)return;if(typeof meta?.has_audio==='boolean'){sourceAudioTracks.set(cacheKey,meta.has_audio);queueMediaTools()}const text=mediaSpecText(meta);label.textContent=text||'规格未知';label.title=text?'源素材 · '+text:'源素材规格暂不可读取；可刷新页面重试';label.setAttribute('aria-label',label.title)})}

 // Bind frozen edit inputs to the current generation only after byte-identity checks.
 let generationSignature='',generationEpoch=0,generationChecking=false,generationSources=new Set(),generationVerifiedInputs=new Set();
 // Only a byte-verified frozen primary can replace the synthetic output node.
 function currentFilmNode(){return project?.artifact&&project?.film?.state==='completed'?graph.nodes.find(n=>mediaKind(n)==='video'&&(generationSources.has(n.asset)||(n.asset===project.result_asset&&project.result_artifact===project.artifact))&&world.querySelector(`.reference-node[data-node-id="${CSS.escape(n.id)}"]`)):null}
 function syncOutputProjection(){
  const node=currentFilmNode(),duplicate=!!node;
  if(duplicate&&!output.classList.contains('is-duplicate-output'))document.querySelector('#video')?.pause();
  output.classList.toggle('is-duplicate-output',duplicate);
  if(duplicate&&!focus&&mediaSelection?.output)mediaSelection={project:pid,node:node.id,asset:node.asset};
 }
 function generationInputs(){return project?.film?.state==='completed'?project.film.inputs:project?.input_manifest}
 function generationEdges(nodes=graph.nodes){
  const links=[];
  for(const child of nodes.filter(n=>generationSources.has(n.asset)))for(const input of generationInputs()?.images||[]){
   if(!generationVerifiedInputs.has(input.asset+':'+input.sha256))continue;
   for(const parent of nodes)if(parent.asset===input.asset&&parent.id!==child.id)links.push({source:parent.id,target:child.id,kind:'first-frame'});
  }
  return links;
 }
 async function syncGenerationSources(){
  const candidates=Object.entries(project?.canvas_assets||{}).filter(([,a])=>a.kind==='video'&&a.provenance?.kind==='edit_source'&&a.provenance.source_id==='primary'&&/^[a-f0-9]{64}$/.test(a.provenance.source_sha256||'')&&a.sha256===a.provenance.source_sha256);
  const signature=JSON.stringify([pid,project?.run_id,project?.artifact,project?.film?.state,candidates.map(([id,a])=>[id,a.sha256]),generationInputs()?.images||[]]);
  if(signature===generationSignature)return;generationSignature=signature;const epoch=++generationEpoch,owner=pid;generationSources.clear();generationVerifiedInputs.clear();generationChecking=false;lines();
  if(!candidates.length||project?.generation_mode!=='single_native'||project?.film?.state!=='completed')return;
  generationChecking=true;updateStatus();
  try{const response=await fetch(`/creative/api/projects/${owner}/edit`,{headers:{Authorization:'Bearer '+key},signal:AbortSignal.any([metadataController.signal,AbortSignal.timeout(20000)])});if(!response.ok)return;const data=await response.json();if(epoch!==generationEpoch||owner!==pid)return;
   const sources=data.sources||{},primary=sources.primary;if(!/^[a-f0-9]{64}$/.test(primary?.sha256||''))return;
   const matched=new Set(candidates.filter(([id,a])=>a.sha256===primary.sha256&&sources['canvas_'+id]?.sha256===primary.sha256).map(([id])=>id)),verified=new Set();
   // Upload receipts may hash the upload before image normalization. Check saved input bytes.
   if(matched.size)for(const input of (generationInputs()?.images||[]).slice(0,8)){
    if(!/^[a-f0-9]{32}$/.test(input.asset||'')||!/^[a-f0-9]{64}$/.test(input.sha256||'')||project?.canvas_assets?.[input.asset]?.kind!=='image')continue;
    try{const source=await fetch(`/creative/api/projects/${owner}/canvas/assets/${input.asset}/source`,{headers:{Authorization:'Bearer '+key},signal:AbortSignal.any([metadataController.signal,AbortSignal.timeout(15000)])});if(!source.ok||!/^image\//i.test(source.headers.get('content-type')||''))continue;const hash=await crypto.subtle.digest('SHA-256',await source.arrayBuffer());const sha=Array.from(new Uint8Array(hash),n=>n.toString(16).padStart(2,'0')).join('');if(sha===input.sha256)verified.add(input.asset+':'+sha)}catch{}
    if(epoch!==generationEpoch||owner!==pid)return;
   }
   if(epoch!==generationEpoch||owner!==pid)return;generationSources=matched;generationVerifiedInputs=verified;lines();
  }catch{/* Missing evidence leaves the original independent nodes intact. */}finally{if(epoch===generationEpoch){generationChecking=false;updateStatus()}}
 }
 function generationColumns(proposal){
  const extra=generationEdges(proposal.nodes);if(!extra.length)return proposal;
  const next=structuredClone(proposal),byId=new Map(next.nodes.map(n=>[n.id,n])),incoming=new Map(next.nodes.map(n=>[n.id,[]])),depth=new Map();
  const edges=[...extra];for(const child of next.nodes)for(const aid of project?.canvas_lineage?.[child.asset]?.sources||[])for(const parent of next.nodes)if(parent.asset===aid)edges.push({source:parent.id,target:child.id});
  for(const e of edges)incoming.get(e.target)?.push(e.source);
  const visit=(id,stack=new Set())=>{if(depth.has(id))return depth.get(id);if(stack.has(id))throw Error('cycle');const branch=new Set([...stack,id]);const level=Math.max(Math.round((byId.get(id).x-40)/310),0,...incoming.get(id).map(p=>visit(p,branch)+1));depth.set(id,level);return level};
  try{for(const n of next.nodes){n.x=40+310*visit(n.id);if(n.x>9000)return proposal}}catch{return proposal}return next;
 }
 let canvasGesture=null,selectionMode=false,suppressSelectionClick=null;let handMode=false,spacePan=false,panGesture=null,panClickUntil=0;let historyPast=[],historyFuture=[],historyCurrent=null,historyBaseline='',historyMergeKey=null;const selectedNodes=new Set();
 const sectionStates=new Map();let openAssetId=null;let foldedGroups=new Set();
 const roles={product:'商品',person:'人物',scene:'场景',style:'风格',story:'脚本',reference:'其他参考'};let tracing=null;
 const legend=make('div','canvas-legend');legend.innerHTML='<span class=derived>素材 → 派生</span><span class=context>导演参考</span><span class=first-frame>视频模型输入</span>';viewport.append(legend);
 const button=(text,fn)=>{const b=make('button','',text);b.type='button';b.onclick=fn;toolbar.append(b);return b};
 const noteButton=button('＋ 文字',()=>addText());const imageButton=button('＋ 图片',()=>choose('image'));const videoButton=button('＋ 视频',()=>choose('video'));
 const zoomOut=button('−',()=>zoom(scale-.1)),zoomIn=button('＋',()=>zoom(scale+.1)),fitButton=button('适应画布',()=>fit());zoomOut.setAttribute('aria-label','缩小画布');zoomIn.setAttribute('aria-label','放大画布');
 // Campaigns reserve graph slots for chapters, continuity frames and the final
 // cut. Older exploratory nodes should be removable without deleting their
 // source assets, so the user can recover them later from the material shelf.
 const campaignInputAssets=()=>new Set([
  // Only the frozen video_input_selection is authoritative.  Historical
  // campaign references can include prior exploratory outputs and must not
  // keep those nodes alive during a new chapter run.
  ...(project?.video_inputs?.references||[]).map(r=>r.asset),
  ...(project?.input_manifest?.images||[]).map(r=>r.asset),
 ].filter(Boolean));
 const cleanupButton=button('清理旧节点',()=>{
  const cleanupLocked=!project||busy||saving||!!canvasGesture||['running','rendering'].includes(project.state)||project.image_task?.state==='running';
  if(cleanupLocked||dirty){toast('请先保存或放弃当前画布草稿');return}
  const keep=campaignInputAssets();
  // A pending multi-shot campaign reserves space for chapter, bridge-frame,
  // and final-cut nodes. Existing video nodes in this state are exploratory
  // outputs from before the campaign was frozen; keep the bound image refs,
  // but remove those stale video nodes in one reversible local edit.
  const pendingCampaign=!!project?.campaign||(
   project?.creation_mode==='agent'&&Number(project?.duration)===60&&
   !project?.artifact&&!project?.result_asset&&
   (Array.isArray(project?.shots)&&project.shots.length===12||
    project?.auto_approval?.state==='needs_review'||
    !!project?.image_task?.video_approval)
  );
  const stale=graph.nodes.filter(n=>pendingCampaign?n.kind==='video':!keep.has(n.asset));
  if(!stale.length){toast('当前没有可清理的旧节点');return}
  if(!window.confirm(`将移出 ${stale.length} 个旧节点，源素材仍保留在项目素材中。继续吗？`))return;
  selectedNodes.clear();stale.forEach(n=>selectedNodes.add(n.id));editSelection('remove');
 });
 cleanupButton.setAttribute('aria-label','清理旧节点');cleanupButton.title='移出不属于当前参考输入的旧节点；源素材仍保留，可用撤销恢复';cleanupButton.classList.add('canvas-cleanup-old');
 const arrangeButton=button('按来源排版',()=>arrange());
 const viewButton=button(focus?'查看参考画布':'返回成片预览',()=>{focus=!focus;viewport.classList.toggle('canvas-focus',focus);viewButton.textContent=focus?'查看参考画布':'返回成片预览';if(focus)clearMediaSelection();updateSelection()});
 const saveButton=button('保存参考',()=>save());const discardButton=button('放弃修改',()=>{if(canvasGesture)return;resetHistory();selectedNodes.clear();dirty=false;revision=-1;sync()});toolbar.append(status);
 const composeButton=button('组合参考生成',()=>composeImage());
 document.addEventListener('creative-compose-image',e=>composeImage(null,false,e.detail));
 async function composeImage(asset=null,region=false,initial={}){
  if(locked()||hasDrafts()){toast('请先保存或放弃草稿，再选择生成输入');return}
  const composerProject=project.id;
  try{const {openImageComposer,generateManualImage,generateDirectorReference}=await import('/creative/image-composer.js?v=20261019-director');await (initial?.director_reference&&initial?.direct?generateDirectorReference:initial?.direct?generateManualImage:openImageComposer)({project:()=>project,locked,hasDrafts,api,toast,busy:setBusy,initial,imageModel:()=>initial?.model||$('imageModelSelect')?.value,
   accepted:p=>{if(project?.id===p.id){if(initial?.director_reference&&initial.request_id&&p.image_task?.id===initial.request_id){for(const k of initial.answerKeys||[])answers.delete(k);if($('message').value===initial.message)$('message').value=''}project=p;clearMedia();draw();schedule()}},
   preview:async aid=>{const r=await fetch(`/creative/api/projects/${project.id}/canvas/assets/${aid}/preview`,{headers:{Authorization:'Bearer '+key}});if(!r.ok)throw Error('参考图片暂不可读取');return URL.createObjectURL(await r.blob())}
  },asset,region);if(!initial?.direct&&!region&&!asset)document.getElementById('imageComposer')?.addEventListener('close',()=>document.dispatchEvent(new CustomEvent('creative-root-image-draft',{detail:{project:composerProject}})),{once:true})}catch(e){toast(e.message||'图像生成入口暂不可用')}
 }
 async function adjustImage(mode,assetOverride=null){
  const asset=assetOverride||selectedMedia()?.node.asset;if(!asset)return;
  try{const {openImageAdjustment}=await import('/creative/image-adjustments.js');await openImageAdjustment({project:()=>project,anchor:()=>selectedMedia()?.card?.getBoundingClientRect(),locked,hasDrafts,api,toast,busy:setBusy,accepted:p=>{if(project?.id===p.id){project=p;clearMedia();draw();schedule()}},preview:async aid=>{const r=await fetch(`/creative/api/projects/${project.id}/canvas/assets/${aid}/preview`,{headers:{Authorization:'Bearer '+key}});if(!r.ok)throw Error();return URL.createObjectURL(await r.blob())}},asset,mode)}catch(e){toast(e.message||'调整面板暂不可用')}
 }
 document.addEventListener('creative-open-image-adjustment',event=>{const {asset,mode}=event.detail||{};if(asset&&['angle','light'].includes(mode))adjustImage(mode,asset)});
 const videoInputsButton=button('视频参考输入',()=>configureVideo());videoInputsButton.id='canvasVideoInputs';
 const toolMenu=(id,label,children)=>{
  const menu=make('details','canvas-tool-menu');menu.id=id;
  const toggle=make('summary','',label),panel=make('div','canvas-tool-menu-panel');panel.id=id+'Panel';toggle.setAttribute('aria-controls',panel.id);toggle.setAttribute('aria-expanded','false');
  panel.append(...children);menu.append(toggle,panel);toolbar.append(menu);
  menu.addEventListener('toggle',()=>{toggle.setAttribute('aria-expanded',String(menu.open));if(menu.open)for(const other of document.querySelectorAll('.canvas-tool-menu'))if(other!==menu)other.open=false});
  panel.addEventListener('click',event=>{const button=event.target.closest('button');if(button&&!button.disabled&&!button.dataset.keepMenu){menu.open=false;if(!document.querySelector('dialog[open]'))toggle.focus()}});
  return {menu,panel,toggle};
 };
 const addMenu=toolMenu('canvasAddMenu','＋ 添加素材',[noteButton,imageButton,videoButton,composeButton]);
 const zoomRow=make('div','canvas-zoom-row');zoomRow.append(zoomOut,zoomIn);zoomOut.dataset.keepMenu=zoomIn.dataset.keepMenu='true';
 const viewMenu=toolMenu('canvasViewMenu','85%',[zoomRow,fitButton,arrangeButton,viewButton]);viewMenu.panel.classList.add('canvas-view-actions');
 toolbar.prepend(addMenu.menu);toolbar.append(videoInputsButton,viewMenu.menu,saveButton,discardButton);
 saveButton.classList.add('canvas-save-draft');discardButton.classList.add('canvas-discard-draft');saveButton.hidden=discardButton.hidden=true;
 document.addEventListener('pointerdown',event=>{for(const menu of document.querySelectorAll('.canvas-tool-menu'))if(menu.open&&!menu.contains(event.target))menu.open=false});
 document.addEventListener('keydown',event=>{if(event.key!=='Escape'||document.querySelector('dialog[open]'))return;for(const menu of document.querySelectorAll('.canvas-tool-menu'))if(menu.open){menu.open=false;menu.querySelector('summary').focus();event.preventDefault()}});

 // The insertion point belongs to one menu/file picker, never the next unrelated action.
 const insertMenu=make('div','canvas-insert-menu');insertMenu.id='canvasInsertMenu';insertMenu.setAttribute('popover','manual');insertMenu.setAttribute('role','menu');insertMenu.setAttribute('aria-label','在此处添加素材');viewport.append(insertMenu);
 insertMenu.append(make('p','canvas-insert-heading','添加素材'));let insertion=null;
 const insertionPoint=(clientX,clientY)=>{const r=viewport.getBoundingClientRect();return{x:Math.round(Math.max(-9000,Math.min(8500,(clientX-r.left-tx)/scale))),y:Math.round(Math.max(-9000,Math.min(8500,(clientY-r.top-ty)/scale)))}};
 function closeInsert(){if(insertMenu.matches(':popover-open'))insertMenu.hidePopover()}
 for(const [label,glyph,run]of [['文字','edit',point=>addText(point)],['上传图片','image',point=>choose('image',point)],['上传视频','video',point=>choose('video',point)]]){const b=make('button');b.type='button';b.setAttribute('role','menuitem');b.append(mediaIcon(glyph),make('span','',label));b.onclick=()=>{const point=insertion&&{...insertion};closeInsert();if(point&&point.pid===pid&&!locked())run({x:point.x,y:point.y})};insertMenu.append(b)}
 const blankCanvas=target=>target===viewport||target===world||target===edges;
 function openInsert(x,y){if(locked()||focus||canvasGesture||handMode||spacePan||panGesture)return;insertion={pid,...insertionPoint(x,y)};clearMediaSelection();for(const menu of document.querySelectorAll('.canvas-tool-menu'))menu.open=false;insertMenu.showPopover();const r=insertMenu.getBoundingClientRect();insertMenu.style.left=Math.max(8,Math.min(innerWidth-r.width-8,x))+'px';insertMenu.style.top=Math.max(8,Math.min(innerHeight-r.height-8,y))+'px';insertMenu.querySelector('button')?.focus({preventScroll:true})}
 viewport.addEventListener('dblclick',event=>{if(event.button!==0||!blankCanvas(event.target))return;event.preventDefault();openInsert(event.clientX,event.clientY)});
 viewport.addEventListener('contextmenu',event=>{if(!blankCanvas(event.target)||locked()||focus)return;event.preventDefault();openInsert(event.clientX,event.clientY)});
 viewport.addEventListener('keydown',event=>{if(event.target!==viewport||!(event.key==='ContextMenu'||event.shiftKey&&event.key==='F10'))return;event.preventDefault();const r=viewport.getBoundingClientRect(),a=canvasArea();openInsert(r.left+a.x+a.w/2,r.top+a.y+a.h/2)});
 insertMenu.addEventListener('keydown',event=>{const buttons=[...insertMenu.querySelectorAll('button')],index=buttons.indexOf(document.activeElement);if(event.key==='Escape'){event.preventDefault();closeInsert();viewport.focus({preventScroll:true});return}let next;if(event.key==='ArrowDown')next=(index+1)%buttons.length;if(event.key==='ArrowUp')next=(index+buttons.length-1)%buttons.length;if(event.key==='Home')next=0;if(event.key==='End')next=buttons.length-1;if(next!==undefined){event.preventDefault();buttons[next].focus()}});
 insertMenu.addEventListener('toggle',()=>{if(!insertMenu.matches(':popover-open'))insertion=null});
 window.addEventListener('resize',closeInsert);
 // Right-button release light-dismisses an auto popover opened by contextmenu.
 document.addEventListener('pointerdown',event=>{if(!insertMenu.contains(event.target))closeInsert()},true);
 document.addEventListener('focusin',event=>{if(!insertMenu.contains(event.target))closeInsert()});
 document.addEventListener('keydown',event=>{if(event.key==='Escape'&&insertMenu.matches(':popover-open')){event.preventDefault();closeInsert();viewport.focus({preventScroll:true})}});
 // Multi-selection belongs to the view; only explicit edits change the graph draft.
 const selectButton=button('框选',()=>{handMode=false;selectionMode=!selectionMode;openCanvas();updateSelection();});selectButton.id='canvasSelectTool';selectButton.title='框选素材；Shift 点击增减选择，Shift 拖动空白处临时框选';toolbar.insertBefore(selectButton,viewMenu.menu);
 const handButton=button('平移画布',()=>{handMode=!handMode;selectionMode=false;openCanvas();updateSelection()});handButton.id='canvasHandTool';handButton.title='手形平移 (H) · 按住空格临时平移';toolbar.insertBefore(handButton,viewMenu.menu);
 function updatePanMode(){viewport.classList.toggle('canvas-hand-mode',handMode||spacePan);viewport.classList.toggle('canvas-panning',!!panGesture);handButton.setAttribute('aria-pressed',String(handMode||spacePan));}

 const groupTools=make('div','canvas-selection-toolbar');groupTools.id='canvasSelectionToolbar';groupTools.hidden=true;groupTools.setAttribute('role','toolbar');groupTools.setAttribute('aria-label','多素材整理');
 const groupCount=make('span','canvas-selection-count');groupCount.setAttribute('role','status');groupTools.append(groupCount);
 const groupAction=(label,fn)=>{const b=make('button','',label);b.type='button';b.onclick=fn;groupTools.append(b);return b};
 const alignTop=groupAction('顶部对齐',()=>editSelection('top')),alignLeft=groupAction('左侧对齐',()=>editSelection('left')),removeSelected=groupAction('移出画布',()=>editSelection('remove')),undoSelection=button('↶',()=>travelHistory(-1)),redoSelection=button('↷',()=>travelHistory(1)),clearSelected=groupAction('取消选择',()=>{selectedNodes.clear();selectionMode=false;updateSelection();});
 const createGroup=groupAction('创建分组',()=>nameGroup()),renameGroup=groupAction('重命名分组',()=>nameGroup(exactGroup())),foldGroup=groupAction('收起分组',()=>{const g=exactGroup();if(g)toggleGroup(g)}),ungroup=groupAction('解散分组',()=>dissolveGroup());
 const historyControls=make('div','canvas-history');historyControls.setAttribute('role','group');historyControls.setAttribute('aria-label','画布历史');historyControls.append(undoSelection,redoSelection);toolbar.insertBefore(historyControls,selectButton);undoSelection.id='canvasUndo';redoSelection.id='canvasRedo';undoSelection.setAttribute('aria-label','撤销画布修改');redoSelection.setAttribute('aria-label','重做画布修改');
 removeSelected.title='移除所选画布节点及其导演连接，保留源素材';viewport.append(groupTools);
 const marquee=make('div','canvas-selection-box');marquee.hidden=true;marquee.setAttribute('aria-hidden','true');viewport.append(marquee);
 const nodeCards=()=>[...world.querySelectorAll('.reference-node')];
 function updateSelection(){
  for(const id of selectedNodes)if(!graph.nodes.some(n=>n.id===id))selectedNodes.delete(id);
  for(const card of nodeCards())card.classList.toggle('canvas-multi-selected',selectedNodes.has(card.dataset.nodeId));
  for(const frame of groupLayer.children){const group=(graph.groups||[]).find(g=>g.id===frame.dataset.groupId);frame.classList.toggle('is-selected',!!group&&group.members.every(id=>selectedNodes.has(id)))}
  updatePanMode();selectButton.setAttribute('aria-pressed',String(selectionMode&&!spacePan));viewport.classList.toggle('canvas-select-mode',selectionMode);
  groupTools.hidden=focus||!selectedNodes.size;groupCount.textContent=(exactGroup()?.name||'已选')+' · '+selectedNodes.size+' 个素材';
  const existing=exactGroup(),supported=project?.canvas_capabilities?.groups;createGroup.hidden=!supported||!!existing;renameGroup.hidden=ungroup.hidden=foldGroup.hidden=!supported||!existing;foldGroup.textContent=existing&&foldedGroups.has(existing.id)?'展开分组':'收起分组';foldGroup.disabled=!!canvasGesture;createGroup.disabled=locked()||selectedNodes.size<2||[...selectedNodes].some(id=>groupFor(id));createGroup.title=createGroup.disabled?'至少选择两个未分组素材；已有分组请先解散':'保存后可重新选择整组';renameGroup.disabled=ungroup.disabled=locked();
  if(historyCurrent&&historyCurrent.signature===graphSignature(graph))historyCurrent.selection=[...selectedNodes];updateHistoryControls();
  alignTop.disabled=alignLeft.disabled=locked()||selectedNodes.size<2;removeSelected.disabled=locked()||!selectedNodes.size;clearSelected.disabled=!!canvasGesture;
  if(selectedNodes.size)clearMediaSelection();
 }
 function selectNode(id,additive=true){if(!additive)selectedNodes.clear();else if(!selectedNodes.size&&graph.nodes.some(n=>n.id===mediaSelection?.node))selectedNodes.add(mediaSelection.node);if(selectedNodes.has(id))selectedNodes.delete(id);else selectedNodes.add(id);clearFocusAnchor();updateSelection()}
 // Saved groups organize references without changing director inputs or model requests.
 const groupLayer=make('div','canvas-group-layer');world.prepend(groupLayer);
 const groupDialog=make('dialog','canvas-group-dialog');groupDialog.id='canvasGroupDialog';groupDialog.setAttribute('aria-label','素材分组名称');
 const groupForm=make('form'),groupHeading=make('h3'),groupLabel=make('label','','分组名称'),groupInput=make('input'),groupActions=make('div','canvas-group-actions'),groupCancel=make('button','','取消'),groupSubmit=make('button','','确定');
 groupInput.id='canvasGroupName';groupInput.maxLength=60;groupInput.required=true;groupLabel.htmlFor=groupInput.id;groupCancel.type='button';groupCancel.onclick=()=>groupDialog.close();groupSubmit.type='submit';groupActions.append(groupCancel,groupSubmit);groupForm.append(groupHeading,groupLabel,groupInput,groupActions);groupDialog.append(groupForm);document.body.append(groupDialog);let groupEdit=null;
 const groupFor=id=>(graph.groups||[]).find(g=>g.members.includes(id));
 function exactGroup(){return (graph.groups||[]).find(g=>g.members.length===selectedNodes.size&&g.members.every(id=>selectedNodes.has(id)))}
 function pruneGroups(){if(!graph.groups)return;const ids=new Set(graph.nodes.map(n=>n.id));graph.groups=graph.groups.map(g=>({...g,members:g.members.filter(id=>ids.has(id))})).filter(g=>g.members.length>=2);if(!graph.groups.length)delete graph.groups}
 function selectGroup(group){if(canvasGesture)return;selectedNodes.clear();group.members.forEach(id=>selectedNodes.add(id));selectionMode=false;clearFocusAnchor();updateSelection()}
 function nameGroup(group=null){
  if(locked()||!project?.canvas_capabilities?.groups)return;const members=[...selectedNodes];if(!group&&(members.length<2||members.some(id=>groupFor(id))))return;
  groupEdit={pid,id:group?.id,members};groupHeading.textContent=group?'重命名分组':'创建素材分组';groupInput.value=group?.name||'素材分组 '+((graph.groups||[]).length+1);groupInput.setCustomValidity('');groupDialog.showModal();groupInput.focus();groupInput.select();
 }
 groupInput.oninput=()=>groupInput.setCustomValidity('');
 groupForm.onsubmit=e=>{e.preventDefault();if(locked()||groupEdit?.pid!==pid)return;const name=groupInput.value.trim();if(!name){groupInput.setCustomValidity('请输入分组名称');groupInput.reportValidity();return}
  if(groupEdit.id){const group=(graph.groups||[]).find(g=>g.id===groupEdit.id);if(!group){groupDialog.close();return}group.name=name}
  else{if(groupEdit.members.some(id=>!graph.nodes.some(n=>n.id===id)||groupFor(id))){groupDialog.close();toast('所选素材已变化，请重新选择');return}(graph.groups??=[]).push({id:'g'+crypto.randomUUID().replaceAll('-',''),name,members:groupEdit.members})}
  groupDialog.close();change();updateGroupFrames();
 };
 function dissolveGroup(){if(locked())return;const group=exactGroup();if(!group)return;graph.groups=graph.groups.filter(g=>g.id!==group.id);change();toast('分组已解散，素材和连接保持不变')}
 // Folding is a per-tab view preference, never a director input or graph edit.
 function rememberFolds(){try{sessionStorage.setItem('creative-canvas-folds:'+pid,JSON.stringify([...foldedGroups].filter(id=>(graph.groups||[]).some(g=>g.id===id))))}catch{}}
 function loadFolds(){try{const ids=JSON.parse(sessionStorage.getItem('creative-canvas-folds:'+pid)||'[]');foldedGroups=new Set(Array.isArray(ids)?ids.filter(id=>typeof id==='string').slice(0,8):[])}catch{foldedGroups=new Set()}}
 function toggleGroup(group,fold=!foldedGroups.has(group.id)){
  if(canvasGesture)return;if(fold)foldedGroups.add(group.id);else foldedGroups.delete(group.id);rememberFolds();clearFocusAnchor();clearMediaSelection();
  if(fold)for(const card of nodeCards().filter(c=>group.members.includes(c.dataset.nodeId))){for(const panel of card.querySelectorAll('[popover]:popover-open'))panel.hidePopover();for(const video of card.querySelectorAll('video'))video.pause()}
  updateGroupFrames();alignOutput();lines();updateSelection();
 }
 function revealNode(card){const group=groupFor(card.dataset.nodeId);if(group&&foldedGroups.has(group.id))toggleGroup(group,false)}
 function visibleCards(){return [...world.querySelectorAll('.canvas-card,.canvas-entry,.canvas-group-frame.is-folded')].filter(c=>!c.hidden&&!c.classList.contains('in-folded-group')&&getComputedStyle(c).display!=='none')}
 function updateGroupFrames(){
  const groups=graph.groups||[],ids=new Set(groups.map(g=>g.id));for(const frame of [...groupLayer.children])if(!ids.has(frame.dataset.groupId))frame.remove();
  for(const card of nodeCards()){const group=groupFor(card.dataset.nodeId),folded=!!group&&foldedGroups.has(group.id);card.classList.toggle('in-folded-group',folded);card.inert=folded;card.setAttribute('aria-hidden',String(folded))}
  for(const group of groups){const cards=nodeCards().filter(c=>group.members.includes(c.dataset.nodeId));if(!cards.length)continue;let frame=[...groupLayer.children].find(c=>c.dataset.groupId===group.id);
   if(!frame){frame=make('section','canvas-group-frame');frame.dataset.groupId=group.id;const head=make('div','canvas-group-head');head.tabIndex=0;head.setAttribute('role','button');head.title='点击选择整组 · 拖动移动整组';
    const toggle=make('button','canvas-group-fold'),summary=make('div','canvas-group-summary');toggle.type='button';frame.append(head,toggle,summary);groupLayer.append(frame);
    const current=()=>(graph.groups||[]).find(g=>g.id===frame.dataset.groupId);head.onclick=()=>{const g=current();if(g)selectGroup(g)};head.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();const g=current();if(g)selectGroup(g)}};
    head.onpointerdown=e=>{const g=current();if(!g||e.button!==0||locked())return;selectGroup(g);startNodeDrag(e,graph.nodes.find(n=>n.id===g.members[0]),head)};
    toggle.onclick=()=>{const g=current();if(g)toggleGroup(g)};summary.onclick=()=>{const g=current();if(g)selectGroup(g)};
   }
   const folded=foldedGroups.has(group.id),left=Math.min(...cards.map(c=>c.offsetLeft))-18,top=Math.min(...cards.map(c=>c.offsetTop))-46,right=Math.max(...cards.map(c=>c.offsetLeft+c.offsetWidth))+18,bottom=Math.max(...cards.map(c=>c.offsetTop+c.offsetHeight))+18;
   Object.assign(frame.style,{left:left+'px',top:top+'px',width:(folded?284:right-left)+'px',height:(folded?154:bottom-top)+'px'});const head=frame.firstElementChild;head.textContent=group.name+' · '+group.members.length;head.setAttribute('aria-label','选择分组 '+group.name);frame.classList.toggle('is-selected',group.members.every(id=>selectedNodes.has(id)));frame.classList.toggle('is-folded',folded);
   const toggle=frame.querySelector('.canvas-group-fold');toggle.textContent=folded?'展开':'收起';toggle.setAttribute('aria-label',(folded?'展开':'收起')+'分组 '+group.name);toggle.setAttribute('aria-expanded',String(!folded));toggle.disabled=!!canvasGesture;
   const summary=frame.querySelector('.canvas-group-summary');summary.hidden=!folded;
   if(folded){const signature=JSON.stringify(cards.map(c=>[c.dataset.nodeId,graph.nodes.find(n=>n.id===c.dataset.nodeId)?.label,c.querySelector('img')?.getAttribute('src')]));if(summary.dataset.signature!==signature){summary.dataset.signature=signature;summary.replaceChildren();for(const card of cards.slice(0,3)){const n=graph.nodes.find(n=>n.id===card.dataset.nodeId),tile=make('div','canvas-group-tile'),src=card.querySelector('img')?.getAttribute('src');if(src){const img=make('img');img.src=src;img.alt='';tile.append(img)}else tile.append(make('span','',n.kind==='text'?'文字':'视频'));tile.append(make('small','',n.label||'未命名素材'));summary.append(tile)}summary.append(make('p','',group.members.length+' 个素材 · 展开查看和编辑'))}}
  }
 }
 // Bounded local history never replays asset uploads or model requests.
 function graphSignature(value){return JSON.stringify(value,(_,v)=>v&&typeof v==='object'&&!Array.isArray(v)?Object.fromEntries(Object.keys(v).sort().map(k=>[k,v[k]])):v)}
 function historySnapshot(){return {graph:structuredClone(graph),signature:graphSignature(graph),selection:[...selectedNodes]}}
 function resetHistory(){historyPast=[];historyFuture=[];historyMergeKey=null;historyCurrent=historySnapshot();historyBaseline=historyCurrent.signature}
 function rememberChange(mergeKey=null){
  const next=historySnapshot();if(!historyCurrent){resetHistory();return}
  if(next.signature!==historyCurrent.signature){if(!mergeKey||mergeKey!==historyMergeKey){historyPast.push(historyCurrent);if(historyPast.length>60)historyPast.shift()}historyFuture=[];historyCurrent=next;historyMergeKey=mergeKey}
  dirty=next.signature!==historyBaseline;
 }
 function updateHistoryControls(){undoSelection.disabled=locked()||!historyPast.length;redoSelection.disabled=locked()||!historyFuture.length;undoSelection.title='撤销画布修改（Ctrl / ⌘ Z） · '+historyPast.length+' 步';redoSelection.title='重做画布修改（Ctrl / ⌘ Shift Z） · '+historyFuture.length+' 步'}
 function travelHistory(direction){
  if(locked())return;const from=direction<0?historyPast:historyFuture,to=direction<0?historyFuture:historyPast;if(!from.length)return;to.push(historySnapshot());historyCurrent=from.pop();historyMergeKey=null;graph=structuredClone(historyCurrent.graph);dirty=historyCurrent.signature!==historyBaseline;selectedNodes.clear();historyCurrent.selection.forEach(id=>selectedNodes.add(id));clearMediaSelection();paint();updateStatus();
 }
 document.addEventListener('keydown',e=>{if(e.defaultPrevented||e.isComposing||!(e.ctrlKey||e.metaKey)||e.altKey||!document.body.classList.contains('canvas-expanded')||e.target.closest('input,textarea,select,[contenteditable],iframe')||document.querySelector('dialog[open],[popover]:popover-open'))return;const key=e.key.toLowerCase();if(key==='z'||key==='y'){e.preventDefault();travelHistory(key==='y'||e.shiftKey?1:-1)}});
 function editSelection(action){
  // Removing stale nodes is a reversible local graph edit and remains allowed
  // while the Director is in planning state. Paid execution and other edits
  // keep the normal lock so a running job cannot be mutated underneath it.
  if((action!=='remove'&&locked())||!selectedNodes.size)return;const nodes=graph.nodes.filter(n=>selectedNodes.has(n.id));
  if(action==='remove'){graph.nodes=graph.nodes.filter(n=>!selectedNodes.has(n.id));graph.edges=graph.edges.filter(e=>!selectedNodes.has(e.source));selectedNodes.clear();change();paint();toast('已移出画布，源素材仍保留；保存后生效');return}
  const axis=action==='top'?'y':'x',positions=new Map(nodeCards().map(c=>[c.dataset.nodeId,{x:c.offsetLeft,y:c.offsetTop}])),target=Math.min(...nodes.map(n=>positions.get(n.id)[axis]));
  if(nodes.every(n=>n[axis]===target))return;
  nodes.forEach(n=>{const rendered=positions.get(n.id);n.x=rendered.x;n.y=rendered.y;n[axis]=target;const card=world.querySelector('[data-node-id="'+CSS.escape(n.id)+'"]');card.style.left=n.x+'px';card.style.top=n.y+'px'});change();
 }
 // Deletion edits the saved canvas graph only; source files and generation tasks remain intact.
 document.addEventListener('keydown',e=>{
  if(!['Delete','Backspace'].includes(e.key)||e.defaultPrevented||e.repeat||e.isComposing||e.ctrlKey||e.metaKey||e.altKey||locked()||!document.body.classList.contains('canvas-expanded')||e.target.closest('input,textarea,select,[contenteditable],iframe,video,audio,.director,.manual-generation-node,.manual-root-node,.manual-reference-edges')||document.querySelector('dialog[open],[popover]:popover-open'))return;
  if(!selectedNodes.size&&mediaSelection?.node&&graph.nodes.some(n=>n.id===mediaSelection.node))selectedNodes.add(mediaSelection.node);
  if(!selectedNodes.size)return;e.preventDefault();editSelection('remove');clearMediaSelection();viewport.focus({preventScroll:true});
 });
 function startNodeDrag(e,node,head){
  if(e.button!==0||locked()||e.target.closest('button,input,textarea,select,label')||e.shiftKey||(selectionMode&&!selectedNodes.has(node.id)))return;
  e.preventDefault();cameraTouched=true;clearFocusAnchor();if(!selectedNodes.has(node.id)){selectedNodes.clear();const group=groupFor(node.id);if(group)group.members.forEach(id=>selectedNodes.add(id));updateSelection()}
  const ids=selectedNodes.has(node.id)?new Set(selectedNodes):new Set([node.id]),items=nodeCards().filter(c=>ids.has(c.dataset.nodeId)).map(c=>({card:c,node:graph.nodes.find(n=>n.id===c.dataset.nodeId),x:c.offsetLeft,y:c.offsetTop})),sx=e.clientX,sy=e.clientY,initialScale=scale;let dx=0,dy=0,moved=false;
  const finish=cancel=>{if(!canvasGesture)return;canvasGesture=null;head.onpointermove=head.onpointerup=head.onpointercancel=head.onlostpointercapture=null;if(head.hasPointerCapture(e.pointerId))head.releasePointerCapture(e.pointerId);
   if(!cancel&&moved){if(selectedNodes.size)suppressSelectionClick={id:node.id,until:performance.now()+500};for(const i of items){i.node.x=i.x+dx;i.node.y=i.y+dy}change();}else for(const i of items){i.card.style.left=i.x+'px';i.card.style.top=i.y+'px'}updateStatus();lines();};
  canvasGesture={cancel:()=>finish(true)};updateStatus();
  head.onpointermove=v=>{if(Math.hypot(v.clientX-sx,v.clientY-sy)<3&&!moved)return;if(!moved)head.setPointerCapture(e.pointerId);moved=true;dx=Math.max(-9000-Math.min(...items.map(i=>i.x)),Math.min(9000-Math.max(...items.map(i=>i.x)),(v.clientX-sx)/initialScale));dy=Math.max(-9000-Math.min(...items.map(i=>i.y)),Math.min(9000-Math.max(...items.map(i=>i.y)),(v.clientY-sy)/initialScale));for(const i of items){i.card.style.left=i.x+dx+'px';i.card.style.top=i.y+dy+'px'}lines()};
  head.onpointerup=()=>finish(false);head.onpointercancel=head.onlostpointercapture=()=>finish(true);
 }
 function startMarquee(e){
  if(e.button!==0)return;const bounds=viewport.getBoundingClientRect(),sx=e.clientX,sy=e.clientY,previous=new Set(selectedNodes),base=e.shiftKey?previous:new Set();clearMediaSelection();clearFocusAnchor();
  const finish=cancel=>{canvasGesture=null;marquee.hidden=true;viewport.onpointermove=viewport.onpointerup=viewport.onpointercancel=viewport.onlostpointercapture=null;if(viewport.hasPointerCapture(e.pointerId))viewport.releasePointerCapture(e.pointerId);if(cancel){selectedNodes.clear();previous.forEach(id=>selectedNodes.add(id))}updateStatus()};
  canvasGesture={cancel:()=>finish(true)};e.preventDefault();viewport.setPointerCapture(e.pointerId);updateStatus();
  viewport.onpointermove=v=>{const x=Math.max(bounds.left,Math.min(bounds.right,v.clientX)),y=Math.max(bounds.top,Math.min(bounds.bottom,v.clientY)),left=Math.min(sx,x),top=Math.min(sy,y),right=Math.max(sx,x),bottom=Math.max(sy,y);marquee.hidden=false;Object.assign(marquee.style,{left:left-bounds.left+'px',top:top-bounds.top+'px',width:right-left+'px',height:bottom-top+'px'});selectedNodes.clear();base.forEach(id=>selectedNodes.add(id));for(const c of [...nodeCards().filter(c=>!c.classList.contains('in-folded-group')),...groupLayer.querySelectorAll('.is-folded')]){const r=c.getBoundingClientRect();if(r.left<right&&r.right>left&&r.top<bottom&&r.bottom>top){if(c.dataset.groupId)(graph.groups||[]).find(g=>g.id===c.dataset.groupId)?.members.forEach(id=>selectedNodes.add(id));else selectedNodes.add(c.dataset.nodeId)}}updateSelection()};
  viewport.onpointerup=()=>finish(false);viewport.onpointercancel=viewport.onlostpointercapture=()=>finish(true);
 }
 world.addEventListener('click',e=>{const card=e.target.closest('.reference-node');if(!card||e.target.closest('button,a,input,textarea,select,summary,[popover]'))return;if(suppressSelectionClick?.id===card.dataset.nodeId&&performance.now()<suppressSelectionClick.until){suppressSelectionClick=null;e.preventDefault();e.stopImmediatePropagation();return}if(e.shiftKey||selectionMode){e.preventDefault();e.stopImmediatePropagation();selectNode(card.dataset.nodeId)}else if(!selectedNodes.has(card.dataset.nodeId)){selectedNodes.clear();updateSelection()}},true);
 document.addEventListener('keydown',e=>{if(e.key!=='Escape'||document.querySelector('dialog[open],[popover]:popover-open'))return;if(canvasGesture){e.preventDefault();e.stopImmediatePropagation();canvasGesture.cancel()}else if(selectedNodes.size||selectionMode){selectedNodes.clear();selectionMode=false;updateSelection()}},true);

 // Navigation reads rendered positions, including temporary collision spacing. It never edits the graph.
 const navToggle=make('button','canvas-navigator-launch','⌕ 素材导航');navToggle.type='button';navToggle.id='canvasNavigatorToggle';navToggle.setAttribute('aria-label','查找素材与缩略导航');navToggle.title='查找素材与缩略导航（/）';navToggle.setAttribute('aria-expanded','false');
 const navigator=make('section','canvas-navigator');navigator.id='canvasNavigator';navigator.setAttribute('popover','auto');navigator.setAttribute('aria-label','画布素材导航');navToggle.popoverTargetElement=navigator;navToggle.setAttribute('aria-controls',navigator.id);
 const navHead=make('div','canvas-navigator-head'),navClose=make('button','','关闭');navClose.type='button';navClose.onclick=()=>{navigator.hidePopover();navToggle.focus()};navHead.append(make('strong','','素材导航'),navClose);
 const search=make('input','canvas-navigator-search');search.type='search';search.placeholder='查找名称、用途或参考内容';search.setAttribute('aria-label','查找画布素材');search.maxLength=120;
 const filter=make('select','canvas-navigator-filter');filter.setAttribute('aria-label','筛选素材类型');for(const [value,label] of [['all','全部'],['image','图片'],['video','视频'],['audio','音频'],['text','文字'],['system','项目节点']]){const o=make('option','',label);o.value=value;filter.append(o)}
 const navControls=make('div','canvas-navigator-controls');navControls.append(search,filter);
 const navCount=make('p','canvas-navigator-count'),navList=make('div','canvas-navigator-list');navCount.setAttribute('role','status');navList.setAttribute('aria-label','素材查找结果');
 const map=document.createElementNS(edges.namespaceURI,'svg');map.classList.add('canvas-minimap');map.setAttribute('role','application');map.setAttribute('aria-label','画布缩略导航，点击或拖动定位，方向键平移');map.setAttribute('tabindex','0');
 const mapHint=make('p','canvas-navigator-hint','点击或拖动缩略图定位 · 方向键平移 · 双击适应画布');navigator.append(navHead,navControls,navCount,navList,map,mapHint);const navigation=make('div','canvas-navigation-bar');navigation.setAttribute('aria-label','画布导航');navigation.append(navToggle,viewMenu.menu);viewport.append(navigation,navigator);
 let navFrame=0,navSignature='',navItems=[],mapDragging=false;
 function canvasArea(){const area={x:16,y:document.body.classList.contains('canvas-expanded')?104:48,w:viewport.clientWidth-32,h:viewport.clientHeight-120};if(viewport.clientWidth<=900&&(mediaSelection||selectedNodes.size))area.y+=Math.max(42,selectedNodes.size?groupTools.offsetHeight:mediaToolbar.offsetHeight)+12;const r=viewport.getBoundingClientRect(),dock=toolbar.getBoundingClientRect(),chat=document.querySelector('.workspace-director-open .workspace-director-frame')||document.querySelector('.director');const rail=viewport.clientWidth>900&&document.querySelector('.canvas-launch-rail');if(rail&&getComputedStyle(rail).display!=='none'){const b=rail.getBoundingClientRect();if(b.left<=r.left+32&&b.right>r.left&&b.top<r.bottom&&b.bottom>r.top){const inset=Math.max(area.x,b.right-r.left+12);area.w-=inset-area.x;area.x=inset}}if(dock.top>r.top)area.h=Math.min(area.h,dock.top-r.top-area.y-12);if(chat&&getComputedStyle(chat).display!=='none'){const c=chat.getBoundingClientRect();if(c.right>r.left&&c.left<r.right&&c.bottom>r.top&&c.top<r.bottom){if(viewport.clientWidth>900)area.w=Math.max(120,c.left-r.left-area.x-20);else if(c.top>r.top+area.y)area.h=Math.min(area.h,c.top-r.top-area.y-14)}}area.h=Math.max(viewport.clientWidth<=900?48:100,area.h);return area}
 function openCanvas(){const wasFocus=focus;focus=false;viewport.classList.remove('canvas-focus');viewButton.textContent='返回成片预览';if(wasFocus)fit()}
 function clearFocusAnchor(){world.querySelectorAll('.reference-node,.canvas-output').forEach(c=>c.style.zIndex='')}
 function navRecords(){return [...world.querySelectorAll('.canvas-card,.canvas-entry')].filter(card=>!card.hidden&&!card.closest('[popover]')&&getComputedStyle(card).display!=='none').map(card=>{const n=graph.nodes.find(node=>node.id===card.dataset.nodeId);if(card.dataset.manualProject)return {card,id:'@manual:'+card.dataset.manualProject,label:card.getAttribute('aria-label')||'创作节点',kind:'system',role:'项目节点',text:''};return {card,id:n?.id||(card.dataset.systemNode==='image-job'?'@image-job':card===output?'@output':card.classList.contains('canvas-entry')?'@product':'@plan'),label:card.dataset.systemNode==='image-job'?card.querySelector('.canvas-image-job-title')?.textContent:n?.label||(n?{image:'图片参考',video:'视频参考',audio:'音轨',text:'文字参考'}[n.kind]:card===output?'成片预览':card.classList.contains('canvas-entry')?'商品参考':'拍摄方案'),kind:n?.kind||'system',role:roles[n?.role]||'项目节点',text:n?.text||''}}).sort((a,b)=>(a.kind==='system')-(b.kind==='system'))}
 function renderNavigation(){navFrame=0;if(!navigator.matches(':popover-open'))return;navItems=navRecords();const term=search.value.trim().toLocaleLowerCase(),items=navItems.filter(n=>(filter.value==='all'||n.kind===filter.value)&&[n.label,n.role,n.text].join(' ').toLocaleLowerCase().includes(term));const signature=JSON.stringify([search.value,filter.value,items.map(n=>[n.id,n.label,n.kind,n.role])]);if(signature!==navSignature){navSignature=signature;navList.replaceChildren();navCount.textContent=`${items.length} / ${navItems.length} 个节点`;for(const item of items){const b=make('button','canvas-navigator-result');b.type='button';b.dataset.nodeId=item.id;b.append(make('strong','',item.label),make('span','',item.kind==='system'?'项目节点':({image:'图片',video:'视频',audio:'音频',text:'文字'}[item.kind])+' · '+item.role));b.onclick=()=>{navigator.hidePopover();revealNode(item.card);world.querySelectorAll('.canvas-navigation-focus').forEach(c=>c.classList.remove('canvas-navigation-focus'));item.card.classList.add('canvas-navigation-focus');clearMediaSelection();if(item.card.dataset.kind!=='text'&&item.card.dataset.nodeId)selectMedia(item.id);focusNode(item.card);viewport.focus({preventScroll:true})};navList.append(b)}if(!items.length)navList.append(make('p','canvas-navigator-empty','没有匹配素材，试试其他名称或类型。'))}
  const mapItems=[...navItems.filter(n=>!n.card.classList.contains('in-folded-group')),...[...groupLayer.querySelectorAll('.is-folded')].map(card=>({card,id:'@group:'+card.dataset.groupId,label:card.firstElementChild.textContent,kind:'group'}))];const cards=mapItems.map(n=>({item:n,x:n.card.offsetLeft,y:n.card.offsetTop,w:n.card.offsetWidth,h:n.card.offsetHeight})).filter(n=>n.w&&n.h);if(!cards.length){map.replaceChildren();return}const left=Math.min(...cards.map(n=>n.x))-60,top=Math.min(...cards.map(n=>n.y))-60,right=Math.max(...cards.map(n=>n.x+n.w))+60,bottom=Math.max(...cards.map(n=>n.y+n.h))+60;map.setAttribute('viewBox',`${left} ${top} ${right-left} ${bottom-top}`);map.replaceChildren();const rect=(x,y,w,h,cls)=>{const e=document.createElementNS(edges.namespaceURI,'rect');for(const [key,value] of Object.entries({x,y,width:w,height:h}))e.setAttribute(key,value);e.setAttribute('class',cls);e.setAttribute('vector-effect','non-scaling-stroke');map.append(e);return e};for(const n of cards){const e=rect(n.x,n.y,n.w,n.h,'canvas-minimap-node '+n.item.kind+(n.item.card.classList.contains('canvas-navigation-focus')?' selected':''));e.dataset.nodeId=n.item.id;const title=document.createElementNS(edges.namespaceURI,'title');title.textContent=n.item.label;e.append(title)}const area=canvasArea();rect((area.x-tx)/scale,(area.y-ty)/scale,area.w/scale,area.h/scale,'canvas-minimap-view');
 }
 function queueNavigation(){if(!navFrame)navFrame=requestAnimationFrame(renderNavigation)}
 search.oninput=filter.onchange=queueNavigation;
 navigator.addEventListener('toggle',()=>{const open=navigator.matches(':popover-open');navToggle.setAttribute('aria-expanded',String(open));if(open){openCanvas();navSignature='';queueNavigation();search.focus()}});
 const mapPoint=e=>{const matrix=map.getScreenCTM();return matrix?new DOMPoint(e.clientX,e.clientY).matrixTransform(matrix.inverse()):null};
 const moveMap=e=>{const point=mapPoint(e);if(!point)return;const a=canvasArea();clearFocusAnchor();tx=a.x+a.w/2-point.x*scale;ty=a.y+a.h/2-point.y*scale;apply()};
 map.onpointerdown=e=>{if(e.button!==0)return;e.preventDefault();e.stopPropagation();map.focus();mapDragging=true;map.setPointerCapture(e.pointerId);moveMap(e)};map.onpointermove=e=>{if(mapDragging)moveMap(e)};map.onpointerup=map.onpointercancel=map.onlostpointercapture=()=>{mapDragging=false};map.ondblclick=()=>{clearFocusAnchor();fit()};map.onkeydown=e=>{if(!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown','Home'].includes(e.key))return;e.preventDefault();clearFocusAnchor();if(e.key==='Home'){fit();return}tx+=e.key==='ArrowLeft'?80:e.key==='ArrowRight'?-80:0;ty+=e.key==='ArrowUp'?80:e.key==='ArrowDown'?-80:0;apply()};
 document.addEventListener('keydown',e=>{if(e.key!=='/'||e.ctrlKey||e.metaKey||e.altKey||e.target.closest('input,textarea,select,[contenteditable=true]')||document.querySelector('dialog[open],[popover]:popover-open'))return;e.preventDefault();navigator.showPopover()});

 const mediaToolbar=make('div','canvas-media-toolbar');mediaToolbar.id='canvasMediaToolbar';mediaToolbar.setAttribute('role','toolbar');mediaToolbar.setAttribute('aria-label','所选素材操作');mediaToolbar.hidden=true;viewport.append(mediaToolbar);
 let mediaSelection=null,mediaFrame=0,mediaSignature='';
 function selectedMedia(){if(!mediaSelection||mediaSelection.project!==pid)return null;if(mediaSelection.output)return !output.hidden?{node:{id:'output',kind:'output',asset:project?.artifact||'partial',label:project?.artifact?'成片':'已生成片段'},card:output}:null;const node=graph.nodes.find(n=>n.id===mediaSelection.node&&n.asset===mediaSelection.asset);const card=node&&world.querySelector(`.reference-node[data-node-id="${CSS.escape(node.id)}"]`);return card?{node,card}:null}
 // Source downloads stay inside the authenticated project asset boundary.
 let sourceDownload=null;
 function cancelSourceDownload(){const active=sourceDownload;sourceDownload=null;active?.controller.abort();queueMediaTools()}
 async function downloadSource(){
  const item=selectedMedia(),kind=item&&mediaKind(item.node);if(!item||!['image','video','audio'].includes(kind))return;
  if(sourceDownload){if(sourceDownload.asset===item.node.asset)cancelSourceDownload();return}
  const request={project:pid,asset:item.node.asset,kind,filename:project?.canvas_assets?.[item.node.asset]?.filename||item.node.label||'素材',controller:new AbortController()};sourceDownload=request;queueMediaTools();
  try{const response=await fetch(`/creative/api/projects/${encodeURIComponent(request.project)}/canvas/assets/${encodeURIComponent(request.asset)}/source`,{headers:{Authorization:'Bearer '+key},signal:AbortSignal.any([request.controller.signal,AbortSignal.timeout(120000)])});if(!response.ok)throw Error();const blob=await response.blob();if(!blob.size||!blob.type.startsWith(request.kind+'/'))throw Error();if(sourceDownload!==request||pid!==request.project)return;
   const extension={'image/png':'png','image/jpeg':'jpg','image/webp':'webp','video/mp4':'mp4','video/quicktime':'mov','audio/mp4':'m4a'}[blob.type];let filename=request.filename.replace(/[\\/\x00-\x1f\x7f<>:"|?*]/g,'_').replace(/^\.+/,'').trim().slice(0,180)||'素材';if(extension&&!new RegExp('\\.'+extension+'$','i').test(filename)&&!(extension==='jpg'&&/\.jpe?g$/i.test(filename)))filename=filename.replace(/\.[a-z0-9]{1,8}$/i,'')+'.'+extension;
   const url=URL.createObjectURL(blob),link=make('a');link.href=url;link.download=filename;document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),30000);toast('原文件已交给浏览器下载');
  }catch{if(!request.controller.signal.aborted&&pid===request.project)toast('原文件下载失败，请点击下载重试')}
  finally{if(sourceDownload===request){sourceDownload=null;queueMediaTools()}}
 }
 function closeMediaOverflow(){mediaToolbar.querySelector('.canvas-media-overflow:popover-open')?.hidePopover()}
 function clearMediaSelection(){closeMediaOverflow();mediaSelection=null;mediaSignature='';mediaToolbar.hidden=true;world.querySelectorAll('.media-tool-selected').forEach(card=>card.classList.remove('media-tool-selected'))}
 function groupMediaTools(kind){
  const primary=new Set(kind==='image'?['preview','edit','region','adjust','light','download','close']:['preview','play','inline','assistant','trim','download','audio-play','audio','close']);
  const extra=[...mediaToolbar.querySelectorAll(':scope>button')].filter(b=>!primary.has(b.dataset.mediaAction));if(!extra.length)return;
  const more=make('button','canvas-media-more','更多工具'),panel=make('div','canvas-media-overflow');more.type='button';more.setAttribute('aria-haspopup','dialog');more.setAttribute('aria-expanded','false');panel.id='canvasMediaOverflow';panel.setAttribute('popover','auto');panel.setAttribute('role','dialog');panel.setAttribute('aria-label','更多'+(kind==='image'?'图片':'视频')+'工具');more.setAttribute('aria-controls',panel.id);
  const enabled=make('div','canvas-media-overflow-group'),pending=make('div','canvas-media-overflow-group');enabled.append(make('strong','','编辑与素材'));pending.append(make('strong','','暂未接入'));
  for(const b of extra){const action=b.onclick;b.onclick=e=>{panel.hidePopover();action?.call(b,e)};(b.dataset.mediaAction.startsWith('pending-')?pending:enabled).append(b)}
  if(enabled.children.length>1)panel.append(enabled);if(pending.children.length>1)panel.append(pending);
  more.onclick=()=>{if(panel.matches(':popover-open')){panel.hidePopover();return}panel.showPopover();const r=more.getBoundingClientRect(),w=panel.offsetWidth,h=panel.offsetHeight;panel.style.left=Math.max(12,Math.min(innerWidth-w-12,r.right-w))+'px';panel.style.top=Math.max(12,Math.min(innerHeight-h-12,r.bottom+8))+'px';panel.querySelector('button:not(:disabled)')?.focus({preventScroll:true})};
  panel.addEventListener('toggle',()=>more.setAttribute('aria-expanded',String(panel.matches(':popover-open'))));mediaToolbar.insertBefore(more,mediaToolbar.querySelector('[data-media-action=close]'));mediaToolbar.append(panel);
 }
 function selectMedia(id,fitMobile=false){selectedNodes.clear();updateSelection();const node=graph.nodes.find(n=>n.id===id),kind=mediaKind(node);if(!node?.asset||!['image','video','audio'].includes(kind))return;mediaSelection={project:pid,node:id,asset:node.asset};queueMediaTools();if(fitMobile&&viewport.clientWidth<=900){const card=selectedMedia()?.card;if(card)focusNode(card)}}
 // The generated output is a read-only projection, never a persisted canvas asset.
 function selectOutput(fitMobile=false){if(output.hidden)return;selectedNodes.clear();updateSelection();mediaSelection={project:pid,output:true};queueMediaTools();if(fitMobile&&viewport.clientWidth<=900)focusNode(output)}
 const outputLabel=outputHead.querySelector('strong');outputLabel.tabIndex=0;outputLabel.setAttribute('role','button');outputLabel.setAttribute('aria-label','选择成片');outputLabel.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();selectOutput(true)}};
 output.addEventListener('click',e=>{if(e.target===outputLabel||e.target===outputHead)selectOutput(true);else if(e.target===document.querySelector('#video'))selectOutput()});
 for(const event of ['play','pause','loadedmetadata','emptied','error'])output.addEventListener(event,queueMediaTools,true);
 const outputSpec=make('span','canvas-media-spec');outputHead.append(outputSpec);const syncOutputSpec=()=>{const video=document.querySelector('#video');outputSpec.textContent=video?.readyState>=1&&!video.error?mediaSpecText({width:video.videoWidth,height:video.videoHeight,duration:video.duration}):'';outputSpec.title=outputSpec.textContent?'当前预览视频 · '+outputSpec.textContent:''};for(const event of ['loadedmetadata','emptied','error'])output.addEventListener(event,syncOutputSpec,true);
 function outputActionAvailable(id){const target=document.getElementById(id);if(!target||target.disabled||target.hidden||target.classList.contains('hidden'))return false;if(['downloadButton','reviewButton'].includes(id)&&!project?.artifact)return false;if(id==='reviewButton'&&project.state!=='completed')return false;if(['inlineEditButton','canvasEditButton'].includes(id)&&locked())return false;return true}
 function outputAction(id){if(!outputActionAvailable(id))return;if(['inlineEditButton','canvasEditButton'].includes(id))document.querySelector('#video')?.pause();document.getElementById(id).click()}
 function mediaAction(selector){const target=selectedMedia()?.card.querySelector(selector);if(target&&!target.disabled)target.click()}
 function openMediaDetails(transforms=false){const item=selectedMedia();if(!item)return;const panel=item.card.querySelector('.asset-tools-panel');if(!panel)return;panel.showPopover();if(transforms){const generation=panel.querySelector('.generation-options'),adjust=panel.querySelector('.image-transforms');if(generation)generation.open=true;if(adjust){adjust.open=true;requestAnimationFrame(()=>adjust.querySelector('select')?.focus({preventScroll:true}))}}}
 function openVideoTool(tool){const item=selectedMedia(),kind=item&&mediaKind(item.node);if(!item||locked())return;const source=kind==='output'?'primary':'canvas_'+item.node.asset;item.card.querySelector('video')?.pause();document.dispatchEvent(new CustomEvent('creative-open-inline-edit',{detail:{source,tool,...(kind==='output'?{}:{canvasAsset:item.node.asset})}}))}
 async function splitSelectedAudio(){
  const item=selectedMedia();if(!item||mediaKind(item.node)!=='video'||locked())return;
  if(hasDrafts()){toast('请先保存或放弃画布修改');return}
  const ownerPid=pid,aid=item.node.asset;setBusy(true);toast('正在分离音视频，原片保留');
  try{const result=await api(`/projects/${ownerPid}/canvas/assets/${aid}/split-audio?revision=${project.revision}`,'POST');if(pid!==ownerPid)return;project=result.project;clearMedia();draw();requestAnimationFrame(()=>locateAsset(result.assets[1].id));toast('已新增无声视频与音轨，保留原片和来源连接')}catch(error){toast(error.message||'分离失败，原片保持不变')}finally{setBusy(false)}
 }
 function renderMediaTools(){mediaFrame=0;const item=selectedMedia();if(!item){clearMediaSelection();return}const {node,card}=item,kind=mediaKind(node);world.querySelectorAll('.media-tool-selected').forEach(c=>c.classList.toggle('media-tool-selected',c===card));card.classList.add('media-tool-selected');const signature=pid+'/'+node.id+'/'+node.asset+'/'+kind+'/'+generationSources.has(node.asset);if(signature!==mediaSignature){mediaSignature=signature;mediaToolbar.replaceChildren();const action=(label,fn,key)=>{const b=make('button');labelMediaAction(b,label,key);b.type='button';b.dataset.mediaAction=key;b.onclick=fn;mediaToolbar.append(b);return b};
   const modelId=kind==='image'?(node.image_model||project?.image_model||''):(node.model||project?.model||'');
   const modelLabel=node.model_label||node.image_model_label||((modelId&&window.studioModelLabel?.(modelId))||modelId);
   if(kind!=='audio'&&(modelId||modelLabel)){const badge=make('span','canvas-media-model-badge');badge.setAttribute('role','status');badge.setAttribute('aria-label','当前生成与编辑模型：'+(modelLabel||modelId));const logo=window.studioModelLogo?.(modelId);if(logo){logo.setAttribute('aria-hidden','true');badge.append(logo)}badge.append(make('span','canvas-media-model-name',modelLabel||modelId),make('small','canvas-media-model-kind','生成 / 编辑'));mediaToolbar.append(badge)}
   if(node.kind==='output'){action('放大预览',()=>showVideo(),'preview');action('播放',()=>{const v=document.querySelector('#video');if(v?.getAttribute('src')){if(v.paused)v.play().catch(()=>toast('视频暂不可播放'));else v.pause()}},'play');action('智能剪辑',()=>outputAction('inlineEditButton'),'inline');action('独立剪辑',()=>outputAction('canvasEditButton'),'editor');action('审阅成片',()=>outputAction('reviewButton'),'review');action('下载成片',()=>outputAction('downloadButton'),'download')}
   else if(kind==='image'){for(const label of ['人像质感调节','全景']){const b=action(label,()=>{},'pending-'+label);b.disabled=true;b.title=label+' · 尚未接入'}action('大图预览',()=>showImage(selectedMedia()?.node.id),'preview');if(comparisonSources(node.asset).length)action('前后对比',()=>showComparison(selectedMedia()?.node.asset),'compare');action('修改图片',()=>document.dispatchEvent(new CustomEvent('creative-edit-image',{detail:{asset:selectedMedia()?.node.asset}})),'edit');action('局部修改',()=>composeImage(selectedMedia()?.node.asset,true),'region');action('裁剪',()=>document.dispatchEvent(new CustomEvent('creative-reframe-image',{detail:{asset:selectedMedia()?.node.asset}})),'crop');action('多角度',()=>adjustImage('angle'),'adjust');action('重打光',()=>adjustImage('light'),'light');for(const label of ['九宫格','高清','元素编辑','图层分离']){const b=action(label,()=>{},'pending-'+label);b.disabled=true;b.title=label+' · 尚未接入'}action('宫格切分',()=>document.dispatchEvent(new CustomEvent('creative-grid-image',{detail:{asset:selectedMedia()?.node.asset}})),'grid');action('组合生成',()=>mediaAction('.compose-reference'),'compose');action('设为商品',()=>mediaAction('.use-product-reference'),'product')}
   else if(kind==='audio'){action('播放音轨',()=>{const audio=card.querySelector('audio');if(audio?.getAttribute('src')){if(audio.paused)audio.play().catch(()=>toast('音轨暂不可播放'));else audio.pause()}else card.querySelector('.canvas-audio-load')?.click()},'audio-play');action('音轨剪辑',()=>openVideoTool('audio'),'audio')}
   else{if(videoComparisonClips(node.asset).length)action('对照原片',()=>showVideoComparison(selectedMedia()?.node.asset),'compare');action('放大预览',()=>showVideo(),'preview');action('播放',()=>{const v=selectedMedia()?.card.querySelector('video');if(v){if(v.paused)v.play().catch(()=>toast('视频暂不可播放'));else v.pause();queueMediaTools()}else mediaAction('.video-actions button:not(.canvas-inline-video-edit)')},'play');action('内嵌剪辑',()=>mediaAction('.canvas-inline-video-edit'),'inline');action('独立剪辑',()=>mediaAction('.video-actions a'),'editor');if(generationSources.has(node.asset)&&outputActionAvailable('reviewButton'))action('审阅成片',()=>outputAction('reviewButton'),'review')}
   if(kind==='video'){const split=action('音视频分离',splitSelectedAudio,'split-audio');split.title='保留原片，新增无声视频与音轨';action('提取画面',()=>showVideo(),'frame');const reference=action('视频参考',()=>{},'pending-video-reference');reference.disabled=true;reference.title='当前生成模型尚未接入视频参考输入；可提取画面后连接为图片参考'}
   if(['video','output'].includes(kind)){action('Agent 剪辑',()=>openVideoTool('assistant'),'assistant');action('片段截取',()=>openVideoTool('trim'),'trim');action('片段重拍',()=>openVideoTool('retake'),'retake');action('口播字幕',()=>openVideoTool('speech'),'speech');for(const label of ['高清','逐帧拉片','画面裁切','智能去字幕','主体消除','创意片头','深度动作捕捉']){const b=action(label,()=>{},'pending-'+label);b.disabled=true;b.title=label==='音视频分离'?'音视频分离 · 音轨提取与音频节点尚未接入':label+' · 暂无可用处理模型'}}
   if(kind!=='output'){action('下载原文件',downloadSource,'download');action('详情',()=>openMediaDetails(),'details')}const close=action('×',()=>{clearMediaSelection();viewport.focus({preventScroll:true})},'close');close.setAttribute('aria-label','取消素材选择');groupMediaTools(kind);
  }
  mediaToolbar.setAttribute('aria-label','所选素材操作 · '+(node.label||'未命名素材'));const targets={adjust:'.image-transforms',compose:'.compose-reference',product:'.use-product-reference',inline:'.canvas-inline-video-edit',editor:'.video-actions a'};for(const button of mediaToolbar.querySelectorAll('button')){const target=targets[button.dataset.mediaAction]&&card.querySelector(targets[button.dataset.mediaAction]);const outputId={inline:'inlineEditButton',editor:'canvasEditButton',review:'reviewButton',download:'downloadButton'}[button.dataset.mediaAction];button.disabled=button.dataset.mediaAction==='grid'?(!project?.canvas_capabilities?.image_grid||locked()):button.dataset.mediaAction==='split-audio'?(!project?.canvas_capabilities?.audio_split||sourceAudioTracks.get(pid+'/'+node.asset)===false||locked()):button.dataset.mediaAction?.startsWith('pending-')?true:kind==='output'&&outputId?!outputActionAvailable(outputId):['split-audio','crop','edit','region','trim','retake','speech','assistant'].includes(button.dataset.mediaAction)?locked():!!targets[button.dataset.mediaAction]&&(!target||target.disabled||(['compose','product','inline','editor'].includes(button.dataset.mediaAction)&&locked()))}
  const splitButton=mediaToolbar.querySelector('[data-media-action=split-audio]');if(splitButton)splitButton.title=sourceAudioTracks.get(pid+'/'+node.asset)===false?'当前视频无音轨，无法分离音视频':!project?.canvas_capabilities?.audio_split?'音视频分离正在接入':'保留原片，新增无声视频与音轨';
  if(kind!=='output'){const download=mediaToolbar.querySelector('[data-media-action=download]'),active=sourceDownload?.asset===node.asset;labelMediaAction(download,active?'取消下载':'下载原文件',active?'close':'download');download.disabled=!!sourceDownload&&!active;download.setAttribute('aria-busy',String(active))}
  const enlarge=mediaToolbar.querySelector('[data-media-action=preview]');if(enlarge&&kind==='output'){const v=card.querySelector('video');enlarge.disabled=!v?.getAttribute('src')||v.readyState<1||!!v.error}
  const audioPlay=mediaToolbar.querySelector('[data-media-action=audio-play]');if(audioPlay){const audio=card.querySelector('audio');labelMediaAction(audioPlay,audio&&!audio.paused?'暂停音轨':'播放音轨',audio&&!audio.paused?'pause':'play')}
  const play=mediaToolbar.querySelector('[data-media-action=play]');if(play){const video=card.querySelector('video');labelMediaAction(play,video&&!video.paused?'暂停':'播放',video&&!video.paused?'pause':'play');play.disabled=kind==='output'?(!video?.getAttribute('src')||video.readyState<1||!!video.error):locked()||(!video&&!card.querySelector('.video-actions button:not(.canvas-inline-video-edit)'))}
  const r=card.getBoundingClientRect(),v=viewport.getBoundingClientRect(),a=canvasArea(),left=r.left-v.left,top=r.top-v.top;mediaToolbar.hidden=focus||left+r.width<0||left>viewport.clientWidth||top+r.height<0||top>viewport.clientHeight;if(mediaToolbar.hidden){closeMediaOverflow();return}mediaToolbar.style.boxSizing='border-box';mediaToolbar.style.maxWidth=Math.max(120,Math.min(viewport.clientWidth-24,a.w))+'px';const width=mediaToolbar.offsetWidth,height=mediaToolbar.offsetHeight;mediaToolbar.style.left=Math.max(12,Math.min(viewport.clientWidth-width-12,left+r.width/2-width/2))+'px';const minTop=document.body.classList.contains('canvas-expanded')?64:12,maxTop=viewport.clientHeight-height-70,above=top-height-10,below=top+r.height+10;mediaToolbar.style.top=Math.max(minTop,Math.min(maxTop,above<minTop&&below<=maxTop?below:above))+'px';if(viewport.clientWidth<=900){mediaToolbar.style.left='12px';mediaToolbar.style.top='104px'}else mediaToolbar.style.left=Math.min(parseFloat(mediaToolbar.style.left),Math.max(12,a.x+a.w-width))+'px';
 }
 function queueMediaTools(){if(videoSession)videoEdit.disabled=!canEditVideo(videoSession);if(!mediaFrame)mediaFrame=requestAnimationFrame(renderMediaTools)}
 document.addEventListener('pointerdown',e=>{if(e.target.closest('.canvas-viewport')&&!e.target.closest('.reference-node,.canvas-output,.canvas-media-toolbar,[popover],button,a,input,textarea,select,summary'))clearMediaSelection()});
 document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!document.querySelector('dialog[open],[popover]:popover-open'))clearMediaSelection()});
 window.addEventListener('resize',queueMediaTools);

 document.addEventListener('creative-video-input-draft',e=>{if(e.detail?.project===project?.id)configureVideo(e.detail)});
 async function configureVideo(draft=null){if(locked()||hasDrafts()){toast('请先保存或放弃草稿');return}try{const {openVideoInputs}=await import('/creative/video-inputs.js');await openVideoInputs({draft,initialMode:draft?.mode,initialAsset:draft?.asset,focusAsset:draft?.focusAsset,project:()=>project,locked,hasDrafts,api,toast,busy:setBusy,accepted:p=>{if(project?.id===p.id){project=p;clearMedia();draw();schedule();document.dispatchEvent(new Event('creative-video-input-saved'))}},preview:async aid=>{const r=await fetch(`/creative/api/projects/${project.id}/canvas/assets/${aid}/preview`,{headers:{Authorization:'Bearer '+key}});if(!r.ok)throw Error();return URL.createObjectURL(await r.blob())}})}catch(e){toast(e.message||'视频输入暂不可读取')}}
 // Restore only controls disabled by the canvas lock; unsupported tools stay disabled.
 const temporarilyDisabled=new WeakMap();
 const locked=()=>!project||busy||saving||!!canvasGesture||(['running','rendering','planning'].includes(project.state)||project.image_task?.state==='running');
 function updateStatus(){saveButton.hidden=discardButton.hidden=!dirty;toolbar.classList.toggle('has-drafts',dirty);status.textContent=dirty?'参考修改尚未保存，保存后再出方案':(project?'已保存 · '+graph.nodes.length+' 个素材 · '+graph.edges.length+' 个导演参考':'先创建一个创作项目');saveButton.disabled=!dirty||locked();discardButton.disabled=!dirty||saving||!!canvasGesture;[noteButton,imageButton,videoButton,arrangeButton,composeButton,videoInputsButton].forEach(b=>b.disabled=locked());[selectButton,handButton,fitButton,zoomOut,zoomIn,viewButton].forEach(b=>b.disabled=!!canvasGesture);arrangeButton.disabled=locked()||generationChecking;arrangeButton.title=generationChecking?'正在核对素材来源':'按已记录的来源排列素材';world.querySelectorAll('.reference-node button,.reference-node input,.reference-node textarea,.reference-node select').forEach(e=>{if(e.matches('.asset-tools-toggle,.asset-tools-close,.node-focus,.media-preview-message button'))return;if(locked()){if(!temporarilyDisabled.has(e))temporarilyDisabled.set(e,e.disabled);e.disabled=true}else if(temporarilyDisabled.has(e)){e.disabled=temporarilyDisabled.get(e);temporarilyDisabled.delete(e)}});queueMediaTools();updateSelection()}
 function change(mergeKey=null){pruneGroups();rememberChange(mergeKey);focus=false;viewport.classList.remove('canvas-focus');viewButton.textContent='返回成片预览';updateStatus();alignOutput();lines()}
 function apply(){viewMenu.toggle.textContent=Math.round(scale*100)+'%';world.style.transform=`translate(${tx}px,${ty}px) scale(${scale})`;
  // Keep the workflow grid in world space. At distant zooms, show every other
  // grid line so dots remain readable without changing the node coordinates.
  let gap=20*scale;while(gap<8)gap*=2;
  viewport.style.setProperty('--canvas-grid-alpha',String(Math.max(.08,Math.min(.15,.15*scale))));viewport.style.setProperty('--canvas-grid-gap',gap+'px');viewport.style.setProperty('--canvas-grid-x',tx+'px');viewport.style.setProperty('--canvas-grid-y',ty+'px');
  queueNavigation();queueMediaTools()}
 function zoom(value,cx=viewport.clientWidth/2,cy=viewport.clientHeight/2){cameraTouched=true;const old=scale;scale=Math.min(1.6,Math.max(.08,value));tx=cx-(cx-tx)*scale/old;ty=cy-(cy-ty)*scale/old;apply()}
 function focusNode(card){revealNode(card);openCanvas();clearFocusAnchor();card.style.zIndex='2';if(viewport.clientWidth<=900&&selectedMedia()?.card===card){renderMediaTools();mediaToolbar.hidden=false}const a=canvasArea();scale=Math.max(.08,Math.min(1.4,a.w/(card.offsetWidth+30),a.h/(card.offsetHeight+30)));tx=a.x+(a.w-card.offsetWidth*scale)/2-card.offsetLeft*scale;ty=a.y+(a.h-card.offsetHeight*scale)/2-card.offsetTop*scale;apply()}
 function syncFilmTask(){
  const p=project,film=p?.film;document.body.classList.toggle('workspace-generating',!!p&&['running','rendering'].includes(p.state));
  if(!p||p.creation_mode==='image'||p.creation_mode==='video'||p.artifact||(p.creation_mode!=='agent'&&!film)){filmTaskCard?.remove();filmTaskCard=null;return}
  if(!filmTaskCard){filmTaskCard=make('section','canvas-card canvas-image-job canvas-film-task');filmTaskCard.dataset.systemNode='film-task';world.append(filmTaskCard)}
  const phase=film?.progress||{};document.body.classList.toggle('workspace-generating',['running','rendering'].includes(p.state));const running=['running','rendering','planning'].includes(p.state);
  const title=syncFailures?'状态同步中断':({intake:'创作需求 · 待补充',planning:'正在整理方案',ready:'方案已就绪',running:'视频生成中',rendering:'正在保存成片',paused:'视频任务已暂停',failed:'视频任务失败'}[p.state]||'创作任务');
  const stage=({queued:'排队中',preparing:'准备素材',submitting:'提交中',generating:'生成中',downloading:'保存结果',finalizing:'检查成片'})[phase.phase||phase.stage];
  filmTaskCard.replaceChildren(make('div','canvas-card-head',title));
  const info=make('p','canvas-image-job-progress',syncFailures?'等待重新连接，已提交任务保持不变':running?(stage?(stage+(Number.isFinite(phase.percent)?' '+Math.round(phase.percent)+'%':'')):'等待任务更新'):p.state==='paused'?'查询已暂停，恢复时继续查询原任务':p.state==='failed'?'本次生成已停止':p.state==='intake'?'在右侧补充需求后生成方案':'');
  info.setAttribute('role','status');filmTaskCard.append(info);
  filmTaskCard.setAttribute('aria-busy',String(running));
  // Keep an indeterminate meter visible during provider polling gaps. The
  // task is still running even when the latest percentage is unavailable.
  if(running||p.state==='paused'){
   const meter=make('div','manual-progress-meter'),fill=make('span'),caption=make('small','manual-progress-caption'),known=Number.isFinite(phase.percent);
   meter.setAttribute('role','progressbar');meter.setAttribute('aria-label','生成进度：'+(info.textContent||'等待任务更新'));meter.dataset.determinate=String(known&&!syncFailures);
   if(known&&!syncFailures){const value=Math.max(0,Math.min(100,phase.percent));meter.setAttribute('aria-valuemin','0');meter.setAttribute('aria-valuemax','100');meter.setAttribute('aria-valuenow',String(value));meter.setAttribute('aria-valuetext',info.textContent||'等待任务更新');meter.removeAttribute('aria-description');fill.style.width=value+'%'}else{meter.removeAttribute('aria-valuemin');meter.removeAttribute('aria-valuemax');meter.removeAttribute('aria-valuenow');meter.removeAttribute('aria-valuetext');meter.setAttribute('aria-description',info.textContent||'等待任务更新')}
   const progressLabel=info.textContent||'等待任务更新';caption.setAttribute('role','status');caption.setAttribute('aria-live','polite');caption.setAttribute('aria-label',progressLabel);caption.textContent=progressLabel;meter.append(fill);filmTaskCard.append(caption,meter);
  }
  if(p.error)filmTaskCard.append(make('p','canvas-image-job-description',p.error));
  if(p.state==='paused'&&film?.job_id){const resume=make('button','','恢复查询已有任务');resume.type='button';resume.onclick=()=>$('executeButton').click();filmTaskCard.append(resume)}
 }
 const manualResultResize=new ResizeObserver(()=>{syncManualResultLayout();queueMediaTools()});
 document.addEventListener('creative-manual-view-ready',syncManualResultLayout);
 function syncManualResultLayout(){
  const root=world.querySelector('.manual-root-node'),result=world.querySelector('.manual-root-result');if(root&&result){root.style.left=result.offsetLeft+'px';root.style.top=(result.offsetTop+result.offsetHeight+12)+'px'}
 }
 function alignOutput(){
  syncManualResultLayout();
  // A video node represents available media, not a permanent empty form.
  output.hidden=!project?.artifact&&!project?.shots?.some(s=>s.state==='completed');syncOutputProjection();
  updateGroupFrames();const cards=visibleCards().filter(c=>c.matches('.reference-node,.canvas-group-frame,.manual-root-node,.manual-generation-node'));
  let nextX=cards.length?Math.max(...cards.map(c=>c.offsetLeft+c.offsetWidth+90)):40;
  for(const task of [imageJobCard,filmTaskCard])if(task&&!task.hidden&&getComputedStyle(task).display!=='none'){task.style.left=nextX+'px';task.style.top='30px';nextX+=task.offsetWidth+90}
  output.style.left=nextX+'px';
  const prompt=world.querySelector('.compiled-prompt-node');if(prompt){prompt.style.left=output.style.left;prompt.style.top=(output.offsetTop+output.offsetHeight+36)+'px'}
  const entry=world.querySelector('.canvas-entry');if(entry){entry.style.left=(Math.min(40,...cards.map(c=>c.offsetLeft))-340)+'px';entry.style.top='30px'}
 }
 function fit(){alignOutput();const cards=visibleCards();world.classList.toggle('canvas-dense',cards.length>8);const a=canvasArea();if(!cards.length){scale=1;tx=a.x;ty=a.y;apply();lines();return}const left=Math.min(...cards.map(n=>n.offsetLeft)),top=Math.min(...cards.map(n=>n.offsetTop)),right=Math.max(...cards.map(n=>n.offsetLeft+n.offsetWidth+20)),bottom=Math.max(...cards.map(n=>n.offsetTop+n.offsetHeight+20));scale=Math.max(.08,Math.min(1,a.w/(right-left),a.h/(bottom-top)));tx=a.x+(a.w-(right-left)*scale)/2-left*scale;ty=a.y+(a.h-(bottom-top)*scale)/2-top*scale;apply();lines()}
 function derived(){const result=[];for(const child of graph.nodes)for(const aid of project?.canvas_lineage?.[child.asset]?.sources||[])for(const parent of graph.nodes)if(parent.asset===aid&&parent.id!==child.id)result.push({source:parent.id,target:child.id,kind:'derived'});return result}
 function connectionY(card){const media=card.querySelector('.canvas-card-body>img,.canvas-card-body>video,.preview video'),box=card.getBoundingClientRect(),image=media?.getBoundingClientRect();return card.offsetTop+(image?.height&&box.height?(image.top-box.top+image.height/2)/box.height*card.offsetHeight:card.offsetHeight/2)}
 function lines(){
  syncManualResultLayout();
  syncOutputProjection();updateGroupFrames();queueNavigation();queueMediaTools();
  edges.replaceChildren();const defs=document.createElementNS(edges.namespaceURI,'defs');for(const kind of ['derived','context','first-frame']){const marker=document.createElementNS(edges.namespaceURI,'marker');marker.id='arrow-'+kind;marker.setAttribute('viewBox','0 0 10 10');marker.setAttribute('refX','9');marker.setAttribute('refY','5');marker.setAttribute('markerWidth','6');marker.setAttribute('markerHeight','6');marker.setAttribute('orient','auto-start-reverse');const tip=document.createElementNS(edges.namespaceURI,'path');tip.setAttribute('d','M 0 0 L 10 5 L 0 10 z');tip.classList.add(kind);marker.append(tip);defs.append(marker)}edges.append(defs);
  const cards=new Map([...world.querySelectorAll('.reference-node')].map(c=>[c.dataset.nodeId,c]));for(const frame of groupLayer.querySelectorAll('.is-folded'))for(const id of (graph.groups||[]).find(g=>g.id===frame.dataset.groupId)?.members||[])cards.set(id,frame);
  // Before a film exists, the visible task card owns the director inputs.
  // Pointing to the hidden output silently drops all of those connections.
  cards.set('director',filmTaskCard?.isConnected&&!filmTaskCard.hidden?filmTaskCard:output);cards.set('product',world.querySelector('.canvas-entry'));
  const bound=graph.nodes.filter(n=>generationSources.has(n.asset)),links=[...derived(),...generationEdges(),...graph.edges.map(e=>({...e,kind:'context'}))],ref=project?.reference;
  if(bound.length){for(const n of bound)links.push({source:n.id,target:'director',kind:'derived'})}
  else for(const input of generationInputs()?.images||[]){const n=graph.nodes.find(n=>n.asset===input.asset);links.push({source:n?.id||'product',target:'director',kind:'first-frame'})}
  world.querySelectorAll('.reference-node').forEach(card=>{const n=graph.nodes.find(n=>n.id===card.dataset.nodeId),bound=generationSources.has(n?.asset);card.toggleAttribute('data-generation-source',bound);let badge=card.querySelector('.generation-source-badge');if(bound&&!badge){badge=make('span','generation-source-badge','生成原片');badge.title='已核对：冻结剪辑来源与本次生成原片内容一致';card.querySelector('.canvas-card-head')?.prepend(badge)}else if(!bound)badge?.remove()});
  if(ref){for(const child of graph.nodes){const origin=project.canvas_lineage?.[child.asset];if(origin?.reference_id===ref.id&&!origin.sources.length)links.push({source:'product',target:child.id,kind:'derived'})}}
  const related=new Set(tracing?[tracing]:[]);if(tracing){let added=true;while(added){added=false;for(const e of links.filter(e=>e.kind==='derived'||e.kind==='first-frame'))if(related.has(e.target)&&!related.has(e.source)){related.add(e.source);added=true}}}
  world.querySelectorAll('.reference-node').forEach(c=>{c.classList.toggle('lineage-dim',!!tracing&&!related.has(c.dataset.nodeId));c.classList.toggle('lineage-focus',tracing===c.dataset.nodeId)});
  for(const edge of links){const a=cards.get(edge.source),b=cards.get(edge.target);if(!a||!b||a===b||a.hidden||b.hidden||!a.offsetWidth||!b.offsetWidth)continue;const path=document.createElementNS(edges.namespaceURI,'path');const x=a.offsetLeft+a.offsetWidth,y=connectionY(a),endX=b.offsetLeft,endY=connectionY(b),bend=Math.max(70,Math.abs(endX-x)*.45);path.setAttribute('d',`M ${x} ${y} C ${x+bend} ${y}, ${endX-bend} ${endY}, ${endX} ${endY}`);path.classList.add(edge.kind);path.dataset.source=edge.source;path.dataset.target=edge.target;path.setAttribute('marker-end','url(#arrow-'+edge.kind+')');if(tracing)path.classList.add(related.has(edge.source)&&related.has(edge.target)?'lineage-active':'lineage-dim');const title=document.createElementNS(edges.namespaceURI,'title');title.textContent={derived:'素材派生来源',context:'仅供导演理解', 'first-frame':'实际视频模型图片输入'}[edge.kind];path.append(title);edges.append(path);if(edge.kind!=='context'){const signal=path.cloneNode(false);signal.classList.add('wire-signal');signal.removeAttribute('marker-end');signal.removeAttribute('data-source');signal.removeAttribute('data-target');signal.setAttribute('aria-hidden','true');signal.setAttribute('pathLength','100');edges.append(signal)}}
 }
 // Keep verified source chains on the same row using the rendered card heights.
 // Source ordering comes from the server; measured columns form a reversible layout draft.
 function alignSourceRows(proposal,sizes){
  const next=generationColumns(structuredClone(proposal)),nodes=next.nodes,byId=new Map(nodes.map(n=>[n.id,n])),parents=new Map(nodes.map(n=>[n.id,[]]));
  for(const e of generationEdges(nodes))if(byId.get(e.source).x<byId.get(e.target).x)parents.get(e.target).push(e.source);
  for(const child of nodes)for(const source of project?.canvas_lineage?.[child.asset]?.sources||[])for(const parent of nodes)if(parent.asset===source&&parent.x<child.x)parents.get(child.id).push(parent.id);
  // The server gives source order; rendered media widths determine column spacing.
  const columns=[...new Set(nodes.map(n=>n.x))].sort((a,b)=>a-b),widths=new Map([...world.querySelectorAll('.reference-node')].map(card=>[card.dataset.nodeId,card.offsetWidth]));
  let columnLeft=40;
  for(const originalX of columns){
   const column=nodes.filter(n=>n.x===originalX),width=Math.max(240,...column.map(n=>widths.get(n.id)||240));
   if(columnLeft+width>9500)return proposal;
   for(const node of column)node.layoutX=columnLeft;
   columnLeft+=width+110;
  }
  for(const node of nodes){node.x=node.layoutX;delete node.layoutX}
  for(const x of [...new Set(nodes.map(n=>n.x))].sort((a,b)=>a-b)){
   let bottom=-24;
   for(const node of nodes.filter(n=>n.x===x).sort((a,b)=>a.y-b.y)){
    const sources=parents.get(node.id).map(id=>byId.get(id)),anchor=sources.length?Math.min(...sources.map(n=>n.y)):node.y;
    node.y=Math.max(30,bottom+54,anchor);bottom=node.y+(sizes[node.id]||450);
    // Preserve the bounded server proposal if a very tall graph cannot fit.
    if(bottom>9000)return proposal;
   }
  }
  return next;
 }
 async function arrange(){if(locked())return;saving=true;updateStatus();const owner=pid,sizes=Object.fromEntries([...world.querySelectorAll('.reference-node')].map(c=>[c.dataset.nodeId,Math.max(100,Math.min(1800,c.offsetHeight))]));try{const result=await api('/projects/'+project.id+'/canvas/layout','POST',{revision,...graph,sizes});if(pid!==owner)return;graph=alignSourceRows(result.canvas,sizes);change();paint();fit();toast('已按来源对齐素材流程，保存参考后保留')}catch(e){if(pid===owner)toast(e.message)}finally{saving=false;updateStatus()}}
 function restoreSource(aid,role){if(locked())return;if(graph.nodes.length>=16){toast('画布最多 16 个素材，请先整理');return}const asset=project.canvas_assets?.[aid];if(!asset)return;const id='n'+crypto.randomUUID().replaceAll('-','');graph.nodes.push({id,kind:asset.kind,asset:aid,label:'来源素材',text:'',role,...position()});tracing=null;change();paint();fit();toast('来源已放回画布，未增加导演参考；保存后保留')}
 // Preview state is view-only. Retrying downloads never starts generation.
 async function thumbnail(asset,img){
  const requestPid=pid,cache=requestPid+'/'+asset;
  const message=img.previewMessage;
  const state=(value,text)=>{img.dataset.previewState=value;img.setAttribute('aria-busy',String(value==='loading'));if(message){message.replaceChildren();message.hidden=value==='ready';if(text)message.append(make('span','',text));if(value==='error'){const retry=make('button','','重试预览');retry.type='button';retry.onclick=()=>thumbnail(asset,img);message.append(retry)}}};
  state('loading','正在加载预览…');
  const failed=()=>{const cached=urls.get(cache);if(cached){URL.revokeObjectURL(cached);urls.delete(cache)}img.removeAttribute('src');state('error','预览暂不可用');};
  try{let url=urls.get(cache);if(!url){const r=await fetch(`/creative/api/projects/${requestPid}/canvas/assets/${asset}/preview`,{headers:{Authorization:'Bearer '+key},signal:AbortSignal.timeout(15000)});if(!r.ok)throw Error();url=URL.createObjectURL(await r.blob());if(pid!==requestPid){URL.revokeObjectURL(url);return}urls.set(cache,url)}
   if(pid!==requestPid)return;
   img.onload=()=>{state('ready');img.style.setProperty('--media-ratio',img.naturalWidth+'/'+img.naturalHeight);if(img.closest('.reference-node'))spaceNodes();img.previewReady?.()};img.onerror=failed;img.src=url;
  }catch{if(pid===requestPid)failed()}
 }
 // Video previews are temporary read-only players; closing cancels downloads and releases media.
 const videoViewer=make('dialog','canvas-video-viewer');videoViewer.id='canvasVideoViewer';videoViewer.setAttribute('aria-label','视频放大预览');
 const videoHead=make('div','canvas-image-viewer-head'),videoTitle=make('strong'),videoEdit=make('button','','智能剪辑'),videoFull=make('button','','全屏'),videoClose=make('button','','×'),videoStage=make('div','canvas-video-viewer-stage'),videoInfo=make('div','canvas-video-viewer-info');
 videoFull.type=videoClose.type='button';videoFull.setAttribute('aria-label','全屏播放');videoClose.setAttribute('aria-label','关闭视频预览');videoInfo.setAttribute('role','status');videoEdit.type='button';videoEdit.className='canvas-video-edit';videoEdit.setAttribute('aria-label','在智能剪辑中打开视频');videoHead.append(videoTitle,videoEdit,videoFull,videoClose);videoViewer.append(videoHead,videoStage,videoInfo);document.body.append(videoViewer);
 const framePosition=make('select','canvas-frame-position');framePosition.setAttribute('aria-label','截帧位置');for(const [value,label] of [['current','当前帧'],['first','首帧'],['last','尾帧']]){const option=make('option','',label);option.value=value;framePosition.append(option)}videoHead.insertBefore(framePosition,videoFull);
 const videoFrame=make('button','','截帧加入画布');videoFrame.type='button';videoFrame.setAttribute('aria-label','提取视频帧到画布');videoHead.insertBefore(videoFrame,videoFull);
 videoFrame.onclick=async()=>{const session=videoSession;if(!canEditVideo(session)||session.output||!session.canExtractFrame||session.player.readyState<2||session.player.seeking)return;session.player.pause();const position=framePosition.value;if(position!=='current'&&!session.framePositions?.includes(position))return;const at=position==='first'?0:Math.min(session.player.currentTime,Math.max(0,session.player.duration-.05));videoFrame.disabled=true;setBusy(true);try{const result=await api('/projects/'+session.project+'/canvas/assets/'+session.asset+'/frame?'+new URLSearchParams({revision:project.revision,at,position}),'POST');if(project?.id!==session.project)return;closeVideo();project=result.project;clearMedia();draw();requestAnimationFrame(()=>locateAsset(result.asset.id));toast('视频帧已加入画布，保留视频来源连接')}catch(e){toast(e.message||'取帧失败，原视频保持不变')}finally{setBusy(false);if(videoSession===session)videoFrame.disabled=false}};
 let videoSession=null,videoEpoch=0;const videoPositions=new Map();
 function playbackState(player){return {time:player.currentTime,volume:player.volume,muted:player.muted,rate:player.playbackRate}}
 function restorePlayback(player,state){if(!state||player.readyState<1||!Number.isFinite(player.duration))return;player.currentTime=Math.min(Math.max(0,state.time),player.duration);player.volume=state.volume;player.muted=state.muted;player.playbackRate=state.rate}
 function rememberVideo(){const session=videoSession;if(!session||session.project!==project?.id||session.player.readyState<1||session.player.error)return;const state=playbackState(session.player);videoPositions.set(session.asset,state);if(session.source?.isConnected&&session.source.getAttribute('src')===session.sourceUrl)restorePlayback(session.source,state)}
 function releaseVideo(){videoEpoch++;const session=videoSession;videoSession=null;if(!session)return;session.controller.abort();session.player.pause();session.player.removeAttribute('src');session.player.load();if(session.url)URL.revokeObjectURL(session.url);videoStage.replaceChildren();videoInfo.textContent='';queueMediaTools()}
 function closeVideo(){rememberVideo();if(document.fullscreenElement===videoStage)document.exitFullscreen().catch(()=>{});releaseVideo();if(videoViewer.open)videoViewer.close()}
 videoClose.onclick=closeVideo;videoViewer.addEventListener('cancel',e=>{e.preventDefault();closeVideo()});videoViewer.addEventListener('close',()=>{if(!videoViewer.open){rememberVideo();releaseVideo()}});
 function canEditVideo(session){return !!session&&session.project===project?.id&&!locked()&&!hasDrafts()&&(session.output?outputActionAvailable('inlineEditButton'):graph.nodes.some(n=>n.asset===session.asset&&mediaKind(n)==='video'))}
 videoEdit.onclick=()=>{const session=videoSession;if(!canEditVideo(session))return;const sourceTime=session.player.readyState>=1&&Number.isFinite(session.player.currentTime)?session.player.currentTime:undefined;closeVideo();document.dispatchEvent(new CustomEvent('creative-open-inline-edit',{detail:{source:session.output?'primary':'canvas_'+session.asset,sourceTime,...(session.output?{}:{canvasAsset:session.asset})}}))};
 videoFull.onclick=async()=>{const v=videoSession?.player;if(!v||v.readyState<1)return;try{if(videoStage.requestFullscreen)await videoStage.requestFullscreen();else if(v.webkitEnterFullscreen)v.webkitEnterFullscreen();else toast('当前浏览器不支持全屏')}catch{toast('无法进入全屏，可以继续在预览中播放')}};
 async function showVideo(){
  const item=selectedMedia();if(!item||!['video','output'].includes(item.node.kind))return;
  releaseVideo();const epoch=videoEpoch,requestPid=pid,source=item.card.querySelector('video'),player=make('video'),controller=new AbortController();
  source?.pause();player.controls=true;player.playsInline=true;player.preload='metadata';player.setAttribute('aria-label','视频预览播放器');
  const session={player,controller,url:null,project:requestPid,asset:item.node.asset,output:item.node.kind==='output',source,sourceUrl:source?.getAttribute('src')};videoSession=session;videoFrame.hidden=framePosition.hidden=session.output;framePosition.value='current';for(const option of framePosition.options)option.disabled=option.value!=='current';videoFrame.disabled=true;videoEdit.disabled=!canEditVideo(session);const current=()=>videoSession===session&&videoEpoch===epoch&&pid===requestPid&&videoViewer.open;
  if(!session.output)fetch(`/creative/api/projects/${requestPid}/canvas/assets/${session.asset}/metadata`,{headers:{Authorization:'Bearer '+key},signal:controller.signal}).then(r=>r.ok?r.json():null).then(meta=>{if(!current())return;session.canExtractFrame=meta?.can_extract_frame===true;session.framePositions=meta?.frame_positions||['current'];for(const option of framePosition.options)option.disabled=!session.framePositions.includes(option.value);videoFrame.title=session.canExtractFrame?'按所选位置提取图片，保留来源视频':'视频取帧服务待启用';videoFrame.disabled=!session.canExtractFrame||player.readyState<2||!canEditVideo(session)}).catch(()=>{});
  videoTitle.textContent=item.node.label||'视频预览';videoInfo.textContent='正在加载视频…';videoFull.disabled=true;videoStage.append(player);if(!videoViewer.open)videoViewer.showModal();
  const failed=()=>{if(!current())return;videoFull.disabled=true;videoInfo.replaceChildren(make('span','','视频暂不可读取 '));const retry=make('button','','重试预览');retry.type='button';retry.onclick=()=>showVideo();videoInfo.append(retry)};
  player.onloadeddata=()=>{if(current())videoFrame.disabled=!canEditVideo(session)||session.output||!session.canExtractFrame};player.onloadedmetadata=()=>{if(!current())return;videoFull.disabled=false;videoInfo.textContent=mediaSpecText({width:player.videoWidth,height:player.videoHeight,duration:player.duration});restorePlayback(player,source?.readyState>=1?playbackState(source):videoPositions.get(session.asset))};player.onerror=failed;
  try{if(source?.getAttribute('src')){player.src=source.currentSrc||source.src;return}if(item.node.kind==='output'){failed();return}
   // Native media requests can seek with Range after an authenticated, asset-only grant.
   // Keep the bearer credential out of media URLs and browser-visible cookies.
   if(location.protocol==='https:'){
    const endpoint=`/creative/api/projects/${encodeURIComponent(requestPid)}/canvas/assets/${encodeURIComponent(item.node.asset)}`;
    const grant=await fetch(endpoint+'/preview-session',{method:'POST',headers:{Authorization:'Bearer '+key},signal:AbortSignal.any([controller.signal,AbortSignal.timeout(30000)])});
    if(grant.ok){
     const data=await grant.json();if(!current())return;if(data.source!==endpoint+'/source')throw Error('preview');
     const poster=item.card.querySelector('img');if(poster?.src)player.poster=poster.src;
     player.onwaiting=()=>{if(current())videoInfo.textContent='正在缓冲视频…'};
     player.onplaying=()=>{if(current())videoInfo.textContent=mediaSpecText({width:player.videoWidth,height:player.videoHeight,duration:player.duration})};
     player.preload='auto';player.src=data.source;return;
    }
    if(![404,405].includes(grant.status))throw Error('preview');
   }
   // A progressing transfer may exceed 30s; only a stalled transfer gets the short deadline.
   const stalled=new AbortController();let idleTimer;const touch=()=>{clearTimeout(idleTimer);idleTimer=setTimeout(()=>stalled.abort(),30000)};touch();
   try{
    const response=await fetch(`/creative/api/projects/${encodeURIComponent(requestPid)}/canvas/assets/${encodeURIComponent(item.node.asset)}/source`,{headers:{Authorization:'Bearer '+key},signal:AbortSignal.any([controller.signal,stalled.signal,AbortSignal.timeout(180000)])});if(!response.ok)throw Error('preview');touch();
    const total=Number(response.headers.get('content-length')),reader=response.body.getReader(),chunks=[];let received=0;
    const paintDownload=()=>{if(!current())return;const size=(received/1048576).toFixed(1),known=Number.isFinite(total)&&total>0;videoInfo.textContent=known?`正在加载视频 ${Math.min(99,Math.floor(received/total*100))}% · ${size} / ${(total/1048576).toFixed(1)} MB`:`正在加载视频 · 已读取 ${size} MB`;};paintDownload();
    while(true){const {done,value}=await reader.read();if(done)break;chunks.push(value);received+=value.byteLength;touch();paintDownload();}
    if(!current())return;videoInfo.textContent='视频已下载，正在准备播放…';session.url=URL.createObjectURL(new Blob(chunks,{type:response.headers.get('content-type')||'video/mp4'}));player.src=session.url;
   }finally{clearTimeout(idleTimer)}
  }catch{if(!controller.signal.aborted)failed()}
 }
 const imageViewer=make('dialog','canvas-image-viewer');imageViewer.id='canvasImageViewer';imageViewer.setAttribute('aria-label','素材大图预览');
 const viewerHead=make('div','canvas-image-viewer-head'),viewerTitle=make('strong'),viewerCount=make('span'),viewerClose=make('button','','关闭');viewerClose.type='button';viewerClose.setAttribute('aria-label','关闭大图预览');viewerClose.onclick=()=>imageViewer.close();viewerHead.append(viewerTitle,viewerCount,viewerClose);
 const viewerStage=make('div','canvas-image-viewer-stage'),viewerFooter=make('div','canvas-image-viewer-footer'),viewerPrevious=make('button','','← 上一张'),viewerNext=make('button','','下一张 →'),viewerSize=make('span'),viewerControls=make('div','canvas-image-viewer-controls'),viewerZoomOut=make('button','','−'),viewerZoomIn=make('button','','＋'),viewerZoom=make('output'),viewerFit=make('button','','适应'),viewerActual=make('button','','100%');
 for(const b of [viewerPrevious,viewerNext,viewerZoomOut,viewerZoomIn,viewerFit,viewerActual])b.type='button';
 viewerZoomOut.setAttribute('aria-label','缩小图片');viewerZoomIn.setAttribute('aria-label','放大图片');viewerZoom.setAttribute('aria-label','图片显示比例');viewerFit.setAttribute('aria-label','图片适应窗口');viewerActual.setAttribute('aria-label','按原始像素显示图片');viewerStage.tabIndex=0;viewerStage.setAttribute('aria-label','图片查看区域，可拖动或滚轮缩放');
 viewerControls.append(viewerZoomOut,viewerZoom,viewerZoomIn,viewerFit,viewerActual);viewerFooter.append(viewerPrevious,viewerSize,viewerNext);imageViewer.append(viewerHead,viewerStage,viewerControls,viewerFooter);document.body.append(imageViewer);let viewingNode=null,imageSession=null,imagePan=null;
 function clearImageSession(){imagePan=null;const previous=imageSession;imageSession=null;previous?.controller.abort();if(previous?.url)URL.revokeObjectURL(previous.url);viewerStage.replaceChildren()}
 function imageFitScale(session){return Math.min(1,Math.max(1,viewerStage.clientWidth-32)/session.img.naturalWidth,Math.max(1,viewerStage.clientHeight-32)/session.img.naturalHeight)}
 function paintImageView(){const s=imageSession,ready=!!s?.ready;for(const b of [viewerZoomOut,viewerZoomIn,viewerFit,viewerActual])b.disabled=!ready;viewerZoom.textContent=ready?Math.round(s.scale*100)+'%':'—';if(!ready){viewerStage.classList.remove('can-pan');viewerFit.setAttribute('aria-pressed','false');viewerActual.setAttribute('aria-pressed','false');return;}
  if(s.fit)s.scale=imageFitScale(s);const maxX=Math.max(0,(s.img.naturalWidth*s.scale-viewerStage.clientWidth)/2),maxY=Math.max(0,(s.img.naturalHeight*s.scale-viewerStage.clientHeight)/2);s.x=Math.max(-maxX,Math.min(maxX,s.x));s.y=Math.max(-maxY,Math.min(maxY,s.y));
  s.img.style.width=s.img.naturalWidth+'px';s.img.style.height=s.img.naturalHeight+'px';s.img.style.transform=`translate(-50%,-50%) translate(${s.x}px,${s.y}px) scale(${s.scale})`;viewerZoom.textContent=Math.round(s.scale*100)+'%';viewerStage.classList.toggle('can-pan',maxX>0||maxY>0);viewerFit.setAttribute('aria-pressed',String(s.fit));viewerActual.setAttribute('aria-pressed',String(!s.fit&&s.scale===1));viewerZoomOut.disabled=s.scale<=Math.min(.1,imageFitScale(s));viewerZoomIn.disabled=s.scale>=8;
 }
 function zoomImage(value,anchor){const s=imageSession;if(!s?.ready)return;const next=Math.max(Math.min(.1,imageFitScale(s)),Math.min(8,value)),factor=next/s.scale;s.fit=false;if(anchor){s.x=anchor.x-(anchor.x-s.x)*factor;s.y=anchor.y-(anchor.y-s.y)*factor}else{s.x*=factor;s.y*=factor}s.scale=next;paintImageView()}
 viewerZoomOut.onclick=()=>zoomImage(imageSession?.scale/1.25);viewerZoomIn.onclick=()=>zoomImage(imageSession?.scale*1.25);viewerFit.onclick=()=>{if(!imageSession?.ready)return;imageSession.fit=true;imageSession.x=imageSession.y=0;paintImageView()};viewerActual.onclick=()=>zoomImage(1);
 new ResizeObserver(()=>{if(imageViewer.open)paintImageView()}).observe(viewerStage);
 viewerStage.addEventListener('wheel',e=>{if(!imageSession?.ready)return;e.preventDefault();e.stopPropagation();const box=viewerStage.getBoundingClientRect();zoomImage(imageSession.scale*Math.exp(-Math.sign(e.deltaY)*.15),{x:e.clientX-box.x-box.width/2,y:e.clientY-box.y-box.height/2})},{passive:false});
 viewerStage.addEventListener('pointerdown',e=>{if(e.button!==0||!imageSession?.ready||e.target.closest('button'))return;e.preventDefault();e.stopPropagation();viewerStage.focus({preventScroll:true});imagePan={id:e.pointerId,x:e.clientX,y:e.clientY,startX:imageSession.x,startY:imageSession.y};viewerStage.setPointerCapture(e.pointerId)});
 viewerStage.addEventListener('pointermove',e=>{if(!imagePan||imagePan.id!==e.pointerId||!imageSession?.ready)return;e.preventDefault();e.stopPropagation();imageSession.x=imagePan.startX+e.clientX-imagePan.x;imageSession.y=imagePan.startY+e.clientY-imagePan.y;paintImageView()});
 for(const event of ['pointerup','pointercancel','lostpointercapture'])viewerStage.addEventListener(event,e=>{if(imagePan?.id===e.pointerId){imagePan=null;if(viewerStage.hasPointerCapture(e.pointerId))viewerStage.releasePointerCapture(e.pointerId)}});
 async function showImage(nodeId){const images=graph.nodes.filter(n=>mediaKind(n)==='image'&&n.asset),index=images.findIndex(n=>n.id===nodeId);if(index<0)return;clearImageSession();viewingNode=nodeId;const n=images[index];viewerTitle.textContent=n.label||'图片参考';viewerCount.textContent=(index+1)+' / '+images.length;viewerPrevious.disabled=index===0;viewerNext.disabled=index===images.length-1;viewerSize.textContent='正在读取原图…';
  const img=make('img'),message=make('div','media-preview-message');img.alt=n.label||'图片参考';img.draggable=false;img.dataset.previewState='loading';img.setAttribute('aria-busy','true');message.setAttribute('role','status');message.textContent='正在读取原图…';viewerStage.append(img,message);const session={project:pid,node:nodeId,img,controller:new AbortController(),url:null,ready:false,fit:true,scale:1,x:0,y:0};imageSession=session;paintImageView();if(!imageViewer.open)imageViewer.showModal();
  const current=()=>imageSession===session&&pid===session.project&&imageViewer.open;
  const failed=()=>{if(!current())return;if(session.url){URL.revokeObjectURL(session.url);session.url=null}img.removeAttribute('src');img.dataset.previewState='error';img.setAttribute('aria-busy','false');viewerSize.textContent='原图暂不可读取';message.replaceChildren(make('span','','原图暂不可读取'));const retry=make('button','','重试原图');retry.type='button';retry.onclick=()=>showImage(nodeId);message.append(retry)};
  img.onload=()=>{if(!current())return;session.ready=true;img.dataset.previewState='ready';img.setAttribute('aria-busy','false');message.hidden=true;viewerSize.textContent=img.naturalWidth+' × '+img.naturalHeight+' · 原图尺寸';paintImageView()};img.onerror=failed;
  try{const response=await fetch(`/creative/api/projects/${encodeURIComponent(session.project)}/canvas/assets/${encodeURIComponent(n.asset)}/source`,{headers:{Authorization:'Bearer '+key},signal:AbortSignal.any([session.controller.signal,AbortSignal.timeout(30000)])});if(!response.ok)throw Error();const blob=await response.blob();if(!blob.size||!blob.type.startsWith('image/'))throw Error();if(!current())return;session.url=URL.createObjectURL(blob);img.src=session.url}catch{if(!session.controller.signal.aborted)failed()}
 }
 function stepImage(delta){const images=graph.nodes.filter(n=>mediaKind(n)==='image'&&n.asset),index=images.findIndex(n=>n.id===viewingNode),next=images[index+delta];if(next)showImage(next.id)}
 viewerPrevious.onclick=()=>stepImage(-1);viewerNext.onclick=()=>stepImage(1);imageViewer.addEventListener('keydown',e=>{if(e.altKey||e.ctrlKey||e.metaKey)return;let action;if(e.key==='ArrowLeft'||e.key==='ArrowRight')action=()=>stepImage(e.key==='ArrowLeft'?-1:1);else if(e.key==='+'||e.key==='=')action=()=>viewerZoomIn.click();else if(e.key==='-')action=()=>viewerZoomOut.click();else if(e.key==='0')action=()=>viewerFit.click();else if(e.key==='1')action=()=>viewerActual.click();if(action){e.preventDefault();e.stopPropagation();action()}});imageViewer.addEventListener('close',()=>{viewingNode=null;clearImageSession()});

 // Compare the immutable export against its recorded source windows, not the latest edit draft.
 const videoComparison=make('dialog','video-comparison-dialog');videoComparison.id='videoComparisonDialog';videoComparison.setAttribute('aria-label','剪辑成片与原片对照');
 const vcHead=make('div','video-comparison-head'),vcTitle=make('strong','','对照原片'),vcClose=make('button','','关闭');vcClose.type='button';vcClose.setAttribute('aria-label','关闭视频对照');vcClose.onclick=()=>videoComparison.close();vcHead.append(vcTitle,vcClose);
 const vcChoice=make('label','video-comparison-choice','对照片段'),vcSelect=make('select');vcSelect.setAttribute('aria-label','对照片段');vcChoice.append(vcSelect);
 const vcStage=make('div','video-comparison-stage'),vcStatus=make('p','video-comparison-status'),vcControls=make('div','video-comparison-controls'),vcPlay=make('button','','同步播放'),vcBack=make('button','','−0.1 秒'),vcNext=make('button','','+0.1 秒'),vcRange=make('input'),vcClock=make('output'),vcSound=make('select'),vcRetry=make('button','','重新读取视频'),vcEdit=make('button','','定位到剪辑');
 vcStatus.setAttribute('role','status');for(const b of [vcPlay,vcBack,vcNext,vcRetry,vcEdit])b.type='button';vcRange.type='range';vcRange.min=0;vcRange.step='.01';vcRange.value=0;vcRange.setAttribute('aria-label','对照片段播放位置');vcSound.setAttribute('aria-label','对照音轨');for(const [value,label]of [['none','静音'],['source','听原片'],['result','听成片']]){const option=make('option','',label);option.value=value;vcSound.append(option)}vcControls.append(vcRange,vcClock,vcBack,vcPlay,vcNext,vcSound,vcEdit);videoComparison.append(vcHead,vcChoice,vcStage,vcStatus,vcRetry,vcControls);document.body.append(videoComparison);
 let vcSession=null;
 function videoComparisonClips(asset){const record=project?.canvas_lineage?.[asset];if(record?.kind!=='video_edit'||project?.canvas_assets?.[asset]?.kind!=='video')return[];return(record.clips||[]).map((c,index)=>({...c,index})).filter(c=>record.sources?.includes(c.asset)&&project.canvas_assets?.[c.asset]?.kind==='video'&&[c.start,c.end,c.at].every(Number.isFinite)&&c.start>=0&&c.end>c.start&&c.at>=0)}
 function vcStop(){const s=vcSession;if(!s)return;s.playing=false;cancelAnimationFrame(s.frame);s.videos.forEach(v=>v.pause());vcPlay.textContent='同步播放'}
 function vcRelease(){vcStop();const s=vcSession;if(!s)return;s.controller.abort();s.videos.forEach(v=>{v.onwaiting=v.onerror=v.onended=null;v.pause();v.removeAttribute('src');v.load()});s.urls.forEach(URL.revokeObjectURL);s.urls=[];s.videos=[]}
 videoComparison.addEventListener('close',()=>{if(videoComparison.open)return;vcRelease();vcSession=null;vcStage.replaceChildren();viewport.focus({preventScroll:true})});
 function vcPosition(t){const s=vcSession;if(!s?.ready)return;const position=Math.max(0,Math.min(s.duration,t));vcRange.value=position;vcRange.setAttribute('aria-valuetext',position.toFixed(2)+' 秒');vcClock.textContent=`原片 ${(s.clip.start+position).toFixed(2)}s · 成片 ${(s.clip.at+position).toFixed(2)}s`;return position}
 function vcSeek(t){const s=vcSession;if(!s?.ready)return;vcStop();const position=vcPosition(t);s.videos[0].currentTime=s.clip.start+position;s.videos[1].currentTime=s.clip.at+position}
 function vcAudio(){const s=vcSession;if(!s)return;s.videos.forEach((v,i)=>v.muted=vcSound.value!==(i?'result':'source'))}
 const vcCurrent=s=>vcSession===s&&videoComparison.open&&pid===s.project&&!s.controller.signal.aborted;
 function vcTick(s){if(!vcCurrent(s)||!s.playing)return;const [source,result]=s.videos,t=result.currentTime-s.clip.at;if(t>=s.duration-.025||result.ended||source.ended){vcSeek(s.duration);return}if(Math.abs(source.currentTime-(s.clip.start+t))>.08&&!source.seeking)source.currentTime=s.clip.start+t;vcPosition(t);s.frame=requestAnimationFrame(()=>vcTick(s))}
 vcPlay.onclick=async()=>{const s=vcSession;if(!s?.ready)return;if(s.playing){vcStop();return}if(Number(vcRange.value)>=s.duration-.03)vcSeek(0);vcAudio();s.playing=true;vcPlay.textContent='暂停对照';try{await Promise.all(s.videos.map(v=>v.play()));if(!vcCurrent(s)||!s.playing){s.videos.forEach(v=>v.pause());return}vcTick(s)}catch{if(vcCurrent(s)){vcStop();vcStatus.textContent='播放未开始，请点击同步播放重试。'}}};
 vcBack.onclick=()=>vcSeek(Number(vcRange.value)-.1);vcNext.onclick=()=>vcSeek(Number(vcRange.value)+.1);vcRange.oninput=()=>vcSeek(Number(vcRange.value));vcSound.onchange=vcAudio;
 async function loadVideoComparison(){
  const previous=vcSession;if(!previous)return;const clip=previous.clips[Number(vcSelect.value)];if(!clip)return;vcRelease();const s={project:previous.project,asset:previous.asset,clips:previous.clips,clip,controller:new AbortController(),urls:[],videos:[],ready:false,playing:false,frame:0};vcSession=s;vcStage.replaceChildren();vcRetry.hidden=true;vcClock.textContent='';vcStatus.textContent='正在读取原片和剪辑成片…';for(const control of [vcPlay,vcBack,vcNext,vcRange,vcSound,vcEdit])control.disabled=true;
  const labels=['原片','剪辑成片'];for(const label of labels){const figure=make('figure'),caption=make('figcaption','',label),video=make('video');video.playsInline=true;video.preload='auto';video.muted=true;video.setAttribute('aria-label',label+'对照播放器');figure.append(caption,video);vcStage.append(figure);s.videos.push(video)}
  try{
   const signal=AbortSignal.any([s.controller.signal,AbortSignal.timeout(60000)]);
   await Promise.all([clip.asset,s.asset].map(async(asset,i)=>{const response=await fetch(`/creative/api/projects/${s.project}/canvas/assets/${asset}/source`,{headers:{Authorization:'Bearer '+key},signal});if(!response.ok)throw Error();const blob=await response.blob();if(!blob.type.startsWith('video/')||!blob.size)throw Error();if(!vcCurrent(s))return;const url=URL.createObjectURL(blob);s.urls.push(url);const video=s.videos[i];await new Promise((resolve,reject)=>{const clean=()=>{clearTimeout(timer);video.removeEventListener('loadeddata',loaded);video.removeEventListener('error',failed);signal.removeEventListener('abort',failed)},loaded=()=>{clean();resolve()},failed=()=>{clean();reject(Error())},timer=setTimeout(failed,20000);video.addEventListener('loadeddata',loaded);video.addEventListener('error',failed);signal.addEventListener('abort',failed,{once:true});video.src=url})}));
   if(!vcCurrent(s))return;const [source,result]=s.videos;s.duration=Math.min(clip.end-clip.start,source.duration-clip.start,result.duration-clip.at);if(!Number.isFinite(s.duration)||s.duration<=0)throw Error();s.ready=true;vcRange.max=s.duration;for(const control of [vcPlay,vcBack,vcNext,vcRange,vcSound,vcEdit])control.disabled=false;
   s.videos.forEach((v,i)=>{vcStage.children[i].querySelector('figcaption').textContent=labels[i]+' · '+mediaSpecText({width:v.videoWidth,height:v.videoHeight,duration:v.duration});v.onwaiting=()=>{if(vcCurrent(s)&&s.playing){vcStop();vcStatus.textContent='视频正在缓冲，准备好后可继续同步播放。'}};v.onended=()=>{if(vcCurrent(s))vcStop()};v.onerror=()=>{if(vcCurrent(s)){vcStop();s.ready=false;for(const control of [vcPlay,vcBack,vcNext,vcRange,vcSound,vcEdit])control.disabled=true;vcStatus.textContent='视频解码失败，可重新读取。';vcRetry.hidden=false}}});
   const transition=s.clips.some(c=>c.transition?.kind&&c.transition.kind!=='cut');vcStatus.textContent='按此导出版本记录的来源时间窗对齐；可逐步核对商品、动作与字幕。'+(transition?'转场区域可能包含相邻画面混合。':'');vcSeek(0);vcAudio();
  }catch{if(!vcCurrent(s))return;vcRelease();s.ready=false;vcStage.replaceChildren(make('p','','视频读取失败，原素材保持不变。'));vcStatus.textContent='重新读取只加载已有文件，不会提交生成。';vcRetry.hidden=false}
 }
 function showVideoComparison(asset){const clips=videoComparisonClips(asset);if(!clips.length)return;vcRelease();world.querySelectorAll('video').forEach(v=>v.pause());vcSession={project:pid,asset,clips,controller:new AbortController(),urls:[],videos:[],frame:0};vcSelect.replaceChildren();clips.forEach((clip,index)=>{const option=make('option','',`第 ${clip.index+1} 段 · 成片 ${clip.at.toFixed(2)}–${(clip.at+clip.end-clip.start).toFixed(2)}s`);option.value=index;vcSelect.append(option)});vcSelect.disabled=clips.length<2;vcSound.value='none';if(!videoComparison.open)videoComparison.showModal();loadVideoComparison()}
 vcEdit.onclick=()=>{const s=vcSession;if(!s?.ready||s.project!==pid)return;if(locked()||hasDrafts()){toast('请先保存或放弃画布草稿，再定位剪辑');return}const asset=s.clip.asset,sourceTime=s.clip.start+Math.min(Number(vcRange.value),Math.max(0,s.duration-.001));vcStop();videoComparison.close();document.dispatchEvent(new CustomEvent('creative-open-inline-edit',{detail:{source:'canvas_'+asset,sourceTime,canvasAsset:asset}}))};
 vcSelect.onchange=loadVideoComparison;vcRetry.onclick=loadVideoComparison;document.addEventListener('visibilitychange',()=>{if(document.hidden)vcStop()});

 // Show owned previews immediately, then upgrade both to source files. View state only.
 const comparisonDialog=make('dialog','image-comparison-dialog');comparisonDialog.id='imageComparisonDialog';comparisonDialog.setAttribute('aria-label','图片处理前后对比');
 const comparisonHead=make('div','image-comparison-head'),comparisonTitle=make('strong'),comparisonClose=make('button','','关闭');comparisonClose.type='button';comparisonClose.setAttribute('aria-label','关闭图片对比');comparisonClose.onclick=()=>comparisonDialog.close();comparisonHead.append(comparisonTitle,comparisonClose);
 const comparisonReference=make('label','image-comparison-reference','对比来源'),comparisonSelect=make('select');comparisonSelect.setAttribute('aria-label','对比来源图片');comparisonReference.append(comparisonSelect);
 const comparisonStage=make('div','image-comparison-stage'),comparisonFooter=make('div','image-comparison-footer'),comparisonModes=make('div','image-comparison-modes'),comparisonPair=make('button','','并排'),comparisonWipe=make('button','','滑动对比'),comparisonRange=make('input'),comparisonMessage=make('p','image-comparison-message'),comparisonReceipt=make('p','image-comparison-receipt'),comparisonRetry=make('button','','重试原图');
 comparisonStage.id='imageComparisonStage';comparisonMessage.setAttribute('role','status');comparisonPair.type=comparisonWipe.type='button';comparisonRange.type='range';comparisonRange.min='0';comparisonRange.max='100';comparisonRange.value='50';comparisonRange.setAttribute('aria-label','处理前画面显示比例');comparisonModes.append(comparisonPair,comparisonWipe);comparisonRetry.type='button';comparisonRetry.hidden=true;comparisonRetry.onclick=()=>loadComparison();comparisonFooter.append(comparisonModes,comparisonRange,comparisonRetry,comparisonMessage);comparisonDialog.append(comparisonHead,comparisonReference,comparisonReceipt,comparisonStage,comparisonFooter);document.body.append(comparisonDialog);
 let comparison=null,comparisonPointer=null;
 const comparisonSources=asset=>[...new Set(project?.canvas_lineage?.[asset]?.sources||[])].filter(id=>id!==asset&&project?.canvas_assets?.[id]?.kind==='image');
 function releaseComparison(){if(!comparison)return;comparison.controller?.abort();for(const url of comparison.urls)URL.revokeObjectURL(url);comparison.urls=[];comparison.images=null;comparisonPointer=null}
 comparisonDialog.addEventListener('close',()=>{if(comparisonDialog.open)return;releaseComparison();comparison=null;comparisonStage.replaceChildren()});
 function sizeComparison(){if(!comparison?.images||comparison.mode!=='wipe')return;const surface=comparisonStage.firstElementChild;if(!surface)return;const ratio=comparison.images[0].naturalWidth/comparison.images[0].naturalHeight,w=Math.min(comparisonStage.clientWidth,comparisonStage.clientHeight*ratio);surface.style.width=w+'px';surface.style.height=w/ratio+'px'}
 new ResizeObserver(sizeComparison).observe(comparisonStage);
 function moveComparison(){const amount=Number(comparisonRange.value);comparisonRange.setAttribute('aria-valuetext',`处理前 ${amount}% · 处理后 ${100-amount}%`);comparisonStage.style.setProperty('--comparison-before',amount+'%')}
 function renderComparison(){
  comparisonStage.dataset.quality=comparison?.quality||'loading';
  const ready=!!comparison?.images,aligned=ready&&comparison.aligned;comparisonPair.disabled=!ready;comparisonWipe.disabled=!aligned;comparisonRange.disabled=!ready;comparisonRange.hidden=!ready||comparison.mode!=='wipe';comparisonPair.setAttribute('aria-pressed',String(comparison?.mode==='pair'));comparisonWipe.setAttribute('aria-pressed',String(comparison?.mode==='wipe'));if(!ready)return;
  const surface=make('div','image-comparison-surface '+(comparison.mode==='wipe'?'is-wipe':'is-pair'));const names=['处理前 · '+comparisonSelect.selectedOptions[0].textContent,'处理后 · '+comparison.title];comparison.images.forEach((img,index)=>{const figure=make('figure',index?'comparison-after':'comparison-before'),caption=make('figcaption','',names[index]+` · ${comparison.quality==='source'?'原图':'预览'} ${img.naturalWidth} × ${img.naturalHeight}`);figure.append(img,caption);surface.append(figure)});if(comparison.mode==='wipe')surface.append(make('span','comparison-divider'));
  comparisonStage.replaceChildren(surface);comparisonMessage.textContent=(comparison.quality==='source'?'原图已加载 · 可核对纹理细节。':comparison.sourceFailed?'预览图 · 原图加载失败，可重试；预览不能用于核对精细纹理。':'预览图 · 正在加载原图，可先比较构图与光线。')+(aligned?'':' 两图画幅不同，使用并排对比。');moveComparison();sizeComparison();
 }
 async function loadComparison(){
  if(!comparison)return;releaseComparison();const current=comparison,controller=new AbortController();current.controller=controller;current.mode='pair';current.quality='loading';current.sourceFailed=false;comparisonRetry.hidden=true;renderComparison();comparisonStage.replaceChildren(make('p','comparison-loading','正在读取图片预览…'));comparisonMessage.textContent='';
  const valid=()=>comparison===current&&current.controller===controller&&!controller.signal.aborted&&comparisonDialog.open;
  const ids=[comparisonSelect.value,current.result];
  async function readPair(view,timeout){
   const localUrls=[],pairController=new AbortController();
   try{
    const signal=AbortSignal.any([controller.signal,pairController.signal,AbortSignal.timeout(timeout)]);
    const images=await Promise.all(ids.map(async (id,index)=>{
     const r=await fetch(`/creative/api/projects/${current.project}/canvas/assets/${id}/${view}`,{headers:{Authorization:'Bearer '+key},signal});if(!r.ok)throw Error('图片暂不可读取');const blob=await r.blob();if(!blob.type.startsWith('image/'))throw Error('素材不是可显示的图片');
     if(!valid()||signal.aborted)throw Error('cancelled');const img=make('img');img.alt=index?'处理后的图片':'处理前的来源图片';const url=URL.createObjectURL(blob);localUrls.push(url);img.src=url;await img.decode();return img;
    }));
    if(!valid())throw Error('cancelled');
    const previous=current.urls;current.urls=localUrls;current.images=images;current.quality=view==='source'?'source':'preview';current.aligned=Math.abs(images[0].naturalWidth/images[0].naturalHeight-images[1].naturalWidth/images[1].naturalHeight)<(view==='source'?.001:.003);if(!current.aligned)current.mode='pair';renderComparison();previous.forEach(URL.revokeObjectURL);
   }catch(e){pairController.abort();localUrls.forEach(URL.revokeObjectURL);throw e}
  }
  try{await readPair('preview',15000)}catch{if(!valid())return;comparisonStage.replaceChildren(make('p','comparison-loading','预览暂不可用，正在读取原图…'))}
  if(!valid())return;
  try{await readPair('source',60000)}catch{
   if(!valid())return;current.sourceFailed=true;comparisonRetry.hidden=false;
   if(current.images)renderComparison();else{current.quality='error';renderComparison();comparisonStage.replaceChildren(make('p','','图片读取失败，原素材保持不变。'));comparisonMessage.textContent='重试仅重新读取文件，不发起生成。'}
  }
 }
 function adjustmentSummary(origin){const c=origin?.control_parameters;if(c?.kind==='angle')return `${c.preset} · 水平 ${c.yaw}° · 俯仰 ${c.pitch}° · 景别 ${c.zoom}%`;if(c?.kind==='light')return `${c.preset} · 方向 ${c.direction}° · 仰角 ${c.elevation}° · 强度 ${c.intensity}% · 色温 ${c.temperature}K`;const a=origin?.adjustments;if(!a)return '';return [['angle','视角','保留原角度'],['light','光照','保留原光照']].filter(([key,,fallback])=>a[key]&&a[key]!==fallback).map(([key,label])=>label+'：'+a[key]).join(' · ')}
 function showComparison(asset){const sources=comparisonSources(asset);if(!sources.length)return;releaseComparison();comparison={project:pid,result:asset,title:graph.nodes.find(n=>n.asset===asset)?.label||'处理结果',urls:[],images:null,mode:'pair'};comparisonTitle.textContent='处理前后对比 · '+comparison.title;comparisonSelect.replaceChildren();sources.forEach((id,index)=>{const option=make('option','',graph.nodes.find(n=>n.asset===id)?.label||`来源图片 ${index+1}`);option.value=id;comparisonSelect.append(option)});comparisonSelect.disabled=sources.length<2;const origin=project.canvas_lineage[asset];comparisonReceipt.textContent=origin.region_edit?'局部修改结果 · 选区外像素保留记录；请核对选区内容与边缘衔接。':adjustmentSummary(origin)?'生成参数 · '+adjustmentSummary(origin):origin.reframe?'裁剪 / 旋转结果 · 比较构图与商品完整性。':'对照实际来源素材，检查生成结果是否符合要求。';comparisonRange.value='50';if(!comparisonDialog.open)comparisonDialog.showModal();loadComparison()}
 comparisonSelect.onchange=loadComparison;comparisonPair.onclick=()=>{if(comparison?.images){comparison.mode='pair';renderComparison()}};comparisonWipe.onclick=()=>{if(comparison?.aligned){comparison.mode='wipe';renderComparison();comparisonRange.focus({preventScroll:true})}};comparisonRange.oninput=moveComparison;
 const slideComparison=e=>{const surface=comparisonStage.firstElementChild;if(!surface)return;const r=surface.getBoundingClientRect();comparisonRange.value=String(Math.round(Math.max(0,Math.min(100,(e.clientX-r.left)/r.width*100))));moveComparison()};
 comparisonStage.onpointerdown=e=>{if(e.button!==0||comparison?.mode!=='wipe'||comparisonPointer!==null)return;e.preventDefault();comparisonPointer=e.pointerId;comparisonStage.setPointerCapture(e.pointerId);slideComparison(e)};comparisonStage.onpointermove=e=>{if(e.pointerId===comparisonPointer)slideComparison(e)};comparisonStage.onpointerup=comparisonStage.onpointercancel=comparisonStage.onlostpointercapture=()=>comparisonPointer=null;

 function paint(){manualResultResize.disconnect();const reopenAsset=openAssetId;world.querySelectorAll('.reference-node video,.reference-node audio').forEach(v=>{v.pause();v.removeAttribute('src');v.load()});world.querySelectorAll('.reference-node').forEach(e=>e.remove());empty.hidden=!!graph.nodes.length;
  for(const n of graph.nodes){const connected=graph.edges.some(e=>e.source===n.id),card=make('section','canvas-card reference-node'+(connected?' connected':''));card.dataset.nodeId=n.id;card.dataset.kind=mediaKind(n);card.classList.toggle('edited-video-result',mediaKind(n)==='video'&&project?.canvas_lineage?.[n.asset]?.kind==='video_edit');card.classList.toggle('manual-primary-result',project?.creation_mode==='video'&&mediaKind(n)==='video'&&!!project.artifact&&!!project.result_asset&&n.asset===project.result_asset&&project.result_artifact===project.artifact);card.classList.toggle('generated-primary-result',mediaKind(n)==='video'&&!!project?.artifact&&n.asset===project.result_asset&&project.result_artifact===project.artifact);card.classList.toggle('manual-root-result',card.classList.contains('manual-primary-result')||(project?.creation_mode==='image'&&project.image_task?.state==='completed'&&n.asset===project.image_task.asset));card.style.left=n.x+'px';card.style.top=n.y+'px';
   const head=make('div','canvas-card-head'),nodeType=mediaKind(n),kind={text:'文字参考',image:'图片参考',video:'视频参考',audio:'音轨'}[nodeType];const cardTitle=make('strong','',n.label||kind);cardTitle.title=n.label||kind;head.append(cardTitle);if(n.asset&&['image','video','audio'].includes(nodeType)){const spec=make('span','canvas-media-spec');head.append(spec);sourceSpec(n.asset,spec)}const focusCard=make('button','','聚焦');focusCard.className='node-focus';focusCard.setAttribute('aria-label','聚焦素材');focusCard.onclick=()=>focusNode(card);head.append(focusCard);const remove=make('button','','×');remove.setAttribute('aria-label','删除'+kind);remove.onclick=()=>{graph.nodes=graph.nodes.filter(v=>v.id!==n.id);graph.edges=graph.edges.filter(e=>e.source!==n.id);if(tracing===n.id)tracing=null;change();paint()};head.append(remove);
   const body=make('div','canvas-card-body'),label=make('input');label.value=n.label;label.placeholder='给参考起个名字';label.maxLength=80;label.setAttribute('aria-label','参考名称');label.oninput=()=>{n.label=label.value;cardTitle.textContent=n.label||kind;cardTitle.title=n.label||kind;const panelTitle=card.querySelector('.asset-tools-title');if(panelTitle)panelTitle.textContent=n.label||kind;change(n.id+':label')};label.onblur=()=>historyMergeKey=null;body.append(label);
   const role=make('select','node-role');role.setAttribute('aria-label','参考用途');for(const [value,text] of Object.entries(roles)){const option=make('option','',text);option.value=value;role.append(option)}role.value=n.role||'reference';role.onchange=()=>{n.role=role.value;const badge=card.querySelector('.text-note-role');if(badge)badge.textContent=roles[n.role];change()};body.append(role);
   if(n.asset){const origin=project?.canvas_lineage?.[n.asset]||{kind:'uploaded',sources:[]},info=make('div','node-origin');info.append(make('span','',{audio_split:'音视频分离',video_frame:'视频取帧',image_reframe:'裁剪版本',image_composite:'多参考合成',image_edit:'原图调整',image_generated:'生成图',scene_browser_preview:'3D 预演',video_edit:'剪辑成片',edit_source:'剪辑原素材',uploaded:'导入素材'}[origin.kind]||'来源记录'));if(origin.sources.length){const trace=make('button','trace-source',tracing===n.id?'显示全部':'追溯来源');trace.onclick=()=>{tracing=tracing===n.id?null:n.id;paint()};info.append(trace);for(const aid of origin.sources)if(!graph.nodes.some(v=>v.asset===aid)){const restore=make('button','restore-source','放回来源');restore.onclick=()=>restoreSource(aid,n.role||'reference');info.append(restore)}}else if(origin.reference_id)info.append(make('span','',' · 商品参考版本'));body.append(info);if(origin.inputs?.length){const d=make('details','image-input-provenance');d.append(make('summary','','实际图片输入 · '+origin.inputs.length+' 张'));origin.inputs.forEach((v,i)=>d.append(make('p','',`图 ${i+1} · ${roles[v.role]||'其他参考'} · ${graph.nodes.find(n=>n.asset===v.asset)?.label||'来源图片'}${v.instruction?'：'+v.instruction:''}`)));body.append(d)}if(origin.kind==='video_frame'&&Number.isFinite(origin.source_time))body.append(make('p','',`来源视频时间：${origin.source_time.toFixed(2)} 秒`));if(origin.clips?.length){const details=make('details','clip-provenance'),summary=make('summary','','来源片段 · '+origin.clips.length+' 段');details.append(summary);origin.clips.forEach((c,i)=>details.append(make('p','',`${i+1}. ${graph.nodes.find(v=>v.asset===c.asset)?.label||'来源素材'} · ${c.start.toFixed(2)}–${c.end.toFixed(2)}s → 成片 ${c.at.toFixed(2)}s`)));body.append(details)}}

   if(n.asset&&nodeType!=='audio'){const img=make('img'),message=make('div','media-preview-message');img.alt=n.label||kind;img.previewMessage=message;message.setAttribute('role','status');body.append(img,message);thumbnail(n.asset,img);const origin=project?.canvas_lineage?.[n.asset],sourceId=origin?.sources?.find(aid=>project?.canvas_assets?.[aid]?.kind==='image'),sourceAsset=sourceId&&project?.canvas_assets?.[sourceId];if(mediaKind(n)==='image'&&sourceAsset){const compare=make('details','image-compare'),summary=make('summary','','处理前后对比'),grid=make('div','image-compare-grid'),before=make('figure','image-compare-item'),after=make('figure','image-compare-item'),beforeImg=make('img'),afterImg=make('img');beforeImg.alt='处理前参考图';afterImg.alt='处理后参考图';before.append(beforeImg,make('figcaption','', '处理前'));after.append(afterImg,make('figcaption','', '处理后'));grid.append(before,after);compare.append(summary,grid);const largeCompare=make('button','','打开大图对比');largeCompare.type='button';largeCompare.onclick=()=>showComparison(n.asset);compare.append(largeCompare);if(origin?.reframe){const r=origin.reframe;compare.append(make('p','image-reframe-receipt',`裁剪结果 ${r.result_dimensions?.join(' × ')||'—'} 像素 · 顺时针 ${r.rotation||0}°${r.mirror?' · 水平镜像':''}`))}if(adjustmentSummary(origin))compare.append(make('p','image-compare-adjustments','生成参数 · '+adjustmentSummary(origin)));const draft=origin?.transform_draft_id&&project?.image_transform_drafts?.[origin.transform_draft_id];if(draft){const observation=draft.result_observation||origin.transform_alignment;const state=observation?.status==='changed_observed'?'已生成结果 · 像素变化已观察 · 仍需人工核对':observation?.status==='unchanged'?'已生成结果 · 像素未变化 · 需要重新核对':observation?.status==='decode_failed'?'结果待核对 · 像素观察失败':draft.result_state==='available'&&draft.result_asset===n.asset?'已生成结果 · 参数已绑定 · 等待像素观察':draft.result_state==='needs_review'?'结果待核对 · 不会自动重试':'已绑定变换草稿 · 等待结果核对';compare.append(make('p','image-compare-draft',state))}if(origin?.region_edit)compare.append(make('p','image-region-receipt',`${origin.region_edit.shape==='brush'?'手绘选区修改':'矩形局部修改'} · 原图 ${origin.region_edit.dimensions.join(' × ')} · 范围 (${origin.region_edit.box.join(', ')}) · 选区外像素保留；内容与衔接待核对`));body.append(compare);thumbnail(sourceId,beforeImg);thumbnail(n.asset,afterImg)}if(mediaKind(n)==='video'){const actions=make('div','video-actions');const play=make('button','','播放视频');play.onclick=async()=>{play.disabled=true;try{const r=await fetch(`/creative/api/projects/${pid}/canvas/assets/${n.asset}/source`,{headers:{Authorization:'Bearer '+key}});if(!r.ok)throw Error();const u=URL.createObjectURL(await r.blob());if(!img.isConnected){URL.revokeObjectURL(u);return}const v=make('video');v.controls=true;v.playsInline=true;v.src=u;v.tabIndex=0;v.setAttribute('aria-label','选择素材 '+(n.label||kind));v.onclick=()=>selectMedia(n.id,true);v.onfocus=()=>selectMedia(n.id,true);v.onloadedmetadata=()=>{restorePlayback(v,videoPositions.get(n.asset));spaceNodes()};v.addEventListener('error',()=>toast('视频暂不可播放'));v.addEventListener('emptied',()=>URL.revokeObjectURL(u),{once:true});img.replaceWith(v);play.remove();await v.play();spaceNodes()}catch{toast('视频暂不可播放')}finally{play.disabled=false}};const edit=make('a','','打开剪辑 ↗');edit.href='/creative/editor?'+new URLSearchParams({project:pid,source:'canvas_'+n.asset});const inline=make('button','','内嵌定位');inline.className='canvas-inline-video-edit';inline.setAttribute('aria-label','内嵌剪辑定位视频');inline.title='在当前画布内打开剪辑并选中这个视频素材';inline.onclick=()=>document.dispatchEvent(new CustomEvent('creative-open-inline-edit',{detail:{source:'canvas_'+n.asset,canvasAsset:n.asset}}));actions.append(play,inline,edit);body.append(actions);const quick=make('div','canvas-quick-media-tools');const quickButton=(label,run,key,disabled=false)=>{const b=make('button','',label);b.type='button';b.dataset.mediaAction=key;b.disabled=disabled;b.onclick=e=>{e.stopPropagation();selectMedia(n.id,true);run()};quick.append(b);return b};quickButton('智能剪辑',()=>openVideoTool('assistant'),'assistant');quickButton('内嵌剪辑',()=>inline.click(),'inline');quickButton('独立剪辑',()=>edit.click(),'editor');quickButton('逐帧拉片',()=>{},'pending-film',true).title='暂无可用处理模型';quickButton('智能去字幕',()=>{},'pending-caption',true).title='暂无可用处理模型';body.append(quick)}}
   if(n.asset&&nodeType==='audio'){
    const audio=make('audio','canvas-audio-player');audio.controls=true;audio.preload='none';audio.hidden=true;audio.setAttribute('aria-label',n.label||'分离音轨');
    const audioStatus=make('div','canvas-audio-status');audioStatus.setAttribute('role','status');audioStatus.hidden=true;
    const load=make('button','canvas-audio-load','播放音轨');load.type='button';load.onclick=async()=>{if(load.disabled)return;load.disabled=true;load.textContent='正在加载…';audioStatus.hidden=false;audioStatus.textContent='正在加载音轨';const ownerPid=pid;try{const response=await fetch(`/creative/api/projects/${ownerPid}/canvas/assets/${n.asset}/source`,{headers:{Authorization:'Bearer '+key},signal:AbortSignal.timeout(60000)});if(!response.ok)throw Error();const url=URL.createObjectURL(await response.blob());if(!audio.isConnected||pid!==ownerPid){URL.revokeObjectURL(url);return}audio.src=url;audio.addEventListener('emptied',()=>URL.revokeObjectURL(url),{once:true});audio.hidden=false;await audio.play();load.hidden=true;audioStatus.hidden=true;spaceNodes()}catch{if(audio.isConnected&&pid===ownerPid){audio.hidden=!audio.readyState;audioStatus.textContent='音轨暂不可播放，请重试';load.textContent='重试播放'}}finally{load.disabled=false;if(load.hidden)load.textContent='播放音轨'}};
    const edit=make('button','canvas-audio-edit','音轨剪辑');edit.type='button';edit.setAttribute('aria-label','剪辑音轨 '+(n.label||'分离音轨'));edit.onclick=e=>{e.stopPropagation();selectMedia(n.id,true);audio.pause();openVideoTool('audio')};
    const actions=make('div','canvas-quick-media-tools');actions.append(load,edit);
    body.append(make('div','canvas-audio-cover','♫'),audio,audioStatus,actions);
   }
   const input=make('textarea');input.value=n.text;input.maxLength=4000;input.placeholder=n.kind==='text'?'产品特点、受众、想法或脚本…':'希望参考它的什么？例如色调、构图或场景';input.setAttribute('aria-label','参考内容');input.oninput=()=>{n.text=input.value;const reading=card.querySelector('.text-note-reading');if(reading){reading.textContent=n.text||'写下想法、产品事实或拍摄要求…';reading.classList.toggle('is-empty',!n.text)}change(n.id+':text')};input.onblur=()=>historyMergeKey=null;body.append(input);
   const connect=make('button','connect-reference',connected?'已连接导演 · 点击断开':'连接到导演');connect.disabled=nodeType==='audio';if(nodeType==='audio'){connect.textContent='音轨理解尚未接入';connect.title='音轨支持播放、下载；暂不作为导演输入'}connect.onclick=()=>{graph.edges=graph.edges.filter(e=>e.source!==n.id);if(!connected)graph.edges.push({source:n.id,target:'director'});change();paint()};body.append(connect);if(mediaKind(n)==='image'&&n.asset){const use=make('button','use-product-reference','设为商品参考');use.onclick=async()=>{if(locked())return;if(dirty||oldHasDrafts()){toast('请先保存或放弃草稿，再设置商品参考');return}setBusy(true);try{project=await api('/projects/'+project.id+'/reference?revision='+project.revision+'&source_asset='+n.asset,'POST');clearMedia();draw();await seek(0);toast('已设为视频商品参考，请重新规划')}catch(e){toast(e.message)}finally{setBusy(false)}};body.append(use)}card.append(head,body);world.append(card);if(card.classList.contains('manual-root-result'))manualResultResize.observe(card);
   if(mediaKind(n)==='image'&&n.asset){const combine=make('button','compose-reference','用此图组合生成');combine.onclick=()=>composeImage(n.asset);body.append(combine)}
   if(n.asset&&mediaKind(n)==='image'){
    const editTools=make('div','canvas-image-edit-actions');
    const angle=make('button','', '多角度编辑器');angle.type='button';angle.setAttribute('aria-label','打开多角度编辑器');angle.onclick=()=>adjustImage('angle',n.asset);
    const light=make('button','', '重打光');light.type='button';light.setAttribute('aria-label','打开重打光编辑器');light.onclick=()=>adjustImage('light',n.asset);
    editTools.append(angle,light);body.append(editTools);const quick=make('div','canvas-quick-media-tools');const quickButton=(label,run,key,disabled=false)=>{const b=make('button','',label);b.type='button';b.dataset.mediaAction=key;b.disabled=disabled;b.onclick=e=>{e.stopPropagation();selectMedia(n.id,true);run()};quick.append(b);return b};quickButton('修改图片',()=>document.dispatchEvent(new CustomEvent('creative-edit-image',{detail:{asset:n.asset}})),'edit');quickButton('局部修改',()=>composeImage(n.asset,true),'region');quickButton('多角度',()=>adjustImage('angle',n.asset),'adjust');quickButton('重打光',()=>adjustImage('light',n.asset),'light');quickButton('高清',()=>{},'pending-hd',true).title='尚未接入处理模型';body.append(quick);
   }
   if(n.asset){
    card.classList.add('media-reference');head.prepend(mediaIcon(n.kind));focusCard.replaceChildren(mediaIcon('preview'));focusCard.title='聚焦素材';
    const panel=make('div','asset-tools-panel');panel.id='asset-tools-'+n.id;panel.setAttribute('popover','auto');panel.setAttribute('role','region');panel.setAttribute('aria-label',kind+'编辑');
    const panelHead=make('div','asset-tools-head'),panelTitle=make('strong','asset-tools-title',n.label||kind),close=make('button','asset-tools-close','关闭');close.type='button';close.setAttribute('aria-label','关闭素材编辑');
    const toggle=make('button','asset-tools-toggle','编辑');toggle.type='button';toggle.setAttribute('aria-label','编辑素材');toggle.setAttribute('aria-controls',panel.id);toggle.setAttribute('aria-expanded','false');
    toggle.replaceChildren(mediaIcon('details'));toggle.title='编辑素材';toggle.popoverTargetElement=panel;toggle.popoverTargetAction='toggle';close.onclick=()=>{panel.hidePopover();toggle.focus()};
    panelHead.append(panelTitle,close);panel.append(panelHead);body.append(panel);head.append(toggle);remove.textContent='移除素材';remove.classList.add('asset-remove');panel.append(remove);
    panel.addEventListener('beforetoggle',event=>{if(!card.isConnected)return;const opened=event.newState==='open';if(opened&&innerWidth>900){const r=card.getBoundingClientRect(),chat=document.querySelector('.director'),chatLeft=chat&&getComputedStyle(chat).display!=='none'?chat.getBoundingClientRect().left:innerWidth,rightLimit=Math.min(innerWidth-12,chatLeft-12);const width=Math.min(340,innerWidth-24);panel.style.setProperty('--asset-panel-left',(r.right+12+width<=rightLimit?r.right+12:r.left-width-12>=12?r.left-width-12:20)+'px')}else panel.style.removeProperty('--asset-panel-left');toggle.setAttribute('aria-expanded',String(opened));card.classList.toggle('asset-selected',opened);if(opened){openAssetId=n.id;selectMedia(n.id)}else if(openAssetId===n.id)openAssetId=null});
   }
   if(n.asset){const thumbnail=body.querySelector(':scope>img');if(thumbnail){if(mediaKind(n)==='image'){thumbnail.title='双击查看大图';thumbnail.onclick=()=>selectMedia(n.id,true);thumbnail.ondblclick=()=>showImage(n.id)}else{thumbnail.title='双击放大播放';thumbnail.onclick=()=>selectMedia(n.id,true);thumbnail.ondblclick=()=>{selectMedia(n.id);showVideo()};const preview=make('button','canvas-video-preview-button','▶');preview.type='button';preview.setAttribute('aria-label','预览视频 '+(n.label||kind));preview.title='放大播放视频';preview.onclick=e=>{e.stopPropagation();selectMedia(n.id);showVideo()};body.append(preview)}thumbnail.tabIndex=0;thumbnail.setAttribute('role','button');thumbnail.setAttribute('aria-label','选择素材 '+(n.label||kind));thumbnail.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();if(e.shiftKey||selectionMode)selectNode(n.id);else selectMedia(n.id,true)}}}
    // Keep double-click zoom reliable even when the click lands on the media
    // card wrapper or a non-interactive overlay. Single click still only selects.
    card.addEventListener('dblclick',e=>{if(e.target.closest('img,button,a,input,textarea,select,summary,details,video,audio,[popover]'))return;if(!e.target.closest('.canvas-card-body'))return;e.preventDefault();e.stopPropagation();selectMedia(n.id,true);if(mediaKind(n)==='image')showImage(n.id);else if(mediaKind(n)==='video')showVideo()});
    const selectFromMedia=e=>{if(e.target.closest('.canvas-card-body img,.canvas-card-body video,.canvas-card-body audio,.canvas-card-head'))selectMedia(n.id,true)};card.addEventListener('pointerdown',selectFromMedia,true);card.addEventListener('click',selectFromMedia);card.addEventListener('focusin',selectFromMedia);card.addEventListener('play',queueMediaTools,true);card.addEventListener('pause',queueMediaTools,true)}
   if(n.kind==='text'){
    card.classList.add('text-reference');const meta=make('div','text-note-meta'),badge=make('span','text-note-role',roles[n.role]||'其他参考'),link=make('span','text-note-link',connected?'已连接导演':'未连接导演'),reading=make('div','text-note-reading',n.text||'写下想法、产品事实或拍摄要求…');reading.classList.toggle('is-empty',!n.text);meta.append(badge,link);body.prepend(meta,reading);
    reading.title='双击编辑文字';reading.ondblclick=()=>{const editor=body.querySelector('.text-note-editor');if(editor){editor.open=true;requestAnimationFrame(()=>input.focus())}};
   }
   if(n.kind==='text'){head.tabIndex=0;head.setAttribute('role','button');head.setAttribute('aria-label','选择文字素材 '+(n.label||kind));head.onclick=e=>{if(!e.shiftKey&&!selectionMode&&(e.target===head||e.target===cardTitle))selectNode(n.id,false)};head.onkeydown=e=>{if(e.target===head&&(e.key==='Enter'||e.key===' ')){e.preventDefault();selectNode(n.id,e.shiftKey||selectionMode)}}}
   head.onpointerdown=e=>startNodeDrag(e,n,head);
   if(mediaKind(n)==='image'||mediaKind(n)==='video'){
    for(const img of body.querySelectorAll('img'))img.draggable=false;
    body.onpointerdown=e=>{if(e.target.closest('button,a,input,textarea,select,summary,details,video,[popover]'))return;startNodeDrag(e,n,body)};
   }
  }alignOutput();lines();updateStatus();document.dispatchEvent(new Event('creative-canvas-painted'));spaceNodes();const restorePanel=reopenAsset&&world.querySelector('#asset-tools-'+CSS.escape(reopenAsset));if(restorePanel){restorePanel.showPopover();openAssetId=reopenAsset}else openAssetId=null;if(requestedCanvasAsset){const match=graph.nodes.find(node=>node.asset===requestedCanvasAsset),target=match&&world.querySelector(`.reference-node[data-node-id="${CSS.escape(match.id)}"]`);if(target){focusNode(target);target.classList.add('canvas-return-focus');toast('已回到画布素材 · 可继续核对对应剪辑')}requestedCanvasAsset=''}
 }
 // Avoid old/expanded card collisions in the view; explicit layout/save owns coordinates.
 function spaceNodes(){
  if(canvasGesture)return;
  for(const card of world.querySelectorAll('.reference-node')){
   const body=card.querySelector('.canvas-card-body'),nid=card.dataset.nodeId;
   const wrap=(key,title,children)=>{const existing=body.querySelector('.'+key);if(existing){existing.append(...children);return}if(!children.length)return;const d=make('details',key),summary=make('summary','',title);d.append(summary,...children);d.open=sectionStates.get(nid+key)||false;d.addEventListener('beforetoggle',event=>{if(!card.isConnected)return;if(key==='text-note-editor'&&d.hasAttribute('popover')&&event.newState==='closed')d.open=false});d.addEventListener('toggle',()=>{if(!card.isConnected)return;sectionStates.set(nid+key,d.open);if(key==='text-note-editor'){if(d.open&&innerWidth<=900){d.setAttribute('popover','auto');if(!d.matches(':popover-open'))d.showPopover()}else if(!d.open&&d.hasAttribute('popover')){d.hidePopover();d.removeAttribute('popover')}}spaceNodes()});body.append(d)};
   if(card.dataset.kind==='text')wrap('text-note-editor','编辑文字与连接',[...body.children].filter(e=>e.matches('input,.node-role,textarea,.connect-reference')));
   if(card.querySelector('img,audio'))wrap('reference-options','参考说明与连接',[...body.children].filter(e=>e.matches('input,.node-role,textarea,.connect-reference,.use-product-reference')));
   wrap('generation-options','生成与图像处理',[...body.children].filter(e=>e.matches('.node-image-controls,.image-transforms,.compose-reference,.image-compare')));
   const panel=body.querySelector('.asset-tools-panel');if(panel){
    for(const section of [...body.children].filter(e=>e.matches('.reference-options,.generation-options,.image-input-provenance,.clip-provenance,.node-origin,.video-actions')))panel.insertBefore(section,panel.querySelector('.asset-remove'));
    const generation=panel.querySelector('.generation-options');if(generation&&!sectionStates.has(nid+'generation-options'))generation.open=true;
   }

  }
  // Independent generation cards share the same world coordinates. Reserve their
  // rendered bounds before placing references and derived media.
  const occupied=[...world.querySelectorAll('.manual-generation-node')].filter(card=>card.offsetWidth&&card.offsetHeight).map(card=>({x:card.offsetLeft,y:card.offsetTop,w:card.offsetWidth,h:card.offsetHeight}));
  for(const card of world.querySelectorAll('.reference-node')){
   const n=graph.nodes.find(n=>n.id===card.dataset.nodeId);if(!n)continue;let x=n.x,y=n.y;const w=card.offsetWidth,h=card.offsetHeight;
   for(let i=0;i<32;i++){const hit=occupied.find(b=>x<b.x+b.w+24&&x+w+24>b.x&&y<b.y+b.h+24&&y+h+24>b.y);if(!hit)break;y=hit.y+hit.h+36;if(y+h>9500){x+=310;y=30}}
   card.style.left=x+'px';card.style.top=y+'px';occupied.push({x,y,w,h});
  }
  alignOutput();lines();const selected=world.querySelector('.reference-node[style*="z-index: 2"]');if(selected)focusNode(selected);else if(!dirty&&!openAssetId&&!cameraTouched&&!panGesture)fit()
 }
 document.addEventListener('creative-node-controls-ready',spaceNodes);
 document.addEventListener('creative-fit-canvas',()=>{spaceNodes();fit()});
 document.addEventListener('creative-inline-timeline',event=>{const data=event.detail||{},asset=String(data.source_id||'').replace(/^canvas_/,'');world.querySelectorAll('.canvas-timeline-focus').forEach(value=>value.classList.remove('canvas-timeline-focus'));world.querySelectorAll('.canvas-timeline-badge').forEach(value=>value.remove());if(!asset)return;const node=graph.nodes.find(value=>value.asset===asset),card=node&&world.querySelector(`.reference-node[data-node-id="${CSS.escape(node.id)}"]`);if(!card)return;card.classList.add('canvas-timeline-focus');const transition=data.transition_kind&&data.transition_kind!=='cut'?` · ${data.transition_kind==='dissolve'?'叠化':'淡黑'} ${Number(data.transition_duration||0).toFixed(2)}s`:'';const badge=make('span','canvas-timeline-badge');badge.textContent=`剪辑游标 ${Number(data.at||0).toFixed(2)}s${transition}`;badge.title=`只读核对 · 片段 ${Number(data.clip_start||0).toFixed(2)}–${Number(data.clip_end||0).toFixed(2)}s${transition}`;badge.setAttribute('aria-label',badge.title);card.querySelector('.canvas-card-head')?.append(badge)});
 function position(){for(let i=0;i<64;i++){const x=40+Math.floor(i/4)*310,y=30+(i%4)*900;if(!graph.nodes.some(n=>Math.abs(n.x-x)<290&&Math.abs(n.y-y)<850))return{x,y}}return{x:7000,y:30}}
 function addText(at=null){if(locked())return;if(graph.nodes.length>=16){toast('每个画布最多 16 个参考');return}const id='n'+Array.from(crypto.getRandomValues(new Uint8Array(16)),v=>v.toString(16).padStart(2,'0')).join('');graph.nodes.push({id,kind:'text',role:'story',label:'创作想法',text:'',...(at||position())});graph.edges.push({source:id,target:'director'});change();paint();const card=world.querySelector('[data-node-id="'+CSS.escape(id)+'"]'),editor=card?.querySelector('.text-note-editor');if(editor){editor.open=true;requestAnimationFrame(()=>card.querySelector('textarea')?.focus({preventScroll:true}))}}
 const importButton=button('导入素材',()=>importPanel.togglePopover());importButton.id='canvasImportStatus';importButton.hidden=true;importButton.setAttribute('aria-live','polite');
 const importPanel=make('section','canvas-import-panel');importPanel.id='canvasImportPanel';importPanel.setAttribute('popover','auto');importPanel.setAttribute('aria-label','素材导入进度');importButton.setAttribute('aria-controls',importPanel.id);importButton.setAttribute('aria-expanded','false');
 const importHead=make('div','canvas-import-head'),importTitle=make('strong','','素材导入'),importClose=make('button','','关闭'),importList=make('ol','canvas-import-list'),importHint=make('p','canvas-import-hint','成功的素材会加入画布草稿，保存参考后保留。'),importStop=make('button','','停止后续上传');importClose.type=importStop.type='button';importClose.onclick=()=>importPanel.hidePopover();importHead.append(importTitle,importClose);importPanel.append(importHead,importList,importHint,importStop);viewport.append(importPanel);importPanel.addEventListener('toggle',()=>importButton.setAttribute('aria-expanded',String(importPanel.matches(':popover-open'))));let uploadRun=null;
 const dropHint=make('div','canvas-drop-hint','松开添加图片或视频');dropHint.hidden=true;viewport.append(dropHint);
 importStop.onclick=()=>{if(uploadRun){uploadRun.cancelled=true;importStop.disabled=true;importStop.textContent='当前文件结束后停止'}};
 function fileKind(file){if(/^image\/(png|jpeg|webp)$/.test(file.type)||(!file.type&&/\.(png|jpe?g|webp)$/i.test(file.name)))return 'image';if(/^video\/(mp4|quicktime)$/.test(file.type)||(!file.type&&/\.(mp4|mov)$/i.test(file.name)))return 'video';return null}
 function renderImports(run){
  importButton.hidden=false;const finished=run.items.filter(v=>!['queued','uploading'].includes(v.state)).length;importButton.textContent=run.done?'导入结果 · '+run.items.filter(v=>v.state==='completed').length+'/'+run.items.length:'导入素材 · '+finished+'/'+run.items.length;importButton.setAttribute('aria-busy',String(!run.done));importButton.title='已导入 '+run.items.filter(v=>v.state==='completed').length+' · 失败 '+run.items.filter(v=>v.state==='failed').length+' · 跳过 '+run.items.filter(v=>v.state==='skipped').length;importTitle.textContent=run.done?(run.pid===project?.id?'素材导入结果':'原项目导入结果'):'正在导入素材';
  importList.replaceChildren();for(const item of run.items){const row=make('li'),name=make('strong','',item.file.name),state=make('span','',item.message||{queued:'等待上传',uploading:'上传与解析中…',completed:'已加入画布',failed:'上传失败',skipped:'未上传'}[item.state]);row.dataset.state=item.state;row.append(name,state);importList.append(row)}importStop.hidden=run.done;importStop.disabled=run.cancelled;
 }
 async function choose(kind,origin=null){if(locked())return;const owner=pid,input=make('input');input.type='file';input.multiple=true;input.accept=kind==='image'?'image/png,image/jpeg,image/webp':'video/mp4,video/quicktime';input.onchange=()=>{if(owner!==pid){toast('项目已切换，请在当前项目重新选择素材');return}importFiles([...input.files],origin)};input.click()}
 function arrangeImports(ids,origin=null){
  const cards=new Map(nodeCards().map(c=>[c.dataset.nodeId,c])),others=nodeCards().filter(c=>!ids.includes(c.dataset.nodeId)),occupied=others.map(c=>({x:c.offsetLeft,y:c.offsetTop,w:c.offsetWidth,h:c.offsetHeight}));
  const startX=origin?Math.min(7800,origin.x):others.length?Math.min(7800,Math.max(...others.map(c=>c.offsetLeft+c.offsetWidth))+54):40;let rowY=origin?.y??30,rowBottom=rowY;
  ids.forEach((id,i)=>{const n=graph.nodes.find(n=>n.id===id),card=cards.get(id);if(!n||!card)return;if(i&&i%3===0){rowY=rowBottom+54}let x=startX+(i%3)*310,y=rowY,w=card.offsetWidth,h=card.offsetHeight;
   for(let j=0;j<64;j++){const hit=occupied.find(b=>x<b.x+b.w+24&&x+w+24>b.x&&y<b.y+b.h+24&&y+h+24>b.y);if(!hit)break;y=hit.y+hit.h+36;if(y+h>9000){x=Math.max(40,x-310);y=30}}
   n.x=x;n.y=Math.min(9000-h,y);card.style.left=n.x+'px';card.style.top=n.y+'px';occupied.push({x:n.x,y:n.y,w,h});rowBottom=Math.max(rowBottom,n.y+h);
  });
 }
 async function importFiles(files,origin=null){
  if(!files.length)return;if(locked()){toast('当前正在制作或保存，请完成后再导入素材');return}if(dirty||oldHasDrafts()){toast('请先保存或放弃草稿，再上传素材');return}
  if(files.length>16-graph.nodes.length){toast('画布还可添加 '+(16-graph.nodes.length)+' 个素材，请减少选择');return}if(files.length>32-Object.keys(project.canvas_assets||{}).length){toast('项目参考文件空间不足，请减少选择');return}
  const run={pid,epoch:openEpoch,id:crypto.randomUUID(),origin,items:files.map(file=>({file,kind:fileKind(file),state:'queued'})),cancelled:false,done:false,ids:[]};uploadRun=run;saving=true;importStop.textContent='停止后续上传';renderImports(run);updateStatus();
  const current=()=>project?.id===run.pid&&openEpoch===run.epoch;
  try{for(const item of run.items){
   if(run.cancelled||!current()){item.state='skipped';item.message='未上传 · 队列已停止';renderImports(run);continue}
   if(!item.kind||!item.file.size||item.file.size>30*1024*1024){item.state='failed';item.message=!item.kind?'仅支持 PNG / JPEG / WebP / MP4 / MOV':!item.file.size?'文件为空':'文件超过 30 MB';renderImports(run);continue}
   item.state='uploading';renderImports(run);
   try{const response=await fetch(`/creative/api/projects/${run.pid}/canvas/assets?kind=${item.kind}&revision=${revision}`,{method:'POST',headers:{Authorization:'Bearer '+key},body:item.file,signal:AbortSignal.timeout(120000)});const data=await response.json().catch(()=>({}));
    if(!response.ok){const error=Error(typeof data.detail==='string'?data.detail:'上传未完成');error.stop=![413,422].includes(response.status);throw error}
    if(!current()){item.state='completed';item.message='文件已存入原项目，未加入当前画布';run.cancelled=true;renderImports(run);continue}
    if(data.project.revision>=project.revision)project=data.project;revision=data.project.revision;
    const id='n'+crypto.randomUUID().replaceAll('-',''),linked=new Set(graph.edges.map(e=>e.source)),connected=graph.nodes.filter(n=>mediaKind(n)!=='text'&&linked.has(n.id)).length<6;
    graph.nodes.push({id,kind:item.kind,role:'reference',asset:data.asset.id,label:item.file.name.slice(0,80),text:'',...position()});if(connected)graph.edges.push({source:id,target:'director'});run.ids.push(id);change('import:'+run.id);paint();item.state='completed';item.message=connected?'已加入画布 · 已连接导演':'已加入画布 · 未连接导演（最多 6 个媒体参考）';
   }catch(error){item.state='failed';item.message=error.stop===undefined?'上传状态未确认，请核对项目素材':error.message||'上传状态待核对';if(error.stop!==false){run.cancelled=true;item.message+='；后续上传已停止，不会自动重试'}}renderImports(run);
  }
  if(current()&&run.ids.length){
   importTitle.textContent='正在整理画布';await Promise.all(run.ids.map(id=>new Promise(resolve=>{const img=world.querySelector('[data-node-id="'+CSS.escape(id)+'"]>.canvas-card-body>img');if(!img||img.naturalWidth||img.dataset.previewState==='error'){resolve();return}const finish=()=>{clearTimeout(timer);img.removeEventListener('load',finish);img.removeEventListener('error',finish);resolve()},timer=setTimeout(finish,6000);img.addEventListener('load',finish);img.addEventListener('error',finish)})));
   if(current()){arrangeImports(run.ids,run.origin);change('import:'+run.id);paint();fit();toast('已添加 '+run.ids.length+' 个素材并自动排版；保存参考后保留')}
  }
  }finally{run.done=true;if(uploadRun===run){saving=false;uploadRun=null;renderImports(run);updateStatus();if(!current())sync();else if(run.items.some(item=>item.state==='failed'))toast('部分文件未导入，点击「导入结果」查看；成功素材已保留')}}
 }
 viewport.addEventListener('dragover',e=>{if(!e.dataTransfer?.types.includes('Files'))return;e.preventDefault();e.dataTransfer.dropEffect=locked()?'none':'copy';dropHint.hidden=locked()});
 viewport.addEventListener('dragleave',e=>{if(!viewport.contains(e.relatedTarget))dropHint.hidden=true});
 viewport.addEventListener('drop',e=>{if(!e.dataTransfer?.files.length)return;e.preventDefault();dropHint.hidden=true;importFiles([...e.dataTransfer.files])});

 async function save(){if(locked()||!dirty)return;if(oldHasDrafts()){toast('请先保存或放弃时间轴修改，再保存参考');return}saving=true;updateStatus();try{project=await api('/projects/'+project.id+'/canvas','PUT',{revision,...graph});graph=structuredClone(project.canvas);if(graphSignature(graph)!==historyCurrent?.signature)resetHistory();else{historyCurrent=historySnapshot();historyBaseline=historyCurrent.signature;historyMergeKey=null}dirty=false;revision=project.revision;paint();clearMedia();draw();await seek(0);toast('参考已保存，可以让导演继续规划')}catch(e){toast(e.message+'；画布草稿已保留')}finally{saving=false;updateStatus()}}
 function sync(){$('beginButton').hidden=Boolean(project);if(!project?.shots?.length){$('previewTitle').textContent='把参考变成一支作品';$('previewDescription').textContent='添加素材并连接给导演，补齐需要的信息后生成分镜。'}if(project?.id!==pid){panGesture?.cancel();cameraTouched=false;handMode=spacePan=false;closeInsert();cancelSourceDownload();canvasGesture?.cancel();selectedNodes.clear();selectionMode=false;groupDialog.close();imageViewer.close();closeVideo();videoPositions.clear();comparisonDialog.close();videoComparison.close();metadataController.abort();metadataController=new AbortController();metadataRequests.clear();pid=project?.id;loadFolds();tracing=null;openAssetId=null;clearMediaSelection();navigator.hidePopover();search.value='';filter.value='all';navSignature='';sectionStates.clear();dirty=false;revision=-1;for(const u of urls.values())URL.revokeObjectURL(u);urls.clear();fit()}
  if(project&&!dirty&&!saving&&!canvasGesture&&(revision!==project.revision||serverGraphSignature!==graphSignature(project.canvas||{nodes:[],edges:[]}))){graph=structuredClone(project.canvas||{nodes:[],edges:[]});serverGraphSignature=graphSignature(graph);resetHistory();revision=project.revision;paint();syncImageJob();if(!cameraTouched)fit()}else syncImageJob();syncGenerationSources();updateStatus();
 }
 let cameraTouched=false;
 document.addEventListener('creative-camera-touched',()=>{cameraTouched=true;clearFocusAnchor()});
 // Panning changes the viewport only, never node coordinates or edit history.
 const panControl=target=>target.closest('[role=button],button,a,input,textarea,select,label,summary,[contenteditable],video,audio,[popover],.canvas-selection-toolbar,.canvas-media-toolbar');
 function startPan(e){
  const sx=e.clientX,sy=e.clientY,x=tx,y=ty;let moved=false;clearFocusAnchor();closeInsert();
  const finish=cancel=>{if(!panGesture)return;panGesture=null;viewport.removeEventListener('pointermove',move);viewport.removeEventListener('pointerup',up);viewport.removeEventListener('pointercancel',cancelPan);viewport.removeEventListener('lostpointercapture',cancelPan);if(viewport.hasPointerCapture(e.pointerId))viewport.releasePointerCapture(e.pointerId);if(cancel){tx=x;ty=y;apply()}if(moved)panClickUntil=performance.now()+500;updatePanMode()};
  const move=v=>{if(v.pointerId!==e.pointerId)return;if(!moved&&Math.hypot(v.clientX-sx,v.clientY-sy)<3)return;if(!moved)viewport.setPointerCapture(e.pointerId);moved=true;cameraTouched=true;tx=x+v.clientX-sx;ty=y+v.clientY-sy;apply()},up=v=>{if(v.pointerId===e.pointerId)finish(false)},cancelPan=v=>{if(v.pointerId===e.pointerId)finish(true)};
  // Preserve the original click target until this becomes an actual drag.
  panGesture={cancel:()=>finish(true)};e.preventDefault();viewport.addEventListener('pointermove',move);viewport.addEventListener('pointerup',up);viewport.addEventListener('pointercancel',cancelPan);viewport.addEventListener('lostpointercapture',cancelPan);updatePanMode();
 }
 viewport.addEventListener('pointerdown',e=>{panClickUntil=0;if(e.button!==0||focus||canvasGesture||panGesture||panControl(e.target))return;if(handMode||spacePan){e.stopImmediatePropagation();startPan(e);return}if(e.target.closest('.canvas-card,.canvas-entry,.canvas-group-frame'))return;if(e.shiftKey||selectionMode){startMarquee(e);return}selectedNodes.clear();updateSelection();startPan(e)},true);
 for(const type of ['click','dblclick'])viewport.addEventListener(type,e=>{if(e.detail&& !panControl(e.target)&&(performance.now()<panClickUntil||(type==='click'&&(handMode||spacePan)))){e.preventDefault();e.stopImmediatePropagation()}},true);
 document.addEventListener('keydown',e=>{
  if(e.key==='Escape'&&panGesture){e.preventDefault();e.stopImmediatePropagation();panGesture.cancel();return}
  if(e.defaultPrevented||e.repeat||e.isComposing||e.ctrlKey||e.metaKey||e.altKey||e.shiftKey||focus||canvasGesture||!document.body.classList.contains('canvas-expanded')||document.querySelector('dialog[open],[popover]:popover-open')||e.target.closest('input,textarea,select,[contenteditable],iframe,video,audio,.director'))return;
  if(e.target!==document.body&&!viewport.contains(e.target)&&!toolbar.contains(e.target))return;
  if(e.code==='Space'){if(e.target.closest('button,a,summary,[role=button]'))return;e.preventDefault();spacePan=true;updateSelection()}
  else if(!panGesture&&e.key.toLowerCase()==='h'){e.preventDefault();handMode=true;selectionMode=false;updateSelection()}
  else if(!panGesture&&e.key.toLowerCase()==='v'){e.preventDefault();handMode=false;selectionMode=true;updateSelection()}
 },true);
 document.addEventListener('keyup',e=>{if(e.code==='Space'&&spacePan){spacePan=false;updateSelection()}});
 const releasePan=()=>{spacePan=false;panGesture?.cancel();updateSelection()};window.addEventListener('blur',releasePan);document.addEventListener('visibilitychange',()=>{if(document.hidden)releasePan()});
 viewport.addEventListener('wheel',e=>{if(canvasGesture||panGesture){e.preventDefault();return}if(panControl(e.target))return;e.preventDefault();if(e.ctrlKey||e.metaKey){const r=viewport.getBoundingClientRect();zoom(scale-e.deltaY*.002,e.clientX-r.left,e.clientY-r.top)}else{cameraTouched=true;clearFocusAnchor();const unit=e.deltaMode===1?16:e.deltaMode===2?viewport.clientHeight:1;tx-=e.deltaX*unit;ty-=e.deltaY*unit;apply()}},{passive:false});
 // A task is a read-only projection; it never becomes a saved reference node.
 let imageJobCard=null,imageJobKey='',imageJobState='',imageJobDismissed='',imageJobObserved='';
 document.addEventListener('creative-view-current-film',e=>{if(e.detail?.project!==pid||e.detail?.artifact!==project?.artifact||project?.state!=='completed'||output.hidden)return;openCanvas();const node=currentFilmNode();if(node){locateAsset(node.asset);showVideo()}else{selectOutput();focusNode(output);if(document.querySelector('#video')?.readyState>=1)showVideo()}});
 document.addEventListener('creative-focus-canvas-node',e=>{if(e.detail?.project!==pid||typeof e.detail.node!=='string')return;const card=world.querySelector(`.reference-node[data-node-id="${CSS.escape(e.detail.node)}"]`);if(card){openCanvas();revealNode(card);focusNode(card)}});
 document.addEventListener('creative-focus-canvas-asset',e=>{if(e.detail?.project===pid&&typeof e.detail.asset==='string')locateAsset(e.detail.asset)});
 let importingManualResult=false;
 document.addEventListener('creative-import-manual-result',async e=>{
  if(importingManualResult||!pid||typeof e.detail?.child!=='string')return;
  if(hasDrafts()){toast('请先保存当前修改，再加入生成结果');return}
  const parent=pid;importingManualResult=true;
  try{const result=await api('/projects/'+parent+'/manual-nodes/'+encodeURIComponent(e.detail.child)+'/result','POST');if(project?.id!==parent)return;project=result.project;draw();requestAnimationFrame(()=>{if(pid!==parent)return;locateAsset(result.node.asset);if(['trim','assistant','retake','speech'].includes(e.detail.tool)&&result.node.kind==='video')openVideoTool(e.detail.tool)});toast('结果已加入当前画布，可继续编辑或作为参考')}
  catch(error){toast(error.message)}finally{importingManualResult=false}
 });
 document.addEventListener('creative-reveal-manual-editor',event=>{
  const card=event.detail?.card;if(!(card instanceof HTMLElement)||!world.contains(card))return;
  const a=canvasArea(),w=card.offsetWidth*scale,h=card.offsetHeight*scale;
  if(w>a.w||h>a.h){focusNode(card);return}
  const left=card.offsetLeft*scale+tx,top=card.offsetTop*scale+ty;
  if(left<a.x)tx+=a.x-left;else if(left+w>a.x+a.w)tx-=left+w-a.x-a.w;
  if(top<a.y)ty+=a.y-top;else if(top+h>a.y+a.h)ty-=top+h-a.y-a.h;
  apply();
 });
 document.addEventListener('creative-focus-manual-node',e=>{const card=e.detail.card||world.querySelector(`[data-manual-project="${CSS.escape(e.detail.id)}"]`);if(card instanceof HTMLElement&&world.contains(card)){cameraTouched=true;focusNode(card)}});
 function locateAsset(asset){const node=graph.nodes.find(n=>n.asset===asset),card=node&&world.querySelector(`.reference-node[data-node-id="${CSS.escape(node.id)}"]`);if(!card){toast('素材暂不在当前画布中');return}revealNode(card);clearMediaSelection();selectMedia(node.id);focusNode(card)}
 function syncImageJob(){
  syncFilmTask();
  const task=project?.image_task,jobKey=task?.id?project.id+'/'+task.id:'';
  if(!jobKey)imageJobObserved='';else if(task.state!=='completed')imageJobObserved=jobKey;
  world.querySelectorAll('[data-image-processing]').forEach(card=>{delete card.dataset.imageProcessing;card.removeAttribute('aria-busy')});
  if(!jobKey||imageJobDismissed===jobKey||(task.state==='completed'&&imageJobObserved!==jobKey)){imageJobCard?.remove();imageJobCard=null;imageJobKey='';alignOutput();lines();return}
  if(imageJobKey!==jobKey){imageJobCard?.remove();imageJobCard=make('section','canvas-card canvas-image-job');imageJobCard.setAttribute('aria-label','图片生成任务');imageJobCard.dataset.systemNode='image-job';world.append(imageJobCard);imageJobKey=jobKey;imageJobState=''}
  const interrupted=!!syncFailures,active=task.state==='running',refs=[...new Set([task.source_asset,task.reference_asset,...(task.prepared?.references||[]).map(r=>r.asset)].filter(Boolean))];
  for(const n of graph.nodes.filter(n=>active&&refs.includes(n.asset))){const card=world.querySelector(`.reference-node[data-node-id="${CSS.escape(n.id)}"]`);if(card){card.dataset.imageProcessing=interrupted?'stale':'running';card.setAttribute('aria-busy',String(!interrupted))}}
  const result=task.state==='completed'&&graph.nodes.find(n=>n.asset===task.asset),label=interrupted?'状态同步中断':({running:'参考图生成中',completed:result?'参考图已加入画布':'图片已生成 · 待定位',needs_review:'图片结果待核对',failed:'图片生成失败'}[task.state]||'图片状态待核对');
  const options=[...document.querySelectorAll('#imageModelSelect option,.node-image-model option')],model=options.find(o=>o.value===task.model)?.textContent||task.model||'已确认模型';
  const signature=JSON.stringify([jobKey,task.state,task.progress,interrupted,model,refs,task.asset,graph.nodes.map(n=>[n.id,n.asset,n.label])]);
  if(signature!==imageJobState){imageJobState=signature;imageJobCard.replaceChildren();imageJobCard.dataset.state=interrupted?'stale':task.state;imageJobCard.setAttribute('aria-busy',String(active&&!interrupted));
   const head=make('div','canvas-card-head'),title=make('strong','canvas-image-job-title',label);title.setAttribute('role','status');head.append(title);imageJobCard.append(head);if(!active)imageJobCard.append(make('p','canvas-image-job-progress',label));if(active){const phase={queued:'排队中',preparing:'准备素材',submitting:'提交中',generating:'生成中',downloading:'保存结果'}[task.progress?.phase]||'等待模型结果';imageJobCard.append(make('p','canvas-image-job-progress',phase+(Number.isFinite(task.progress?.percent)?' '+Math.round(task.progress.percent)+'%':'')))}
   // Keep progress outside the collapsible task details: manual canvas hides that body.
   if(active){
    const meter=make('div','manual-progress-meter'),fill=make('span'),caption=make('small','manual-progress-caption'),known=Number.isFinite(task.progress?.percent),value=known?Math.max(0,Math.min(100,task.progress.percent)):null;
   const progressLabel=imageJobCard.querySelector('.canvas-image-job-progress')?.textContent||'等待模型结果';meter.setAttribute('role','progressbar');meter.setAttribute('aria-label','图片生成进度：'+progressLabel);meter.dataset.determinate=String(known&&!interrupted);
    if(known&&!interrupted){meter.setAttribute('aria-valuemin','0');meter.setAttribute('aria-valuemax','100');meter.setAttribute('aria-valuenow',String(value));meter.setAttribute('aria-valuetext',progressLabel);meter.removeAttribute('aria-description');fill.style.width=value+'%'}else{meter.removeAttribute('aria-valuemin');meter.removeAttribute('aria-valuemax');meter.removeAttribute('aria-valuenow');meter.removeAttribute('aria-valuetext');meter.setAttribute('aria-description',progressLabel)}
    caption.setAttribute('role','status');caption.setAttribute('aria-live','polite');caption.setAttribute('aria-label',progressLabel);caption.textContent=progressLabel;meter.append(fill);imageJobCard.append(caption,meter);
   }
   const body=make('div','canvas-image-job-body'),activity=make('div','canvas-image-job-activity');activity.setAttribute('aria-hidden','true');body.append(activity);
   body.append(make('p','canvas-image-job-model',model));
   body.append(make('p','canvas-image-job-description',interrupted?'暂未取得最新状态，正在重新连接。':active?'已提交，正在等待图片结果。完成后会自动排版到画布。':task.state==='completed'?'结果已保留，点击定位后继续查看和调整。':'请打开任务详情核对已有结果，不会自动重新生成。'));
   if(refs.length){const inputs=make('div','canvas-image-job-inputs');inputs.append(make('span','','本次输入'));for(const asset of refs){const node=graph.nodes.find(n=>n.asset===asset),b=make('button','',node?.label||'画布外参考');b.type='button';b.disabled=!node;b.onclick=()=>locateAsset(asset);inputs.append(b)}body.append(inputs)}else body.append(make('p','canvas-image-job-inputs',task.reference_id||(task.prepared?.references||[]).some(r=>r.reference_id)?'本次输入 · 商品参考图':'本次输入 · 文字生成'));
   const actions=make('div','canvas-image-job-actions'),details=make('button','','查看任务详情');details.type='button';details.onclick=()=>{const panel=document.querySelector('#productionTask');if(panel){panel.open=true;panel.querySelector('summary')?.focus({preventScroll:true})}};actions.append(details);
   if(task.state==='completed'){const locate=make('button','',result?'定位生成结果':'结果暂不在画布');locate.type='button';locate.disabled=!result;locate.onclick=()=>locateAsset(task.asset);actions.prepend(locate)}
   if(!active){const close=make('button','','收起');close.type='button';close.onclick=()=>{imageJobDismissed=jobKey;syncImageJob();queueNavigation();viewport.focus({preventScroll:true})};actions.append(close)}
   body.append(actions);imageJobCard.append(body);
  }
  alignOutput();lines();
 }
 document.addEventListener('creative-status-sync',syncImageJob);
 const oldDraw=draw;draw=function(){oldDraw();sync()};const oldBusy=setBusy;setBusy=function(value){oldBusy(value);updateStatus()};const oldHasDrafts=hasDrafts;hasDrafts=function(){return dirty||!!uploadRun||!!canvasGesture||oldHasDrafts()};
 const oldOpen=openProject;openProject=async function(id){if(dirty&&pid!==id&&!confirm('参考画布有未保存修改，仍要离开吗？'))return;return oldOpen(id)};
 window.addEventListener('beforeunload',e=>{if(dirty||uploadRun){e.preventDefault();e.returnValue=''}});
 new ResizeObserver(()=>{if(!cameraTouched&&!dirty&&!canvasGesture&&!panGesture){const selected=selectedMedia();if(selected&&viewport.clientWidth<=900)focusNode(selected.card);else fit()}}).observe(viewport);sync();fit();
})();
