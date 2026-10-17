import {build} from 'esbuild';
import {writeFile} from 'node:fs/promises';
const result=await build({entryPoints:['runtime.js'],bundle:true,format:'esm',minify:true,write:false});
// Normalize insignificant line-end whitespace in bundled shader literals.
await writeFile('../scene-runtime.js',result.outputFiles[0].text.replace(/[ \t]+$/gm,''));
