/* Coordinate-free review labels shared by the scene and edit timeline. */
(function(root){
 'use strict';
 // Scene handoffs serialize time to hundredths; allow rounding, never a sample interval.
 const tolerance=.0051;
 function at(risk,time){
  if(!risk||!Number.isFinite(time))return {hit:false,pairs:[],detail:false};
  const hit=(risk.collision_times||[]).some(value=>Number.isFinite(value)&&Math.abs(value-time)<=tolerance);
  const points=(risk.collision_pairs_by_time||[]).filter(point=>Number.isFinite(point.at)&&Math.abs(point.at-time)<=tolerance);
  const pairs=[];
  if(hit)for(const point of points)for(const pair of point.pairs||[]){
   if(!Array.isArray(pair)||pair.length!==2)continue;
   const ordered=pair.map(String).sort();
   if(!pairs.some(item=>item[0]===ordered[0]&&item[1]===ordered[1]))pairs.push(ordered);
  }
  return {hit,pairs:pairs.slice(0,32),detail:hit&&points.length>0};
 }
 function compare(saved,draft,time){
  const left=at(saved,time),right=at(draft,time);
  const label=left.hit&&right.hit?'两版此时均有命中记录':left.hit?'仅保存版此时有命中记录':right.hit?'仅草稿版此时有命中记录':'两版此时均无命中记录';
  return {saved:left,draft:right,label};
 }
 function describe(result,objects=[]){
  if(!result.hit)return '无命中记录';
  if(!result.detail)return '有命中记录 · 对象明细未记录';
  return result.pairs.slice(0,3).map(pair=>pair.map(id=>objects.find(object=>object.id===id)?.name||id).join(' × ')).join('；')||'有命中记录';
 }
 root.SceneRiskContext={at,compare,describe};
 if(typeof module!=='undefined')module.exports=root.SceneRiskContext;
})(globalThis);
