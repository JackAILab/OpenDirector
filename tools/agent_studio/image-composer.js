/* Image inputs are a separate explicit generation contract, not director edges. */
const roles={product:'商品',person:'人物',scene:'场景',style:'风格',reference:'其他参考'};
const el=(tag,text,cls)=>{const n=document.createElement(tag);if(text)n.textContent=text;if(cls)n.className=cls;return n};
const button=(text,fn,cls)=>{const n=el('button',text,cls);n.type='button';n.onclick=fn;return n};
let active=null,opening=false;

export async function openImageComposer(ctx,initialAsset=null,regionMode=false){
  if(active?.open){active.focus();return}
  if(opening)return;
  if(ctx.locked()||ctx.hasDrafts()){ctx.toast('请先保存或放弃草稿，再选择生成输入');return}
  const snapshot=ctx.project(),pid=snapshot.id,revision=snapshot.revision;
  let catalog;opening=true;try{catalog=await ctx.api('/models')}finally{opening=false}
  if(ctx.project()?.id!==pid||ctx.project().revision!==revision||ctx.locked()||ctx.hasDrafts())return;
  let savedDraft=null;try{savedDraft=JSON.parse(sessionStorage.getItem('manual-image-draft:'+pid)||'null')}catch{}
  const models=catalog.image_models||[],nodes=snapshot.canvas?.nodes||[],assets=Object.values(snapshot.canvas_assets||{}).filter(a=>a.kind==='image');
  const name=aid=>nodes.find(n=>n.asset===aid)?.label||'画布图片';
  const draftRole=aid=>{const role=nodes.find(n=>n.asset===aid)?.role;return role in roles?role:'reference'};
  let selected=ctx.initial?.references?.length?structuredClone(ctx.initial.references):!initialAsset&&snapshot.creation_mode==='image'&&savedDraft?.references? savedDraft.references.filter(v=>assets.some(a=>a.id===v.asset)):initialAsset?[{asset:initialAsset,role:draftRole(initialAsset),instruction:''}]:[],review=null,submitting=false,loading=false,closed=false;
  const previews=new Map(),dialog=el('dialog');dialog.id='imageComposer';active=dialog;
  const head=el('div',null,'image-composer-head'),close=button('×',()=>dialog.close());close.setAttribute('aria-label','关闭图像生成');
  head.append(el('div',regionMode?'局部修改 · 选择区域':'图像生成 · 组合参考'),close);
  const intro=el('p',regionMode?'框选或涂抹需要修改的区域。仅将生成候选的选区合回原图，选区外保留原图像素；选区内容和边缘衔接需查看结果。结果另存为新素材。':'按顺序选择图片，并指定每张图需要保留的内容。生成结果会作为新素材加入画布。','image-composer-intro');
  const form=el('div',null,'image-composer-grid'),library=el('section'),editor=el('section');
  library.append(el('h3',regionMode?'原图 · 标出需要修改的范围':'画布图片'));
  const choices=el('div',null,'image-composer-choices');choices.id='composeImageChoices';library.append(choices);
  if(!assets.length)choices.append(el('p','尚无图片。可先关闭此窗口，在画布添加商品、人物或场景图。'));
  const model=el('select');model.id='composeImageModel';model.setAttribute('aria-label','此次图像生成模型');
  for(const m of models){const o=el('option',m.label+(m.available?'':' · 暂不可用'));o.value=m.id;o.disabled=!m.available;model.append(o)}
  const saved=ctx.initial?.model||savedDraft?.model||snapshot.image_model||ctx.imageModel();if(models.some(m=>m.id===saved))model.value=saved;if(regionMode&&models.find(m=>m.id===model.value)?.mode!=='edit'){const edit=models.find(m=>m.available&&m.region_composite);if(edit)model.value=edit.id}
  const modelLabel=el('label','模型');modelLabel.append(model);editor.append(modelLabel);
  const capability=el('p',null,'image-composer-hint');editor.append(capability);
  const inputs=el('div');inputs.id='composeImageInputs';editor.append(inputs);
  const prompt=el('textarea');prompt.id='composeImagePrompt';prompt.maxLength=4000;prompt.rows=4;prompt.setAttribute('aria-label','此次图像生成要求');prompt.placeholder='例如：保留图 1 的夹克结构，让图 2 的人物穿上它，置于图 3 的场景中。';
  prompt.value=regionMode?'':ctx.initial?.prompt||savedDraft?.prompt||snapshot.direct_prompt||[snapshot.brief?.product,snapshot.brief?.style].filter(Boolean).join('，');if(regionMode)prompt.placeholder='例如：将选中的墙面改成暖灰色，保留原来的材质和光影。';const promptLabel=el('label','生成要求');promptLabel.append(prompt);editor.append(promptLabel);
  const connect=el('input');connect.type='checkbox';connect.id='composeImageConnect';connect.checked=false;
  const connection=el('label',null,'image-composer-connect');connection.hidden=snapshot.creation_mode!=='agent';connection.append(connect,el('span','生成后交给导演，重新整理拍摄方案'));editor.append(connection);
  const reviewBox=el('section',null,'image-composer-review');reviewBox.id='composeImageReview';reviewBox.hidden=true;
  const message=el('p',null,'image-composer-message');message.id='composeImageMessage';message.setAttribute('role','status');
  const footer=el('div',null,'image-composer-footer'),preview=button('核对生成输入',previewInput),confirm=button('确认生成 · 1 积分',submit,'primary');preview.id='composeImagePreview';confirm.id='composeImageConfirm';confirm.hidden=true;
  footer.append(message,preview,confirm);form.append(library,editor);dialog.append(head,intro,form,reviewBox,footer);document.body.append(dialog);

  async function thumbnail(aid,img){
    try{if(!previews.has(aid))previews.set(aid,ctx.preview(aid));const url=await previews.get(aid);if(!closed)img.src=url}catch{img.alt='图片暂不可读取'}
  }
  let region={x:.25,y:.25,width:.5,height:.5,feather:8},regionReady=false,regionGesture=null,regionShape='rectangle',strokes=[],strokeFuture=[],brushSize=.06,brushErase=false,maskEmpty=true;
  const regionInputs=new Map(),regionStage=el('div',null,'image-region-stage'),regionImage=el('img'),regionBox=el('div',null,'image-region-box');regionStage.id='imageRegionStage';regionImage.alt='局部修改原图';regionBox.setAttribute('aria-hidden','true');
  const brushCanvas=el('canvas',null,'image-brush-mask'),regionTools=el('div',null,'image-region-tools'),brushTools=el('div',null,'image-brush-tools');regionTools.id='imageRegionTools';brushCanvas.setAttribute('aria-hidden','true');const brushControls={};
  function paintRegion(){
    regionBox.hidden=regionShape!=='rectangle';brushCanvas.hidden=regionShape!=='brush';brushTools.hidden=regionShape!=='brush';
    Object.assign(regionBox.style,{left:region.x*100+'%',top:region.y*100+'%',width:region.width*100+'%',height:region.height*100+'%'});for(const [key,input] of regionInputs){input.value=key==='feather'?region[key]:+(region[key]*100).toFixed(2);input.parentElement.hidden=regionShape==='brush'&&key!=='feather'}
    for(const [key,value] of [['rect',regionShape==='rectangle'],['brush',regionShape==='brush'],['paint',!brushErase],['erase',brushErase]])brushControls[key]?.setAttribute('aria-pressed',String(value));
    if(regionShape==='brush'&&regionReady){brushCanvas.width=regionImage.naturalWidth;brushCanvas.height=regionImage.naturalHeight;const c=brushCanvas.getContext('2d');for(const stroke of [...strokes,...(regionGesture?.stroke?[regionGesture.stroke]:[])]){c.globalCompositeOperation=stroke.erase?'destination-out':'source-over';c.strokeStyle=c.fillStyle='#59d9ef';c.lineWidth=stroke.size*Math.min(brushCanvas.width,brushCanvas.height);c.lineCap=c.lineJoin='round';c.beginPath();stroke.points.forEach(([x,y],i)=>c[i?'lineTo':'moveTo'](x*(brushCanvas.width-1),y*(brushCanvas.height-1)));c.stroke();if(stroke.points.length===1){const [x,y]=stroke.points[0];c.beginPath();c.arc(x*(brushCanvas.width-1),y*(brushCanvas.height-1),c.lineWidth/2,0,Math.PI*2);c.fill()}}const pixels=c.getImageData(0,0,brushCanvas.width,brushCanvas.height).data;maskEmpty=true;for(let i=3;i<pixels.length;i+=4)if(pixels[i]){maskEmpty=false;break}}
  }
  if(regionMode){
   choices.hidden=true;inputs.hidden=true;regionStage.append(regionImage,regionBox,brushCanvas);library.append(regionTools,regionStage);
   const control=(key,label,fn)=>{const b=button(label,()=>{if(submitting||loading||regionGesture)return;fn();paintRegion();invalidate()});brushControls[key]=b;return b};
   regionTools.append(control('rect','矩形',()=>regionShape='rectangle'),control('brush','涂抹',()=>regionShape='brush'));
   brushTools.append(control('paint','画笔',()=>brushErase=false),control('erase','擦除',()=>brushErase=true),control('undo','撤销一笔',()=>{if(strokes.length)strokeFuture.push(strokes.pop())}),control('redo','重做',()=>{if(strokeFuture.length)strokes.push(strokeFuture.pop())}),control('clear','清空',()=>{strokes=[];strokeFuture=[]}));
   const sizeLabel=el('label','画笔大小'),sizeInput=el('input');sizeInput.type='range';sizeInput.min='1';sizeInput.max='30';sizeInput.value='6';sizeInput.setAttribute('aria-label','画笔大小');sizeInput.oninput=()=>brushSize=Number(sizeInput.value)/100;sizeLabel.append(sizeInput);brushTools.append(sizeLabel);regionTools.append(brushTools);
   const fields=el('div',null,'image-region-fields');for(const [key,title] of [['x','左侧 %'],['y','顶部 %'],['width','宽度 %'],['height','高度 %'],['feather','边缘过渡 px']]){const label=el('label',title),input=el('input');input.type='number';input.min=key==='width'||key==='height'?'1':'0';input.max=key==='feather'?'32':'100';input.step=key==='feather'?'1':'.1';input.setAttribute('aria-label',title);input.oninput=()=>{region[key]=Number(input.value)/(key==='feather'?1:100);Object.assign(regionBox.style,{left:region.x*100+'%',top:region.y*100+'%',width:region.width*100+'%',height:region.height*100+'%'});invalidate()};regionInputs.set(key,input);label.append(input);fields.append(label)}const precision=el('details',null,'image-region-precision');precision.append(el('summary','精确范围与边缘'),fields);library.append(precision);paintRegion();
   regionImage.onload=()=>{regionReady=true;paintRegion();invalidate()};regionImage.onerror=()=>{regionReady=false;message.textContent='原图暂不可读取，请关闭后重试。';controls()};thumbnail(initialAsset,regionImage);
   const point=e=>{const r=regionStage.getBoundingClientRect();return {x:Math.max(0,Math.min(1,(e.clientX-r.left)/r.width)),y:Math.max(0,Math.min(1,(e.clientY-r.top)/r.height))}};
   regionStage.onpointerdown=e=>{if(e.button!==0||submitting||loading||regionGesture||!regionReady)return;if(regionShape==='brush'&&(strokes.length>=32||strokes.reduce((n,s)=>n+s.points.length,0)>=4096)){message.textContent='选区最多 32 笔 / 4096 个轨迹点，请撤销或清空后重新涂抹。';return}e.preventDefault();const p=point(e);regionGesture={start:p,before:{...region},id:e.pointerId,...(regionShape==='brush'?{stroke:{points:[[p.x,p.y]],size:brushSize,erase:brushErase}}:{})};regionStage.setPointerCapture(e.pointerId);paintRegion();invalidate()};
   regionStage.onpointermove=e=>{if(!regionGesture||regionGesture.id!==e.pointerId)return;const p=point(e),a=regionGesture.start,stroke=regionGesture.stroke;if(stroke){const last=stroke.points.at(-1);if(stroke.points.length<256&&strokes.reduce((n,s)=>n+s.points.length,0)+stroke.points.length<4096&&Math.hypot(p.x-last[0],p.y-last[1])>.002)stroke.points.push([p.x,p.y])}else region={...region,x:Math.min(a.x,p.x),y:Math.min(a.y,p.y),width:Math.abs(a.x-p.x),height:Math.abs(a.y-p.y)};paintRegion()};
   const finish=cancel=>{if(!regionGesture)return;const g=regionGesture;regionGesture=null;if(cancel)region=g.before;else if(g.stroke){strokes.push(g.stroke);strokeFuture=[]}if(regionStage.hasPointerCapture(g.id))regionStage.releasePointerCapture(g.id);paintRegion();invalidate()};regionStage.onpointerup=()=>finish(false);regionStage.onpointercancel=regionStage.onlostpointercapture=()=>finish(true);

  }
  const choiceButtons=new Map();
  for(const a of (regionMode?[]:assets)){const b=button('',()=>{if(submitting||loading)return;const index=selected.findIndex(v=>v.asset===a.id);if(index>=0)selected.splice(index,1);else{if(selected.length>=3){message.textContent='最多选择三张图片，可先移除一张。';return}selected.push({asset:a.id,role:draftRole(a.id),instruction:''})}invalidate();drawInputs()});b.dataset.asset=a.id;const img=el('img');img.alt=name(a.id);b.append(img,el('span',name(a.id)));choices.append(b);choiceButtons.set(a.id,b);thumbnail(a.id,img)}
  function invalidReason(){if(regionMode){if(!regionReady)return '正在读取原图…';if(regionGesture)return '请完成区域选择。';if(!models.find(m=>m.id===model.value)?.region_composite)return '所选模型不支持此局部修改流程。';if(!initialAsset||!assets.some(a=>a.id===initialAsset))return '原图不属于当前项目。';if(!Number.isInteger(region.feather)||region.feather<0||region.feather>32||(regionShape==='rectangle'&&(Object.values(region).some(v=>!Number.isFinite(v))||region.x<0||region.y<0||region.width<=0||region.height<=0||region.x+region.width>1.00000001||region.y+region.height>1.00000001)))return '选框必须在图片内，边缘过渡为 0–32 整数像素。';if(regionShape==='brush'){if(!models.find(m=>m.id===model.value)?.region_brush)return '所选模型不支持手绘选区。';if(maskEmpty)return '请先涂抹需要修改的区域。'}else if(region.width*regionImage.naturalWidth<16||region.height*regionImage.naturalHeight<16)return '选区至少需要 16 × 16 像素。'}const m=models.find(m=>m.id===model.value);if(!m?.available)return '所选模型暂不可用，请选择可用模型。';if(m.mode==='text'&&selected.length)return '当前模型只接受文字。请改选参考图编辑模型，或明确移除已选图片。';if(m.mode==='edit'&&!selected.length)return '请从画布图片中选择至少一张参考图。';if(selected.length&&selected.length<(m.min_edit_references||1))return '此模型参考生成至少需要两张图片。';if(selected.length>(m.max_references??1))return '已选图片超过所选模型的输入上限。';if(prompt.value.trim().length<2)return '请填写具体的生成要求。';return ''}
  function controls(){
    const m=models.find(m=>m.id===model.value);capability.textContent=regionMode?'单张原图 · 选区外保留 · 生成 1 张新素材':['edit','both'].includes(m?.mode)?`支持 1–${m.max_references??1} 张参考 · ${snapshot.aspect} · 生成 1 张`:`文字生图 · ${snapshot.aspect} · 生成 1 张`;
    if(regionMode){brushControls.brush.dataset.boundary=String(!m?.region_brush);brushControls.undo.dataset.boundary=String(!strokes.length);brushControls.redo.dataset.boundary=String(!strokeFuture.length);brushControls.clear.dataset.boundary=String(!strokes.length)}
    preview.disabled=submitting||loading||!!invalidReason();confirm.disabled=submitting||loading||!review;close.disabled=submitting;
    dialog.querySelectorAll('input,textarea,select,#composeImageChoices button,#composeImageInputs button,#imageRegionTools button').forEach(n=>n.disabled=submitting||loading||!!regionGesture||n.dataset.boundary==='true');
  }
  function invalidate(){if(!regionMode&&!initialAsset&&snapshot.creation_mode==='image'){try{sessionStorage.setItem('manual-image-draft:'+pid,JSON.stringify({model:model.value,prompt:prompt.value,references:selected}))}catch{}}review=null;reviewBox.hidden=true;confirm.hidden=true;preview.hidden=false;message.textContent=invalidReason()||'核对输入后确认一次生成，失败不自动重试。';controls()}
  function drawInputs(){
    inputs.replaceChildren();inputs.append(el('h3',`本次输入 · ${selected.length}/3`));
    for(const [aid,b] of choiceButtons){const i=selected.findIndex(v=>v.asset===aid);b.setAttribute('aria-pressed',String(i>=0));b.setAttribute('aria-label',(i>=0?`移除图片 ${i+1}：`:'选择图片：')+name(aid))}
    if(!selected.length)inputs.append(el('p','尚未选择参考图','image-composer-hint'));
    selected.forEach((item,index)=>{
      const row=el('article',null,'image-composer-input');row.dataset.asset=item.asset;
      const img=el('img');img.alt=name(item.asset);thumbnail(item.asset,img);
      const fields=el('div'),title=el('div',null,'image-composer-input-title');title.append(el('strong',`图 ${index+1} · ${name(item.asset)}`));
      const up=button('↑',()=>{if(index===0)return;[selected[index-1],selected[index]]=[selected[index],selected[index-1]];invalidate();drawInputs()});up.setAttribute('aria-label','图片提前');up.dataset.boundary=String(index===0);
      const remove=button('×',()=>{selected.splice(index,1);invalidate();drawInputs()});remove.setAttribute('aria-label','移除此输入');title.append(up,remove);
      const role=el('select');role.setAttribute('aria-label',`图 ${index+1} 用途`);for(const [key,value] of Object.entries(roles)){const o=el('option',value);o.value=key;role.append(o)}role.value=item.role;role.onchange=()=>{item.role=role.value;invalidate()};
      const note=el('input');note.maxLength=240;note.value=item.instruction;note.placeholder='要保留什么？例如斜拉链、轮廓、光线方向';note.setAttribute('aria-label',`图 ${index+1} 保留要求`);note.oninput=()=>{item.instruction=note.value;invalidate()};fields.append(title,role,note);row.append(img,fields);inputs.append(row);
    });controls();
  }
  model.onchange=invalidate;prompt.oninput=invalidate;connect.onchange=invalidate;
  function body(){return {revision,model:model.value,prompt:prompt.value.trim(),...(regionMode?{source_asset:initialAsset,region:regionShape==='brush'?{x:0,y:0,width:1,height:1,feather:region.feather,shape:'brush',strokes:structuredClone(strokes)}:{...region}}:{references:selected.map(v=>({...v}))}),connect_to_director:connect.checked}}
  async function previewInput(){
    if(invalidReason()||loading||submitting)return;
    if(ctx.project()?.id!==pid||ctx.project().revision!==revision||ctx.hasDrafts()){message.textContent='项目已变化，请关闭窗口后重新选择输入。';return}
    loading=true;controls();message.textContent='正在核对图片与生成要求…';
    const draft=body();try{
      const result=await ctx.api('/projects/'+pid+'/images/preview','POST',draft);if(closed)return;
      review={body:draft,input_hash:result.input_hash,request_id:crypto.randomUUID().replaceAll('-','')};
      reviewBox.replaceChildren();reviewBox.append(el('h3','本次生成确认'));
      const summary=el('p',`${models.find(m=>m.id===draft.model).label} · ${result.references.length} 张输入${result.region?.shape==='brush'?' + 1 张选区引导':''} → 1 张新图 · ${result.aspect} · ${result.credits} 平台积分`);summary.id='composeImageSummary';reviewBox.append(summary);if(result.region)reviewBox.append(el('p',`${result.region.shape==='brush'?'手绘选区 · '+result.region.strokes.length+' 笔 · 外接范围':'修改范围'}：(${result.region.box.join(', ')}) · 原图 ${result.region.dimensions.join(' × ')} · 向内过渡 ${result.region.feather}px。仅替换选区内像素；完成后检查内容与衔接。`));
      const details=el('details'),label=el('summary','查看完整生成要求');details.append(label,el('pre',result.prompt));reviewBox.append(details,el('p',connect.checked?'完成后交给导演，当前拍摄方案将重新规划。':'完成后放入画布供查看，当前拍摄方案保留。'));
      reviewBox.hidden=false;confirm.hidden=false;preview.hidden=true;message.textContent='图片顺序、用途与提示词已核对。';reviewBox.scrollIntoView({block:'nearest'});
    }catch(e){message.textContent=e.message}finally{loading=false;controls()}
  }
  async function submit(){
    if(!review||submitting||loading)return;
    if(ctx.project()?.id!==pid||ctx.project().revision!==revision||ctx.hasDrafts()){invalidate();message.textContent='项目已变化，请重新打开并核对输入。';return}
    submitting=true;controls();ctx.busy(true);message.textContent='正在提交这一次生成…';
    try{const p=await ctx.api('/projects/'+pid+'/images','POST',{...review.body,input_hash:review.input_hash,request_id:review.request_id,approved_credits:1});ctx.accepted(p);dialog.close();ctx.toast('图片生成已提交，完成后会自动放入画布。')}
    catch(e){
      // Query this project after an uncertain response; never resubmit a POST automatically.
      try{ctx.accepted(await ctx.api('/projects/'+pid))}catch{}
      dialog.close();ctx.toast(e.message+'；请核对项目中的原任务，不会自动再次提交。');
    }finally{submitting=false;ctx.busy(false)}
  }
  dialog.addEventListener('cancel',e=>{if(submitting)e.preventDefault()});
  dialog.addEventListener('close',()=>{closed=true;previews.forEach(p=>p.then(URL.revokeObjectURL).catch(()=>{}));previews.clear();dialog.remove();if(active===dialog)active=null});
  drawInputs();invalidate();dialog.showModal();prompt.focus({preventScroll:true});dialog.scrollTop=0;if(ctx.initial?.focusAsset){const row=[...inputs.querySelectorAll('article')].find(r=>r.dataset.asset===ctx.initial.focusAsset);if(row){row.classList.add('reference-input-focus');row.querySelector('select')?.focus({preventScroll:true});row.scrollIntoView({block:'nearest'})}}if(ctx.initial?.review&&!invalidReason())await previewInput();
}

// A manual send performs the same hash-bound preflight without an Agent dialog.
export async function generateManualImage(ctx){
 if(opening||ctx.locked()||ctx.hasDrafts())return;
 const snapshot=ctx.project();if(snapshot?.creation_mode!=='image')throw Error('请从手动图片工作台生成');
 const pid=snapshot.id;let saved={};try{saved=JSON.parse(sessionStorage.getItem('manual-image-draft:'+pid)||'{}')}catch{}
 const draft={revision:snapshot.revision,model:ctx.initial?.model||saved.model||snapshot.image_model,prompt:(ctx.initial?.prompt||saved.prompt||snapshot.direct_prompt||'').trim(),references:ctx.initial?.references??saved.references??[],connect_to_director:false};
 if(draft.prompt.length<2){ctx.toast('请填写图片生成要求');return}
 opening=true;ctx.busy(true);let submitted=false;
 try{
  sessionStorage.setItem('manual-image-draft:'+pid,JSON.stringify(draft));
  const checked=await ctx.api('/projects/'+pid+'/images/preview','POST',draft);
  if(checked.credits!==1)throw Error('生成费用已变化，请重新读取模型费用');
  if(ctx.project()?.id!==pid||ctx.project().revision!==snapshot.revision)throw Error('项目已变化，请检查输入后再次发送');
  submitted=true;
  const result=await ctx.api('/projects/'+pid+'/images','POST',{...draft,input_hash:checked.input_hash,request_id:crypto.randomUUID().replaceAll('-',''),approved_credits:checked.credits});
  ctx.accepted(result);ctx.toast('图片生成已提交，结果将返回画布');
 }catch(e){if(submitted){try{ctx.accepted(await ctx.api('/projects/'+pid))}catch{}}ctx.toast(e.message)}finally{opening=false;ctx.busy(false)}
}
