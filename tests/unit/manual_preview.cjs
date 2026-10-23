// Preview requests are read-only; loading a canvas must not download every film.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('tools/agent_studio/manual-nodes.js','utf8');
const body=source.slice(source.indexOf(' async function media(c,p)'),source.indexOf(' async function configureReferences'));
class Element {
 constructor(tag,cls,text){this.tagName=tag.toUpperCase();this.className=cls;this.textContent=text;this.children=[];this.hidden=false;this.events={}}
 append(...xs){xs.forEach(x=>{x.parent=this;this.children.push(x)})}
 prepend(x){x.parent=this;this.children.unshift(x)}
 replaceChildren(...xs){this.children=[];this.append(...xs)}
 replaceWith(x){const a=this.parent.children;x.parent=this.parent;a.splice(a.indexOf(this),1,x)}
 setAttribute(){} addEventListener(n,fn){this.events[n]=fn} async play(){this.played=true}
}
function setup(){
 const calls=[],revoked=[];let gate=null;
 const context={AbortController,AbortSignal,Blob,key:'test',make:(...a)=>new Element(...a),progressMeter(){},installResultPort(){},URL:{createObjectURL:()=>`blob:${Math.random()}`,revokeObjectURL:u=>revoked.push(u)},fetch:async(url,opts)=>{calls.push({url,signal:opts.signal});if(url.endsWith('/media/final')&&gate)await gate;return {ok:true,blob:async()=>({})}}};
 vm.createContext(context);vm.runInContext(body+';this.media=media;',context);
 const card={card:{isConnected:true},index:4,preview:new Element('div'),label:new Element('span'),project:{}};
 const p={id:'child',creation_mode:'video',state:'completed',artifact:'film',result_artifact:'film',result_asset:'asset'};
 return {context,card,p,calls,revoked,setGate:p=>gate=p};
}
test('initial video preview requests only thumbnail; explicit play downloads once',async()=>{
 const s=setup();await s.context.media(s.card,s.p);
 assert.equal(s.calls.length,1);assert.ok(s.calls[0].url.endsWith('/asset/preview'));
 const play=s.card.preview.children.find(x=>x.tagName==='BUTTON');
 let resolve;s.setGate(new Promise(r=>resolve=r));const pending=play.onclick();await play.onclick();
 assert.equal(s.calls.filter(x=>x.url.endsWith('/media/final')).length,1);
 resolve();await pending;
 assert.ok(s.card.preview.children.some(x=>x.tagName==='VIDEO'&&x.played));
 await s.context.media(s.card,s.p);assert.equal(s.calls.length,2);
});
test('deleted node abort cannot attach a late player',async()=>{
 const s=setup();await s.context.media(s.card,s.p);const play=s.card.preview.children.find(x=>x.tagName==='BUTTON');
 let resolve;s.setGate(new Promise(r=>resolve=r));const pending=play.onclick();s.card.card.isConnected=false;s.card.mediaController.abort();resolve();await pending;
 assert.equal(s.calls[1].signal.aborted,true);assert.ok(!s.card.preview.children.some(x=>x.tagName==='VIDEO'));
});
test('replacement result revokes old preview and aborts pending reads',async()=>{
 const s=setup();await s.context.media(s.card,s.p);const old=s.card.posterUrl,controller=s.card.mediaController;
 await s.context.media(s.card,{...s.p,artifact:'new-film',result_artifact:'new-film',result_asset:'new-asset'});
 assert.equal(controller.signal.aborted,true);assert.ok(s.revoked.includes(old));assert.ok(s.calls[1].url.endsWith('/new-asset/preview'));
});

test('download reports received bytes and retains the video MIME',async()=>{
 const s=setup();let responseBlob;
 s.context.URL.createObjectURL=b=>{responseBlob=b;return 'blob:loaded'};
 s.context.fetch=async url=>url.endsWith('/preview')?{ok:true,blob:async()=>({})}:{ok:true,headers:{get:()=> 'video/mp4'},body:{getReader:()=>{let sent=false;return {read:async()=>sent?{done:true}:(sent=true,{done:false,value:new Uint8Array(1048576)}),releaseLock(){}}}}};
 await s.context.media(s.card,s.p);const play=s.card.preview.children.find(x=>x.tagName==='BUTTON');await play.onclick();
 assert.equal(play.textContent,'正在加载 · 1.0 MB');assert.equal(responseBlob.type,'video/mp4');assert.equal(responseBlob.size,1048576);
});
