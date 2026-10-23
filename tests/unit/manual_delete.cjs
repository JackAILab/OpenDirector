const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync('tools/agent_studio/manual-nodes.js','utf8');
const start=source.indexOf(" document.addEventListener('keydown',async event=>{");
const end=source.indexOf('\n },true);',start)+11;
async function run(overrides={}){
 let handler,deletions=0,removed=false;
 const card={dataset:{manualProject:'child'},remove(){removed=true}};
 const item={project:{}};
 const context={document:{body:{matches:()=>!!overrides.story},querySelector:s=>s.startsWith('dialog')?null:card,activeElement:null,addEventListener:(_,fn)=>handler=fn,dispatchEvent(){}},cards:new Map([['child',item]]),root:'parent',active:()=>false,resumeOnly:()=>false,api:async()=>{deletions++},toast(){},Event:class{},URL,encodeURIComponent};
 vm.runInNewContext(source.slice(start,end),context);
 const event={key:'Delete',target:{closest:()=>overrides.input?{}:null},preventDefault(){},stopPropagation(){},...overrides};
 await handler(event);
 return {deletions,removed};
}
test('selected idle canvas node deletes with either plain deletion key',async()=>{
 for(const key of ['Delete','Backspace'])assert.deepEqual(await run({key}),{deletions:1,removed:true});
});
test('storyboard does not delete a selected hidden canvas node',async()=>{
 assert.equal((await run({story:true})).deletions,0);
});
test('text editing keeps the selected node',async()=>{
 assert.equal((await run({input:true,key:'Backspace'})).deletions,0);
});
test('modified, repeated, composed and consumed keys cannot delete nodes',async()=>{
 for(const flag of ['ctrlKey','metaKey','altKey','repeat','isComposing','defaultPrevented'])assert.equal((await run({[flag]:true})).deletions,0,flag);
});

test('node drag surface takes keyboard focus; editing controls retain their own focus',()=>{
 const from=source.indexOf(' function moveNode(c,head){'),to=source.indexOf('\n function emptyVideo',from);
 let selected=null,focused=0;
 const card={dataset:{},style:{},parentElement:{},offsetLeft:20,offsetTop:30,focus(options){assert.equal(options.preventScroll,true);focused++}};
 const head={style:{},setPointerCapture(){}};
 const c={card,project:{id:'child'}};
 const context={selectManualCard:value=>selected=value,root:'parent',getComputedStyle:()=>({transform:'none'}),DOMMatrixReadOnly:class{constructor(){this.a=1}}};
 vm.createContext(context);vm.runInContext(source.slice(from,to),context);context.moveNode(c,head);
 const event={button:0,pointerId:1,clientX:0,clientY:0,target:{closest:()=>null},preventDefault(){},stopPropagation(){}};
 head.onpointerdown(event);assert.equal(selected,card);assert.equal(focused,1);
 for(const state of [{target:{closest:()=>({})}},{button:2}]){head.onpointerdown({...event,...state});assert.equal(focused,1)}
 c.saving=true;head.onpointerdown(event);assert.equal(focused,1);
});
