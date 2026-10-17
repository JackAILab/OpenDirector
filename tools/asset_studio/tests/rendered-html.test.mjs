import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const root = new URL("../", import.meta.url);

async function render(path = "/") {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);
  return worker.fetch(new Request(new URL(path, "http://localhost/"), { headers: { accept: "text/html" } }), {
    ASSETS: { fetch: async () => new Response("Not found", { status: 404 }) },
  }, { waitUntil() {}, passThroughOnException() {} });
}

test("server renders the interactive Asset Studio shell", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);
  const html = await response.text();
  assert.match(html, /VisualAgent/);
  assert.match(html, /直播制作 Agent/);
  assert.match(html, /秒时间线/);
  assert.match(html, /AI 合成/);
  assert.match(html, /条视频可审/);
});

test("one-port version index links all four cards to the Asset Studio workbench", async () => {
  const response = await render("/versions");
  assert.equal(response.status, 200);
  const html = await response.text();
  assert.match(html, /visualagent-versions-v1/);
  assert.match(html, /一个地址，进入四个无限画布/);
  assert.match(html, /href="\/cybercab"/);
  assert.match(html, /Cybercab 直播/);
  for (const variant of ["portrait-zh", "portrait-en", "landscape-zh", "landscape-en"])
    assert.match(html, new RegExp(`\\?variant=${variant}`));
});

test("Cybercab has a dedicated truthful pre-production board", async () => {
  const response = await render("/cybercab");
  assert.equal(response.status, 200);
  const html = await response.text();
  assert.match(html, /data-studio="visualagent-canvas-v3"/);
  assert.match(html, /Cybercab/);
  assert.match(html, /(?:user-cybercab-exterior\.png|Omni 原生音画)/);
  assert.match(html, /(?:非最终 Camera Feed|秒时间线)/);
  assert.match(html, /training_eligible=false/);
});

test("legacy viewer URL redirects to the matching one-port workbench", async () => {
  const response = await render("/viewer.html?v=portrait-zh");
  assert.equal(response.status, 302);
  const location = new URL(response.headers.get("location"), "http://localhost/");
  assert.equal(location.pathname, "/");
  assert.equal(location.searchParams.get("variant"), "portrait-zh");
});

test("source wires every advertised control to a state transition", async () => {
  const source = await readFile(new URL("app/AssetStudio.tsx", root), "utf8");
  for (const contract of [
    /onClick=\{\(\) => chooseGroup\(item\.id\)\}/,
    /onClick=\{\(\) => chooseAsset\(asset\)\}/,
    /onClick=\{toggleCompare\}/,
    /onClick=\{playSelectedVideo\}/,
    /播放视频/,
    /播放时间线/,
    /setCanvasZoom\(zoom - 10\)/,
    /setCanvasZoom\(zoom \+ 10\)/,
    /onClick=\{\(\) => selectState\(state\.time\)\}/,
    /onClick=\{\(\) => inspectEvent/,
    /setPlaying\(value => !value\)/,
    /onClick=\{\(\) => void addNote\(\)\}/,
    /fetch\("\/api\/iterations"/,
    /data-studio="visualagent-canvas-v3"/,
    /href="\/versions"/,
    /href="\/cybercab"/,
    /href=\{`\/\?variant=\$\{variant\.id\}`\}/,
  ]) assert.match(source, contract);
});

test("creator shell exposes three real modes and durable iteration intake", async () => {
  const component = await readFile(new URL("app/AssetStudio.tsx", root), "utf8");
  const route = await readFile(new URL("app/api/iterations/route.ts", root), "utf8");
  const hosting = JSON.parse(await readFile(new URL(".openai/hosting.json", root), "utf8"));
  for (const contract of [
    /WorkspaceMode = "create" \| "logic" \| "review"/,
    /创作模式/,
    /制作逻辑/,
    /审片模式/,
    /Task/,
    /Trajectory/,
    /Evaluator/,
    /不自动触发付费生成/,
  ]) assert.match(component, contract);
  assert.match(route, /CREATE TABLE IF NOT EXISTS iteration_requests/);
  assert.match(route, /paid_generation_allowed/);
  assert.match(route, /oai-authenticated-user-id/);
  assert.equal(hosting.d1, "DB");
});

test("health gate checks browser-playable MP4 range delivery", async () => {
  const source = await readFile(new URL("scripts/health.mjs", root), "utf8");
  for (const contract of [
    /\.mp4/,
    /Range: "bytes=0-1023"/,
    /mediaResponse\.status === 206/,
    /video\\\/mp4/,
    /accept-ranges/,
    /content-range/,
    /versionsReady/,
    /legacyViewerReady/,
    /cybercabReady/,
  ]) assert.match(source, contract);
});

test("source manifest exposes current pilot ads and excludes renderer scratch files", async () => {
  const data = JSON.parse(await readFile(new URL("app/data/studio-data.json", root), "utf8"));
  for (const name of [
    "visualagent-gpu-15s-v2.mp4",
    "visualagent-phone-15s-v2.mp4",
    "visualagent-mobility-15s-v2.mp4",
  ]) {
    const asset = data.assets.find(item => item.name === name);
    assert.ok(asset, `${name} is projected`);
    assert.equal(asset.trainingEligible, false);
    assert.equal(asset.humanReview, "pending");
  }
  assert.equal(data.assets.some(asset => /visualagent-.+-15s-v1\.mp4/.test(asset.name)), false);
  assert.ok(data.assets.some(asset => asset.name === "synthetic_gpu_presenter_live_60s_v5.native-variants.plan.json"));
  assert.ok(data.assets.some(asset => asset.name === "cybercab_live_60s_v1.plan.json"));
  assert.ok(data.assets.some(asset => asset.name === "api_mcp.md"));
  assert.equal(data.timeline.duration, 60);
  assert.equal(data.assets.some(asset => /work-|captured-frames|chunk-encode/.test(asset.path)), false);
});

test("portrait video preview is contained and the studio has no desktop minimum-width overflow", async () => {
  const component = await readFile(new URL("app/AssetStudio.tsx", root), "utf8");
  const styles = await readFile(new URL("app/globals.css", root), "utf8");
  assert.match(component, /selectedIsVideo \? "video-preview"/);
  assert.match(component, /9:16 竖屏 · 完整预览/);
  assert.match(styles, /\.preview-grid\.video-preview \.preview-cell\{width:auto;aspect-ratio:9\/16\}/);
  assert.match(styles, /video\.media\{width:100%;height:100%;aspect-ratio:9\/16;object-fit:contain\}/);
  assert.doesNotMatch(styles, /\.studio\{[^}]*min-width:1120px/);
  assert.match(styles, /@media\(max-width:900px\)/);
});

test("canvas shell keeps asset navigation, Agent context and six-track timeline", async () => {
  const component = await readFile(new URL("app/AssetStudio.tsx", root), "utf8");
  for (const contract of [
    /所有资产/,
    /点阵画布/,
    /直播制作 Agent/,
    /Kling Camera Feed/,
    /HyperFrames 直播合成/,
    /const TRACK_ORDER = \["camera", "speech", "comments", "ui", "vfx", "ar"\]/,
  ]) assert.match(component, contract);
});

test("multiformat entries open a scrollable workbench with settings and canonical assets", async () => {
  const component = await readFile(new URL("app/AssetStudio.tsx", root), "utf8");
  const styles = await readFile(new URL("app/globals.css", root), "utf8");
  for (const contract of [
    /portrait-zh/,
    /portrait-en/,
    /landscape-zh/,
    /landscape-en/,
    /当前版本设置/,
    /版本素材/,
    /打开完整配置/,
    /training_eligible=false/,
    /旧版中文音轨占位；英文 Camera Feed 与英文口播尚未生成/,
    /旧版竖屏 Camera Feed 布局预览；16:9 原生媒体尚未生成/,
  ]) assert.match(component, contract);
  assert.match(styles, /\.canvas-stage\{overflow:scroll;/);
  assert.match(styles, /\.canvas-flow\{width:1600px;min-height:1120px/);
  assert.match(styles, /\.variant-settings-node/);
  assert.match(styles, /\.variant-assets-node/);
});
