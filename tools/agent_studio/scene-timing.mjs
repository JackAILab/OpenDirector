// Shared shot boundaries: hard cuts, next shot owns the exact boundary.
export function shotAt(spec, at) {
 if(!Number.isFinite(at)||at<0||at>spec.duration)throw Error('预演时间超出范围');
 let start=0;
 for(let index=0;index<spec.shots.length;index++){
  const shot=spec.shots[index],end=start+shot.duration;
  if(at<end||index===spec.shots.length-1)return {shot,index,start,local:Math.max(0,Math.min(shot.duration,at-start))};
  start=end;
 }
}
export function shotStart(spec,id){let at=0;for(const shot of spec.shots){if(shot.id===id)return at;at+=shot.duration}throw Error('找不到镜头')}
export function shotSchedule(spec){return spec.shots.map(shot=>({id:shot.id,name:shot.name,start:shotStart(spec,shot.id),duration:shot.duration,camera:'Camera_'+shot.id,animation:'Shot_'+shot.id}))}
