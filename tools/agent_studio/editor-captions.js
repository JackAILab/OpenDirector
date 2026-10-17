/* Shared presentation for live preview and frozen HyperFrames exports.
 * Rise adapts the registry staggered-fade-up primitive to one readable phrase:
 * explicit from/to, small y offset, finite ramps, no word guessing or DOM measurements in tweens.
 */
'use strict';
window.EditCaptions = (() => {
  const defaults={preset:'box',size:'medium',motion:'none'};
  const appearance=c=>({...defaults,...c.appearance});
  const visible=(spec,c)=>(spec.caption_visibility||[true,true,true])[c.track??0];
  const baseColor=c=>appearance(c).preset==='accent'?'#f7db74':'#fff';
  function activeWord(c,clock){
    if(!c.word_highlight||clock<c.start||clock>=c.end)return -1;
    const local=Math.round((clock-c.start)*1000)/1000;
    return (c.words||[]).findIndex(w=>local>=w.start&&local<w.end);
  }
  function wordStyle(c,active){return {color:active?'#141414':baseColor(c),backgroundColor:active?'#f7db74':'rgba(0,0,0,0)',borderRadius:'.08em',textShadow:'none'}}
  function content(effect,c,clock){
    if(!c.words?.length){effect.textContent=c.text;return}
    effect.replaceChildren();const active=activeWord(c,clock);
    c.words.forEach((w,i)=>{const span=document.createElement('span');span.dataset.wordIndex=i;span.textContent=w.text;Object.assign(span.style,wordStyle(c,i===active));effect.append(span)});
  }
  function wordsFit(c){return !c.words?.length||c.words.every(w=>w.start>=0&&w.end<=Math.round((c.end-c.start)*1000)/1000)}
  function geometry(c,width,height){
    const a=appearance(c),factor={small:.8,medium:1,large:1.2}[a.size];
    const font=width*(a.preset==='box'?.033:width<height?.05:.036)*factor;
    return {font,bottom:9+(c.track||0)*12};
  }
  function phase(c){const d=c.end-c.start;return {enter:Math.min(.18,d/4),exit:Math.min(.14,d/4)}}
  function pose(c,clock,width,height){
    const a=appearance(c),local=clock-c.start,length=c.end-c.start;
    if(local<0||local>=length)return {opacity:0,y:0};
    if(a.motion==='none')return {opacity:1,y:0};
    const {enter,exit}=phase(c),distance=a.motion==='rise'?geometry(c,width,height).font*.32:0;
    if(local<enter){const p=local/enter,ease=a.motion==='rise'?1-(1-p)**2:p;return {opacity:ease,y:distance*(1-ease)}}
    if(local>length-exit){const p=(local-length+exit)/exit,ease=a.motion==='rise'?p*p:p;return {opacity:1-ease,y:-distance*.5*ease}}
    return {opacity:1,y:0};
  }
  function style(slot,effect,c,width,height){
    const a=appearance(c),g=geometry(c,width,height),box=a.preset==='box';
    Object.assign(slot.style,{position:'absolute',padding:'0',background:'transparent',borderRadius:'0',left:'8%',width:'84%',bottom:g.bottom+'%',textAlign:'center',pointerEvents:'none',fontFamily:'Studio,system-ui',fontSize:g.font+'px',lineHeight:'1.4',fontWeight:box?'600':'700',whiteSpace:'pre-wrap',overflowWrap:'anywhere'});
    Object.assign(effect.style,{display:'inline-block',maxWidth:'100%',boxSizing:'border-box',width:box?'100%':'auto',padding:box?'.24em .34em':'.06em .16em',borderRadius:'.24em',background:box?'#0009':'transparent',color:a.preset==='accent'?'#f7db74':'#fff',textShadow:box?'none':'.025em .035em .08em #000,0 0 .1em #000',transformOrigin:'50% 100%'});
  }
  function mountTimeline(tl,captions,width,height){
    captions.forEach((c,i)=>{
      const slot=document.getElementById('caption-'+i);if(!slot)return;
      const effect=slot.querySelector('.caption-effect');style(slot,effect,c,width,height);
      effect.querySelectorAll('[data-word-index]').forEach((span,j)=>{
        const w=c.words?.[j];Object.assign(span.style,wordStyle(c,false));
        if(!w||!c.word_highlight)return;
        tl.set(span,wordStyle(c,false),0);
        tl.set(span,wordStyle(c,true),c.start+w.start);
        tl.set(span,wordStyle(c,false),c.start+w.end);
      });
      const a=appearance(c);if(a.motion==='none')return;
      const {enter,exit}=phase(c),distance=a.motion==='rise'?geometry(c,width,height).font*.32:0;
      tl.fromTo(effect,{opacity:0,y:distance},{opacity:1,y:0,duration:enter,ease:a.motion==='rise'?'power1.out':'none'},c.start);
      tl.to(effect,{opacity:0,y:-distance*.5,duration:exit,ease:a.motion==='rise'?'power1.in':'none'},c.end-exit);
    });
  }
  return {appearance,visible,geometry,pose,style,mountTimeline,activeWord,content,wordsFit};
})();
