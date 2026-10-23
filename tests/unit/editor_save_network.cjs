const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const source=fs.readFileSync('tools/agent_studio/editor.js','utf8');
function setup(fetch){
 const nodes=new Map(),messages=[];let expire,cleared=false;
 const ctx={fetch,AbortController,Promise,Error,base:'/test',key:'test',project:{revision:8},spec:{clips:[{end:15}]},dirty:true,working:false,
 setTimeout(fn,ms){assert.equal(ms,30000);expire=fn;return 1},clearTimeout(){cleared=true},
 $:id=>{if(!nodes.has(id))nodes.set(id,{});return nodes.get(id)},status:s=>messages.push(s),draw(){},stop(){}};
 vm.createContext(ctx);
 for(const [start,end] of [['async function fetchOwned(', '\nasync function uploadDigest('],['async function request(', '\nfunction button('],['async function save(){', '\nfunction exportPending(']])vm.runInContext(source.slice(source.indexOf(start),source.indexOf(end)),ctx);
 return {ctx,messages,expire:()=>expire(),cleared:()=>cleared};
}
test('successful save confirms revision and releases controls',async()=>{
 let calls=0;const h=setup(async()=>{calls++;return {ok:true,json:async()=>({revision:9,spec:{clips:[{end:15}]}})}});
 await h.ctx.$('save').onclick();assert.equal(calls,1);assert.equal(h.ctx.dirty,false);assert.equal(h.ctx.project.revision,9);assert.equal(h.ctx.working,false);assert.equal(h.cleared(),true);assert.equal(h.messages[0],'正在保存剪辑…');assert.equal(h.messages.at(-1),'剪辑已保存');
});
test('stalled request releases controls, preserves draft, never retries or applies a late response',async()=>{
 let calls=0,resolve,signal;const h=setup(async(_,opts)=>{calls++;signal=opts.signal;return new Promise(r=>resolve=r)}),draft=h.ctx.spec;
 const pending=h.ctx.$('save').onclick();h.expire();await pending;
 assert.equal(signal.aborted,true);assert.equal(h.ctx.working,false);assert.equal(h.ctx.dirty,true);assert.equal(h.ctx.spec,draft);assert.equal(h.ctx.project.revision,8);assert.match(h.messages.at(-1),/尚未确认成功/);
 resolve({ok:true,json:async()=>({revision:99,spec:{clips:[]}})});await new Promise(r=>setImmediate(r));assert.equal(h.ctx.project.revision,8);assert.equal(calls,1);
});
test('response-body stall also expires without clearing dirty state',async()=>{
 const h=setup(async()=>({ok:true,json:()=>new Promise(()=>{})}));const pending=h.ctx.$('save').onclick();await Promise.resolve();await Promise.resolve();h.expire();await pending;assert.equal(h.ctx.dirty,true);assert.equal(h.ctx.working,false);assert.match(h.messages.at(-1),/超时/);
});
test('network failure and revision conflict preserve the local draft',async()=>{
 for(const fetch of [async()=>{throw Error('offline')},async()=>({ok:false,status:409,json:async()=>({detail:'版本已变化'})})]){
 const h=setup(fetch);await h.ctx.$('save').onclick();assert.equal(h.ctx.dirty,true);assert.equal(h.ctx.project.revision,8);assert.equal(h.ctx.working,false);assert.equal(h.cleared(),true);assert.notEqual(h.messages.at(-1),'剪辑已保存');
 }
});
