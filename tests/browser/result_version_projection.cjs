// Verify the actual canvas selector against same-run edited deliverables.
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const source=fs.readFileSync('tools/agent_studio/canvas.js','utf8');
const selector=source.slice(source.indexOf('function currentFilmNode()'),source.indexOf('function syncOutputProjection()'));
const node={kind:'video',asset:'result',id:'node'};
const context={project:{artifact:'run/edit-a/final.mp4',result_artifact:'run/edit-a/final.mp4',result_asset:'result',film:{state:'completed'}},graph:{nodes:[node]},generationSources:new Set(),world:{querySelector:()=>({})},CSS:{escape:x=>x}};
vm.createContext(context);vm.runInContext(selector,context);
assert.equal(context.currentFilmNode(),node);
context.project.artifact='run/edit-b/final.mp4';
assert.equal(context.currentFilmNode(),null,'Old result must not hide the new edit');
context.project.result_artifact=context.project.artifact;
assert.equal(context.currentFilmNode(),node);
context.world.querySelector=()=>null;
assert.equal(context.currentFilmNode(),null,'A missing node must not hide the playable output');
console.log('Result version projection: PASS');
