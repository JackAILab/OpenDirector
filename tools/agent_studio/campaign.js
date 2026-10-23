/* Web Agent duration and persisted chapter progress. No browser-side production loop. */
(()=>{
 const section=document.createElement('section');section.className='campaign-status';section.setAttribute('aria-label','Agent 自动制作');
 const label=document.createElement('label');label.textContent='成片时长 ';
 const select=document.createElement('select');select.setAttribute('aria-label','Agent 成片时长');
 for(const n of [15,30,60])select.add(new Option(n+' 秒'+(n>15?' · 自动分章与剪辑':''),n));label.append(select);
 const status=document.createElement('div');status.setAttribute('role','status');status.setAttribute('aria-live','polite');
 section.append(label,status);document.getElementById('chatForm').prepend(section);
 const style=document.createElement('style');style.textContent='.campaign-status{padding:10px 14px;font-size:12px;color:#aebfc0;border-bottom:1px solid #354144}.campaign-status label{display:flex;align-items:center;gap:10px}.campaign-status select{max-width:230px}.campaign-status ol{padding-left:22px;margin:8px 0}.campaign-status progress{width:100%;accent-color:#21c4df}';document.head.append(style);
 let changing=false;
 select.onchange=async()=>{if(!project||changing)return;const p=project;changing=true;select.disabled=true;try{project=await api('/projects/'+p.id+'/agent-duration','PATCH',{revision:p.revision,duration:Number(select.value)});draw();toast('时长已保存，请让导演按新时长规划')}catch(e){toast(e.message)}finally{changing=false;paint()}};
 function paint(){const p=project;section.hidden=!p||p.creation_mode!=='agent';if(section.hidden)return;select.value=String(p.duration);select.disabled=changing||busy||['planning','running','rendering'].includes(p.state)||!!p.campaign||!!p.film?.job_id;for(const option of select.options)option.disabled=Number(option.value)>15&&!['kling-video-v4_0','kling-video-v3_0_omni'].includes(p.model);status.replaceChildren();if(p.generation_mode!=='chaptered_native')return;
  const campaign=p.campaign,chapters=campaign?.chapters||[];const heading=document.createElement('p');heading.textContent=campaign?({queued:'等待制作',generating:'正在逐章生成',checking:'检查画面与音轨',editing:'自动剪辑并生成成片',completed:'成片制作完成 · 内容待审阅',paused:'制作已暂停，可恢复原任务',failed:'制作失败，已有素材保留'}[campaign.stage]||'准备制作'):`${p.duration/15} 个15秒章节 · 自动衔接、剪辑和上画布`;status.append(heading);
  const list=document.createElement('ol');for(const c of chapters){const row=document.createElement('li');const state=c.state==='generating'&&c.progress?.stage==='finalizing'?'正在取回并保存视频':c.state==='generating'&&c.progress?.stage==='queued'?'排队中':{planned:'等待前一章',submitting:'提交中',generating:'生成中',completed:'音视频技术检查通过',failed:'失败'}[c.state]||c.state;row.textContent=`${c.start}–${c.start+15} 秒 · ${state}`;if(c.state==='generating'){const bar=document.createElement('progress');bar.max=100;if(Number.isFinite(c.progress?.percent)){bar.value=c.progress.percent;row.append(document.createTextNode(' '+c.progress.percent+'%'))}bar.setAttribute('aria-label','当前章节生成进度');row.append(bar)}list.append(row)}status.append(list);
 }
 Object.assign(events,{agent_duration_changed:'广告时长已更新',chapter_submit_requested:'Agent 提交章节',chapter_accepted:'章节任务已接受',chapter_source_passed:'章节音视频检查通过',campaign_technical_passed:'Agent 成片已完成技术检查',campaign_stopped:'Agent 制作已暂停'});
 Object.assign(events,{reference_film_approved:'参考图与成片预算已确认',director_reference_bound:'参考图已绑定视频输入',auto_approval_stopped:'自动制作已停止，等待核对'});
 document.addEventListener('creative-state-change',paint);document.addEventListener('creative-status-sync',paint);paint();
})();
