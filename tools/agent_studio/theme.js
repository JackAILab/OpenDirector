// Presentation wrapper; the existing select remains the source of submitted values.
window.installStudioModelPicker=function(select){
 const trigger=document.createElement('button'),menu=document.createElement('section');
 trigger.type='button';trigger.className='studio-model-picker-trigger';trigger.setAttribute('aria-haspopup','menu');trigger.setAttribute('aria-expanded','false');
 menu.className='studio-image-model-menu studio-model-picker-menu';menu.setAttribute('popover','auto');menu.setAttribute('role','menu');menu.setAttribute('aria-label','选择生成模型');
 const id='studio-model-menu-'+crypto.randomUUID();menu.id=id;trigger.setAttribute('aria-controls',id);select.after(trigger);select.hidden=true;select.classList.add('studio-model-picker-native');document.body.append(menu);
 function sync(){trigger.textContent=(select.selectedOptions[0]?.textContent||'选择模型')+' ⌄';trigger.disabled=select.disabled||!select.options.length;trigger.setAttribute('aria-label','选择模型：'+(select.selectedOptions[0]?.textContent||'读取中'))}
 function rows(){menu.replaceChildren();for(const option of select.options){if(!option.value)continue;const row=document.createElement('button'),mark=document.createElement('span'),copy=document.createElement('span'),title=document.createElement('strong'),description=document.createElement('small');row.type='button';row.disabled=option.disabled;row.dataset.model=option.value;row.setAttribute('role','menuitemradio');row.setAttribute('aria-checked',String(select.value===option.value));mark.className='studio-model-mark';mark.textContent=option.textContent.startsWith('Kling')?'K':option.textContent.slice(0,1);title.textContent=option.textContent;const model=typeof catalog==='undefined'?null:catalog.find(m=>m.id===option.value),durations=model?.manual_durations;description.textContent=option.disabled?'尚未接入':option.dataset.description||(durations?.length?`${durations.length===Math.max(...durations)-Math.min(...durations)+1?Math.min(...durations)+'–'+Math.max(...durations):durations.join(' / ')} 秒 · ${model.audio?'原生音频':'静音视频'}`:'图片生成');copy.append(title,description);row.append(mark,copy);row.onclick=()=>{if(row.disabled)return;select.value=option.value;select.dispatchEvent(new Event('change',{bubbles:true}));sync();menu.hidePopover();trigger.focus()};menu.append(row)}}
 trigger.onclick=()=>{if(menu.matches(':popover-open')){menu.hidePopover();return}rows();menu.showPopover();const r=trigger.getBoundingClientRect();menu.style.width=Math.min(380,innerWidth-24)+'px';menu.style.maxHeight=Math.max(160,Math.min(440,innerHeight-32))+'px';menu.style.left=Math.max(12,Math.min(innerWidth-menu.offsetWidth-12,r.left))+'px';menu.style.top=Math.max(12,Math.min(innerHeight-menu.offsetHeight-12,r.top-menu.offsetHeight-8))+'px';menu.querySelector('[aria-checked=true]:not(:disabled)')?.focus()};
 menu.addEventListener('toggle',()=>trigger.setAttribute('aria-expanded',String(menu.matches(':popover-open'))));menu.onkeydown=e=>{if(!['ArrowDown','ArrowUp','Home','End'].includes(e.key))return;e.preventDefault();const items=[...menu.querySelectorAll('button:not(:disabled)')],at=items.indexOf(document.activeElement);items[e.key==='Home'?0:e.key==='End'?items.length-1:(at+(e.key==='ArrowDown'?1:-1)+items.length)%items.length]?.focus()};
 select.addEventListener('change',sync);const observer=new MutationObserver(sync);observer.observe(select,{childList:true,subtree:true,attributes:true});sync();return {sync,destroy(){observer.disconnect();select.removeEventListener('change',sync);menu.remove();trigger.remove();select.hidden=false;select.classList.remove('studio-model-picker-native')}};
};
(()=>{
 const root=document.documentElement;
 function apply(theme){root.dataset.theme=theme==='light'?'light':'dark';root.style.colorScheme=root.dataset.theme;}
 try{apply(localStorage.getItem('creative-theme'))}catch{apply('dark')}
 document.addEventListener('DOMContentLoaded',()=>{
  const button=document.createElement('button');button.type='button';button.id='themeToggle';
  function label(){button.textContent=root.dataset.theme==='dark'?'☀ 浅色':'☾ 深色';button.setAttribute('aria-label','切换到'+(root.dataset.theme==='dark'?'浅色':'深色')+'界面')}
  button.onclick=()=>{apply(root.dataset.theme==='dark'?'light':'dark');try{localStorage.setItem('creative-theme',root.dataset.theme)}catch{}label()};label();
  (document.querySelector('header nav')||document.querySelector('header'))?.append(button);
  installStudioShell(button);document.documentElement.dataset.shellReady='true';window.revealStudio?.();
 });
})();

/* Shared shell, built around existing controls so service contracts stay intact. */
function installStudioShell(themeButton){
 const create=(tag,cls,text)=>{const e=document.createElement(tag);if(cls)e.className=cls;if(text)e.textContent=text;return e};
 const paths={check:'M21 11a9 9 0 1 1-5-8M8 11l4 4 9-10',plus:'M12 5v14M5 12h14',spark:'m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5Z',cube:'m12 3 9 5v8l-9 5-9-5V8Z M3 8l9 5 9-5 M12 13v8',home:'m3 10 9-7 9 7v10H3Z',folder:'M3 6h7l2 3h9v11H3Z',film:'M4 3h16v18H4Z M4 8h16M4 16h16M8 3v18M16 3v18',arrow:'M12 19V5m-6 6 6-6 6 6',chat:'M21 12a8 8 0 0 1-8 8H4l-2 2v-9A9 9 0 1 1 21 12Z',menu:'M4 6h16M4 12h16M4 18h16',sun:'M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1.5 1.5m11 11L19 19M5 19l1.5-1.5m11-11L19 5'};
 const icon=name=>{const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.classList.add('studio-icon');svg.setAttribute('viewBox','0 0 24 24');svg.setAttribute('fill','none');svg.setAttribute('stroke','currentColor');svg.setAttribute('stroke-width','1.6');svg.setAttribute('stroke-linecap','round');svg.setAttribute('stroke-linejoin','round');svg.setAttribute('aria-hidden','true');const path=document.createElementNS(svg.namespaceURI,'path');path.setAttribute('d',paths[name]||paths.spark);svg.append(path);return svg};
 const link=(label,href,name)=>{const a=create('a','studio-nav-link');a.href=href;a.append(icon(name),create('span','',label));return a};
 if(document.body.classList.contains('skill-home')){
  document.body.classList.add('studio-home');
  const sidebar=create('aside','studio-sidebar');sidebar.setAttribute('aria-label','创作导航');
  const logo=link('VisualAgent','/creative/discover','spark');logo.className='studio-logo';
  const fresh=link('新建项目','/creative?new=1','plus');fresh.classList.add('studio-new');
  const navigation=create('nav','studio-navigation');navigation.setAttribute('aria-label','工作空间');
  const agent=link('VisualAgent','/creative/discover','spark');agent.setAttribute('aria-current','page');
  navigation.append(agent,link('3D-BOX','/creative/scene','cube'),create('div','studio-nav-divider'),link('我的项目','/creative?projects=1','folder'),link('Skill 收藏','#collection','home'));
  const foot=create('div','studio-sidebar-foot');foot.append(link('账户与额度','/account','home'),themeButton);
  sidebar.append(logo,fresh,navigation,foot);document.body.prepend(sidebar);
  const header=document.querySelector('body>header');header.classList.add('studio-home-top');
  const toggle=create('button','studio-nav-toggle');toggle.type='button';toggle.setAttribute('aria-label','展开创作导航');toggle.setAttribute('aria-expanded','false');toggle.append(icon('menu'));toggle.onclick=()=>{const open=document.body.classList.toggle('nav-open');toggle.setAttribute('aria-expanded',String(open));toggle.setAttribute('aria-label',open?'收起创作导航':'展开创作导航')};header.prepend(toggle);
  const closeNavigation=()=>{document.body.classList.remove('nav-open');toggle.setAttribute('aria-expanded','false');toggle.setAttribute('aria-label','展开创作导航')};
  navigation.lastChild.onclick=()=>{document.querySelector('[data-tab="favorites"]')?.click();closeNavigation()};
  const curtain=create('button','studio-nav-curtain');curtain.type='button';curtain.setAttribute('aria-label','关闭创作导航');curtain.onclick=()=>{closeNavigation();toggle.focus()};document.body.append(curtain);
  document.addEventListener('keydown',e=>{if(e.key==='Escape'&&document.body.classList.contains('nav-open'))curtain.click()});
  document.querySelector('.hero h1').textContent='说个想法，开始创作';
  document.querySelector('.hero p').textContent='和导演一起，从一张参考图到一支完整广告。';
  const entry=document.getElementById('entryLayout');entry.classList.add('studio-entry');
  const pathsRow=document.querySelector('.entry-paths');if(pathsRow)document.querySelector('.quick-suggestions').after(pathsRow);
  const config=document.getElementById('entryConfigSummary'),more=create('details','studio-entry-details'),summary=create('summary','','创作配置与费用');
  more.append(summary,config,document.getElementById('modelNote'),document.getElementById('modelCatalog'));document.getElementById('quickForm').after(more);if(pathsRow)more.append(pathsRow);
  document.getElementById('quickForm').addEventListener('submit',()=>{if(['entrySkill','entryVideo'].some(id=>{const select=document.getElementById(id);return !select.value||select.selectedOptions[0]?.disabled}))more.open=true});
  // Featured samples remain available in their own expandable section.
  const samples=document.querySelector('.sample-gallery');samples.open=false;samples.querySelector('summary').textContent='广告样片 · 观看与使用';samples.querySelector('summary').after(document.getElementById('featuredFilm'));
  const prompt=document.getElementById('quickPrompt');prompt.placeholder='描述你的创意，或从下方选择一个 Skill 开始…';
  const send=document.querySelector('#quickForm button[type=submit]');send.textContent='';send.append(icon('arrow'));send.setAttribute('aria-label','和导演聊聊');send.title='和导演聊聊';
  for(const control of document.querySelectorAll('.compose-toolbar .model-control')){const text=[...control.childNodes].find(n=>n.nodeType===3);if(text){control.title=text.textContent;control.querySelector('select')?.setAttribute('aria-label',text.textContent)}}
 }
 if(document.getElementById('trackScroll')&&document.getElementById('monitor')){
  document.body.classList.add('studio-editor');
  const header=document.querySelector('body>header'),library=document.querySelector('.library'),settings=document.getElementById('settings');
  const media=create('button','','素材与字幕');media.id='editorMediaToggle';media.type='button';media.setAttribute('aria-expanded','false');media.setAttribute('aria-controls','editorMediaDrawer');library.id='editorMediaDrawer';
  media.onclick=()=>{const open=document.body.classList.toggle('editor-library-open');media.setAttribute('aria-expanded',String(open))};header.insertBefore(media,settings);
  const close=create('button','editor-library-close','关闭素材');close.type='button';close.onclick=()=>media.click();library.prepend(close);
  document.addEventListener('click',event=>{if(event.target.closest('.clip:not(.rhythm-preview),.caption-list-item,#addCaption')){document.body.classList.add('inspector-open');settings.setAttribute('aria-expanded','true')}});
  // Keep the existing controls and handlers; only reorganize their presentation.
  const transport=document.querySelector('.transport'),editTools=create('div','editor-edit-tools'),playback=create('div','editor-playback'),viewTools=create('div','editor-view-tools');
  editTools.setAttribute('role','group');editTools.setAttribute('aria-label','时间轴编辑工具');playback.setAttribute('role','group');playback.setAttribute('aria-label','时间轴播放');viewTools.setAttribute('role','group');viewTools.setAttribute('aria-label','时间轴视图');
  const editIcons={
   undo:['撤销','M9 5 4 10l5 5 M4 10h10a5 5 0 0 1 0 10'],redo:['重做','m15 5 5 5-5 5 M20 10H10a5 5 0 0 0 0 10'],
   split:['分割 · S','M9 4v16M15 4v16M3 6h3v12H3m18-12h-3v12h3'],clipActions:['片段操作','M4 5h16v14H4Z M7 9h10M7 13h6'],
   rippleDelete:['联动删除 · R','M4 5h5v14H4m16-14h-5v14h5M2 12h6m-3-3 3 3-3 3m17-3h-6m3-3-3 3 3 3'],
   marqueeSelection:['框选片段','M9 4H4v5m11-5h5v5M4 15v5h5m11-5v5h-5'],timelineSnap:['吸附对齐','M5 4v9a7 7 0 0 0 14 0V4h-4v9a3 3 0 0 1-6 0V4Z M5 8h4m6 0h4'],
   timelineGroupAlign:['编组对齐','M4 3v18M7 6h13v4H7Zm0 8h9v4H7Z'],retake:['重拍片段','M6 5H3v5m0-5 4 4a7 7 0 1 1-1 8 M11 9l5 3-5 3Z'],
   earlier:['提前','m10 6-6 6 6 6M4 12h16'],later:['延后','m14 6 6 6-6 6M4 12h16'],
   addCaption:['添加字幕','M5 5h14M12 5v14M8 19h8'],speechCaptions:['口播转字幕','M5 5h14v12H9l-4 3Z M8 9h8m-8 4h5']
  };
  for(const [id,[label,path]] of Object.entries(editIcons)){const control=document.getElementById(id);if(!control)continue;const svg=icon('spark');svg.querySelector('path').setAttribute('d',path);const text=create('span','editor-tool-label',label);control.setAttribute('aria-label',label);control.title=control.title||label;control.classList.add('editor-icon-button');control.replaceChildren(svg,text);editTools.append(control)}
  playback.append(document.getElementById('play'),document.getElementById('clock'));
  const zoom=document.getElementById('zoom');viewTools.append(transport.querySelector('label[for="zoom"]'),zoom,document.getElementById('editorShortcuts'));zoom.setAttribute('aria-label','时间轴缩放');
  transport.replaceChildren(editTools,playback,viewTools);
  installEditorPreview(create,icon,playback);
  // The editor header mirrors the focused film view; secondary tools remain reachable below.
  const editorTitle=header.querySelector('h1'),back=document.getElementById('back'),exportButton=document.getElementById('export');editorTitle.textContent='智能剪辑';
  const exportGroup=create('div','editor-export-group'),exportToggle=create('button','editor-export-toggle','⌄');exportToggle.id='editorExportMenuToggle';exportToggle.type='button';exportToggle.setAttribute('aria-label','导出与保存选项');exportButton.textContent='导出';exportGroup.append(exportButton,exportToggle);
  const toolToggle=create('button','editor-icon-button');toolToggle.id='editorToolsToggle';toolToggle.type='button';const toolsIcon=icon('spark');toolsIcon.querySelector('path').setAttribute('d','M4 7h4m4 0h8M4 17h8m4 0h4M8 4v6m4 4v6');toolToggle.append(toolsIcon);toolToggle.setAttribute('aria-label','更多剪辑工具');toolToggle.title='素材、属性、混音与审阅';viewTools.prepend(toolToggle);
  const popup=(id,label,trigger,above)=>{const panel=create('section','editor-action-popover');panel.id=id;panel.setAttribute('popover','auto');panel.setAttribute('aria-label',label);panel.setAttribute('role','dialog');document.body.append(panel);trigger.setAttribute('popovertarget',id);trigger.setAttribute('aria-haspopup','dialog');trigger.setAttribute('aria-expanded','false');
   const place=()=>{if(!panel.matches(':popover-open'))return;const b=trigger.getBoundingClientRect(),r=panel.getBoundingClientRect();panel.style.left=Math.max(8,Math.min(innerWidth-r.width-8,b.right-r.width))+'px';panel.style.top=Math.max(8,Math.min(innerHeight-r.height-8,above?b.top-r.height-8:b.bottom+8))+'px'};
   panel.addEventListener('beforetoggle',event=>{if(event.newState==='open'){panel.style.left='8px';panel.style.top='8px';requestAnimationFrame(place)}});panel.addEventListener('toggle',()=>{const open=panel.matches(':popover-open');trigger.setAttribute('aria-expanded',String(open));if(open)place()});new ResizeObserver(place).observe(panel);window.addEventListener('resize',place);
   panel.addEventListener('click',event=>{const control=event.target.closest('button');if(control?.parentElement===panel&&!control.disabled&&control.id!=='themeToggle')panel.hidePopover()});return panel};
  const exportMenu=popup('editorExportMenu','导出与保存选项',exportToggle,false);exportMenu.append(document.getElementById('save'),document.getElementById('download'),document.getElementById('toCanvas'));
  const toolMenu=popup('editorToolsMenu','剪辑工具',toolToggle,true);for(const id of ['editorMediaToggle','settings','editorMixerToggle','assistant','review','creativeContract','themeToggle']){const control=document.getElementById(id);if(control)toolMenu.append(control)}
  back.textContent='×';back.classList.add('editor-close-control');back.setAttribute('aria-label','返回画布');back.title='返回画布';
  const editorStatus=document.getElementById('status');editorStatus.classList.add('editor-header-status');editorStatus.setAttribute('role','status');
  const statusVisibility=()=>{editorStatus.title=editorStatus.textContent;editorStatus.classList.toggle('is-idle',!editorStatus.textContent||editorStatus.textContent.startsWith('项目已载入'))};new MutationObserver(statusVisibility).observe(editorStatus,{childList:true,subtree:true,characterData:true});statusVisibility();
  header.replaceChildren(editorTitle,editorStatus,exportGroup,back);
  const timeline=document.querySelector('.timeline'),resize=create('div','editor-timeline-resize');resize.setAttribute('role','separator');resize.setAttribute('aria-label','调整时间轴高度');resize.setAttribute('aria-orientation','horizontal');resize.setAttribute('aria-valuemin','160');resize.setAttribute('aria-valuemax',String(Math.round(innerHeight*.55)));resize.setAttribute('aria-valuenow',String(Math.round(timeline.getBoundingClientRect().height)));resize.tabIndex=0;timeline.prepend(resize);
  const height=value=>{const h=Math.max(160,Math.min(innerHeight*.55,value));timeline.style.height=h+'px';resize.setAttribute('aria-valuemax',String(Math.round(innerHeight*.55)));resize.setAttribute('aria-valuenow',String(Math.round(h)));window.dispatchEvent(new Event('resize'))};
  resize.onpointerdown=e=>{const y=e.clientY,h=timeline.getBoundingClientRect().height;resize.setPointerCapture(e.pointerId);resize.onpointermove=v=>height(h+y-v.clientY);resize.onpointerup=resize.onpointercancel=()=>resize.onpointermove=null};
  resize.onkeydown=e=>{if(['ArrowUp','ArrowDown','Home'].includes(e.key)){e.preventDefault();height(e.key==='Home'?innerHeight*.26:timeline.offsetHeight+(e.key==='ArrowUp'?20:-20))}};
  document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!document.querySelector('dialog[open]')&&!document.querySelector('[popover]:popover-open')&&!document.querySelector('.adviser:not([hidden])')){document.body.classList.remove('editor-library-open','inspector-open');media.setAttribute('aria-expanded','false');settings.setAttribute('aria-expanded','false')}});
 }
 if(document.body.classList.contains('canvas-expanded')){
  document.body.classList.add('studio-workspace');
  const header=document.querySelector('body>header'),panel=document.getElementById('workspaceProjectPanel');
  const links=create('div','studio-project-links');for(const el of [...header.children])if(!el.classList.contains('brand')&&!el.classList.contains('spacer')&&!el.classList.contains('tag')&&el!==themeButton)links.append(el);
  links.append(themeButton);panel?.append(links);
  const brand=header.querySelector('.brand');brand.replaceChildren(icon('spark'),create('span','','VisualAgent'));brand.title='返回 Skill 首页';
  const form=document.querySelector('.director .compose');form.prepend(document.getElementById('creativeStatusButton'));
  const submit=document.getElementById('sendButton');submit.setAttribute('aria-label','发送给创作导演');submit.title='发送给创作导演';submit.replaceChildren(icon('arrow'));
  const chatName=document.querySelector('.director .panehead h2');chatName.replaceChildren(create('span','avatar','✦'),document.createTextNode('VisualAgent'));
  document.querySelector('.director .panehead .muted').textContent='创作导演';
  const projectLabel=document.querySelector('.workspace-project-label');if(projectLabel)projectLabel.textContent='画布';
  // A reopenable shot list belongs to its video node rather than an always-open block.
  const shotFlow=document.getElementById('shotFlow'),fold=create('details','studio-shot-list');
  fold.append(create('summary','','查看分镜 · 画面与声音'));shotFlow.before(fold);fold.append(shotFlow);
  const settings=document.querySelector('.creative-settings');if(settings){settings.setAttribute('popover','auto');settings.id='studioSettings';
   const heading=create('div','studio-settings-heading');heading.append(create('strong','','创作设置'));const close=create('button','','关闭');close.type='button';close.onclick=()=>{settings.hidePopover();settings.open=false};heading.append(close);settings.querySelector('summary').after(heading);
   const trigger=document.getElementById('creativeStatusButton'),original=trigger.onclick;trigger.onclick=()=>{original?.();settings.open=true;settings.showPopover()};
  }
  installCanvasChrome(create,icon);
  installCanvasEntry(create,icon);
  installCreationModes(create,icon);
  // Project navigation is explicit; a plain /creative link continues the latest task.
  if(new URLSearchParams(location.search).get('projects')==='1')document.getElementById('projectsButton')?.click();
 }
}


// Presentation adapters retain each original control and its service handler.
function installCanvasChrome(create,icon){
 const $=id=>document.getElementById(id),body=document.body,toolbar=document.querySelector('.canvas-toolbar');
 const paths={check:'M21 11a9 9 0 1 1-5-8M8 11l4 4 9-10',plus:'M12 4v16M4 12h16',pointer:'m5 3 15 9-8 2-3 7Z',video:'M3 5h13v14H3Z m13 5 5-3v10l-5-3',timeline:'M3 5h18v14H3Z M8 5v14m8-14v14M3 10h18',scissors:'M8 8a3 3 0 1 1-6 0 3 3 0 0 1 6 0Zm0 8a3 3 0 1 1-6 0 3 3 0 0 1 6 0ZM7 10l14 11M7 14 21 3',undo:'m8 4-5 5 5 5M3 9h10a7 7 0 0 1 0 14',redo:'m16 4 5 5-5 5M21 9H11a7 7 0 0 0 0 14',layout:'M3 4h18v16H3ZM15 4v16',sliders:'M3 6h6m4 0h8M3 12h12m4 0h2M3 18h3m4 0h11M9 3v6m6 0v6M6 15v6',history:'M3 4v5h5M3 9a9 9 0 1 1 0 6M12 7v6l4 2',keyboard:'M3 5h18v14H3ZM6 8h1m3 0h1m3 0h1m3 0h1M6 11h1m3 0h1m3 0h1m3 0h1M7 16h10',user:'M16 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0ZM4 21v-3a8 8 0 0 1 16 0v3',assets:'M3 4h18v16H3ZM8 4v16',fit:'M8 3H3v5m13-5h5v5M3 16v5h5m13-5v5h-5',hand:'M8 13V5a2 2 0 0 1 4 0v7-9a2 2 0 0 1 4 0v9-6a2 2 0 0 1 4 0v9c0 8-10 10-14 4l-4-5c-1-2 1-4 3-2l3 3',skill:'M5 3h10l4 4v14H5ZM14 3v5h5M8 12h8m-8 4h6',cube:'m12 3 9 5v8l-9 5-9-5V8ZM3 8l9 5 9-5M12 13v8'};
 function decorate(control,name,label){if(!control)return;const svg=`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="black" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round"><path d="${paths[name]}"/></svg>`;control.style.setProperty('--control-icon',`url("data:image/svg+xml,${encodeURIComponent(svg)}")`);control.classList.add('studio-icon-control');control.setAttribute('aria-label',label);control.title=label;}
 const makeButton=(id,name,label,fn)=>{const b=create('button');b.type='button';b.id=id;b.textContent=label;b.onclick=fn;decorate(b,name,label);return b};
 for(const [id,name,label] of [['canvasSelectTool','pointer','框选素材 (V)'],['canvasHandTool','hand','平移画布 (H)'],['canvasVideoInputs','video','视频参考输入'],['timelineToggle','timeline','时间轴'],['inlineEditButton','scissors','打开内嵌剪辑'],['canvasUndo','undo','撤销画布修改'],['canvasRedo','redo','重做画布修改'],['chatToggle','layout','切换对话布局']])decorate($(id),name,label);
 decorate(document.querySelector('#canvasAddMenu>summary'),'plus','添加素材');
 const menu=document.querySelector('#workspaceProjectMenu>summary'),title=$('projectTitle'),label=menu.querySelector('.workspace-project-label');menu.append(title,label);label.textContent='画布 1';
 const brand=document.querySelector('body>header .brand');brand.setAttribute('aria-label','VisualAgent 首页');brand.title='VisualAgent 首页';
 const layout=$('chatToggle');menu.closest('details').after(layout);
 const account=create('a','studio-canvas-account');account.href='/account';account.append(icon('spark'));account.title='账户与额度';account.setAttribute('aria-label','账户与额度');document.querySelector('.projectbar').append(account);
 // Keep account actions in the top-right island and production actions with the conversation.
 const accountGroup=create('nav','studio-canvas-account-actions');accountGroup.setAttribute('aria-label','账户操作');
 for(const [label,href] of [['积分明细','/account?tab=usage'],['账户中心','/account']]){const a=create('a','studio-account-link',label);a.href=href;accountGroup.append(a)}
 const balance=create('a','studio-account-link studio-account-balance','积分');balance.href='/account?tab=usage';balance.hidden=true;accountGroup.append(balance,account);document.querySelector('.projectbar').append(accountGroup);
 // Project links contain only the saved project id; access remains owner-scoped.
 paths.share='M18 8a3 3 0 1 0 0-6 3 3 0 0 0 0 6Zm0 14a3 3 0 1 0 0-6 3 3 0 0 0 0 6ZM6 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6Zm2.6-4.5 6.8-4M8.6 13.5l6.8 4';
 const share=makeButton('studioShareProject','share','分享项目链接',()=>{
  if(!project?.id){toast('创建项目后可以复制画布链接');return}
  if(sharePanel.matches(':popover-open')){sharePanel.hidePopover();return}
  shareProject=project.id;shareTitle.textContent=project.brief?.product||'当前项目';
  const url=new URL('/creative',location.origin);url.searchParams.set('project',shareProject);url.searchParams.set('view','canvas');shareLink.value=url.href;shareStatus.textContent='';sharePanel.showPopover();
 });
 share.classList.add('studio-project-share');share.setAttribute('aria-controls','studioSharePanel');share.setAttribute('aria-expanded','false');accountGroup.prepend(share);
 const sharePanel=create('section','studio-share-panel');sharePanel.id='studioSharePanel';sharePanel.setAttribute('popover','auto');sharePanel.setAttribute('aria-labelledby','studioShareHeading');
 const shareHead=create('div','studio-share-head'),shareHeading=create('h3','','项目链接');shareHeading.id='studioShareHeading';
 const closeShare=create('button','','×');closeShare.type='button';closeShare.setAttribute('aria-label','关闭项目链接');closeShare.onclick=()=>{sharePanel.hidePopover();share.focus()};shareHead.append(shareHeading,closeShare);
 const shareTitle=create('p','studio-share-title'),shareLink=create('input'),shareStatus=create('p','studio-share-status'),shareCopy=create('button','studio-share-copy','复制链接');let shareProject='';
 shareLink.readOnly=true;shareLink.setAttribute('aria-label','当前项目链接');shareLink.onclick=()=>shareLink.select();shareStatus.setAttribute('role','status');shareCopy.type='button';
 shareCopy.onclick=async()=>{if(!project?.id||project.id!==shareProject){sharePanel.hidePopover();return}const pid=shareProject,url=shareLink.value;shareCopy.disabled=true;try{await globalThis.navigator.clipboard.writeText(url);if(sharePanel.matches(':popover-open')&&shareProject===pid)shareStatus.textContent='链接已复制'}catch{if(sharePanel.matches(':popover-open')&&shareProject===pid){shareLink.focus();shareLink.select();shareStatus.textContent='未能自动复制，请复制已选中的链接'}}finally{shareCopy.disabled=false}};
 sharePanel.append(shareHead,shareTitle,create('p','studio-share-note','链接打开项目已保存的画布。需要登录拥有访问权限的账户；复制链接不会公开素材。'),shareLink,shareCopy,shareStatus);document.body.append(sharePanel);
 sharePanel.addEventListener('toggle',()=>{const open=sharePanel.matches(':popover-open');share.setAttribute('aria-expanded',String(open));if(!open){shareProject='';shareLink.value='';shareStatus.textContent=''}});
 const syncShare=()=>{if(sharePanel.matches(':popover-open')&&project?.id!==shareProject)sharePanel.hidePopover()};document.addEventListener('creative-state-change',syncShare);document.addEventListener('creative-status-sync',syncShare);
 const showLogin=()=>{account.hidden=true;for(const el of accountGroup.querySelectorAll('.studio-account-link'))el.hidden=true;let login=accountGroup.querySelector('.studio-login-link');if(!login){login=create('a','studio-account-link studio-login-link','注册 / 登录');accountGroup.append(login)}login.hidden=false;login.href='/creative/login?return_to='+encodeURIComponent(location.pathname+location.search+location.hash)};
 window.addEventListener('creative-login-required',showLogin);
 const token=sessionStorage.getItem('h3_api_key');if(!token)showLogin();if(token)fetch('/me',{headers:{Authorization:'Bearer '+token},signal:AbortSignal.timeout(15000)}).then(r=>r.ok?r.json():null).then(me=>{if(!me){showLogin();return}balance.textContent='ϟ '+(me.unlimited?'无限积分':Number(me.remaining).toLocaleString());balance.hidden=false;account.replaceChildren(document.createTextNode((me.email||'V')[0].toUpperCase()));account.setAttribute('role','button');createStudioAccountMenu(account,me,[{id:'account',label:'账户中心',run:()=>location.href='/account'},{id:'usage',label:'积分明细',run:()=>location.href='/account?tab=usage'},{id:'projects',label:'我的项目',run:()=>location.href='/creative/discover?view=projects'},{id:'assets',label:'我的资产',run:()=>location.href='/creative/discover?view=assets'},{id:'theme',label:()=>document.documentElement.dataset.theme==='dark'?'切换到浅色界面':'切换到深色界面',run:()=>$('themeToggle').click(),keepOpen:true}])}).catch(()=>{});
 const production=create('div','studio-production-actions');production.id='studioProductionActions';
 const review=makeButton('studioFilmPlan','skill','查看拍摄方案',()=>{const b=[...$('workspaceProjectPanel').querySelectorAll('button')].find(b=>b.textContent==='整片拍摄方案');b?.click()});production.append(review,$('executeButton'),$('stopButton'));document.querySelector('.director .compose').before(production);
 const addPanel=$('canvasAddMenuPanel'),uploadProduct=makeButton('studioUploadProduct','plus','上传商品参考图',()=>$('referenceFile').click());uploadProduct.classList.remove('studio-icon-control');addPanel.prepend(uploadProduct);
 const productSettings=$('productReferenceSettings');addPanel.append(productSettings);document.body.append($('productReferencePanel'));
 // Original selectors keep their model handlers, but never occupy the media canvas.
 const controls=document.querySelector('.video-node-controls');if(controls){controls.hidden=true;$('workspaceProjectPanel').append(controls)}
 const outputHead=document.querySelector('.canvas-output>.canvas-card-head');outputHead.querySelector('strong').textContent='成片';outputHead.querySelector('.canvas-generate')?.remove();
 $('canvasViewMenuPanel').append(document.querySelector('.canvas-history'));
 const navigator=$('canvasNavigatorToggle');navigator.textContent='资产管理';navigator.prepend(icon('folder'));
 const fit=makeButton('canvasFitShortcut','fit','适应画布',()=>document.dispatchEvent(new Event('creative-fit-canvas')));navigator.after(fit);
 const zoom=document.querySelector('#canvasViewMenu>summary');zoom.setAttribute('aria-label','画布缩放与排版');zoom.title='缩放、自动排版与视图';
 const head=document.querySelector('.director .panehead'),chatName=head.querySelector('h2');chatName.replaceChildren();
 const updateTitle=()=>{chatName.textContent=title.textContent||'创作导演';chatName.title=chatName.textContent};new MutationObserver(updateTitle).observe(title,{childList:true,characterData:true,subtree:true});updateTitle();head.querySelector('.muted').hidden=true;
 const history=makeButton('studioChatHistory','history','查看最早对话',()=>{const conversation=document.querySelector('.conversation');conversation.scrollTop=0;conversation.focus({preventScroll:true})});
 const syncHistory=()=>{history.disabled=document.querySelectorAll('.conversation>.bubble').length<2;history.title=history.disabled?'暂无更早的对话':'查看最早对话'};new MutationObserver(syncHistory).observe(document.querySelector('.conversation'),{childList:true});syncHistory();
 const settings=makeButton('studioChatSettings','sliders','创作设置',()=>$('creativeStatusButton').click());head.insertBefore(history,head.lastElementChild);head.insertBefore(settings,head.lastElementChild);
 paths.expand='M14 3h7v7m0-7-7 7M10 21H3v-7m0 7 7-7';paths.contract='M21 3l-7 7m0-7v7h7M3 21l7-7m-7 0h7v7';
 const director=head.closest('.director'),conversation=director.querySelector('.conversation');
 const expandChat=makeButton('studioChatExpand','expand','放大对话',()=>setChatExpanded(!body.classList.contains('studio-chat-expanded')));expandChat.setAttribute('aria-expanded','false');expandChat.setAttribute('aria-controls','conversation');head.insertBefore(expandChat,head.lastElementChild);
 let chatLayoutEpoch=0;
 function setChatExpanded(expanded){
  if(body.classList.contains('studio-chat-expanded')===expanded)return;
  const epoch=++chatLayoutEpoch,box=conversation.getBoundingClientRect(),atEnd=conversation.scrollHeight-conversation.scrollTop-conversation.clientHeight<8;
  const anchor=[...conversation.children].find(e=>{const r=e.getBoundingClientRect();return r.bottom>box.top&&r.top<box.bottom}),offset=anchor?anchor.getBoundingClientRect().top-box.top:0;
  document.dispatchEvent(new Event('creative-conversation-layout-start'));
  body.classList.toggle('studio-chat-expanded',expanded);decorate(expandChat,expanded?'contract':'expand',expanded?'恢复对话大小':'放大对话');expandChat.setAttribute('aria-expanded',String(expanded));
  requestAnimationFrame(()=>{if(epoch!==chatLayoutEpoch)return;if(atEnd)conversation.scrollTop=conversation.scrollHeight;else if(anchor?.isConnected)conversation.scrollTop+=anchor.getBoundingClientRect().top-conversation.getBoundingClientRect().top-offset;requestAnimationFrame(()=>{if(epoch===chatLayoutEpoch)document.dispatchEvent(new Event('creative-conversation-layout-end'))})});
 }
 layout.addEventListener('click',()=>{if(body.classList.contains('chat-collapsed'))setChatExpanded(false)});
 document.addEventListener('keydown',event=>{if(event.key!=='Escape'||event.defaultPrevented||!body.classList.contains('studio-chat-expanded')||document.querySelector('dialog[open],:popover-open'))return;event.preventDefault();setChatExpanded(false);expandChat.focus({preventScroll:true})});

 const form=document.querySelector('.director .compose'),row=form.querySelector('.row');
 const upload=makeButton('studioChatAdd','plus','添加参考素材',()=>{const m=$('canvasAddMenu');m.open=true;m.querySelector('summary').focus()});
 const model=makeButton('studioChatModel','cube','选择生成模型',()=>{renderModels();modelPicker.showPopover()});
 const skill=makeButton('studioChatSkill','skill','选择创作 Skill',()=>document.dispatchEvent(new Event('creative-open-skill-picker')));
 const modelPicker=create('section','studio-model-picker');modelPicker.id='studioCanvasModels';modelPicker.setAttribute('popover','auto');modelPicker.setAttribute('aria-label','选择生成模型');model.setAttribute('aria-controls',modelPicker.id);model.setAttribute('aria-expanded','false');
 const pickerHead=create('div','studio-settings-heading');pickerHead.append(create('strong','','选择模型'));const pickerClose=create('button','','关闭');pickerClose.type='button';pickerClose.onclick=()=>modelPicker.hidePopover();pickerHead.append(pickerClose);
 const modelTabs=create('div','studio-model-tabs');modelTabs.setAttribute('role','tablist');modelTabs.setAttribute('aria-label','生成类型');const modelRows=create('div','studio-model-rows');modelRows.setAttribute('role','tabpanel');modelRows.id='studioCanvasModelRows';let modelKind='video';
 for(const [kind,text] of [['image','图片'],['video','视频']]){const tab=create('button','',text);tab.type='button';tab.dataset.kind=kind;tab.id='studioModelTab-'+kind;tab.setAttribute('role','tab');tab.setAttribute('aria-controls',modelRows.id);tab.onclick=()=>{modelKind=kind;renderModels()};tab.onkeydown=e=>{if(['ArrowLeft','ArrowRight','Home','End'].includes(e.key)){e.preventDefault();modelKind=e.key==='Home'?'image':e.key==='End'?'video':modelKind==='video'?'image':'video';renderModels();modelTabs.querySelector('[data-kind="'+modelKind+'"]').focus()}};modelTabs.append(tab)}
 function renderModels(){
  for(const tab of modelTabs.children){tab.setAttribute('aria-selected',String(tab.dataset.kind===modelKind));tab.tabIndex=tab.dataset.kind===modelKind?0:-1}modelRows.setAttribute('aria-labelledby','studioModelTab-'+modelKind);
  const select=$(modelKind==='video'?'videoModelSelect':'imageModelSelect');modelRows.replaceChildren();
  if(!select?.options.length){const state=select?.dataset.catalogState||'loading',note=create('p','studio-model-empty',state==='loading'?'正在读取模型…':state==='error'?'模型读取失败，请重试。':'当前没有'+(modelKind==='video'?'视频':'图片')+'模型。');note.setAttribute('role','status');modelRows.append(note);if(state!=='loading'){const retry=create('button','studio-model-retry','重新读取模型');retry.type='button';retry.onclick=()=>document.dispatchEvent(new Event('creative-reload-model-catalog'));modelRows.append(retry)}return}
  for(const option of select.options){const b=create('button','studio-model-choice');b.type='button';b.disabled=select.disabled||option.disabled;b.setAttribute('aria-pressed',String(option.selected));b.setAttribute('aria-label','选择'+(modelKind==='video'?'视频':'图片')+'模型 '+option.textContent);const symbol=create('span','studio-model-symbol');symbol.append(icon(modelKind==='video'?'film':'cube'));const copy=create('span','studio-model-copy');copy.append(create('strong','',option.textContent));const card=[...document.querySelectorAll('#modelDialog article')].find(c=>c.dataset.model===option.value);const detail=card?.querySelectorAll('p')[1]?.textContent;copy.append(create('small','',detail||'查看模型与费用'));b.append(symbol,copy,create('span','studio-model-check',option.selected?'✓':'+'));
   b.onclick=async()=>{if(select.disabled||option.disabled)return;if(select.value!==option.value){select.value=option.value;await select.onchange?.()}modelPicker.hidePopover();model.focus()};modelRows.append(b)
  }
 }
 modelPicker.append(pickerHead,modelTabs,modelRows);body.append(modelPicker);modelPicker.addEventListener('toggle',()=>model.setAttribute('aria-expanded',String(modelPicker.matches(':popover-open'))));
 for(const id of ['videoModelSelect','imageModelSelect']){const select=$(id);if(select)new MutationObserver(()=>{if(modelPicker.matches(':popover-open'))renderModels()}).observe(select,{childList:true,attributes:true,subtree:true,attributeFilter:['disabled','data-catalog-state']})}
 const approval=makeButton('studioChatApproval','hand','选择审批方式',()=>document.dispatchEvent(new Event('creative-open-approval-picker')));approval.setAttribute('aria-controls','canvasApprovalPicker');approval.setAttribute('aria-expanded','false');skill.setAttribute('aria-controls','canvasSkillPicker');skill.setAttribute('aria-expanded','false');
 const syncApproval=()=>{const mode=$('creativeStatusButton').textContent.includes('自动审批')?'auto':'manual';decorate(approval,mode==='auto'?'check':'hand','选择审批方式');approval.title=mode==='auto'?'自动审批 · 单次预算':'手动审批 · 生成前确认';approval.dataset.approval=mode};new MutationObserver(syncApproval).observe($('creativeStatusButton'),{childList:true,subtree:true,characterData:true});syncApproval();
 row.prepend(upload,model,skill,approval);const prompt=$('message');prompt.placeholder='开始你的创作，描述画面、动作或想修改的细节…';
 const help=create('dialog','studio-shortcut-dialog');help.id='studioCanvasHelp';help.setAttribute('aria-label','画布操作与快捷键');
 const helpHead=create('div','studio-settings-heading');helpHead.append(create('strong','','画布操作'));const close=create('button','','关闭');close.type='button';close.onclick=()=>help.close();helpHead.append(close);help.append(helpHead);
 const shortcuts=create('dl');for(const [key,value] of [['双击 / 右键空白','在此处添加素材'],['Shift + F10','画布聚焦时打开添加菜单'],['H / V','切换平移 / 框选工具'],['按住空格 + 拖动','临时平移画布'],['拖动空白','平移画布'],['Ctrl / ⌘ + 滚轮','缩放画布'],['Shift + 点击 / 拖动','多选素材'],['Ctrl / ⌘ + Z','撤销画布修改'],['Ctrl / ⌘ + Shift + Z','重做画布修改'],['/','查找素材'],['Esc','关闭菜单或取消选择']])shortcuts.append(create('dt','',key),create('dd','',value));help.append(shortcuts);body.append(help);
 // The task inspector belongs to the tool dock; the account island stays free of task chrome.
 const task=$('productionTask'),taskPanel=$('productionTaskPanel'),taskSummary=task.querySelector(':scope>summary');
 paths.clock='M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0ZM12 6v6l4 3';
 task.classList.add('canvas-task-tool');decorate(taskSummary,'clock','制作记录与进度');toolbar.append(task);
 taskPanel.setAttribute('popover','auto');taskPanel.setAttribute('role','dialog');
 const taskState=create('p','studio-task-current');taskPanel.querySelector('.production-task-panel-head').after(taskState);
 function placeTaskPanel(){if(!taskPanel.matches(':popover-open'))return;const anchor=taskSummary.getBoundingClientRect(),r=taskPanel.getBoundingClientRect();taskPanel.style.left=Math.max(12,Math.min(innerWidth-r.width-12,anchor.right-r.width))+'px';taskPanel.style.top=Math.max(12,Math.min(innerHeight-r.height-12,anchor.top-r.height-12))+'px'}
 task.addEventListener('toggle',()=>{if(task.open){if(!taskPanel.matches(':popover-open'))taskPanel.showPopover();placeTaskPanel()}else if(taskPanel.matches(':popover-open'))taskPanel.hidePopover()});
 taskPanel.addEventListener('toggle',()=>{if(!taskPanel.matches(':popover-open'))task.open=false;else placeTaskPanel()});
 new ResizeObserver(placeTaskPanel).observe(taskPanel);window.addEventListener('resize',placeTaskPanel);
 const updateTaskLabel=()=>{const state=[task.querySelector('.production-task-title').textContent,task.querySelector('.production-task-progress').textContent].filter(Boolean).join(' · ');taskState.textContent=state;taskSummary.title='制作记录与进度 · '+state;taskSummary.setAttribute('aria-label',taskSummary.title)};
 new MutationObserver(updateTaskLabel).observe(task.querySelector('.production-task-summary'),{childList:true,subtree:true,characterData:true});updateTaskLabel();
 toolbar.append(makeButton('studioCanvasShortcuts','keyboard','画布快捷键',()=>help.showModal()));
}

/* Shared authenticated account popover; actions use the page's existing navigation. */
function createStudioAccountMenu(trigger,profile,actions){
 const node=(tag,cls,text)=>{const e=document.createElement(tag);e.className=cls||'';if(text)e.textContent=text;return e};
 const panel=node('section','studio-user-menu');panel.id='studioAccountMenu';panel.setAttribute('popover','auto');panel.setAttribute('role','dialog');panel.setAttribute('aria-label','账户菜单');
 const identity=node('div','studio-user-identity'),avatar=node('span','studio-user-avatar',(profile.email||'V')[0].toUpperCase()),copy=node('div');copy.append(node('strong','studio-user-name',profile.email||'当前账户'),node('span','studio-user-role',profile.role==='admin'?'超级管理员':'创作者'));identity.append(avatar,copy);const balance=node('div','studio-user-quota');balance.append(node('span','','可用积分'),node('strong','',profile.unlimited?'无限积分':Number.isFinite(Number(profile.remaining))&&profile.remaining!==null?Number(profile.remaining).toLocaleString():'—'));panel.append(identity,balance);
 const controls=[];for(const action of actions){const b=node('button','studio-user-action');b.type='button';b.dataset.accountAction=action.id;b.onclick=()=>{if(!action.keepOpen)panel.hidePopover();action.run();paint()};panel.append(b);controls.push([b,action])}
 function paint(){for(const [b,a]of controls){const label=typeof a.label==='function'?a.label():a.label;b.textContent=label;b.setAttribute('aria-label',label)}}
 function place(){if(!panel.matches(':popover-open'))return;const r=panel.getBoundingClientRect(),a=trigger.getBoundingClientRect();panel.style.left=Math.max(8,Math.min(innerWidth-r.width-8,a.right-r.width))+'px';panel.style.top=Math.max(8,Math.min(innerHeight-r.height-8,a.bottom+8))+'px'}
 paint();document.body.append(panel);trigger.setAttribute('aria-label','打开账户菜单');trigger.setAttribute('aria-haspopup','dialog');trigger.setAttribute('aria-controls',panel.id);trigger.setAttribute('aria-expanded','false');trigger.setAttribute('popovertarget',panel.id);
 trigger.onclick=e=>{e.preventDefault();panel.togglePopover()};trigger.onkeydown=e=>{if(trigger.tagName==='A'&&e.key===' '){e.preventDefault();trigger.click()}};
 panel.addEventListener('beforetoggle',e=>{trigger.setAttribute('aria-expanded',String(e.newState==='open'));if(e.newState==='open'){paint();panel.style.left='8px';panel.style.top='8px';requestAnimationFrame(place)}});panel.addEventListener('toggle',()=>{trigger.setAttribute('aria-expanded',String(panel.matches(':popover-open')));place()});const observer=new ResizeObserver(place);observer.observe(panel);window.addEventListener('resize',place);
 return {destroy(){observer.disconnect();window.removeEventListener('resize',place);panel.remove();trigger.onclick=null;trigger.onkeydown=null;for(const attr of ['aria-haspopup','aria-controls','aria-expanded','popovertarget'])trigger.removeAttribute(attr)}};
}


// The first message uses the same creation controls and submit handler as before.
// Only its presentation moves into the Agent composer; no project or model call
// is made by opening, configuring, or dismissing this entry.
function installCanvasEntry(create,icon){
 const $=id=>document.getElementById(id),form=$('createForm'),director=document.querySelector('.director');
 if(!form||!director)return;
 const brief=$('initialBrief'),file=$('initialReference'),add=$('initialReferenceButton'),submit=$('createButton');
 const selectors=['initialSkill','provider','initialApproval','aspect','duration'].map($);
 $('provider').required=false; // Availability is validated by the original submit handler.
 const reference=create('div','studio-entry-reference');reference.hidden=true;
 const referenceMode=create('small','studio-entry-reference-mode'),referenceList=create('div','studio-entry-reference-list');reference.append(referenceMode,referenceList);file.multiple=true;
 const roles={product:'商品',person:'人物',scene:'场景',style:'风格',reference:'其他参考'};let referenceItems=[],referenceDraftStarted=false,referenceDraftPending=false,referenceDraftError=false,referenceDraftEpoch=0;
 form.getReferenceInputs=()=>{if(referenceDraftPending)throw Error('参考图片仍在载入，请稍候');if(referenceDraftError)throw Error('参考图片未能载入，请重试或清空待恢复图片');return referenceItems.map(({file,role,instruction})=>({file,role,instruction}))};
 const config=create('div','studio-entry-config'),actions=create('div','studio-entry-actions');
 brief.setAttribute('aria-label','产品与创作目标');brief.placeholder='开始你的创作，描述画面、动作或想修改的细节…';brief.rows=4;
 add.removeAttribute('style');add.setAttribute('aria-label','添加商品参考图');add.title='添加参考图 · JPEG、PNG、WebP，最大 4 MB';add.replaceChildren(icon('plus'));
 submit.replaceChildren(icon('arrow'));submit.setAttribute('aria-label','发送创作需求');submit.title='发送创作需求';
 const exit=$('closeNew');exit.textContent='返回首页';exit.className='studio-entry-exit';
 const note=create('p','studio-entry-note','发送后先和导演确认方案，生成视频前确认费用。');note.id='studioEntryNote';brief.setAttribute('aria-describedby',note.id);
 actions.append(add,create('span','spacer'),submit);
 form.replaceChildren(reference,brief,config,actions,note,file,...selectors,$('modelPrice'),exit);form.classList.add('studio-entry-compose');director.append(form);
 for(const select of selectors){select.classList.add('studio-entry-native');select.tabIndex=-1;select.setAttribute('aria-hidden','true')}
 $('modelPrice').hidden=true;
 const picker=create('section','studio-entry-picker');picker.id='studioEntryPicker';picker.setAttribute('popover','auto');picker.setAttribute('role','dialog');picker.setAttribute('aria-label','创作设置');
 const heading=create('div','canvas-picker-heading'),title=create('strong'),close=create('button','','关闭');close.type='button';close.onclick=()=>picker.hidePopover();heading.append(title,close);
 const search=create('input');search.type='search';search.placeholder='搜索 Skill';search.setAttribute('aria-label','搜索新创作 Skill');
 const list=create('div','studio-entry-choices'),hint=create('p','studio-entry-note');picker.append(heading,search,list,hint);document.body.append(picker);
 const labels={initialSkill:'选择 Skill',provider:'选择视频模型',initialApproval:'制作审批',aspect:'画面比例',duration:'成片时长'};
 let active=null,origin=null;
 const buttons=new Map();
 function renderChoices(){
  if(!active)return;list.replaceChildren();
  const options=[...active.options].filter(o=>!search.value||o.textContent.toLowerCase().includes(search.value.toLowerCase()));
  for(const option of options){const button=create('button','studio-entry-choice');button.type='button';button.dataset.value=option.value;button.disabled=active.disabled||option.disabled||!option.value;button.setAttribute('aria-pressed',String(option.selected));button.append(create('span','',option.textContent),create('span','',option.selected?'✓':'+'));button.onclick=()=>{if(active.disabled||option.disabled)return;active.value=option.value;active.dispatchEvent(new Event('change',{bubbles:true}));picker.hidePopover();origin?.focus()};list.append(button)}
  if(!options.length)list.append(create('p','studio-entry-note','没有匹配的选项'));
  if(active.id==='initialSkill'&&active.disabled){const retry=create('button','studio-entry-choice','重新读取 Skill');retry.type='button';retry.onclick=()=>document.dispatchEvent(new Event('creative-reload-skills'));list.append(retry)}
  hint.textContent=active.id==='provider'?$('modelPrice').textContent:active.id==='initialApproval'?'自动审批也需要在出方案前明确授权单次生成预算。':active.id==='initialSkill'&&active.disabled?'Skill 正在读取，读取完成后即可选择。':'';
 }
 search.oninput=renderChoices;
 for(const select of selectors){
  const button=create('button','studio-entry-setting');button.type='button';button.id='entry-'+select.id;button.setAttribute('aria-controls',picker.id);button.setAttribute('aria-expanded','false');buttons.set(select,button);config.append(button);
  const sync=()=>{button.textContent=(select.selectedOptions[0]?.textContent||labels[select.id]).split(' · ')[0];button.title=labels[select.id]+' · '+(select.selectedOptions[0]?.textContent||'正在读取');button.setAttribute('aria-label',button.title);if(active===select&&picker.matches(':popover-open'))renderChoices()};
  button.onclick=()=>{active=select;origin=button;title.textContent=labels[select.id];picker.setAttribute('aria-label',labels[select.id]);search.hidden=select.id!=='initialSkill';search.value='';renderChoices();picker.showPopover();if(!search.hidden)search.focus();else list.querySelector('button:enabled')?.focus()};
  select.addEventListener('change',sync);new MutationObserver(sync).observe(select,{childList:true,subtree:true,attributes:true,attributeFilter:['disabled']});sync();
 }
 picker.addEventListener('toggle',()=>{for(const [select,button]of buttons)button.setAttribute('aria-expanded',String(picker.matches(':popover-open')&&active===select))});
 const referenceEditor=create('section','studio-entry-picker studio-entry-reference-editor');referenceEditor.id='studioEntryReferenceEditor';referenceEditor.setAttribute('popover','auto');referenceEditor.setAttribute('role','dialog');referenceEditor.setAttribute('aria-label','参考图用途');
 const refHead=create('div','canvas-picker-heading'),refTitle=create('strong'),refDone=create('button','','完成');refDone.type='button';refDone.onclick=()=>referenceEditor.hidePopover();refHead.append(refTitle,refDone);
 const refImage=create('img'),refRole=create('select'),refInstruction=create('textarea'),refOrder=create('div','studio-entry-reference-order');refRole.setAttribute('aria-label','参考图用途');refInstruction.setAttribute('aria-label','参考图保留要求');refInstruction.placeholder='希望保留哪些外观、动作或场景特征？';refInstruction.maxLength=240;refInstruction.rows=3;
 for(const [value,label]of Object.entries(roles)){const option=create('option','',label);option.value=value;refRole.append(option)}
 const previous=create('button','','向前一张'),next=create('button','','向后一张');previous.type=next.type='button';refOrder.append(previous,next);
 referenceEditor.append(refHead,refImage,create('label','','用途'),refRole,create('label','','保留要求 · 可选'),refInstruction,refOrder);document.body.append(referenceEditor);let editingReference=null;
 const refCurrent=()=>referenceItems.includes(editingReference)&&document.body.dataset.newEntry==='true'&&!busy;
 function syncRefEditor(){const index=referenceItems.indexOf(editingReference);refTitle.textContent='参考图片 '+(index+1);previous.disabled=index<=0;next.disabled=index===referenceItems.length-1;}
 refRole.onchange=()=>{if(refCurrent()){editingReference.role=refRole.value;syncReference()}};refInstruction.oninput=()=>{if(refCurrent()){editingReference.instruction=refInstruction.value;syncReference()}};
 function moveReference(delta){if(!refCurrent())return;const index=referenceItems.indexOf(editingReference),target=index+delta;if(target<0||target>=referenceItems.length)return;[referenceItems[index],referenceItems[target]]=[referenceItems[target],referenceItems[index]];syncReference();syncRefEditor()}
 previous.onclick=()=>moveReference(-1);next.onclick=()=>moveReference(1);
 function syncReferenceMode(){
  const spec=catalog.find(m=>m.id===$('provider').value),mode=spec?.video_input_modes?.references?'references':spec?.video_input_modes?.first_frame?'first_frame':'unsupported',limit=spec?.video_input_modes?.[mode]||0;
  reference.dataset.inputMode=mode;
  referenceMode.textContent=mode==='references'?`多图软参考 · ${referenceItems.length} / ${limit} 张`:mode==='first_frame'?'首帧参考 · 1 张 · '+$('aspect').value:'当前模型不支持图片输入';
  if(referenceItems.length>limit)referenceMode.textContent+=' · 请调整图片数量';
  referenceMode.title=mode==='references'?'按编号送入模型，图片保留原始比例；成片按所选画幅生成。':'首帧需与成片画幅一致。';
 }
 for(const id of ['provider','aspect'])$(id).addEventListener('change',syncReferenceMode);
 function syncReference(persist=true){
  if(persist&&document.body.dataset.newEntry==='true'&&!referenceDraftPending&&!referenceDraftError)CreativeReferenceDraft.write(referenceItems).catch(()=>{note.textContent='参考图片暂存失败；当前图片可继续使用，刷新页面可能丢失。'});
  add.replaceChildren(icon('plus'));reference.hidden=!referenceItems.length;syncReferenceMode();referenceList.replaceChildren();
  referenceItems.forEach((item,index)=>{
   const tile=create('div','studio-entry-reference-tile'),edit=create('button','studio-entry-reference-image'),image=create('img'),badge=create('span','studio-entry-reference-index',String(index+1)),role=create('span','studio-entry-reference-role',roles[item.role]),remove=create('button','studio-entry-reference-remove','×');
   edit.type=remove.type='button';edit.setAttribute('aria-label','编辑参考图 '+(index+1));edit.title=item.file.name+' · '+roles[item.role];image.alt=item.file.name;image.src=item.url;edit.append(image,badge);remove.setAttribute('aria-label','移除待上传参考图 '+(index+1));
   edit.onclick=()=>{if(busy)return;editingReference=item;refImage.src=item.url;refImage.alt=item.file.name;refRole.value=item.role;refInstruction.value=item.instruction;syncRefEditor();referenceEditor.showPopover()};
   remove.onclick=()=>{if(busy)return;referenceItems=referenceItems.filter(r=>r!==item);URL.revokeObjectURL(item.url);if(editingReference===item&&referenceEditor.matches(':popover-open'))referenceEditor.hidePopover();syncReference();add.focus()};tile.append(edit,role,remove);referenceList.append(tile);
  });
 }
 function addReferenceFiles(chosen){
  if(!chosen.length||document.body.dataset.newEntry!=='true')return;
  if(busy||referenceDraftPending){toast(referenceDraftPending?'参考图片仍在恢复，请稍候再添加':'正在提交创作，请稍候');return}
  if(referenceItems.length+chosen.length>7){toast('最多添加 7 张参考图；当前图片已保留，请减少本次选择');syncReference();return}
  if(chosen.some(f=>!['image/jpeg','image/png','image/webp'].includes(f.type)||f.size>4*1024*1024)){toast('请选择每张不超过 4 MB 的 JPEG、PNG 或 WebP；当前图片已保留');syncReference();return}
  referenceDraftError=false;note.textContent='发送后先和导演确认方案，生成视频前确认费用。';
  for(const f of chosen)referenceItems.push({file:f,role:referenceItems.length?'reference':'product',instruction:'',url:URL.createObjectURL(f)});syncReference();
 }
 file.addEventListener('change',()=>{const chosen=[...file.files];file.value='';addReferenceFiles(chosen)});
 const dropHint=create('div','studio-entry-drop-hint','松开添加参考图');dropHint.hidden=true;document.querySelector('.canvas-viewport').append(dropHint);
 const entryDropTarget=target=>document.body.dataset.newEntry==='true'&&target instanceof Element&&!!target.closest('.canvas-viewport,#createForm');
 const clearDrop=()=>{dropHint.hidden=true;form.classList.remove('studio-entry-dragging')};
 document.addEventListener('dragover',event=>{if(!entryDropTarget(event.target)||!event.dataTransfer?.types.includes('Files'))return;event.preventDefault();event.stopPropagation();const blocked=busy||referenceDraftPending;event.dataTransfer.dropEffect=blocked?'none':'copy';dropHint.hidden=blocked||!!event.target.closest('#createForm');form.classList.toggle('studio-entry-dragging',!blocked)},true);
 document.addEventListener('dragleave',event=>{if(!entryDropTarget(event.relatedTarget))clearDrop()},true);
 document.addEventListener('drop',event=>{const target=entryDropTarget(event.target);clearDrop();if(!target||!event.dataTransfer?.files.length)return;event.preventDefault();event.stopPropagation();addReferenceFiles([...event.dataTransfer.files])},true);
 document.addEventListener('dragend',clearDrop,true);
 document.addEventListener('paste',event=>{if(document.body.dataset.newEntry!=='true'||!form.contains(event.target)||!event.clipboardData?.files.length)return;event.preventDefault();addReferenceFiles([...event.clipboardData.files])});
 add.title='添加参考图 · 可拖入画布或粘贴到输入框 · JPEG、PNG、WebP，最大 4 MB';
 function clearReferences(){for(const item of referenceItems)URL.revokeObjectURL(item.url);referenceItems=[];editingReference=null;refImage.removeAttribute('src');if(referenceEditor.matches(':popover-open'))referenceEditor.hidePopover();syncReference(false)}
 document.addEventListener('creative-reset-initial-references',clearReferences);
 async function restoreReferenceDraft(){
  referenceDraftStarted=true;referenceDraftPending=true;referenceDraftError=false;const epoch=++referenceDraftEpoch;add.disabled=true;note.textContent='正在恢复参考图片…';
  try{const saved=await CreativeReferenceDraft.read();if(epoch!==referenceDraftEpoch||document.body.dataset.newEntry!=='true')return;for(const item of referenceItems)URL.revokeObjectURL(item.url);referenceItems=saved.map(item=>({...item,role:Object.hasOwn(roles,item.role)?item.role:'reference',instruction:String(item.instruction||'').slice(0,240),url:URL.createObjectURL(item.file)}));syncReference(false);note.textContent='发送后先和导演确认方案，生成视频前确认费用。'}
  catch{if(epoch!==referenceDraftEpoch)return;referenceDraftError=true;note.textContent='参考图片未能恢复，当前尚未创建项目。 ';const retry=create('button','','重新读取参考图'),clear=create('button','','清空待恢复图片');retry.type=clear.type='button';retry.onclick=()=>restoreReferenceDraft();clear.onclick=()=>{CreativeReferenceDraft.clear().catch(()=>{});referenceDraftError=false;note.textContent='已清空待恢复图片，请重新添加或继续文字创作。'};note.append(retry,clear)}
  finally{if(epoch===referenceDraftEpoch){referenceDraftPending=false;add.disabled=false}}
 }
 function syncEntry(){
  const open=document.body.dataset.newEntry==='true';document.body.classList.toggle('studio-new-entry',open);form.hidden=!open;
  if(open){document.body.classList.remove('chat-collapsed');$('chatToggle').setAttribute('aria-expanded','true');$('projectTitle').textContent='未命名项目';director.querySelector('.panehead h2').textContent='新创作';for(const select of selectors)select.dispatchEvent(new Event('change'));if(!referenceDraftStarted&&CreativeReferenceDraft.has())restoreReferenceDraft();syncReference(false);brief.focus({preventScroll:true})}
  else {clearDrop();if(picker.matches(':popover-open'))picker.hidePopover();clearReferences()}
 }
 const settings=$('studioChatSettings'),originalSettings=settings.onclick;settings.onclick=()=>{if(document.body.dataset.newEntry==='true')$('entry-provider').click();else originalSettings?.()};
 document.addEventListener('creative-new-entry',syncEntry);syncEntry();
 brief.addEventListener('keydown',e=>{if(e.key==='Enter'&&(e.ctrlKey||e.metaKey)&&!e.isComposing){e.preventDefault();form.requestSubmit(submit)}});
 window.addEventListener('pagehide',clearReferences);
}

// Per-tab, short-lived local reference drafts. Files never enter sessionStorage or trajectories.
const CreativeReferenceDraft=(()=>{
 const slot='creative_reference_draft',ttl=24*60*60*1000;let queue=Promise.resolve();
 const valid=items=>Array.isArray(items)&&items.length<=7&&items.every(i=>i.file instanceof File&&['image/jpeg','image/png','image/webp'].includes(i.file.type)&&i.file.size<=4*1024*1024);
 function run(work){const task=queue.catch(()=>{}).then(work);queue=task;return task}
 async function transaction(mode,work){
  const db=await new Promise((resolve,reject)=>{const r=indexedDB.open('visualagent-reference-drafts',1);r.onupgradeneeded=()=>r.result.createObjectStore('drafts',{keyPath:'id'});r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(r.error);r.onblocked=()=>reject(Error('本地图片暂存不可用'))});
  return new Promise((resolve,reject)=>{const tx=db.transaction('drafts',mode);let result;tx.oncomplete=()=>{db.close();resolve(result)};tx.onerror=tx.onabort=()=>{db.close();reject(tx.error||Error('本地图片暂存失败'))};work(tx.objectStore('drafts'),value=>result=value)});
 }
 function clear(){const id=sessionStorage.getItem(slot);sessionStorage.removeItem(slot);return id?run(()=>transaction('readwrite',store=>store.delete(id))):Promise.resolve()}
 return {has:()=>!!sessionStorage.getItem(slot),clear,
  write(items){if(!valid(items))return Promise.reject(Error('参考图格式或数量无效'));if(!items.length)return clear();let id=sessionStorage.getItem(slot);if(!id){id=crypto.randomUUID();sessionStorage.setItem(slot,id)}const record={id,expires:Date.now()+ttl,items:items.map(i=>({file:i.file,role:i.role||'reference',instruction:i.instruction||''}))};return run(()=>transaction('readwrite',store=>{store.put(record);const cursor=store.openCursor();cursor.onsuccess=()=>{const c=cursor.result;if(c){if(c.value.expires<Date.now())c.delete();c.continue()}}}))},
  read(){const id=sessionStorage.getItem(slot);if(!id)return Promise.resolve([]);return run(()=>transaction('readonly',(store,result)=>{const request=store.get(id);request.onsuccess=()=>result(request.result)})).then(record=>{if(!record||record.expires<Date.now()||!valid(record.items))throw Error('参考图暂存已失效，请重新添加图片');return record.items})}
 };
})();


// Preview the complete composition, including code-rendered captions and its existing audio clock.
function installEditorPreview(create,icon,playback){
 const $=id=>document.getElementById(id),stage=$('monitor').parentElement,play=$('play'),scrub=$('scrub'),clock=$('clock');
 const toggle=create('button','editor-icon-button');toggle.id='editorPreviewFullscreen';toggle.type='button';toggle.setAttribute('aria-label','全屏预览');toggle.title='全屏预览';toggle.setAttribute('aria-expanded','false');const symbol=icon('spark');symbol.querySelector('path').setAttribute('d','M8 3H3v5m13-5h5v5M3 16v5h5m13-5v5h-5');toggle.append(symbol);playback.append(toggle);
 const controls=create('div','editor-preview-controls'),playPreview=create('button'),time=create('time'),position=create('input'),close=create('button','','退出全屏');controls.hidden=true;playPreview.type=close.type='button';playPreview.id='editorPreviewPlay';close.id='editorPreviewClose';close.setAttribute('aria-label','退出全屏预览');position.id='editorPreviewScrub';position.type='range';position.min='0';position.step='.01';position.setAttribute('aria-label','全屏预览播放位置');time.id='editorPreviewClock';controls.append(playPreview,time,position,close);stage.append(controls);
 let fallback=false,opened=false,pending=false;
 const isOpen=()=>document.fullscreenElement===stage||fallback;
 function sync(){const active=isOpen();stage.classList.toggle('editor-preview-expanded',active);controls.hidden=!active;toggle.setAttribute('aria-expanded',String(active));toggle.setAttribute('aria-label',active?'退出全屏预览':'全屏预览');toggle.title=active?'退出全屏预览':'全屏预览';toggle.disabled=pending||!$('pictures').querySelector('video');time.textContent=clock.textContent;position.max=scrub.max;position.value=scrub.value;position.setAttribute('aria-valuetext',scrub.getAttribute('aria-valuetext')||clock.textContent);playPreview.textContent=play.textContent;playPreview.setAttribute('aria-label',play.textContent.includes('Ⅱ')?'暂停全屏预览':'播放全屏预览');if(opened&&!active)toggle.focus({preventScroll:true});opened=active}
 async function exit(){fallback=false;if(document.fullscreenElement===stage)await document.exitFullscreen();sync()}
 toggle.onclick=async()=>{if(pending)return;if(isOpen()){await exit();return}pending=true;sync();try{if(!stage.requestFullscreen)throw Error('unavailable');await stage.requestFullscreen()}catch{fallback=true}finally{pending=false;sync();close.focus({preventScroll:true})}};
 close.onclick=exit;playPreview.onclick=()=>play.click();position.oninput=()=>{scrub.value=position.value;scrub.dispatchEvent(new Event('input',{bubbles:true}));sync()};
 document.addEventListener('fullscreenchange',sync);document.addEventListener('keydown',event=>{if(event.key==='Escape'&&fallback){event.preventDefault();exit()}});
 const observer=new MutationObserver(sync);observer.observe(clock,{childList:true,characterData:true,subtree:true});observer.observe(play,{childList:true,characterData:true,subtree:true});observer.observe($('pictures'),{childList:true});sync();
}

// Distinct entry surfaces: a blank canvas and a full-page Agent conversation.
function installCreationModes(create,icon){
 const $=id=>document.getElementById(id),body=document.body,form=$('createForm'),director=document.querySelector('.director'),viewport=$('canvasViewport')||document.querySelector('.canvas-viewport');
 const glyphs={workflow:'M7 3a2 2 0 1 0 0 4 2 2 0 0 0 0-4M17 17a2 2 0 1 0 0 4 2 2 0 0 0 0-4M7 7v3h10a3 3 0 0 1 0 6H7a3 3 0 0 1 0-6M17 16v1',storyboard:'M5 4h14a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2ZM10 4v16M10 12h11',image:'M3 5h15v14H3Z m0 10 5-5 5 6 3-3 2 2M18 2v6m-3-3h6',video:'M4 5h13v14H4Z m13 5 5-3v10l-5-3M9 9l4 3-4 3Z',audio:'M3 10v4m4-8v12m5-15v18m5-15v12m4-8v4',script:'M8 4h12v16H8M8 4H5a2 2 0 0 0-2 2v3h5m4 0h5m-5 4h5m-5 4h3',cut:'M12 2v5m0 10v5M2 12h5m10 0h5M5 5l3 3m8 8 3 3M5 19l3-3m8-8 3-3',shapes:'m7 2 4 4-4 4-4-4Zm10 1a3 3 0 1 0 0 6 3 3 0 0 0 0-6M3 14h7v7H3m14-8v8m-4-4h8',smile:'M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0ZM8 9h.01M16 9h.01M7 14c2 5 8 5 10 0',help:'M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0ZM9 8c0-3 6-3 6 0 0 2-3 2-3 5m0 4h.01'};
 const symbol=name=>{const svg=icon('spark');svg.querySelector('path').setAttribute('d',glyphs[name]||glyphs.video);return svg};
 const button=(name,label,run)=>{const b=create('button','',label);b.type='button';b.onclick=run;if(name)b.prepend(symbol(name));return b};
 const agentWelcome=create('section','studio-agent-welcome');agentWelcome.hidden=true;agentWelcome.setAttribute('aria-label','开始 Agent 创作');
 const agentMark=create('div','studio-agent-welcome-mark');agentMark.append(icon('spark'));
 const agentCards=create('div','studio-agent-suggestions'),agentNote=create('p','studio-agent-welcome-note');
 const moreSkills=button(null,'查看全部 Skill →',()=>{if(isWorkspaceDirectorDraft())document.dispatchEvent(new Event('creative-open-skill-picker'));else $('entry-initialSkill').click()});moreSkills.className='studio-agent-more-skills';
 agentWelcome.append(agentMark,create('h1','','说个想法，或者选一个 Skill'),create('p','','和 Director 一起，从想法开始创作。'),agentCards,agentNote,moreSkills);director.insertBefore(agentWelcome,$('conversation'));
 let suggestionKey='';
 function syncAgentSuggestions(){const select=$('initialSkill'),existing=isWorkspaceDirectorDraft(),current=existing?project.skill_id:select.value,key=JSON.stringify([existing,current,select.disabled,select.dataset.skillState,[...select.options].map(o=>[o.value,o.textContent,o.disabled])]);if(key===suggestionKey)return;suggestionKey=key;agentCards.replaceChildren();const options=[...select.options].filter(o=>o.value&&!o.disabled);agentNote.textContent=select.dataset.skillState==='error'?'Skill 目录暂不可读取，可打开全部 Skill 重试。':select.disabled?'正在读取可用 Skill…':!options.length?'暂无可用 Skill，可打开列表重新读取。':'';agentNote.hidden=!agentNote.textContent;moreSkills.disabled=false;
  for(const option of options.slice(0,4)){const card=button(null,'',()=>{if(select.disabled||option.disabled)return;if(existing){document.dispatchEvent(new CustomEvent('creative-open-skill-picker',{detail:{skill:option.value}}));return}select.value=option.value;select.dispatchEvent(new Event('change',{bubbles:true}));$('initialBrief').focus({preventScroll:true})});card.className='studio-agent-suggestion';card.disabled=select.disabled;card.setAttribute('aria-pressed',String(option.value===current));card.append(icon('spark'),create('span','',option.textContent.split(' · ')[0]),create('span','studio-agent-suggestion-arrow','→'));agentCards.append(card)}
 }
 $('initialSkill').addEventListener('change',syncAgentSuggestions);new MutationObserver(syncAgentSuggestions).observe($('initialSkill'),{childList:true,subtree:true,attributes:true,attributeFilter:['disabled','data-skill-state']});syncAgentSuggestions();
 const brand=document.querySelector('header .brand svg');if(brand){brand.setAttribute('viewBox','0 0 32 24');brand.setAttribute('fill','currentColor');brand.setAttribute('stroke','none');brand.querySelector('path').setAttribute('d','M8 3h23l-4 13h-7l3-8H6ZM4 8h7L8 17h18l-2 5H0Z')}
 const welcome=create('section','studio-canvas-welcome');welcome.setAttribute('aria-label','创建节点');const hint=create('p','','双击画布 自由生成节点');hint.prepend(icon('spark'));const tiles=create('div','studio-canvas-starts');welcome.append(hint,tiles);viewport.append(welcome);
 const stage=create('section','studio-free-node');stage.hidden=true;const label=create('div','studio-free-node-label'),preview=create('div','studio-free-node-preview'),play=create('span','studio-free-node-play','▶'),tips=create('div','studio-free-node-tips');tips.append(create('small','','尝试：'),create('p','','首尾帧生成视频'),create('p','','参考图片生成视频'));preview.append(play,tips);const back=button(null,'×',()=>choose(''));back.className='studio-free-node-close';back.setAttribute('aria-label','返回空画布');label.append(create('span','','视频节点 1'),back);stage.append(label,preview);viewport.append(stage);
 const insert=create('section','studio-start-menu');insert.id='studioStartMenu';insert.setAttribute('popover','auto');insert.setAttribute('aria-label','创建节点');body.append(insert);
 const entries=[['image','图片生成'],['video','视频生成'],['audio','音频生成'],['script','剧本生成'],['cut','智能剪辑']];
 for(const [name,text]of entries){for(const parent of [tiles,insert]){const b=button(name,text,()=>{insert.hidePopover();if(name==='cut'){location.href='/creative/discover?view=projects&action=edit';return}if(project&&body.dataset.newEntry!=='true'&&['image','video'].includes(name)){document.dispatchEvent(new CustomEvent('creative-add-manual-node',{detail:{kind:name}}));return}choose(name)});b.dataset.createNode=name;if(name==='audio'){b.disabled=true;b.title='独立音频模型尚未接入'}parent.append(b)}}
 const imageSelect=create('select');imageSelect.id='entryImageModel';imageSelect.setAttribute('aria-label','图片生成模型');const imageToggle=button('image','Kling Image 3.0',()=>{imageMenu.showPopover();const r=imageToggle.getBoundingClientRect();imageMenu.style.left=Math.max(8,Math.min(innerWidth-390,r.left))+'px';imageMenu.style.top=Math.max(60,r.top-imageMenu.offsetHeight-8)+'px'});imageToggle.className='studio-image-model-toggle';const imageMenu=create('section','studio-image-model-menu');imageMenu.setAttribute('popover','auto');body.append(imageMenu);form.querySelector('.studio-entry-config').prepend(imageSelect,imageToggle);imageSelect.hidden=true;
 const source=$('imageModelSelect');function syncImageModels(){if(!source)return;const saved=imageSelect.value;imageSelect.replaceChildren(...[...source.options].map(o=>o.cloneNode(true)));imageSelect.value=saved||source.value||imageSelect.options[0]?.value;imageMenu.replaceChildren();for(const o of imageSelect.options){const row=button('image',o.textContent,()=>{imageSelect.value=o.value;imageSelect.dispatchEvent(new Event('change'));imageMenu.hidePopover()});row.disabled=o.disabled;row.dataset.model=o.value;if(o.dataset.description){const copy=create('span');copy.append(create('strong','',o.textContent),create('small','',o.dataset.description));row.lastChild.replaceWith(copy)}imageMenu.append(row)}imageToggle.lastChild.textContent=imageSelect.selectedOptions[0]?.textContent||'读取图片模型…'}imageSelect.onchange=()=>{source.value=imageSelect.value;source.dispatchEvent(new Event('change'));imageToggle.lastChild.textContent=imageSelect.selectedOptions[0]?.textContent||'选择模型'};if(source)new MutationObserver(syncImageModels).observe(source,{childList:true,subtree:true});syncImageModels();
 const price=create('span','studio-manual-price');form.querySelector('.studio-entry-config').append(price);const syncPrice=()=>{const m=catalog.find(m=>m.id===$('provider').value);price.textContent=body.dataset.creationMode==='image'?'2K · 1 张 · 1 积分':m?`${m.credits_per_5s*Math.ceil(Number($('duration').value||15)/5)} 积分 / 次`:''};$('provider').addEventListener('change',syncPrice);$('duration').addEventListener('change',syncPrice);new MutationObserver(syncPrice).observe($('provider'),{childList:true});
 function manualEntryModels(){const manual=body.dataset.creationMode==='video';for(const option of $('provider').options){const m=catalog.find(v=>v.id===option.value);if(!m)continue;option.disabled=manual?!m.manual_available:!m.single_film||m.available===false;option.textContent=m.label+(manual?(m.manual_available?'':' · 尚未接入'):(option.disabled?' · '+(m.limitation||'尚未接入'):''))}if(manual){const m=catalog.find(v=>v.id===$('provider').value),old=$('duration').value;$('duration').replaceChildren(...(m?.manual_durations||[15]).map(n=>{const o=create('option','',n+' 秒');o.value=n;return o}));$('duration').value=(m?.manual_durations||[15]).includes(Number(old))?old:String(m?.manual_durations?.at(-1)||15)}else{$('duration').replaceChildren(new Option('15 秒',15))}$('duration').dispatchEvent(new Event('change'));syncPrice()}
 $('provider').addEventListener('change',manualEntryModels);
 const manualPanel=create('section','studio-manual-image-compose');manualPanel.hidden=true;manualPanel.setAttribute('aria-label','手动图片创作');const manualPrompt=create('textarea');manualPrompt.setAttribute('aria-label','图片生成要求');manualPrompt.placeholder='描述你想要生成的图片内容，@引用素材';manualPrompt.maxLength=4000;const manualTools=create('div','studio-manual-image-tools'),manualModel=create('select');manualModel.setAttribute('aria-label','手动图片模型');const manualRefs=button('image','参考 / 编辑',()=>document.dispatchEvent(new CustomEvent('creative-compose-image',{detail:{prompt:manualPrompt.value,model:manualModel.value}}))),manualGenerate=button(null,'↑',()=>document.dispatchEvent(new CustomEvent('creative-compose-image',{detail:{prompt:manualPrompt.value,model:manualModel.value,direct:true}})));manualGenerate.className='studio-manual-image-generate';manualGenerate.setAttribute('aria-label','生成图片');const manualDuration=create('select');manualDuration.setAttribute('aria-label','视频生成时长');const manualMode=button(null,'文生视频',()=>manualRefs.click());manualMode.className='manual-video-mode';manualMode.setAttribute('aria-label','视频生成模式');manualTools.append(manualModel,manualMode,manualDuration,create('span','studio-manual-image-size','2K · 1 张'),manualGenerate);const manualReferenceBar=create('div','manual-reference-bar');manualReferenceBar.append(manualRefs);manualPanel.append(manualReferenceBar,manualPrompt,manualTools);viewport.append(manualPanel);let manualPid='';const manualPicker=window.installStudioModelPicker(manualModel);
 let manualRoot=null;
 function placeManualRoot(){
  if(manualRoot.dataset.manualPlaced||manualRoot.dataset.manualMoving)return;
  const obstacles=[...document.querySelectorAll('.canvas-world .reference-node,.canvas-world .canvas-image-job,.canvas-world .manual-generation-node')].filter(n=>!n.hidden&&n.offsetWidth&&n.offsetHeight);
  const width=manualRoot.offsetWidth,height=manualRoot.offsetHeight,refs=obstacles.filter(n=>n.matches('.reference-node'));
  const collisions=(x,y)=>obstacles.filter(n=>x<n.offsetLeft+n.offsetWidth+24&&x+width+24>n.offsetLeft&&y<n.offsetTop+n.offsetHeight+24&&y+height+24>n.offsetTop);
  let x=40,y=40;
  // Prefer a readable source → generator row; never move user-positioned sibling nodes.
  if(refs.length){const right=Math.max(...refs.map(n=>n.offsetLeft+n.offsetWidth))+80,top=Math.min(...refs.map(n=>n.offsetTop));if(right+width<=10000&&!collisions(right,top).length){x=right;y=top}}
  for(let i=0;i<=obstacles.length;i++){const hits=collisions(x,y);if(!hits.length)break;y=Math.max(...hits.map(n=>n.offsetTop+n.offsetHeight))+40}
  const changed=manualRoot.offsetLeft!==x||manualRoot.offsetTop!==y;manualRoot.style.left=x+'px';manualRoot.style.top=y+'px';return changed;
 }

 const manualObstacles=new ResizeObserver(()=>{if(manualRoot&&!stage.hidden&&placeManualRoot())document.dispatchEvent(new Event('creative-fit-canvas'))});
 function observeManualObstacles(){manualObstacles.disconnect();for(const card of document.querySelectorAll('.canvas-world .reference-node,.canvas-world .canvas-image-job,.canvas-world .manual-generation-node'))manualObstacles.observe(card)}
 const manualWorld=document.querySelector('.canvas-world');if(manualWorld)new MutationObserver(observeManualObstacles).observe(manualWorld,{childList:true});observeManualObstacles();
 const videoStarts=[['first_frame','首帧生成视频'],['first_last','首尾帧生成视频'],['references','参考图片生成视频']];
 tips.replaceChildren(create('small','','尝试：'));
 for(const [mode,text]of videoStarts){const entry=button(null,text,()=>{if(!project||manualRefs.disabled)return;document.dispatchEvent(new CustomEvent('creative-video-input-draft',{detail:{project:project.id,mode,prompt:manualPrompt.value,model:manualModel.value,duration:Number(manualDuration.value)}}))});entry.dataset.videoStart=mode;tips.append(entry)}
 function syncVideoStarts(){const caps=catalog.find(m=>m.id===manualModel.value)?.video_input_modes||{};for(const entry of tips.querySelectorAll('button')){entry.disabled=!(entry.dataset.videoStart in caps);entry.title=entry.disabled?'当前模型尚不支持此模式':''}}
 function syncManual(){const active=['image','video'].includes(project?.creation_mode)&&body.dataset.newEntry!=='true';manualPanel.hidden=!active;if(manualRoot)manualRoot.hidden=!active;if(!active)return;if(!manualRoot){manualRoot=document.createElement('section');manualRoot.className='canvas-card manual-root-node';manualRoot.style.left='40px';manualRoot.style.top='40px';document.querySelector('.canvas-world').append(manualRoot);manualRoot.append(stage,manualPanel);requestAnimationFrame(()=>document.dispatchEvent(new Event('creative-fit-canvas')))}if(manualRoot.dataset.positionProject!==project.id){manualRoot.dataset.positionProject=project.id;manualRoot.style.left=(project.manual_position?.x??40)+'px';manualRoot.style.top=(project.manual_position?.y??40)+'px';manualRoot.dataset.manualPlaced=project.manual_position?'true':''}body.dataset.creationMode=project.creation_mode;const isVideo=project.creation_mode==='video';manualPanel.setAttribute('aria-label',isVideo?'手动视频创作':'手动图片创作');manualPrompt.setAttribute('aria-label',isVideo?'视频生成要求':'图片生成要求');manualPrompt.placeholder=isVideo?'描述你想生成的画面内容，@引用素材':'描述你想要生成的图片内容，@引用素材';manualModel.setAttribute('aria-label',isVideo?'手动视频模型':'手动图片模型');manualMode.hidden=!isVideo;manualMode.textContent=({text:'文生视频',first_frame:'首帧生成',first_last:'首尾帧',references:'全能参考'})[project.video_inputs?.mode||project.input_manifest?.mode||'text']||'选择模式';manualDuration.hidden=project.creation_mode!=='video';if(project.creation_mode==='video'&&(!catalog.some(m=>m.id===project.model)||![...($('videoModelSelect')?.options||[])].some(o=>o.value===project.model))){manualGenerate.disabled=true;return}if(manualPid!==project.id||!manualModel.options.length){manualPid=project.id;manualDuration.replaceChildren();let savedDraft=null;try{savedDraft=JSON.parse(sessionStorage.getItem('manual-image-draft:'+project.id)||'null')}catch{}manualPrompt.value=savedDraft?.prompt||project.image_task?.prompt||project.direct_prompt||'';manualModel.replaceChildren(...[...(project.creation_mode==='video'?$('videoModelSelect'):imageSelect).options].map(o=>o.cloneNode(true)));manualModel.value=project.creation_mode==='video'?project.model:savedDraft?.model||project.image_model||imageSelect.value;manualModel.disabled=false;const durations=()=>{const m=catalog.find(v=>v.id===manualModel.value),old=manualDuration.value||String(project.duration);manualDuration.replaceChildren(...(m?.manual_durations||[15]).map(n=>new Option(n+' 秒',n)));manualDuration.value=(m?.manual_durations||[15]).includes(Number(old))?old:String(m?.manual_durations?.at(-1)||15);updatePrice()};function updatePrice(){syncVideoStarts();const m=catalog.find(v=>v.id===manualModel.value);manualPanel.querySelector('.studio-manual-image-size').textContent=`720P · ${m?.audio?'有声':'静音'} · ${(m?.credits_per_5s||0)*Math.ceil(Number(manualDuration.value)/5)} 积分`}manualModel.onchange=()=>{if(project.creation_mode==='video')durations();else{source.value=manualModel.value;source.dispatchEvent(new Event('change'))}};manualDuration.onchange=updatePrice;if(project.creation_mode==='video'){for(const o of manualModel.options){const m=catalog.find(v=>v.id===o.value);o.disabled=!m?.manual_available;o.textContent=m?.label||o.textContent}durations()}}if(project.creation_mode==='image'&&!manualModel.options.length&&imageSelect.options.length){manualModel.replaceChildren(...[...imageSelect.options].map(o=>o.cloneNode(true)));manualModel.value=project.image_model||imageSelect.value}const working=busy||['running','rendering'].includes(project.state)||project.image_task?.state==='running';manualGenerate.disabled=working;manualRefs.disabled=working;manualMode.disabled=working||!!(project.film&&!['planned','completed','failed'].includes(project.film.state));manualGenerate.setAttribute('aria-label',project.creation_mode==='video'?'生成视频':'生成图片');manualPanel.querySelector('.studio-manual-image-size').textContent=project.creation_mode==='video'?`720P · ${catalog.find(m=>m.id===manualModel.value)?.audio?'有声':'静音'} · ${(catalog.find(m=>m.id===manualModel.value)?.credits_per_5s||0)*Math.ceil(Number(manualDuration.value||project.duration)/5)} 积分`:'2K · 1 张 · 1 积分';const empty=!(project.creation_mode==='video'?project.artifact:project.image_task);stage.hidden=!empty;if(empty)placeManualRoot();else if(!document.querySelector('.manual-primary-result')&&!manualRoot.dataset.manualMoving)manualRoot.style.top=(Math.max(0,...[...document.querySelectorAll('.canvas-world .reference-node,.canvas-world .canvas-image-job')].map(n=>n.offsetTop+n.offsetHeight))+40)+'px';if(empty){label.firstChild.textContent=project.creation_mode==='video'?'视频节点 1':'图片节点 1';play.replaceChildren(project.creation_mode==='video'?document.createTextNode('▶'):symbol(project.creation_mode));tips.hidden=project.creation_mode!=='video'||!!project.film;syncVideoStarts();back.hidden=true;stage.classList.add('studio-manual-empty-node')}else stage.classList.remove('studio-manual-empty-node');manualPicker.sync();document.dispatchEvent(new Event('creative-manual-view-ready'));}
 manualRefs.onclick=()=>{if(project?.creation_mode==='video')document.dispatchEvent(new CustomEvent('creative-video-input-draft',{detail:{project:project.id,prompt:manualPrompt.value,model:manualModel.value,duration:Number(manualDuration.value)}}));else document.dispatchEvent(new CustomEvent('creative-compose-image',{detail:{prompt:manualPrompt.value,model:manualModel.value}}))};manualGenerate.onclick=async()=>{if(manualPrompt.value.trim().length<2){toast('请填写生成要求');return}if(project?.creation_mode==='video'){if(project.film&&!['planned','completed','failed'].includes(project.film.state)){executeManualVideo();return}setBusy(true);try{project=await api('/projects/'+project.id+'/manual-prompt','PATCH',{revision:project.revision,prompt:manualPrompt.value.trim(),model:manualModel.value,duration:Number(manualDuration.value)});draw();setBusy(false);$('executeButton').click()}catch(e){toast(e.message)}finally{setBusy(false)}}else document.dispatchEvent(new CustomEvent('creative-compose-image',{detail:{prompt:manualPrompt.value,model:manualModel.value,direct:true}}))};
 document.addEventListener('creative-root-image-draft',e=>{if(e.detail?.project!==project?.id||project.creation_mode!=='image')return;try{const draft=JSON.parse(sessionStorage.getItem('manual-image-draft:'+project.id)||'null');if(draft){manualPrompt.value=draft.prompt;manualModel.value=draft.model;manualPicker.sync()}}catch{}});
 document.addEventListener('creative-root-image-reference-manage',e=>{if(project?.creation_mode!=='image'||manualRefs.disabled)return;document.dispatchEvent(new CustomEvent('creative-compose-image',{detail:{prompt:manualPrompt.value,model:manualModel.value,focusAsset:e.detail.asset}}))});
 document.addEventListener('creative-root-reference-manage',e=>{if(project?.creation_mode!=='video'||manualRefs.disabled)return;document.dispatchEvent(new CustomEvent('creative-video-input-draft',{detail:{project:project.id,focusAsset:e.detail.asset,prompt:manualPrompt.value,model:manualModel.value,duration:Number(manualDuration.value)}}))});
 document.addEventListener('creative-root-reference-drop',e=>{
  if(e.detail?.project!==project?.id||manualRefs.disabled)return;
  if(project.creation_mode==='video'){document.dispatchEvent(new CustomEvent('creative-video-input-draft',{detail:{project:project.id,asset:e.detail.asset,prompt:manualPrompt.value,model:manualModel.value,duration:Number(manualDuration.value)}}));return}
  let saved={};try{saved=JSON.parse(sessionStorage.getItem('manual-image-draft:'+project.id)||'{}')}catch{}
  const references=(saved.references||[]).some(r=>r.asset===e.detail.asset)?saved.references:[...(saved.references||[]),{asset:e.detail.asset,role:'reference',instruction:''}];
  document.dispatchEvent(new CustomEvent('creative-compose-image',{detail:{prompt:manualPrompt.value,model:manualModel.value,references}}));
 });
 document.addEventListener('creative-video-input-saved',()=>{if(project?.creation_mode!=='video')return;manualModel.value=project.model;manualModel.dispatchEvent(new Event('change'));manualDuration.value=String(project.duration);manualPrompt.value=project.direct_prompt||'';manualPicker.sync()});
 document.addEventListener('creative-state-change',()=>requestAnimationFrame(syncManual));document.addEventListener('creative-new-entry',()=>requestAnimationFrame(syncManual));if(source)new MutationObserver(syncManual).observe(source,{childList:true});if($('videoModelSelect'))new MutationObserver(syncManual).observe($('videoModelSelect'),{childList:true});
 let selected='',entryWasOpen=false;
 function choose(kind){selected=kind;body.classList.toggle('studio-blank-entry',body.dataset.newEntry==='true'&&!kind);agentWelcome.hidden=body.dataset.newEntry!=='true'||!['agent','script'].includes(kind);imageToggle.hidden=kind!=='image';body.dataset.creationMode=kind==='video'?'video':kind==='image'?'image':'agent';manualEntryModels();body.classList.toggle('studio-agent-session',kind==='agent'||kind==='script');body.classList.toggle('studio-free-compose',kind==='video'||kind==='image');welcome.hidden=!!kind;stage.hidden=!['video','image'].includes(kind);if(stage.hidden)director.append(form);else{stage.append(form);label.firstChild.textContent=kind==='image'?'图片节点 1':'视频节点 1';play.replaceChildren(symbol(kind));tips.hidden=kind==='image'}$('initialBrief').placeholder=kind==='video'?'描述你想要生成的画面内容，@引用素材':kind==='image'?'描述你想要生成的图片内容…':'开始你的创作，或者 @引用工作流/节点/资源';$('createButton').title=kind==='image'?'生成图片 · 1 积分':kind==='video'?'生成视频 · 按所选模型计费':'发送创作需求';$('createButton').setAttribute('aria-label',$('createButton').title);if(kind)requestAnimationFrame(()=>$('initialBrief').focus({preventScroll:true}));}
 function sync(){const fresh=body.dataset.newEntry==='true';body.classList.toggle('studio-blank-entry',fresh&&!selected);welcome.hidden=!fresh||!!selected;stage.hidden=!fresh||!['video','image'].includes(selected);if(fresh&&!entryWasOpen){const query=new URLSearchParams(location.search);choose(query.get('mode')==='agent'?'agent':['image','video'].includes(query.get('tool'))?query.get('tool'):!query.has('new')&&sessionStorage.getItem('creative_quick_prompt')?'agent':'')}const draft=!fresh&&isWorkspaceDirectorDraft();body.classList.toggle('studio-director-welcome',draft);if(!fresh){agentWelcome.hidden=!draft;body.classList.remove('studio-free-compose','studio-blank-entry');director.append(form)}entryWasOpen=fresh;}
 document.addEventListener('creative-new-entry',sync);document.addEventListener('creative-state-change',()=>{sync();syncAgentSuggestions()});sync();requestAnimationFrame(syncManual);
 viewport.addEventListener('dblclick',event=>{if((body.dataset.newEntry!=='true'&&!['image','video'].includes(project?.creation_mode))||event.target.closest('button,textarea,input,select,.studio-free-node,.reference-node,.manual-generation-node'))return;event.preventDefault();event.stopImmediatePropagation();insert.showPopover();const r=insert.getBoundingClientRect();insert.style.left=Math.max(8,Math.min(innerWidth-r.width-8,event.clientX))+'px';insert.style.top=Math.max(8,Math.min(innerHeight-r.height-8,event.clientY))+'px'},true);
 const dock=document.querySelector('.canvas-toolbar'),extra=$('canvasAddMenuPanel');
 for(const id of ['canvasHandTool','canvasVideoInputs','timelineToggle','inlineEditButton']){const control=$(id);if(control){extra.append(control);control.classList.remove('studio-icon-control')}}
 for(const [kind,label] of [['image','图片生成'],['video','视频生成']]){const add=button(kind,label,()=>{if(project&&body.dataset.newEntry!=='true')document.dispatchEvent(new CustomEvent('creative-add-manual-node',{detail:{kind}}));else choose(kind)});add.dataset.manualAdd=kind;extra.prepend(add)}
 const shapes=button('shapes','节点工具',()=>{insert.style.left=Math.max(8,innerWidth/2-140)+'px';insert.style.top=Math.max(60,innerHeight-360)+'px';insert.showPopover()});shapes.className='studio-dock-symbol';shapes.title='创建节点';shapes.setAttribute('aria-label','创建节点');dock.append(shapes);
 const skills=button('smile','创作 Skill',()=>{if(body.dataset.newEntry==='true')$('entry-initialSkill').click();else $('studioChatSkill').click()});skills.className='studio-dock-symbol';skills.title='创作 Skill';skills.setAttribute('aria-label','创作 Skill');dock.append(skills);
 const help=button('help','帮助',()=>$('studioCanvasHelp').showModal());help.className='studio-dock-symbol';help.setAttribute('aria-label','画布帮助');help.style.order='8';dock.append(help);shapes.style.order='2';skills.style.order='3';
 let directorFrame=null,frameProject='',openingDirector=false;
 async function openDirector(story=false){
  if(body.dataset.newEntry==='true'){body.classList.remove('chat-collapsed');choose('agent');if(!story)body.classList.remove('studio-agent-session');return}
  if(!project)return;
  if(project.creation_mode==='agent'){body.classList.remove('chat-collapsed');body.classList.toggle('studio-agent-session',story);requestAnimationFrame(()=>document.dispatchEvent(new Event('creative-fit-canvas')));return}
  if(openingDirector)return;openingDirector=true;
  try{
   const owner=project.id,child=await api('/projects/'+owner+'/director','POST');
   if(project?.id!==owner)return;project.director_project=child.id;
   if(!directorFrame){directorFrame=create('iframe','workspace-director-frame');directorFrame.title='Director 创作';body.append(directorFrame)}
   if(frameProject!==child.id){frameProject=child.id;directorFrame.src='/creative?project='+child.id+'&embedded=director'}
   body.classList.add('workspace-director-open');body.classList.toggle('workspace-director-story',story);requestAnimationFrame(()=>document.dispatchEvent(new Event('creative-fit-canvas')));
  }catch(e){toast(e.message)}finally{openingDirector=false}
 }
 function workflow(){body.classList.remove('studio-agent-session','workspace-director-story');if(body.dataset.newEntry==='true'&&selected==='agent')choose('');document.dispatchEvent(new Event('creative-fit-canvas'))}
 const views=create('div','workspace-view-switch');views.setAttribute('role','group');views.setAttribute('aria-label','工作区视图');
 const flow=button('workflow','工作流',workflow),story=button('storyboard','故事板',()=>openDirector(true));
 flow.title='工作流';flow.setAttribute('aria-label','工作流');story.title='故事板';story.setAttribute('aria-label','故事板');views.append(flow,story);$('chatToggle').before(views);$('chatToggle').hidden=true;
 function closeDirector(){if(body.dataset.newEntry==='true'){choose('');return}body.classList.remove('workspace-director-open','workspace-director-story','studio-agent-session');if(project?.creation_mode==='agent')body.classList.add('chat-collapsed');requestAnimationFrame(()=>document.dispatchEvent(new Event('creative-fit-canvas')))}
 const directorVisible=()=>body.dataset.newEntry==='true'?['agent','script'].includes(selected)&&!body.classList.contains('chat-collapsed'):body.classList.contains('workspace-director-open')||(project?.creation_mode==='agent'&&!body.classList.contains('chat-collapsed'));
 const orb=button(null,'',()=>{if(directorVisible())closeDirector();else openDirector(false)});orb.className='studio-agent-orb';orb.setAttribute('aria-label','打开 Director');orb.title='Director';orb.append(create('span'));dock.after(orb);
 $('chatToggle').addEventListener('click',()=>{body.classList.remove('studio-agent-session');});
 document.addEventListener('creative-state-change',()=>{if(directorFrame&&frameProject&&project?.director_project!==frameProject){directorFrame.remove();directorFrame=null;frameProject='';body.classList.remove('workspace-director-open','workspace-director-story')}});
 const referenceStrip=create('div','director-reference-strip');referenceStrip.hidden=true;referenceStrip.setAttribute('aria-label','下次发送引用的画布节点');$('chatForm').prepend(referenceStrip);
 let referenceRequest=false,referenceSignature='';
 async function syncDirectorReferences(){
  if(referenceRequest||!project||project.creation_mode!=='agent'||document.hidden)return;
  referenceRequest=true;const requested=project.id;
  try{const data=await api('/projects/'+requested+'/director-context');if(project?.id!==requested)return;
   const signature=JSON.stringify(data);if(signature===referenceSignature)return;referenceSignature=signature;referenceStrip.replaceChildren();referenceStrip.hidden=!data.references.length;
   for(const ref of data.references){const chip=button(ref.kind==='text'?'script':ref.kind,ref.label,()=>{const detail={project:data.project,node:ref.id};if(window.parent!==window)parent.postMessage({type:'director-focus-reference',...detail},location.origin);else{workflow();document.dispatchEvent(new CustomEvent('creative-focus-canvas-node',{detail}))}});chip.className='director-reference-chip';chip.title='下次发送引用 · 点击定位画布节点';referenceStrip.append(chip)}
  }catch{referenceSignature='';referenceStrip.replaceChildren(create('span','','参考状态暂不可读取'));referenceStrip.hidden=false}
  finally{referenceRequest=false}
 }
 document.addEventListener('creative-state-change',()=>{if(project?.creation_mode!=='agent'){referenceStrip.hidden=true;referenceSignature=''}else syncDirectorReferences()});setInterval(syncDirectorReferences,4000);
 if(new URLSearchParams(location.search).get('embedded')==='director'){
  body.classList.add('workspace-embedded-director');
  $('chatToggle').addEventListener('click',()=>parent.postMessage({type:'director-close'},location.origin));
  let lastResult='';
  document.addEventListener('creative-state-change',()=>{if(project?.artifact&&lastResult!==project.artifact){lastResult=project.artifact;parent.postMessage({type:'director-completed',project:project.id},location.origin)}});
 }
 window.addEventListener('message',e=>{if(e.origin!==location.origin||e.source!==directorFrame?.contentWindow)return;if(e.data?.type==='director-focus-reference'&&e.data.project===project?.id){workflow();document.dispatchEvent(new CustomEvent('creative-focus-canvas-node',{detail:{project:project.id,node:e.data.node}}))}if(e.data?.type==='director-close')closeDirector();if(e.data?.type==='director-completed'&&e.data.project===frameProject){body.classList.remove('workspace-director-story');document.dispatchEvent(new Event('creative-state-change'))}});
 const syncView=()=>{const storyOn=body.classList.contains('studio-agent-session')||body.classList.contains('workspace-director-story');flow.setAttribute('aria-pressed',String(!storyOn));story.setAttribute('aria-pressed',String(storyOn));orb.setAttribute('aria-expanded',String(directorVisible()));orb.setAttribute('aria-label',directorVisible()?'收起 Director':'打开 Director')};
 new MutationObserver(syncView).observe(body,{attributes:true,attributeFilter:['class']});syncView();
 // Persist the explicit entry choice across the first project creation.
 if(new URLSearchParams(location.search).get('mode')==='agent')body.classList.add('studio-agent-session');
 const settings=create('dialog','studio-director-confirm');settings.setAttribute('aria-label','确认 Director 设置');const heading=create('div','studio-settings-heading'),close=button(null,'×',()=>settings.close());heading.append(create('strong','','确认 Director 设置'),close);settings.append(heading,create('p','studio-director-notice','素材生成单独计费，生成前会显示本次任务与预算。'),create('p','studio-director-section','协作模式'));
 const auto=create('input');auto.type='checkbox';auto.setAttribute('role','switch');auto.setAttribute('aria-label','自动生成素材');const row=create('label','studio-director-setting'),copy=create('span');copy.append(create('strong','','自动生成图片 / 视频'),create('small','','开启后，先授权本次生成预算，方案完成后自动提交一次任务。'));row.append(copy,auto);settings.append(row);
 const notify=create('input');notify.type='checkbox';notify.setAttribute('role','switch');notify.setAttribute('aria-label','浏览器通知');const notifyRow=create('label','studio-director-setting'),notifyCopy=create('span');notifyCopy.append(create('strong','','浏览器通知'),create('small','','导演回复完成后，通过浏览器通知提醒。'));notifyRow.append(notifyCopy,notify);settings.append(create('p','studio-director-section','通知设置'),notifyRow);const status=create('p','studio-entry-note');status.setAttribute('role','status');let confirmed=false;
 const confirm=button(null,'确认并发送',async()=>{if(notify.checked&&'Notification'in window){const permission=await Notification.requestPermission();if(permission!=='granted'){status.textContent='浏览器未允许通知，可关闭此选项继续。';return}}sessionStorage.setItem('creative_notify',String(notify.checked));$('initialApproval').value=auto.checked?'auto':'manual';$('initialApproval').dispatchEvent(new Event('change'));confirmed=true;settings.close();form.requestSubmit($('createButton'))});confirm.className='studio-director-send';settings.append(status,confirm);body.append(settings);
 form.addEventListener('submit',event=>{if(body.dataset.creationMode!=='agent'||confirmed){confirmed=false;return}event.preventDefault();event.stopImmediatePropagation();auto.checked=$('initialApproval').value==='auto';notify.checked=sessionStorage.getItem('creative_notify')==='true';status.textContent='';settings.showModal()},true);
 let wasPlanning=false;document.addEventListener('creative-state-change',()=>{const planning=project?.state==='planning';if(wasPlanning&&!planning&&document.hidden&&sessionStorage.getItem('creative_notify')==='true'&&window.Notification?.permission==='granted')new Notification('VisualAgent',{body:'创作导演已回复，点击返回工作区。'}).onclick=()=>window.focus();wasPlanning=planning});
}

// Record authenticated presence only; no prompt, media, URL or device data is sent.
(()=>{const ping=()=>{const token=sessionStorage.getItem('h3_api_key');if(token&&document.visibilityState==='visible')fetch('/credits/activity',{method:'POST',headers:{Authorization:'Bearer '+token},signal:AbortSignal.timeout(10000)}).catch(()=>{})};document.addEventListener('DOMContentLoaded',ping);setInterval(ping,300000)})();
