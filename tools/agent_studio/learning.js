/* Optional private learning controls; no media generation or automatic consent. */
(()=>{
 const panel=node('details');panel.id='learningPanel';
 panel.append(node('summary','作品系列与数据授权'));
 const open=node('button','管理当前作品');open.id='learningButton';open.type='button';panel.append(open);
 document.querySelector('.inspector').append(panel);
 const dialog=node('dialog');dialog.id='learningDialog';dialog.style.maxHeight='90dvh';dialog.style.overflowY='auto';dialog.append(node('h2','作品系列与数据授权'));
 const status=node('p','正在读取…');status.id='learningStatus';dialog.append(status);
 const label=node('label','归属系列');label.htmlFor='learningFamily';dialog.append(label);
 const select=node('select');select.id='learningFamily';select.style.width='100%';dialog.append(select);
 const familyRow=node('div',undefined,'row');const familySave=node('button','保存系列');familySave.id='saveLearningFamily';familyRow.append(familySave);dialog.append(familyRow);
 const newLabel=node('label','新建系列');newLabel.htmlFor='learningSeriesName';dialog.append(newLabel);
 const newRow=node('div',undefined,'row');const name=node('input');name.id='learningSeriesName';name.maxLength=80;name.placeholder='例如：陶瓷杯秋季广告';
 const create=node('button','新建');create.id='createLearningSeries';newRow.append(name,create);dialog.append(newRow);
 dialog.append(node('h3','当前成片的数据使用'));
 const terms=node('p');terms.id='learningPolicy';dialog.append(terms);
 const train=node('input');train.type='checkbox';train.id='learningTraining';
 const publicData=node('input');publicData.type='checkbox';publicData.id='learningPublic';
 for(const [input,text] of [[train,'允许当前版本经审查后用于改进广告导演模型'],[publicData,'另行允许公开经审查、脱敏后的训练数据']]){
  const item=node('label');item.append(input,document.createTextNode(' '+text));dialog.append(item);
 }
 const note=node('p',undefined,'muted');note.id='learningReviewStatus';dialog.append(note);
 const row=node('div',undefined,'row');const close=node('button','关闭');const save=node('button','保存数据授权');save.id='saveLearningConsent';row.append(close,save);dialog.append(row);document.body.append(dialog);
 let ticket=0,target=null,view=null;
 function valid(t){return t===ticket&&dialog.open&&project?.id===target?.id&&project?.revision===target?.revision}
 function busy(on){[select,familySave,create,name,train,publicData,save].forEach(el=>el.disabled=on);if(!on&&!view?.artifact_sha256){train.disabled=publicData.disabled=save.disabled=true}}
 function draw(v){view=v;select.value=v.family_id.startsWith('project:')?'':v.family_id;train.checked=v.training;publicData.checked=v.public_dataset;terms.textContent=v.policy_text;note.textContent=v.artifact_sha256?'授权只适用于版本 '+v.revision+'。'+v.review_status:'完成成片后才能授权该版本。'+v.review_status;busy(false)}
 close.onclick=()=>dialog.close();dialog.addEventListener('close',()=>{ticket++;target=null;view=null;train.checked=false;publicData.checked=false});
 async function act(fn){const t=ticket;if(!valid(t)){status.textContent='作品已变化，请关闭后重新打开。';return}busy(true);try{await fn(t)}catch(e){if(valid(t))status.textContent=e.message}finally{if(valid(t))busy(false)}}
 open.onclick=async()=>{
  if(!project){toast('请先打开一个作品');return}target={id:project.id,revision:project.revision};const t=++ticket;view=null;train.checked=false;publicData.checked=false;name.value='';status.textContent='正在读取当前作品…';dialog.showModal();busy(true);
  try{const [v,series]=await Promise.all([api('/projects/'+target.id+'/learning'),api('/learning/series')]);if(!valid(t))return;if(v.revision!==target.revision){status.textContent='作品已更新，请关闭后重新打开。';return}select.replaceChildren(new Option('独立作品',''),...series.map(s=>new Option(s.label,s.id)));draw(v);status.textContent='系列只在你的账户内可见。数据授权不影响正常创作。'}catch(e){if(valid(t))status.textContent=e.message}
 };
 familySave.onclick=()=>act(async t=>{const v=await api('/projects/'+target.id+'/learning/family','PUT',{revision:target.revision,series_id:select.value||null});if(valid(t)){draw(v);status.textContent='已保存作品系列。'}});
 create.onclick=()=>act(async t=>{const s=await api('/learning/series','POST',{label:name.value});if(valid(t)){select.add(new Option(s.label,s.id));select.value=s.id;name.value='';status.textContent='系列已新建，请保存当前作品的归属。'}});
 train.onchange=()=>{if(!train.checked)publicData.checked=false};
 publicData.onchange=()=>{if(publicData.checked&&!train.checked){publicData.checked=false;status.textContent='请先明确允许训练使用，再选择公开数据。'}};
 save.onclick=()=>act(async t=>{const v=await api('/projects/'+target.id+'/learning/consent','POST',{revision:target.revision,artifact_sha256:view.artifact_sha256,policy:view.policy,policy_sha256:view.policy_sha256,training:train.checked,public_dataset:publicData.checked});if(valid(t)){draw(v);status.textContent=v.training?'已记录当前版本授权，仍需独立审查。':'已关闭当前版本的后续训练与公开数据导出。'}});
})();
