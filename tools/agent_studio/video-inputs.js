const roles={product:'商品',person:'人物',scene:'场景',style:'风格',reference:'其他参考'},modes={text:'文字生成',first_frame:'首帧',first_last:'首尾帧',references:'多图参考'};
const el=(tag,text,cls)=>{const e=document.createElement(tag);if(text)e.textContent=text;if(cls)e.className=cls;return e};
const btn=(text,fn)=>{const b=el('button',text);b.type='button';b.onclick=fn;return b};
let active=false;
export async function openVideoInputs(ctx){
 if(active)return;active=true;
 let dialog,modelPicker;
 try{
  if(ctx.locked()||ctx.hasDrafts()){ctx.toast('请先保存或放弃草稿');active=false;return}
  const p=ctx.project(),pid=p.id,revision=p.revision,manual=p.creation_mode==='video',catalog=await ctx.api('/models');
  if(ctx.project()?.id!==pid||ctx.project().revision!==revision){active=false;return}
  const draft=manual&&ctx.draft?{prompt:ctx.draft.prompt.trim(),duration:ctx.draft.duration}:null;
  const duration=draft?.duration??p.duration;
  const models=catalog.models,available=m=>manual?m.manual_available&&m.manual_durations?.includes(duration):m.available,assets=Object.values(p.canvas_assets||{}).filter(a=>a.kind==='image'),nodes=p.canvas?.nodes||[];
  const name=aid=>nodes.find(n=>n.asset===aid)?.label||'画布图片';
  let selected=(p.video_inputs?.references||[]).map(({asset,role,instruction})=>({asset,role,instruction})),review=null,waiting=false,closed=false;
  if(!p.video_inputs&&p.reference?.source_asset)selected=[{asset:p.reference.source_asset,role:'product',instruction:''}];
  if(ctx.initialAsset&&assets.some(a=>a.id===ctx.initialAsset)&&!selected.some(r=>r.asset===ctx.initialAsset))selected.push({asset:ctx.initialAsset,role:'reference',instruction:''});
  const urls=new Map();dialog=el('dialog');dialog.id='videoInputDialog';dialog.setAttribute('aria-label','视频参考输入');
  const head=el('div',null,'image-composer-head'),close=btn('×',()=>dialog.close());close.setAttribute('aria-label','关闭视频参考');head.append(el('strong','视频参考 · 选择实际输入'),close);
  const intro=el('p',p.creation_mode==='video'?'选择实际送入模型的图片。保存后返回画布，点击发送才生成。':`选择实际送入 ${duration} 秒视频的图片。相同图片重新确认归属会保留现有方案。`,'image-composer-intro');
  const form=el('div',null,'image-composer-grid'),left=el('section'),right=el('section'),choices=el('div',null,'image-composer-choices');choices.id='videoInputChoices';left.append(el('h3','画布图片'),choices);
  const model=el('select');model.id='videoInputModel';model.setAttribute('aria-label','视频参考模型');for(const m of models){const o=el('option',m.label);o.value=m.id;o.disabled=!available(m);o.dataset.disabledReason=!(manual?m.manual_available:m.available)?'尚未接入':`不支持 ${duration} 秒`;o.dataset.description=`${Object.keys(m.video_input_modes||{text:0}).map(k=>modes[k]).filter(Boolean).join(' / ')} · ${m.audio?'原生音频':'静音视频'}`;model.append(o)}model.value=ctx.draft?.model||p.model;
  const mode=el('select');mode.id='videoInputMode';mode.setAttribute('aria-label','视频参考模式');
  const modelLabel=el('label','视频模型'),modeLabel=el('label','输入模式'),modelControl=el('span',null,'video-input-model-control');modelControl.append(model);modelLabel.append(modelControl);modeLabel.append(mode);
  const hint=el('p',null,'image-composer-hint'),inputs=el('div');inputs.id='videoInputRows';right.append(modelLabel,modeLabel,hint,inputs);form.append(left,right);
  const box=el('section',null,'image-composer-review');box.id='videoInputReview';box.hidden=true;
  const footer=el('div',null,'image-composer-footer'),message=el('p',null,'image-composer-message');message.setAttribute('role','status');
  const preview=btn('核对视频输入',inspect),save=btn('确认保存',submit);preview.id='videoInputPreview';save.id='videoInputSave';save.className='primary';save.hidden=true;footer.append(message,preview,save);
  const productNotice=el('p',p.video_inputs_needs_review?`请确认以下图片仍属于当前商品：${p.brief?.product||'当前商品'}。核对并保存后即可继续制作。`:'');productNotice.hidden=!p.video_inputs_needs_review;productNotice.setAttribute('role','status');dialog.append(head,intro,productNotice,form,box,footer);document.body.append(dialog);modelPicker=window.installStudioModelPicker?.(model);
  const spec=()=>models.find(m=>m.id===model.value),caps=()=>spec()?.video_input_modes||{text:0};
  function modeOptions(value){mode.replaceChildren();for(const [key,title] of Object.entries(modes)){const o=el('option',title+(key in caps()?'':' · 所选模型不支持'));o.value=key;o.disabled=!(key in caps());mode.append(o)}mode.value=value}
  let initialMode=ctx.initialMode||p.video_inputs?.mode||p.input_manifest?.mode||'text';if(ctx.initialAsset&&initialMode==='text')initialMode='references' in caps()?'references':'first_frame' in caps()?'first_frame':initialMode;modeOptions(initialMode);
  async function thumb(aid,img){try{if(!urls.has(aid))urls.set(aid,ctx.preview(aid));const u=await urls.get(aid);if(!closed)img.src=u}catch{img.alt='图片暂不可读取'}}
  function reason(){if(!available(spec()||{}))return '请选择支持当前时长的可用模型。';if(!(mode.value in caps()))return '请明确选择所选模型支持的输入模式。';if(mode.value==='text'&&selected.length)return '文字生成不能带参考图，请明确移除图片或选择图片模式。';if(mode.value!=='text'&&!selected.length)return '请选择至少一张图片。';if(selected.length>caps()[mode.value])return `当前已选 ${selected.length} 张，此模式最多 ${caps()[mode.value]} 张，请移除多余图片。`;if(mode.value==='first_last'&&selected.length!==2)return '首尾帧模式需要两张图片：第一张首帧，第二张尾帧。';return ''}
  function controls(){dialog.querySelectorAll('input,select,button:not([role=menuitemradio])').forEach(e=>e.disabled=waiting||e.dataset.boundary==='true');modelPicker?.sync();preview.disabled=waiting||!!reason();save.disabled=waiting||!review;hint.textContent=!(mode.value in caps())?'所选模型不支持原输入模式，请选择新的模式；已选图片暂时保留。':mode.value==='references'?`最多 ${caps().references} 张，按顺序作为商品、人物、场景等软参考；不承诺精确首尾帧。`:mode.value==='first_last'?'两张图分别用作首帧和尾帧，需要与项目画幅一致。':mode.value==='first_frame'?'一张图用作整片首帧，需要与项目画幅一致。':(manual?'仅提交当前节点的提示词。':'仅提交拍摄方案文字。');}
  function invalidate(){review=null;box.hidden=true;save.hidden=true;preview.hidden=false;message.textContent=reason()||'保存输入不产生生成费用。';controls()}
  function draw(){
   inputs.replaceChildren(el('h3',`已选图片 · ${selected.length} 张`));
   choices.querySelectorAll('button').forEach(b=>b.setAttribute('aria-pressed',String(selected.some(r=>r.asset===b.dataset.asset))));
   selected.forEach((r,i)=>{const row=el('article',null,'image-composer-input');row.dataset.asset=r.asset;const img=el('img');img.alt=name(r.asset);thumb(r.asset,img);const fields=el('div'),title=el('div',null,'image-composer-input-title');
    const slot=mode.value==='first_last'?(i===0?'首帧':'尾帧'):mode.value==='first_frame'?'首帧':`图片${i+1}`;
    const up=btn('↑',()=>{[selected[i-1],selected[i]]=[selected[i],selected[i-1]];invalidate();draw()});up.dataset.boundary=String(i===0);up.setAttribute('aria-label','图片提前');
    const remove=btn('×',()=>{selected.splice(i,1);invalidate();draw()});remove.setAttribute('aria-label','移除视频输入');title.append(el('strong',`${slot} · ${name(r.asset)}`),up,remove);
    const role=el('select');role.setAttribute('aria-label',`视频图片 ${i+1} 用途`);for(const [k,v] of Object.entries(roles)){const o=el('option',v);o.value=k;role.append(o)}role.value=r.role;role.onchange=()=>{r.role=role.value;invalidate()};
    const note=el('input');note.maxLength=240;note.value=r.instruction;note.placeholder='应保留的外观或场景特征';note.setAttribute('aria-label',`视频图片 ${i+1} 保留要求`);note.oninput=()=>{r.instruction=note.value;invalidate()};fields.append(title,role,note);row.append(img,fields);inputs.append(row);
   });controls();
  }
  for(const a of assets){const b=btn('',()=>{const i=selected.findIndex(r=>r.asset===a.id);if(i>=0)selected.splice(i,1);else if(selected.length<(caps()[mode.value]||0))selected.push({asset:a.id,role:roles[nodes.find(n=>n.asset===a.id)?.role]?nodes.find(n=>n.asset===a.id).role:'reference',instruction:''});else{message.textContent=mode.value==='text'?'请先选择首帧、首尾帧或多图参考模式。':`此模式最多选择 ${caps()[mode.value]||0} 张参考图，请先移除一张再添加。`;return}invalidate();draw()});b.dataset.asset=a.id;const img=el('img');img.alt=name(a.id);b.append(img,el('span',name(a.id)));choices.append(b);thumb(a.id,img)}
  if(!assets.length)choices.append(el('p','先在画布添加图片，再配置视频参考。'));
  model.onchange=()=>{modeOptions(mode.value);invalidate();draw()};mode.onchange=()=>{invalidate();draw()};
  function body(){return {...(draft?{manual:draft}:{}),revision,model:model.value,mode:mode.value,references:selected.map(r=>({...r}))}}
  function changed(){return ctx.project()?.id!==pid||ctx.project().revision!==revision||ctx.hasDrafts()}
  async function inspect(){if(waiting||reason())return;if(changed()){message.textContent='项目已变化，请关闭后重新打开。';return}waiting=true;controls();try{const draft=body(),result=await ctx.api('/projects/'+pid+'/video-inputs/preview','POST',draft);if(closed)return;review={draft,result};box.replaceChildren(el('h3',`${spec().label} · ${duration} 秒 · ${p.aspect} · ${modes[mode.value]} · ${result.references.length} 张图片`));result.references.forEach((r,i)=>box.append(el('p',`${i+1}. ${name(r.asset)} · ${roles[r.role]} · ${r.width} × ${r.height}${r.instruction?' · '+r.instruction:''}`)));box.append(el('p',manual?'保存参考输入，保留当前提示词与时长；点击画布发送按钮后生成。':result.requires_plan?'保存后重新规划，原成片保留在历史。':'确认图片仍适用于当前商品，保留现有方案。'));box.hidden=false;preview.hidden=true;save.hidden=false;save.textContent=manual?'保存输入 · 返回画布':result.requires_plan?'保存输入 · 重新规划':'确认输入 · 保留方案';message.textContent='仅保存所选输入，不开始生成。';box.scrollIntoView({block:'nearest'})}catch(e){message.textContent=e.message}finally{waiting=false;controls()}}
  async function submit(){if(!review||waiting)return;if(changed()){invalidate();message.textContent='项目已变化，请重新打开核对。';return}waiting=true;controls();ctx.busy(true);try{const result=await ctx.api('/projects/'+pid+'/video-inputs','PUT',{...review.draft,input_hash:review.result.input_hash});ctx.accepted(result);dialog.close();ctx.toast(manual?'参考输入已保存，点击画布发送按钮开始生成。':'视频输入已保存，请核对拍摄方案后再生成。')}catch(e){message.textContent=e.message;review=null;box.hidden=true;save.hidden=true;preview.hidden=false}finally{waiting=false;ctx.busy(false);controls()}}
  dialog.addEventListener('cancel',e=>{if(waiting)e.preventDefault()});dialog.addEventListener('close',()=>{closed=true;modelPicker?.destroy();urls.forEach(p=>p.then(URL.revokeObjectURL).catch(()=>{}));dialog.remove();active=false});
  draw();invalidate();dialog.showModal();if(ctx.focusAsset){const row=[...inputs.querySelectorAll('article')].find(e=>e.dataset.asset===ctx.focusAsset);if(row){row.classList.add('reference-input-focus');row.scrollIntoView({block:'nearest'});row.querySelector('select')?.focus({preventScroll:true})}}
 }catch(e){modelPicker?.destroy();dialog?.remove();active=false;throw e}
}
