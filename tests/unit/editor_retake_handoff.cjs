const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const src=fs.readFileSync('tools/agent_studio/editor.js','utf8');
function setup(){
 const elements=new Map();let opened=0,assistant=false;
 const ctx={spec:{clips:[],audio:[]},working:false,selected:{kind:'clips',index:0},
 $:id=>{if(!elements.has(id))elements.set(id,{focus(){},hidden:false});return elements.get(id)},
 meta:()=>({duration:5}),stop(){},status(){},sourceLibraryLocation(){},
 adviser(value){assistant=value},focusEditorSource:async()=>false,RetakeUI:{open(){opened++}},duration:()=>0,
 checkpoint(){},bindSource(){},selectClip(i){ctx.selected={kind:'clips',index:i}},changed(){},seek:async()=>{},showInspector(){}};
 vm.createContext(ctx);
 vm.runInContext(src.slice(src.indexOf('let videoToolEpoch='),src.indexOf('\nfunction showInspector()')),ctx);
 vm.runInContext(src.slice(src.indexOf('async function appendVideo('),src.indexOf('\nfunction appendAudio(')),ctx);
 return {ctx,opened:()=>opened,assistant:()=>assistant};
}
test('canvas retake follows the requested source only after explicit timeline insertion',async()=>{
 const {ctx,opened}=setup();assert.equal(await ctx.openCanvasVideoTool('retake','target'),false);assert.equal(opened(),0);assert.equal(ctx.spec.clips.length,0);
 await ctx.appendVideo('other');assert.equal(opened(),0);
 await ctx.appendVideo('target');assert.equal(opened(),1);assert.equal(ctx.spec.clips[ctx.selected.index].source,'target');
 await ctx.appendVideo('target');assert.equal(opened(),1);
});
test('switching tool clears the pending retake handoff',async()=>{
 const {ctx,opened}=setup();await ctx.openCanvasVideoTool('retake','target');await ctx.openCanvasVideoTool('trim','other');await ctx.appendVideo('target');assert.equal(opened(),0);
});
test('busy editor cannot insert or open a pending retake',async()=>{
 const {ctx,opened}=setup();await ctx.openCanvasVideoTool('retake','target');ctx.working=true;await ctx.appendVideo('target');assert.equal(opened(),0);assert.equal(ctx.spec.clips.length,0);
});
test('slow preview loading does not delay the retake controls',async()=>{
 const {ctx,opened}=setup();await ctx.openCanvasVideoTool('retake','target');let loaded;ctx.seek=()=>new Promise(resolve=>loaded=resolve);
 const pending=ctx.appendVideo('target');assert.equal(opened(),1);loaded();await pending;
});

test('canvas assistant waits for its source, not an unrelated existing timeline',async()=>{
 const {ctx,assistant}=setup();ctx.spec.clips.push({source:'existing',start:0,end:5});
 assert.equal(await ctx.openCanvasVideoTool('assistant','target'),false);assert.equal(assistant(),false);
 await ctx.appendVideo('other');assert.equal(assistant(),false);
 await ctx.appendVideo('target');assert.equal(assistant(),true);assert.equal(ctx.spec.clips[ctx.selected.index].source,'target');
});
test('changing tool clears pending assistant handoff',async()=>{
 const {ctx,assistant}=setup();await ctx.openCanvasVideoTool('assistant','target');await ctx.openCanvasVideoTool('trim','other');await ctx.appendVideo('target');assert.equal(assistant(),false);
});
