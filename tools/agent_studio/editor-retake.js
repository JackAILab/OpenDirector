/* Paid retakes are separate, immutable candidates. Applying only changes a draft. */
'use strict';
const RetakeUI={
  job:null,jobs:[],base:null,timer:null,media:[],initialized:false,rangeKey:null,compareReady:false,comparePlaying:false,compareMuted:false,compareEpoch:0,compareFrame:null,loadEpoch:0,
  message(text){$('retakeStatus').textContent=text},
  busyState(job){return ['submitting','generating','checking'].includes(job?.state)},
  open(){stop();document.querySelectorAll('.adviser').forEach(e=>e.hidden=true);$('retakePanel').hidden=false;this.draw();},
  close(){this.pauseComparison();$('retakePanel').hidden=true;},
  draw(){
    if(!this.initialized)return;
    const c=selected.kind==='clips'&&spec?.clips[selected.index];
    $('retake').disabled=working||!c;
    $('retakePrepare').disabled=working||!c||c.end-c.start<3||c.end-c.start>10;
    this.drawRange(c);
    $('retakeIntent').disabled=working;
    $('retakeHistory').disabled=working;
    $('retakeSelection').textContent=c?`画面 ${selected.index+1} · ${meta(c.source)?.title||'素材'} · ${c.start.toFixed(2)}–${c.end.toFixed(2)} s`:'先在时间轴选择一个画面片段';
    const job=this.job,matching=!dirty&&JSON.stringify(spec)===this.base;
    $('retakeCompose').hidden=!!job;
    $('retakeNew').hidden=!job||this.busyState(job);
    $('retakeNew').disabled=working;
    $('retakeReview').hidden=!job;
    $('retakeGenerating').hidden=!this.busyState(job);
    $('retakeGenerate').hidden=job?.state!=='ready';
    $('retakeGenerate').disabled=working||!matching||job?.stale;
    $('retakeApply').hidden=job?.state!=='completed';
    $('retakeApply').disabled=working||!matching||job?.stale;
    $('retakeCandidateWrap').hidden=job?.state!=='completed';
    $('retakeCompareControls').hidden=job?.state!=='completed';
    $('retakeOriginal').controls=job?.state!=='completed';$('retakeCandidate').controls=false;
    for(const id of ['retakeComparePlay','retakeCompareSeek','retakeCompareAudio'])$(id).disabled=!this.compareReady;
    if(job){
      $('retakeQuote').textContent=`画面 ${job.clip_index+1} · Kling O3 · 720p · ${job.duration.toFixed(2)} 秒 · 本次 ${job.credits} 积分`;
      $('retakeGenerate').textContent=`确认生成候选 · ${job.credits} 积分`;
      $('retakeAudio').textContent=job.preserve_audio?'候选恢复原片段的声音。字幕、配乐、转场和音量设置沿用当前剪辑。':'原片段没有声音。字幕、配乐和转场沿用当前剪辑。';
      $('retakeFrozenIntent').textContent=job.intent;
      if(!matching&&!this.busyState(job))this.message('当前草稿已改变；此记录保留，请按新草稿重新准备。');
    }
  },
  openRange(start,end,intent=''){this.pauseComparison();this.loadEpoch++;this.compareReady=false;this.job=null;this.base=null;this.open();this.history();this.setRange(start,end);$('retakeIntent').value=intent.slice(0,1600);},
  setRange(start,end){$('retakeRangeStart').value=start;$('retakeRangeEnd').value=end;this.drawRange(selected.kind==='clips'&&spec?.clips[selected.index]);},
  drawRange(c){
    const key=c?JSON.stringify([selected.index,c]):'';
    if(key!==this.rangeKey){this.rangeKey=key;for(const [id,value]of [['retakeRangeStart',c?.start],['retakeRangeEnd',c?.end]]){$(id).value=value??'';$(id).min=c?.start??0;$(id).max=c?.end??0}}
    const start=$('retakeRangeStart').valueAsNumber,end=$('retakeRangeEnd').valueAsNumber;
    for(const id of ['retakeRangeStart','retakeRangeEnd'])$(id).disabled=working||!c;
    $('retakeRangePlay').disabled=working||!c||!Number.isFinite(start)||!Number.isFinite(end)||start<c.start||end>c.end||end-start<.2;
    let issue='',proposal;try{proposal=EditTiming.isolateClipRange(spec?.clips||[],selected.index,start,end)}catch(e){issue=e.message}
    $('retakeRangeIsolate').disabled=working||!c||!!issue||!proposal?.changed;
    $('retakePrepare').disabled=working||!c||!!issue||start!==c.start||end!==c.end;
    $('retakeRangeHint').textContent=issue||(proposal.changed?`已选 ${(end-start).toFixed(2)} 秒；分离后保留两侧画面、原声和字幕，可撤销。`:'当前整段可重拍；填写要求后准备输入与费用。');
  },
  history(){
    const s=$('retakeHistory');s.replaceChildren(new Option('本次选中片段',''));
    for(const j of [...this.jobs].reverse())s.add(new Option(`画面 ${j.clip_index+1} · ${j.duration.toFixed(1)}s · `+({ready:'待确认',completed:'候选就绪',failed:'未完成',needs_review:'待核对'}[j.state]||'处理中'),j.id));
    s.value=this.job?.id||'';
  },
  compareDuration(){return Math.min(this.job?.duration||0,$('retakeOriginal').duration||0,$('retakeCandidate').duration||0)},
  paintComparison(){const value=$('retakeCandidate').currentTime||0,length=this.compareDuration();$('retakeCompareClock').textContent=`${value.toFixed(2)} / ${Number.isFinite(length)?length.toFixed(2):'0.00'} 秒`;$('retakeCompareSeek').max=Number.isFinite(length)?length:0;$('retakeCompareSeek').value=value;$('retakeCompareSeek').setAttribute('aria-valuetext',`${value.toFixed(2)} 秒`);$('retakeComparePlay').textContent=this.comparePlaying?'暂停对比':'同步播放';$('retakeComparePlay').setAttribute('aria-label',this.comparePlaying?'暂停原片与候选':'同步播放原片与候选');$('retakeCompareAudio').setAttribute('aria-pressed',String(!this.compareMuted));$('retakeCompareAudio').textContent=this.compareMuted?'原声已静音':'候选原声';},
  pauseComparison(){this.compareEpoch++;this.comparePlaying=false;cancelAnimationFrame(this.compareFrame);for(const id of ['retakeOriginal','retakeCandidate'])$(id).pause();this.paintComparison();},
  async seekComparison(value,resume=false){
    this.pauseComparison();if(!this.compareReady)return;const token=this.compareEpoch,target=Math.max(0,Math.min(this.compareDuration(),value));
    try{await Promise.all(['retakeOriginal','retakeCandidate'].map(async id=>{const v=$(id);if(Math.abs(v.currentTime-target)<.001&&!v.seeking)return;v.currentTime=target;await mediaReady(v,'seeked',()=>!v.seeking&&Math.abs(v.currentTime-target)<.05)}));if(token!==this.compareEpoch)return;this.paintComparison();if(!resume)return;
      stop();$('retakeOriginal').muted=true;$('retakeCandidate').muted=this.compareMuted;
      await Promise.all([$('retakeOriginal').play(),$('retakeCandidate').play()]);if(token!==this.compareEpoch)return;this.comparePlaying=true;this.paintComparison();this.message('原片与候选使用共同播放时钟，原输入静音；请核对商品、动作与候选原声。');
      const tick=()=>{if(token!==this.compareEpoch)return;if($('retakePanel').hidden||!this.comparePlaying){this.pauseComparison();return}const original=$('retakeOriginal'),candidate=$('retakeCandidate');if(candidate.ended||candidate.currentTime>=this.compareDuration()-.005){this.pauseComparison();return}if(!original.seeking&&Math.abs(original.currentTime-candidate.currentTime)>.06)original.currentTime=candidate.currentTime;this.paintComparison();this.compareFrame=requestAnimationFrame(tick)};this.compareFrame=requestAnimationFrame(tick);
    }catch(e){if(token===this.compareEpoch){this.pauseComparison();this.message('对比播放未完成：'+e.message)}}
  },
  async video(id,path,token){
    const v=$(id);v.pause();v.removeAttribute('src');v.load();
    const jobId=this.job?.id,r=await fetchOwned(path),url=URL.createObjectURL(await r.blob());
    if(jobId!==this.job?.id||token!==this.loadEpoch){URL.revokeObjectURL(url);return}
    this.media.push(url);v.preload='auto';v.src=url;v.load();
    await mediaReady(v,'canplay',()=>v.readyState>=3);
  },
  async show(job){
    this.pauseComparison();this.compareReady=false;const token=++this.loadEpoch;for(const id of ['retakeOriginal','retakeCandidate']){$(id).removeAttribute('src');$(id).load()}
    this.job=job;this.jobs=this.jobs.filter(j=>j.id!==job.id);this.jobs.push(job);this.history();this.draw();
    this.media.forEach(URL.revokeObjectURL);this.media=[];
    this.message(job.error||({ready:'先回放原画面并核对要求，再确认一次生成。',completed:'候选技术检查通过。请比较商品细节、动作和声音，再决定是否替换。'}[job.state]||'正在处理原任务…'));
    await this.video('retakeOriginal','/edit/retakes/'+job.id+'/input',token);
    if(this.job?.id!==job.id||token!==this.loadEpoch)return;
    if(job.state==='completed'){await this.video('retakeCandidate','/edit/sources/'+job.asset,token);if(token!==this.loadEpoch||this.job?.id!==job.id)return;this.compareReady=true;$('retakeOriginal').muted=true;$('retakeCandidate').muted=this.compareMuted;this.paintComparison();this.draw()}
  },
  async poll(){
    try{
      const job=await request('/edit/retakes/'+this.job.id);this.job=job;this.draw();
      if(this.busyState(job)){this.message(job.state==='checking'?'正在恢复原声并检查候选…':'正在生成候选，关闭面板后仍可继续查看。');this.timer=setTimeout(()=>this.poll(),2500);return}
      const latest=await request('/edit');project.revision=latest.revision;project.sources=latest.sources;
      working=false;draw();await this.show(job);
      if(job.asset)loadWave(job.asset);
    }catch(e){this.message('暂时无法查询，正在继续查询原任务；不会重新生成。');this.timer=setTimeout(()=>this.poll(),5000)}
  },
  async init(){
    this.initialized=true;
    $('retake').onclick=()=>this.open();$('closeRetake').onclick=()=>this.close();
    for(const id of ['retakeRangeStart','retakeRangeEnd'])$(id).oninput=()=>this.drawRange(selected.kind==='clips'&&spec?.clips[selected.index]);
    $('retakeRangePlay').onclick=async()=>{const c=selected.kind==='clips'&&spec?.clips[selected.index];if(working||!c||$('retakeRangePlay').disabled)return;const at=offset(selected.index),start=$('retakeRangeStart').valueAsNumber,end=$('retakeRangeEnd').valueAsNumber;await playTimeline(at+start-c.start,at+end-c.start)};
    $('retakeRangeIsolate').onclick=()=>{if(working||selected.kind!=='clips')return;try{const proposal=EditTiming.isolateClipRange(spec.clips,selected.index,$('retakeRangeStart').valueAsNumber,$('retakeRangeEnd').valueAsNumber);if(!proposal.changed)return;stop();checkpoint();spec.clips=proposal.clips;selectClip(proposal.index);changed();this.message('范围已分离到剪辑草稿，可撤销。填写修改要求后点击准备片段，再核对费用。')}catch(e){this.message(e.message)}};

    $('retakeNew').onclick=()=>{this.pauseComparison();this.loadEpoch++;this.compareReady=false;this.job=null;this.base=null;this.history();this.draw();this.message('按当前片段重新准备，之前的候选仍保留在记录中。');$('retakeIntent').focus()};
    $('retakeComparePlay').onclick=()=>{if(this.comparePlaying){this.pauseComparison();return}const at=$('retakeCandidate').currentTime;this.seekComparison(at>=this.compareDuration()-.02?0:at,true)};
    $('retakeCompareSeek').oninput=()=>this.seekComparison(Number($('retakeCompareSeek').value));
    $('retakeCompareAudio').onclick=()=>{this.compareMuted=!this.compareMuted;$('retakeCandidate').muted=this.compareMuted;this.paintComparison()};
    $('retakeCandidate').onended=()=>this.pauseComparison();
    for(const id of ['retakeOriginal','retakeCandidate'])$(id).addEventListener('waiting',()=>{if(this.comparePlaying&&!$(id).seeking&&$(id).readyState<3){this.pauseComparison();this.message('对比视频正在缓冲，准备好后可继续同步播放。')}});
    for(const id of ['retakeOriginal','retakeCandidate'])$(id).addEventListener('error',()=>{if(this.comparePlaying){this.pauseComparison();this.message('对比视频未能继续播放，请重新打开该记录。')}});
    new MutationObserver(()=>{if($('retakePanel').hidden)this.pauseComparison()}).observe($('retakePanel'),{attributes:true,attributeFilter:['hidden']});
    $('retakePrepare').onclick=async()=>{
      if($('retakePrepare').disabled)return;
      const intent=$('retakeIntent').value.trim();if(working||!intent){this.message('请先说明要修改的画面');return}
      const clip=selected.kind==='clips'&&spec.clips[selected.index];
      if(!clip||clip.end-clip.start<3||clip.end-clip.start>10){this.message('先分割或裁切，选中 3–10 秒的画面片段再重拍。');return}
      stop();working=true;draw();this.message('正在保存剪辑并准备原片段…');
      try{
        await save();this.base=JSON.stringify(spec);
        const payload={revision:project.revision,clip_index:selected.index,intent};if(project.scene_retake?.id)payload.scene_retake_id=project.scene_retake.id;
        const job=await request('/edit/retakes/preview','POST',payload);
        await this.show(job);
      }catch(e){this.message(e.message)}finally{working=false;draw()}
    };
    $('retakeGenerate').onclick=async()=>{
      const job=this.job;if(working||job?.state!=='ready'||dirty||JSON.stringify(spec)!==this.base)return;
      stop();working=true;draw();this.message('已确认本次费用，正在提交一次重拍…');
      try{
        try{this.job=await request('/edit/retakes/'+job.id+'/generate','POST',{revision:job.revision,quote_digest:job.quote_digest,approved_credits:job.credits})}
        catch(e){const known=await request('/edit/retakes/'+job.id);if(known.state==='ready')throw e;this.job=known}
        this.draw();await this.poll();
      }catch(e){working=false;draw();this.message(e.message)}
    };
    $('retakeApply').onclick=async()=>{
      if(working||dirty||JSON.stringify(spec)!==this.base||this.job?.state!=='completed')return;
      working=true;draw();
      try{
        const result=await request('/edit/retakes/'+this.job.id+'/plan','POST',{revision:project.revision});
        checkpoint();project.sources=result.sources;spec=result.spec;selected={kind:'clips',index:this.job.clip_index};
        working=false;changed();this.close();status('重拍候选已放入草稿 · 原声与字幕保留，可撤销；保存后生效');
      }catch(e){this.message(e.message)}finally{working=false;draw()}
    };
    $('retakeHistory').onchange=async()=>{
      if(working)return;this.pauseComparison();this.compareReady=false;const token=++this.loadEpoch,id=$('retakeHistory').value;this.base=JSON.stringify(spec);this.draw();
      if(!id){this.job=null;this.draw();return}
      try{const job=await request('/edit/retakes/'+id);if(token!==this.loadEpoch)return;await this.show(job);if(this.busyState(this.job)){working=true;draw();this.poll()}}catch(e){this.message(e.message)}
    };
    this.draw();
    try{
      const r=await request('/edit/retakes');this.jobs=r.jobs;this.history();
      const live=r.jobs.find(j=>this.busyState(j));
      if(live&&!working){this.base=JSON.stringify(spec);working=true;await this.show(live);draw();this.poll()}
    }catch(e){this.message('暂时无法读取重拍记录')}
  }
};
