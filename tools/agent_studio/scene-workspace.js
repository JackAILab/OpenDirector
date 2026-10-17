// The ruler follows the existing native range and scene clock; it owns no scene data.
export function installSceneTransport(){
 const $=id=>document.getElementById(id),rail=$('sceneTimeline'),ruler=$('sceneRuler'),playhead=$('scenePlayhead'),label=$('scenePlayheadTime'),scrub=$('scrub'),clock=$('clock'),play=$('play');
 const preview=$('cameraPreview'),previewPlay=$('previewPlay'),expand=$('previewExpand'),notice=$('previewNotice');
 previewPlay.onclick=()=>play.click();
 // Fullscreen is presentation state only. The renderer measures the same canvas each frame.
 expand.onclick=async()=>{
  notice.textContent='';
  try{
   if(document.fullscreenElement===preview)await document.exitFullscreen();
   else if(preview.classList.contains('is-expanded'))preview.classList.remove('is-expanded');
   else if(preview.requestFullscreen)await preview.requestFullscreen();
   else preview.classList.toggle('is-expanded');
  }catch{notice.textContent='暂时无法全屏，已放大预览。';preview.classList.add('is-expanded')}
  syncExpanded();
 };
 function syncExpanded(){const expanded=document.fullscreenElement===preview||preview.classList.contains('is-expanded');expand.setAttribute('aria-pressed',String(expanded));expand.setAttribute('aria-label',expanded?'收起机位预览':'放大机位预览');expand.title=expanded?'收起机位预览 · Esc':'放大机位预览';expand.innerHTML=`<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="${expanded?'M20 4l-7 7m0-6v6h6M4 20l7-7m-6 0h6v6':'M14 4h6v6M20 4l-7 7M10 20H4v-6M4 20l7-7'}"/></svg>`}
 let wasPreviewFullscreen=false;
 document.addEventListener('fullscreenchange',()=>{const own=document.fullscreenElement===preview;syncExpanded();if(wasPreviewFullscreen&&!own)expand.focus({preventScroll:true});wasPreviewFullscreen=own});
 preview.addEventListener('keydown',event=>{if(event.key==='Escape'&&preview.classList.contains('is-expanded')){preview.classList.remove('is-expanded');notice.textContent='';syncExpanded();expand.focus({preventScroll:true});event.preventDefault()}});
 let duration=10,rulerKey='',lastLabel='',lastClock='',lastAria='',lastPlaying=null;
 const timecode=seconds=>`${String(Math.floor(seconds/60)).padStart(2,'0')}:${String(Math.floor(seconds%60)).padStart(2,'0')}`;
 function paintRuler(){
  const width=rail.clientWidth,key=`${duration}:${width}`;if(key===rulerKey)return;rulerKey=key;
  const target=Math.max(duration>=5?1:.25,duration/Math.max(1,Math.floor(width/70))),step=[.25,.5,1,2,5,10,15,30,60].find(n=>n>=target)||60;
  const ticks=[];
  for(let at=0;at<duration;at+=step/4){const tick=document.createElement('span'),major=Math.abs(at/step-Math.round(at/step))<.001;tick.className=major?'major':'minor';tick.style.left=`${at/duration*100}%`;if(major&&duration-at>step*.45)tick.textContent=`${Number(at.toFixed(2))}s`;ticks.push(tick)}
  const end=document.createElement('span');end.className='major end';end.style.left='100%';end.textContent=`${Number(duration.toFixed(2))}s`;ticks.push(end);ruler.replaceChildren(...ticks);
 }
 new ResizeObserver(paintRuler).observe(rail);
 return {sync(at,total,playing,shotCount){
  duration=total;paintRuler();const percentage=Math.max(0,Math.min(100,at/total*100));playhead.style.left=`${percentage}%`;playhead.classList.toggle('at-start',percentage<4);playhead.classList.toggle('at-end',percentage>96);
  const text=`${at.toFixed(1)}s`;if(text!==lastLabel){label.textContent=text;lastLabel=text}const aria=`${at.toFixed(2)} 秒，共 ${total.toFixed(2)} 秒`;if(aria!==lastAria){scrub.setAttribute('aria-valuetext',aria);lastAria=aria}
  const stamp=`${timecode(at)} / ${timecode(total)}`;if(stamp!==lastClock){clock.textContent=stamp;lastClock=stamp}clock.title=`${at.toFixed(2)} / ${total.toFixed(2)} 秒`;
  if(playing!==lastPlaying){play.textContent=playing?'Ⅱ':'▶';play.setAttribute('aria-label',playing?'暂停预演':'播放预演');play.title=playing?'暂停 · Space':'播放 · Space';play.setAttribute('aria-pressed',String(playing));previewPlay.textContent=playing?'Ⅱ':'▶';previewPlay.setAttribute('aria-label',playing?'暂停机位预演':'播放机位预演');previewPlay.title=playing?'暂停 · Space':'播放 · Space';previewPlay.setAttribute('aria-pressed',String(playing));lastPlaying=playing}
  $('shotTrack').classList.toggle('single-shot',shotCount===1);
 }};
}

// Panel navigation is transient UI state; it never changes the scene document.
export function installSceneWorkspace(){
 const $=id=>document.getElementById(id);
 installSceneChrome();
 const panels={inspector:$('sceneInspector'),timeline:$('timelineOverlay'),agent:$('sceneAgent')};
 const toggles={inspector:$('toggleInspector'),timeline:$('openTimelineOverlay'),agent:$('toggleAgent')};
 const groups=[
  {id:'shots',label:'镜头',sections:['.shots-section','#cameraSettings','#roleBindings']},
  {id:'objects',label:'对象',sections:['.tree-section','#properties','#stationKeyframes']},
  {id:'production',label:'制作',sections:['#assetIntent','#sceneHandoff','#renderPrep','#timelineDraft','#renderReviewPanel']}
 ];
 const tabs=document.createElement('nav');tabs.className='inspector-tabs';tabs.setAttribute('role','tablist');tabs.setAttribute('aria-label','场景设置');
 const pages=new Map(),buttons=new Map();let currentTab='objects';
 for(const group of groups){
  const button=document.createElement('button');button.type='button';button.id=`inspectorTab-${group.id}`;button.textContent=group.label;button.setAttribute('role','tab');button.setAttribute('aria-controls',`inspectorPage-${group.id}`);
  const page=document.createElement('div');page.id=`inspectorPage-${group.id}`;page.className='inspector-page';page.setAttribute('role','tabpanel');page.setAttribute('aria-labelledby',button.id);page.tabIndex=0;
  for(const selector of group.sections){const section=panels.inspector.querySelector(selector);if(section)page.append(section)}
  if(group.id==='objects'){
   const tree=page.querySelector('.tree-section'),root=document.createElement('details'),summary=document.createElement('summary'),name=document.createElement('span');
   root.id='sceneObjectRoot';root.open=true;name.id='sceneObjectRootTitle';name.textContent=$('title').value;summary.append(name);root.append(summary,page.querySelector('#tree'));tree.querySelector('.section-head').after(root);
   const properties=document.createElement('div');properties.className='scene-object-properties';properties.setAttribute('aria-label','选中对象属性');properties.append(page.querySelector('#properties'),page.querySelector('#stationKeyframes'));page.append(properties);
  }
  button.onclick=()=>selectTab(group.id);
  button.onkeydown=event=>{
   const index=groups.indexOf(group);let next;
   if(event.key==='ArrowRight')next=(index+1)%groups.length;
   if(event.key==='ArrowLeft')next=(index+groups.length-1)%groups.length;
   if(event.key==='Home')next=0;if(event.key==='End')next=groups.length-1;
   if(next===undefined)return;event.preventDefault();selectTab(groups[next].id);buttons.get(groups[next].id).focus();
  };
  pages.set(group.id,page);buttons.set(group.id,button);tabs.append(button);panels.inspector.append(page);
 }
 panels.inspector.querySelector('.inspector-heading').after(tabs);
 function selectTab(id){
  if(!pages.has(id))return;currentTab=id;
  for(const [name,page]of pages){page.hidden=name!==id;const button=buttons.get(name);button.setAttribute('aria-selected',String(name===id));button.tabIndex=name===id?0:-1}
 }
 selectTab(currentTab);
 const desktop=matchMedia('(min-width:1101px)');let inspectorOpen=true,active=null;
 function renderPanels(){
  for(const name of Object.keys(panels)){
   const visible=name==='inspector'&&desktop.matches?inspectorOpen:name===active;
   panels[name].hidden=!visible;toggles[name].setAttribute('aria-expanded',String(visible));toggles[name].classList.toggle('active',visible);
  }
  document.body.classList.toggle('scene-inspector-docked',desktop.matches&&inspectorOpen);
  document.dispatchEvent(new CustomEvent('scene-panel-change',{detail:{active,inspectorOpen:!panels.inspector.hidden}}));
 }
 function focusPanel(kind){if(kind)panels[kind].querySelector('button,input,textarea,select')?.focus({preventScroll:true})}
 function show(kind,{focus=false}={}){
  if(kind!==null&&!panels[kind])return;
  const previous=active;
  if(desktop.matches&&kind==='inspector')inspectorOpen=true;else active=kind;
  renderPanels();if(focus){if(kind)focusPanel(kind);else toggles[previous]?.focus({preventScroll:true})}
 }
 function closeInspector(focus=true){if(desktop.matches)inspectorOpen=false;else if(active==='inspector')active=null;renderPanels();if(focus)toggles.inspector.focus({preventScroll:true})}
 toggles.inspector.onclick=()=>{if(!panels.inspector.hidden)closeInspector();else show('inspector',{focus:true})};
 toggles.timeline.onclick=()=>show(active==='timeline'?null:'timeline',{focus:true});
 $('closeInspector').onclick=()=>closeInspector();
 $('toggleTimelineOverlay').onclick=()=>show(null,{focus:true});
 document.addEventListener('keydown',event=>{
  if(event.key!=='Escape'||event.defaultPrevented||document.querySelector('dialog[open]'))return;
  if(!panels.inspector.hidden&&(panels.inspector.contains(event.target)||!active)){event.preventDefault();closeInspector();return}
  if(active){event.preventDefault();show(null,{focus:true})}
 });
 desktop.addEventListener('change',()=>{const focused=document.activeElement;if(desktop.matches&&active==='inspector'){inspectorOpen=true;active=null}renderPanels();if(focused?.closest('#sceneInspector')&&panels.inspector.hidden)toggles.inspector.focus({preventScroll:true})});
 renderPanels();
 function showInspector(tab){selectTab(tab);show('inspector')}
 return {show,showInspector};
}

// Reuse live controls and handlers; chrome does not create a second scene state.
function installSceneChrome(){
 const $=id=>document.getElementById(id),paths={move:'M12 2v20M2 12h20M8 6l4-4 4 4M8 18l4 4 4-4M6 8l-4 4 4 4M18 8l4 4-4 4',rotate:'M20 8a8 8 0 1 0 0 8M20 2v6h-6',scale:'M3 3h7v7H3ZM14 14h7v7h-7ZM13 3h8v8M21 3l-8 8',resetView:'M8 3H3v5m13-5h5v5M3 16v5h5m13-5v5h-5',drawPath:'M4 19c-3-6 6-2 7-6s-5-5-1-8 8-3 10-1M2 21l4-1-3-3Z',save:'M4 3h14l3 3v15H3V3ZM7 3v6h10V3M7 21v-8h10v8',undo:'M3 10h11a6 6 0 1 1 0 12M3 10l6-6M3 10l6 6',redo:'M21 10H10a6 6 0 1 0 0 12M21 10l-6-6M21 10l-6 6',back:'M13 3h8v8M21 3l-12 12M9 3H3v18h18v-6',sceneMode:'M12 3a3 3 0 1 0 0 6 3 3 0 0 0 0-6M8 20v-6a4 4 0 0 1 8 0v6M6 16c-6 3 0 6 6 6s12-3 6-6',cameraMode:'M4 3h16v18H4ZM4 8h16M4 16h16M8 3v18M16 3v18'};
 for(const [id,path]of Object.entries(paths)){const control=$(id);if(!control)continue;const label=control.getAttribute('aria-label')||control.title||control.textContent.trim();control.setAttribute('aria-label',label);control.title=label;const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');for(const [key,value]of Object.entries({viewBox:'0 0 24 24',fill:'none',stroke:'currentColor','stroke-width':'1.6','stroke-linecap':'round','stroke-linejoin':'round','aria-hidden':'true'}))svg.setAttribute(key,value);const shape=document.createElementNS(svg.namespaceURI,'path');shape.setAttribute('d',path);svg.append(shape);control.replaceChildren(svg);if(id==='sceneMode'||id==='cameraMode'){const text=document.createElement('span');text.textContent=id==='sceneMode'?'场景调度':'机位预演';control.append(text)}}
 for(const id of ['sceneMode','cameraMode','move','rotate','scale'])$(id).setAttribute('aria-pressed',String($(id).classList.contains('active')));
 const arrangeMobileActions=()=>{const menu=document.querySelector('.export-menu>div'),controls=[document.querySelector('.scene-history'),$('back'),$('themeToggle')].filter(Boolean),homes=controls.map(control=>{const anchor=document.createComment('scene action');control.before(anchor);return [control,anchor]}),query=matchMedia('(max-width:620px)');const arrange=()=>{for(const [control,anchor]of homes){if(query.matches)menu.append(control);else anchor.after(control)}};query.addEventListener('change',arrange);arrange()};
 if(!$('themeToggle'))document.addEventListener('DOMContentLoaded',arrangeMobileActions,{once:true});else arrangeMobileActions();
 const transport=document.querySelector('.transport'),settings=document.createElement('details'),summary=document.createElement('summary'),panel=document.createElement('div');settings.id='scenePlaybackSettings';settings.className='scene-playback-settings';summary.textContent='运镜设置';summary.setAttribute('aria-label','运镜与时长设置');panel.className='scene-playback-panel';for(const input of [$('duration'),$('easing')])panel.append(input.closest('label'));settings.append(summary,panel);transport.append(settings);
 document.addEventListener('pointerdown',event=>{if(!settings.contains(event.target))settings.open=false;const exportMenu=document.querySelector('.export-menu');if(!exportMenu.contains(event.target))exportMenu.open=false});
 document.addEventListener('keydown',event=>{if(event.key!=='Escape')return;for(const menu of [settings,document.querySelector('.export-menu')])if(menu.open){event.preventDefault();menu.open=false;menu.querySelector('summary').focus()}});
}
