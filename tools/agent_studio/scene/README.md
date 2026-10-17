# Scene runtime

Three.js 0.180.0 is bundled locally so the studio does not depend on a third-party CDN at runtime. Rebuild with `npm ci && npm run build` in this directory. The generated `../scene-runtime.js` and upstream MIT license are checked in for the existing Python static-file deployment.

Scene behavior lives in `../scene.js`. Stored documents and GLB input limits are validated by `harness/tools/creative_scene.py`; authenticated routes live in `harness/studio/scene_api.py`. No provider or paid generation is invoked by the renderer.
