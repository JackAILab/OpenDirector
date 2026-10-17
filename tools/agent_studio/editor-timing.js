/* Keep the output clock contract in sync with harness/tools/creative_edit_timing.py. */
'use strict';
window.EditTiming = (() => {
  const round = n => Math.round(n * 1000) / 1000;
  const overlap = c => ['dissolve','fade_black'].includes(c?.transition?.kind) ? c.transition.duration : 0;
  function schedule(clips) {
    let cursor = 0;
    return clips.map((c, index) => {
      const length = round(c.end-c.start), item = {index, at:round(cursor), length, incoming:index?overlap(clips[index-1]):0, outgoing:overlap(c)};
      cursor += length-item.outgoing;
      return item;
    });
  }
  function poses(clips, clock) {
    return schedule(clips).flatMap(s => {
      const local=clock-s.at;
      if(local<0 || local>=s.length) return [];
      let opacity=1, gain=1;
      if(s.incoming && local<s.incoming) {
        const p=local/s.incoming;
        opacity=clips[s.index-1].transition.kind==='fade_black'?Math.max(0,2*p-1):p;
        gain*=p;
      }
      if(s.outgoing && local>s.length-s.outgoing) {
        const p=(s.length-local)/s.outgoing;
        if(clips[s.index].transition.kind==='fade_black') opacity=Math.max(0,2*p-1);
        gain*=p;
      }
      return [{...s, source:clips[s.index].start+local, opacity, gain}];
    });
  }
  function normalize(clips) {
    let adjusted=false;
    clips.forEach((c,i)=>{
      const d=overlap(c); if(!d)return;
      const next=clips[i+1],limit=next?Math.min(2,(c.end-c.start)/2,(next.end-next.start)/2):0;
      if(d>limit){adjusted=true;c.transition=limit>=.05?{kind:c.transition.kind,duration:Math.floor(limit*1000)/1000}:{kind:'cut',duration:0}}
    });
    return adjusted;
  }
  // Deterministic action mirrored by harness/tools/creative_edit_ripple.py.
  function rippleDelete(spec,index){
    const clips=spec.clips||[];if(!Number.isInteger(index)||index<0||index>=clips.length||clips.length<2||clips.length>32)throw Error('请选择画面片段，且至少保留一个画面');
    const ms=n=>{if(typeof n!=='number'||!Number.isFinite(n))throw Error('时间必须为有限数值');return Math.floor(n*1000+.5)},sec=n=>n/1000,copy=x=>JSON.parse(JSON.stringify(x));
    const timing=schedule(clips)[index],left=ms(timing.at)+ms(timing.incoming),right=ms(timing.at)+ms(timing.length)-ms(timing.outgoing),delta=right-left;
    if(delta<0)throw Error('转场区间无效，请先核对相邻片段');
    const mapped=n=>n<=left?n:Math.max(left,n-delta),result=copy(spec);
    result.clips.splice(index,1);if(index)result.clips[index-1].transition={kind:'cut',duration:0};
    const receipt={start:sec(left),end:sec(right),removed_seconds:sec(delta),cut_words:0,removed_captions:0,removed_audio:0,removed_rhythm:0,split_audio:0,cleared_transitions:Number(timing.incoming>0)+Number(timing.outgoing>0)};
    for(const kind of ['captions','rhythm']){result[kind]=[];for(const item of spec[kind]||[]){
      const start=ms(item.start),end=ms(item.end),newStart=mapped(start),newEnd=mapped(end),row={...copy(item),start:sec(newStart),end:sec(newEnd)};
      if(kind==='captions'&&item.words?.length&&delta){row.words=[];for(const word of item.words){const a=start+ms(word.start),b=start+ms(word.end);if(b<=left||a>=right)row.words.push({...word,start:sec(mapped(a)-newStart),end:sec(mapped(b)-newStart)});else if(a<left||b>right)receipt.cut_words++}row.text=row.words.map(w=>w.text).join('').trim()}
      if(newEnd-newStart<200||(kind==='captions'&&item.words?.length&&!row.words.length))receipt['removed_'+kind]++;else result[kind].push(row);
    }}
    result.audio=[];for(const item of spec.audio||[]){
      const at=ms(item.at),sourceStart=ms(item.start),sourceEnd=ms(item.end),end=at+sourceEnd-sourceStart,fragments=delta?[[at,Math.min(end,left)],[Math.max(at,right),end]]:[[at,end]],kept=[];
      for(const [a,b]of fragments){if(b-a<200)continue;const length=b-a,fadeIn=Math.min(a===at?ms(item.fade_in||0):10,length),fadeOut=Math.min(b===end?ms(item.fade_out||0):10,length-fadeIn);kept.push({...copy(item),at:sec(mapped(a)),start:sec(sourceStart+a-at),end:sec(sourceStart+b-at),fade_in:sec(fadeIn),fade_out:sec(fadeOut)})}
      receipt.removed_audio+=Number(!kept.length);receipt.split_audio+=Number(kept.length>1);result.audio.push(...kept);
    }
    if(result.audio.length>16)throw Error('分段后超过 16 条音频，请先整理音轨');
    const timings=schedule(result.clips),last=timings.at(-1);result.duration=round(last.at+last.length);receipt.duration_after=result.duration;receipt.training_eligible=false;
    return {spec:result,receipt};
  }
  function rippleDeleteMany(spec,indexes){
    const values=[...new Set(indexes||[])];
    if(!values.length||values.length>=((spec.clips||[]).length)||values.some(index=>!Number.isInteger(index)||index<0||index>=(spec.clips||[]).length))throw Error('请选择要删除的画面，且至少保留一个画面');
    const copy=x=>JSON.parse(JSON.stringify(x));let current=copy(spec),receipts=[];
    values.sort((a,b)=>b-a).forEach(index=>{const proposal=rippleDelete(current,index);current=proposal.spec;receipts.push(proposal.receipt)});
    const receipt=receipts.reduce((sum,item)=>{for(const key of ['removed_seconds','cut_words','removed_captions','removed_audio','removed_rhythm','split_audio','cleared_transitions'])sum[key]=(sum[key]||0)+(item[key]||0);return sum},{start:Math.min(...receipts.map(item=>item.start)),end:Math.max(...receipts.map(item=>item.end)),removed_seconds:0,cut_words:0,removed_captions:0,removed_audio:0,removed_rhythm:0,split_audio:0,cleared_transitions:0});
    receipt.duration_after=current.duration;receipt.training_eligible=false;
    return {spec:current,receipts,receipt};
  }
  function moveMany(clips,indexes,direction){
    const values=[...new Set(indexes||[])].sort((a,b)=>a-b),n=clips.length;
    if(!values.length||values.some(index=>!Number.isInteger(index)||index<0||index>=n)||![-1,1].includes(direction))throw Error('请选择有效的画面片段和移动方向');
    for(let i=1;i<values.length;i++)if(values[i]!==values[i-1]+1)throw Error('批量移动需选择连续画面片段');
    const start=values[0],length=values.length;if((direction<0&&start===0)||(direction>0&&start+length===n))return {clips:clips.slice(),indexes:values,moved:false};
    const result=clips.slice(),block=result.splice(start,length),insertAt=direction<0?start-1:start+1;result.splice(insertAt,0,...block);
    return {clips:result,indexes:Array.from({length},(_,i)=>insertAt+i),moved:true};
  }
  // Isolate a source-time window without removing media or changing existing transition clocks.
  function isolateClipRange(clips,index,start,end){
    const c=clips[index];if(!Number.isInteger(index)||!c)throw Error('请先选择画面片段');
    if(!Number.isFinite(start)||!Number.isFinite(end))throw Error('请输入有效的开始和结束时间');
    start=round(start);end=round(end);const length=round(end-start);
    if(start<c.start||end>c.end||length<3||length>10)throw Error('请选择当前片段内 3–10 秒的范围');
    const left=round(start-c.start),right=round(c.end-end);
    if((left>0&&left<.2)||(right>0&&right<.2))throw Error('分割后两侧至少保留 0.2 秒，或将边界设到片段端点');
    const parts=[];if(left)parts.push({...structuredClone(c),end:start,transition:{kind:'cut',duration:0}});
    parts.push({...structuredClone(c),start,end,...(right?{transition:{kind:'cut',duration:0}}:{})});
    if(right)parts.push({...structuredClone(c),start:end});
    if(clips.length+parts.length-1>32)throw Error('分割后超过 32 段，请先整理时间轴');
    const result=structuredClone(clips);result.splice(index,1,...parts);
    if(normalize(structuredClone(result)))throw Error('范围过于靠近转场，请保留转场所需长度后再分割');
    return {clips:result,index:index+(left?1:0),changed:parts.length>1};
  }
  return {schedule,poses,normalize,overlap,rippleDelete,rippleDeleteMany,moveMany,isolateClipRange};
})();
