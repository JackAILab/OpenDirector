"use client";

import { useEffect, useMemo, useRef, useState, type RefObject } from "react";

type Asset = {
  id: string; name: string; path: string; url: string; kind: string; group: string; owner: string;
  status: string; model?: string | null; operation?: string | null; bytes: number; sha256: string;
  trainingEligible: boolean; humanReview: string;
};
type TimelineEvent = {
  id: string; start?: number; end?: number; time?: number; duration?: number; type?: string; text?: string;
  action?: string; title?: string; owner?: string; model_owned?: boolean; responds_to?: string; caused_by?: string;
};
type TrackedEvent = TimelineEvent & { track: string };
type StudioData = {
  generatedAt: string; caseId: string; assets: Asset[]; counts: Record<string, number>;
  timeline: {
    duration: number; disclosure: string;
    reference_states?: Array<{ id: string; time: number; camera_semantics: string }>;
    tracks: Record<string, TimelineEvent[]>;
  };
};
type ReviewNote = { id: string; assetId: string; playhead: number; text: string; createdAt: string; status?: string };
type WorkspaceMode = "create" | "logic" | "review";
type VariantId = "portrait-zh" | "portrait-en" | "landscape-zh" | "landscape-en";
type StudioProject = "gpu" | "cybercab";
type Variant = {
  id: VariantId; title: string; short: string; locale: string; orientation: string; canvas: string;
  commentSlots: number; presentation: string; configName: string; mediaStatus: string;
};

const GROUPS = [
  { id: "keyframes", label: "关键画面", glyph: "◇" },
  { id: "references", label: "参考元素", glyph: "◫" },
  { id: "video", label: "视频", glyph: "▶" },
  { id: "audio", label: "声音", glyph: "≋" },
  { id: "layers", label: "界面图层", glyph: "▱" },
  { id: "specs", label: "版本设置", glyph: "⚙" },
  { id: "all", label: "所有资产", glyph: "⌘" },
];
const VARIANTS: Variant[] = [
  { id: "portrait-zh", title: "中文竖屏", short: "ZH · 9:16", locale: "简体中文", orientation: "竖屏", canvas: "1080 × 1920", commentSlots: 4, presentation: "透明弹幕叠加于镜头", configName: "mobile_live_text_zh_portrait_v4.json", mediaStatus: "旧版竖屏中文 Camera Feed；v5 原生重生成待执行" },
  { id: "portrait-en", title: "English Portrait", short: "EN · 9:16", locale: "English", orientation: "Portrait", canvas: "1080 × 1920", commentSlots: 3, presentation: "Camera overlay with stacked copy", configName: "mobile_live_text_en_portrait_v4.json", mediaStatus: "旧版中文音轨占位；英文 Camera Feed 与英文口播尚未生成" },
  { id: "landscape-zh", title: "中文横屏", short: "ZH · 16:9", locale: "简体中文", orientation: "横屏", canvas: "1920 × 1080", commentSlots: 6, presentation: "独立右侧讨论栏", configName: "desktop_live_text_zh_landscape_v4.json", mediaStatus: "旧版竖屏 Camera Feed 布局预览；16:9 原生媒体尚未生成" },
  { id: "landscape-en", title: "English Landscape", short: "EN · 16:9", locale: "English", orientation: "Landscape", canvas: "1920 × 1080", commentSlots: 6, presentation: "Dedicated discussion rail", configName: "desktop_live_text_en_landscape_v4.json", mediaStatus: "旧版竖屏中文音轨占位；16:9 英文原生媒体尚未生成" },
];
const CYBERCAB_VARIANTS: Variant[] = [
  { id: "portrait-zh", title: "中文竖屏 · Omni", short: "ZH · 9:16", locale: "简体中文", orientation: "竖屏", canvas: "1080 × 1920", commentSlots: 4, presentation: "透明弹幕、商品说明与礼物特效叠加于镜头", configName: "cybercab_live_60s_v2.omni-native-av.plan.json", mediaStatus: "4 段 Omni 原生音画 + 3 段 Omni 接缝素材已生成；60 秒合成可审，独立语义与人工审阅待完成" },
];
const TRACK_ORDER = ["camera", "speech", "comments", "ui", "vfx", "ar"];
const TRACK_LABELS: Record<string, string> = { camera: "镜头", speech: "口播", comments: "弹幕", ui: "界面", vfx: "礼物", ar: "试戴" };
const STATE_ASSET_NAMES: Record<number, string> = {
  0: "first-v2.png", 7.5: "state-075-dynamic-v2.png", 15: "state-150-dynamic-v2.png",
  22.5: "state-225-dynamic-v2.png", 30: "state-300-dynamic-v2.png",
  37.5: "state-375-cable-v1-technical-v2.png", 45: "state-450-airflow-v1-technical-v2.png",
  52.5: "state-525-clearance-v1-technical-v2.png", 60: "state-600-summary-v1-technical-v2.png",
};
const STATE_LABELS: Record<number, string> = {
  0: "开场展示", 7.5: "回应功耗", 15: "讲解散热", 22.5: "正面试戴", 30: "阶段总结",
  37.5: "检查供电", 45: "梳理风道", 52.5: "检查空间", 60: "完整收尾",
};
const CYBERCAB_STATE_ASSET_NAMES: Record<number, string> = {
  0: "state-00-000.png", 15: "state-15-000.png", 30: "state-30-000.png",
  45: "state-45-000.png", 60: "state-60-000.png",
};
const CYBERCAB_STATE_LABELS: Record<number, string> = {
  0: "展厅外观", 15: "蝶翼门开启", 30: "乘客入座", 45: "启动行程", 60: "低速驶离目标",
};
const STATUS_LABELS: Record<string, string> = { candidate: "待审", review: "待审", generated: "已生成", rejected: "未采用", failed: "生成失败" };
const KIND_LABELS: Record<string, string> = {
  keyframe: "关键画面", "reference element": "参考元素", video: "视频", audio: "声音",
  overlay: "界面图层", timeline: "时间线", storyboard: "脚本", metadata: "数据",
  provenance: "生成记录", "composition snapshot": "合成预览",
};
const EVENT_LABELS: Record<string, string> = {
  cam_hook: "开场展示", cam_power_response: "回应功耗", cam_rubin_concept: "讲解散热", cam_close: "收尾",
  speech_hook: "开场", speech_power: "功耗回应", speech_rubin: "散热说明", speech_close: "收尾",
  commerce_drawer: "购物卡", counter_update: "数字变化", heart_burst: "爱心", rocket: "火箭",
  sports_car: "跑车", face_anchor_sunglasses: "墨镜试戴", sunglasses: "墨镜试戴",
};
const PIPELINE_STEPS = [
  { name: "Task", detail: "保存目标、资产、时间点与付费边界", state: "ready" },
  { name: "Agent", detail: "解释修改意图并选择有界 Action", state: "ready" },
  { name: "Runner", detail: "远程执行连接器尚未接管队列", state: "waiting" },
  { name: "Tool / Model", detail: "CLIProxyAPI 仅负责模型网关；媒体调用保持显式", state: "locked" },
  { name: "Observation", detail: "Runner 执行后追加真实观测", state: "pending" },
  { name: "Trajectory", detail: "只追加、脱敏、不可追溯改写", state: "pending" },
  { name: "Evaluator", detail: "technical → semantic/visual → human", state: "pending" },
] as const;

function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
}
function eventStart(event: TimelineEvent) { return event.start ?? event.time ?? 0; }
function eventEnd(event: TimelineEvent) { const start = eventStart(event); return event.end ?? (start + (event.duration ?? .8)); }
function eventLabel(event: TimelineEvent) {
  return event.text || event.title || event.action || EVENT_LABELS[event.type || ""] || EVENT_LABELS[event.id]
    || STATE_LABELS[eventStart(event)] || TRACK_LABELS[(event as TrackedEvent).track] || "状态变化";
}

function normalizeVariant(value: string | undefined, variants: Variant[]): VariantId {
  return variants.some(item => item.id === value) ? value as VariantId : variants[0].id;
}

function variantSnapshot(data: StudioData, variant: VariantId, project: StudioProject) {
  if (project === "cybercab") {
    return data.assets.find(asset => asset.name === "state-00-000.png")
      || data.assets.find(asset => asset.group === "keyframes");
  }
  return data.assets.find(asset => asset.path.includes(`/jensen_rubin_live_60s_v4_multiformat/${variant}/snapshots/`) && asset.name === "frame-04-at-59.0s.png")
    || data.assets.find(asset => asset.path.includes(`/jensen_rubin_live_60s_v4_multiformat/${variant}/snapshots/`));
}

function Preview({ asset, videoRef }: { asset: Asset; videoRef?: RefObject<HTMLVideoElement | null> }) {
  const [unavailable, setUnavailable] = useState(false);
  const ext = asset.name.split(".").pop()?.toLowerCase();
  if (unavailable) return <div className="media-placeholder"><strong>媒体等待连接</strong><span>当前 Runner 尚未把原始文件接入此网页</span></div>;
  if (["png", "jpg", "jpeg", "webp"].includes(ext || "")) return <img className="media" src={asset.url} alt={asset.name} onError={() => setUnavailable(true)} />;
  if (["mp4", "webm", "mov"].includes(ext || "")) return <video ref={videoRef} className="media" src={asset.url} controls playsInline preload="metadata" onError={() => setUnavailable(true)}><track kind="captions" label="字幕由直播文字层提供" /></video>;
  if (["wav", "mp3"].includes(ext || "")) return <div className="audio-preview"><div className="record-mark"><i /><i /><i /><i /><i /></div><strong>声音素材</strong><audio src={asset.url} controls><track kind="captions" label="转录待审" /></audio></div>;
  return <div className="document-preview"><span>{ext?.toUpperCase()}</span><strong>{asset.name}</strong><p>这是一份制作数据，不参与画面预览。</p><a href={asset.url} target="_blank" rel="noreferrer">查看文件</a></div>;
}

export default function AssetStudio({ data, initialVariant, project = "gpu" }: { data: StudioData; initialVariant?: string; project?: StudioProject }) {
  const isCybercab = project === "cybercab";
  const variants = isCybercab ? CYBERCAB_VARIANTS : VARIANTS;
  const stateAssetNames = isCybercab ? CYBERCAB_STATE_ASSET_NAMES : STATE_ASSET_NAMES;
  const stateLabels = isCybercab ? CYBERCAB_STATE_LABELS : STATE_LABELS;
  const projectName = isCybercab ? "Cybercab 直播" : "广告片试制 · GPU / 手机 / 出行";
  const initialVariantId = normalizeVariant(initialVariant, variants);
  const initialSnapshot = variantSnapshot(data, initialVariantId, project);
  const preferredNames = isCybercab
    ? ["cybercab_live_60s-omni-native-av-v2-departure-repaired.mp4", "camera_feed_60s-omni-native-av-v2-departure-repaired.mp4", "cybercab_live_60s-omni-native-av-v2-seam-repaired.mp4", "camera_feed_60s-omni-native-av-v2-seam-repaired.mp4", "seg-00-15-omni-native-av-v2.source-15s.mp4"]
    : ["visualagent-gpu-15s-v2.mp4", "visualagent-phone-15s-v2.mp4", "visualagent-mobility-15s-v2.mp4", "jensen_rubin_live_60s_v2_audio_fx.draft.mp4", "jensen_rubin_live_60s_v1.final.mp4", "camera_feed_60s.mp4"];
  const preferredVideo = preferredNames.map(name => data.assets.find(asset => asset.name === name)).find(Boolean) || data.assets.find(asset => asset.group === "video");
  const initialAsset = preferredVideo || initialSnapshot;
  const [variantId, setVariantId] = useState<VariantId>(initialVariantId);
  const [group, setGroup] = useState(preferredVideo ? "video" : initialSnapshot ? "layers" : "keyframes");
  const [query, setQuery] = useState("");
  const [selectedId, setSelectedId] = useState(initialAsset?.id || data.assets.find(a => a.name === "first-v2.png")?.id || data.assets[0]?.id);
  const [compareId, setCompareId] = useState<string | null>(null);
  const [playhead, setPlayhead] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [focusedEventId, setFocusedEventId] = useState<string | null>(null);
  const [feedback, setFeedback] = useState(isCybercab ? "工作台可审 · 60 秒 Omni 原生音画与完整资产已载入" : "工作台已恢复 · 三条 15 秒广告片 v2 已载入，等待人工审阅");
  const [notes, setNotes] = useState<ReviewNote[]>([]);
  const [draft, setDraft] = useState("");
  const [zoom, setZoom] = useState(86);
  const [agentMode, setAgentMode] = useState<"review" | "production">("review");
  const [workspaceMode, setWorkspaceMode] = useState<WorkspaceMode>("create");
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [inspectorOpen, setInspectorOpen] = useState(true);
  const [timelineOpen, setTimelineOpen] = useState(true);
  const [saving, setSaving] = useState(false);
  const videoRef = useRef<HTMLVideoElement | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    void fetch(`/api/iterations?caseId=${encodeURIComponent(data.caseId)}`, { signal: controller.signal })
      .then(response => response.ok ? response.json() : Promise.reject(new Error("iteration store unavailable")))
      .then(payload => setNotes(payload.iterations || []))
      .catch(error => { if (error.name !== "AbortError") setFeedback("云端指令库正在连接；画布仍可正常审阅"); });
    return () => controller.abort();
  }, [data.caseId]);
  useEffect(() => {
    if (!playing) return;
    const timer = window.setInterval(() => setPlayhead(current => {
      const next = Math.min(data.timeline.duration, Number((current + .1).toFixed(1)));
      if (next >= data.timeline.duration) setPlaying(false);
      return next;
    }), 100);
    return () => window.clearInterval(timer);
  }, [playing, data.timeline.duration]);

  const assets = useMemo(() => data.assets.filter(asset =>
    (group === "all" || asset.group === group)
    && (`${asset.name} ${asset.path} ${asset.owner} ${asset.model || ""}`.toLowerCase().includes(query.toLowerCase()))
  ), [data.assets, group, query]);
  const selected = data.assets.find(asset => asset.id === selectedId) || data.assets[0];
  const variant = variants.find(item => item.id === variantId) || variants[0];
  const variantAssets = isCybercab
    ? data.assets.filter(asset => asset.path.includes("/cybercab_live_60s_v1/reference_states/") && ["png", "jpg", "jpeg", "webp"].includes(asset.name.split(".").pop()?.toLowerCase() || ""))
    : data.assets.filter(asset => asset.path.includes(`/jensen_rubin_live_60s_v4_multiformat/${variantId}/snapshots/`));
  const variantConfig = data.assets.find(asset => asset.name === variant.configName);
  const selectedExt = selected.name.split(".").pop()?.toLowerCase();
  const selectedIsVideo = ["mp4", "webm", "mov"].includes(selectedExt || "");
  const compare = data.assets.find(asset => asset.id === compareId);
  const comparableAssets = data.assets.filter(asset => asset.id !== selected.id && asset.group === selected.group);
  const events: TrackedEvent[] = TRACK_ORDER.flatMap(track => (data.timeline.tracks[track] || []).map(event => ({ track, ...event })));
  const active = events.filter(event => playhead >= eventStart(event) && playhead <= eventEnd(event));
  const currentState = [...(data.timeline.reference_states || [])].reverse().find(state => state.time <= playhead) || (data.timeline.reference_states || [])[0];
  const rulerStep = data.timeline.duration > 30 ? 10 : 5;
  const rulerTimes = Array.from({ length: Math.floor(data.timeline.duration / rulerStep) + 1 }, (_, index) => index * rulerStep);

  const announce = (message: string) => setFeedback(message);
  const chooseAsset = (asset: Asset) => { setSelectedId(asset.id); setCompareId(null); announce(`正在查看：${asset.name}`); };
  const chooseGroup = (next: string) => { setGroup(next); setQuery(""); announce(`已切换到${GROUPS.find(item => item.id === next)?.label}`); };
  const jumpTo = (time: number, message: string) => { setPlayhead(time); setPlaying(false); announce(message); };
  const inspectEvent = (event: TrackedEvent) => { setFocusedEventId(event.id); jumpTo(eventStart(event), `已定位：${eventLabel(event)}`); };
  const addNote = async () => {
    const text = draft.trim();
    if (!text) { announce("先写下审阅意见"); return; }
    setSaving(true);
    try {
      const response = await fetch("/api/iterations", {
        method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ caseId: data.caseId, assetId: selected.id, playhead, text }),
      });
      if (!response.ok) throw new Error("save failed");
      const payload = await response.json();
      setNotes(current => [...current, payload.iteration]);
      setDraft("");
      announce("迭代指令已持久保存，等待 Runner 接管");
    } catch {
      announce("指令还没有保存成功，请稍后再试");
    } finally { setSaving(false); }
  };
  const deleteNote = async (id: string) => {
    const response = await fetch(`/api/iterations?id=${encodeURIComponent(id)}`, { method: "DELETE" });
    if (!response.ok) { announce("暂时无法删除这条指令"); return; }
    setNotes(current => current.filter(item => item.id !== id));
    announce("迭代指令已删除");
  };
  const toggleCompare = () => {
    if (compareId) { setCompareId(null); announce("已关闭对比"); return; }
    const fallback = comparableAssets[0];
    if (fallback) { setCompareId(fallback.id); announce(`正在与 ${fallback.name} 对比`); }
    else announce("当前没有同类资产可对比");
  };
  const selectState = (time: number) => {
    jumpTo(time, `已跳到 ${stateLabels[time]}`);
    const asset = data.assets.find(item => item.name === stateAssetNames[time]);
    if (asset) setSelectedId(asset.id);
  };
  const playSelectedVideo = () => {
    if (!videoRef.current) { announce("请先选择一条视频"); return; }
    void videoRef.current.play(); announce(`正在播放：${selected.name}`);
  };
  const setCanvasZoom = (next: number) => { const value = Math.max(60, Math.min(120, next)); setZoom(value); announce(`画布缩放 ${value}%`); };
  const chooseVariant = (next: VariantId) => {
    const target = variantSnapshot(data, next, project);
    setVariantId(next);
    setGroup(isCybercab ? "video" : "layers");
    setQuery("");
    setCompareId(null);
    if (target) setSelectedId(target.id);
    const nextVariant = variants.find(item => item.id === next);
    window.history.replaceState(null, "", isCybercab ? `/cybercab?variant=${next}` : `/?variant=${next}`);
    announce(`已进入 ${nextVariant?.title || next} 无限画布`);
  };

  return <main className={`studio mode-${workspaceMode} ${sidebarOpen ? "" : "sidebar-collapsed"} ${inspectorOpen ? "" : "inspector-closed"} ${timelineOpen ? "" : "timeline-closed"}`} data-studio="visualagent-canvas-v3">
    <aside className="sidebar">
      <div className="sidebar-brand"><span className="brand-orbit"><i /></span><div><strong>VisualAgent</strong><small>Live Studio</small></div><button className="panel-toggle" onClick={() => setSidebarOpen(value => !value)} aria-label={sidebarOpen ? "收起项目栏" : "展开项目栏"}>{sidebarOpen ? "‹" : "›"}</button></div>
      <nav className="primary-nav" aria-label="工作区导航">
        <button className={workspaceMode === "create" ? "active" : ""} onClick={() => { setWorkspaceMode("create"); setAgentMode("production"); announce("已进入创作模式"); }}><span>＋</span>开始创作</button>
        <button className={workspaceMode === "review" ? "active" : ""} onClick={() => { setWorkspaceMode("review"); setAgentMode("review"); announce("已进入审片模式"); }}><span>▱</span>审片画布</button>
        <button onClick={() => { chooseGroup("all"); setWorkspaceMode("review"); }}><span>◫</span>资产中心</button>
        <button className={workspaceMode === "logic" ? "active" : ""} onClick={() => { setWorkspaceMode("logic"); announce("已展开 Agent 制作逻辑"); }}><span>⌘</span>制作逻辑</button>
      </nav>

      <div className="project-tree">
        <div className="section-row"><span>当前项目</span><button aria-label="收起当前项目">⌃</button></div>
        <a className="project-item" href="/tvc"><i>10</i><span><strong>十支原创商品广告</strong><small>15s · 成片、参考图与对比输入</small></span><b>↗</b></a>
        <a className={`project-item ${!isCybercab ? "active" : ""}`} href={`/?variant=${variantId}`}><i>AI</i><span><strong>GPU 直播概念片</strong><small>60s · 四版 UI 可审 · 原生媒体待生成</small></span><b>↗</b></a>
        <a className={`project-item cybercab-project ${isCybercab ? "active" : ""}`} href="/cybercab"><i>EV</i><span><strong>Cybercab 直播</strong><small>60s · 7 段 Omni 原生音画 · 完整工作台</small></span><b>↗</b></a>
        <div className="variant-list" aria-label="直播版本">
          {VARIANTS.map(item => <button key={item.id} aria-pressed={variantId === item.id} className={variantId === item.id ? "active" : ""} onClick={() => chooseVariant(item.id)}><span>{item.title}</span><b>{item.short}</b></button>)}
        </div>
      </div>

      <label className="search"><span>⌕</span><input value={query} onChange={event => { setQuery(event.target.value); announce(event.target.value ? `正在搜索：${event.target.value}` : "已清空搜索"); }} placeholder="搜索全部资产" /></label>
      <nav className="groups" aria-label="资产分类">{GROUPS.map(item => <button key={item.id} aria-pressed={group === item.id} className={group === item.id ? "active" : ""} onClick={() => chooseGroup(item.id)}><span className="group-glyph">{item.glyph}</span><span>{item.label}</span><b>{item.id === "all" ? data.assets.length : (data.counts[item.id] || 0)}</b></button>)}</nav>
      <div className="asset-list">{assets.length ? assets.map(asset => <button key={asset.id} aria-pressed={selectedId === asset.id} className={`asset-row ${selectedId === asset.id ? "selected" : ""}`} onClick={() => chooseAsset(asset)}><span className={`thumb-mark ${asset.group}`}>{asset.group === "video" ? "▶" : asset.group === "audio" ? "≋" : "◇"}</span><div><strong>{asset.name}</strong><small>{KIND_LABELS[asset.kind] || "制作资产"} · {formatBytes(asset.bytes)}</small></div><em className={asset.status}>{STATUS_LABELS[asset.status] || "已生成"}</em></button>) : <div className="empty-results">没有找到匹配的资产</div>}</div>
      <div className="sidebar-foot"><span><i /> AI 合成内容</span><b>{data.assets.length} 项资产</b></div>
    </aside>

    <header className="topbar">
      <div className="breadcrumbs"><span>项目</span><b>/</b><strong>{projectName}</strong><b>/</b><strong>{variant.title}</strong><em>{isCybercab ? "OMNI 音画审片" : "旧媒体预览"}</em></div>
      <nav className="mode-switch" aria-label="工作模式">
        {([{"id":"create","label":"创作"},{"id":"logic","label":"逻辑"},{"id":"review","label":"审片"}] as Array<{id: WorkspaceMode; label: string}>).map(item => <button key={item.id} aria-pressed={workspaceMode === item.id} onClick={() => { setWorkspaceMode(item.id); setAgentMode(item.id === "review" ? "review" : "production"); announce(`已进入${item.label}模式`); }}>{item.label}</button>)}
      </nav>
      <div className="interaction-feedback" role="status" aria-live="polite">{feedback}</div>
      <div className="header-status"><a className="version-index" href="/versions">四版本入口</a><span>{data.counts.video || 0} 条视频可审</span><button onClick={() => setTimelineOpen(value => !value)}>{timelineOpen ? "收起时间线" : "展开时间线"}</button><button onClick={() => setInspectorOpen(value => !value)}>{inspectorOpen ? "收起 Agent" : "展开 Agent"}</button></div>
    </header>

    <section className="workspace">
      {workspaceMode === "logic" ? <div className="logic-view">
        <header><div><span>AGENT SYSTEM</span><h1>每一次创作，都能看清它如何发生</h1><p>网页先把指令保存为 Task；只有远程 Runner 真正领取后，后续状态才会被点亮。</p></div><aside><small>当前安全状态</small><strong>等待 Runner 连接</strong><span>付费生成未授权 · training_eligible=false</span></aside></header>
        <div className="logic-pipeline">{PIPELINE_STEPS.map((step, index) => <article key={step.name} className={step.state}><i>{index + 1}</i><div><small>{step.name}</small><strong>{step.detail}</strong></div><span>{step.state === "ready" ? "就绪" : step.state === "waiting" ? "待连接" : step.state === "locked" ? "已锁定" : "等待"}</span></article>)}</div>
        <section className="logic-contracts"><article><small>当前输入</small><strong>{notes.length} 条持久化迭代指令</strong><p>每条指令绑定 case、资产和播放时间点，刷新或换设备后仍可恢复。</p></article><article><small>执行边界</small><strong>浏览器不直接运行 Shell</strong><p>Runner 只接收 harness/tools 中注册的有界 Action，不允许任意命令越权。</p></article><article><small>下一步连接</small><strong>CloudCLI Runner Bridge</strong><p>连接后将按租约领取 queued Task，并回写 Observation 和 Trajectory。</p></article></section>
      </div> : <>
      <div className="mode-banner"><span>{workspaceMode === "create" ? "创作模式" : "审片模式"}</span><strong>{workspaceMode === "create" ? "在右侧描述你想改变什么" : "选择资产与时间点，逐帧检查结果"}</strong><p>{workspaceMode === "create" ? "指令会持久保存；涉及付费媒体时仍需单独明确授权。" : "技术、独立视觉和人工审阅全部通过前，不进入训练集。"}</p></div>
      <div className="canvas-toolbar">
        <div><button onClick={() => setCanvasZoom(zoom - 10)} aria-label="缩小画布">−</button><span>{zoom}%</span><button onClick={() => setCanvasZoom(zoom + 10)} aria-label="放大画布">＋</button></div>
        <button onClick={() => setCanvasZoom(86)}>适合画布</button>
        <span className="canvas-mode">点阵画布 · 自动保存</span>
      </div>
      <div className="canvas-stage">
        <div className="canvas-flow" style={{ transform: `scale(${zoom / 100})` }}>
          <div className="node-tools">
            {selectedIsVideo && <button className="video-action" onClick={playSelectedVideo}>▶ 播放视频</button>}
            <button aria-pressed={Boolean(compareId)} onClick={toggleCompare}>{compareId ? "结束对比" : "A/B 对比"}</button>
            <a href={selected.url} target="_blank" rel="noreferrer">打开原件</a>
          </div>

          <article className="asset-node primary-node">
            <header><div><span className={`node-type ${selected.group}`}>{selected.group === "video" ? "VIDEO" : selected.group.toUpperCase()}</span><strong>{selected.name}</strong></div><span className={`node-status ${selected.status}`}>{STATUS_LABELS[selected.status] || "已生成"}</span></header>
            <div className={`preview-grid ${compare ? "compare" : ""} ${selectedIsVideo ? "video-preview" : ""}`}>
              <div className="preview-cell"><Preview asset={selected} videoRef={videoRef} /><span className="preview-label">{compare ? "当前画面" : selectedIsVideo ? "9:16 竖屏 · 完整预览" : "画布预览"}</span></div>
              {compare && <div className="preview-cell"><Preview asset={compare} /><span className="preview-label">对比画面</span></div>}
            </div>
            <footer><div><span className={`status-dot ${selected.status}`} /><strong>{STATUS_LABELS[selected.status] || "已生成"}</strong><span>{selected.model || selected.owner}</span></div><details><summary>查看详情</summary><p><b>来源</b>{selected.owner}</p><p><b>大小</b>{formatBytes(selected.bytes)}</p><p><b>路径</b>{selected.path}</p></details></footer>
          </article>

          <article className="context-node state-node">
            <span className="node-kicker">当前直播状态</span>
            <strong>{stateLabels[currentState?.time || 0] || "直播讲解"}</strong>
            <p>{currentState?.camera_semantics || "当前时间点的主播动作、商品状态与物理场景。"}</p>
            <div className="active-tags">{active.slice(0, 4).map(event => <button key={event.id} aria-pressed={focusedEventId === event.id} onClick={() => inspectEvent(event)}>{TRACK_LABELS[event.track]} · {eventLabel(event)}</button>)}</div>
            <div className="state-time"><b>{playhead.toFixed(1)}s</b><span>/ {data.timeline.duration}s</span></div>
          </article>

          <article className="context-node state-strip">
            <span className="node-kicker">关键状态</span>
            <div>{(data.timeline.reference_states || []).map(state => <button aria-pressed={Math.abs(playhead - state.time) < .05} className={Math.abs(playhead - state.time) < .05 ? "active" : ""} key={state.id} onClick={() => selectState(state.time)}><b>{state.time.toFixed(state.time % 1 ? 1 : 0)}s</b><span>{stateLabels[state.time] || "直播状态"}</span></button>)}</div>
          </article>

          <article className="context-node variant-settings-node">
            <header><div><span className="node-kicker">当前版本设置</span><strong>{variant.title}</strong></div>{isCybercab
              ? <a href={`/cybercab?variant=${variant.id}`} target="_blank" rel="noreferrer">打开此版本 ↗</a>
              : <a href={`/?variant=${variant.id}`} target="_blank" rel="noreferrer">打开此版本 ↗</a>}
            </header>
            <dl>
              <div><dt>画布</dt><dd>{variant.canvas} · {variant.orientation}</dd></div>
              <div><dt>语言</dt><dd>{variant.locale}</dd></div>
              <div><dt>弹幕槽位</dt><dd>最多 {variant.commentSlots} 条</dd></div>
              <div><dt>排版方式</dt><dd>{variant.presentation}</dd></div>
              <div><dt>可读界面</dt><dd>Code / HyperFrames</dd></div>
              <div><dt>媒体状态</dt><dd>{variant.mediaStatus}</dd></div>
            </dl>
            <footer><span><i /> training_eligible=false</span>{variantConfig && <button onClick={() => chooseAsset(variantConfig)}>打开完整配置</button>}</footer>
          </article>

          <article className="context-node variant-assets-node">
            <header><div><span className="node-kicker">版本素材</span><strong>合成快照与配置</strong></div><span>{variantAssets.length} 张快照</span></header>
            <div className="variant-thumbnails">
              {variantAssets.map(asset => <button key={asset.id} aria-pressed={selected.id === asset.id} onClick={() => chooseAsset(asset)}><img src={asset.url} alt={asset.name} /><span>{asset.name.replace("frame-", "").replace(".png", "")}</span></button>)}
            </div>
            <footer><button onClick={() => chooseGroup("all")}>查看全部 {data.assets.length} 项资产</button><span>canonical projection · human review pending</span></footer>
          </article>
        </div>
      </div>
      </>}
    </section>

    <aside className="inspector">
      <header className="agent-head"><div><span className="agent-avatar">VA</span><div><strong>直播制作 Agent</strong><small><i /> 在线 · {agentMode === "review" ? "审阅模式" : "制作模式"}</small></div></div><button onClick={() => setInspectorOpen(false)}>收起</button></header>
      <div className="agent-thread">
        <article className="agent-message"><span>AGENT</span><p>已载入当前 case 的全部资产和 {data.timeline.duration} 秒标准时间线。镜头、口播、弹幕、界面、礼物与 AR 保持独立轨道。</p></article>
        <article className="agent-message"><span>v5 制作路径</span><div className="step-list"><div className="done"><i>✓</i><p><strong>原生四版本合同</strong><small>中/英与横/竖各自独立 lineage</small></p></div><div className="active"><i>2</i><p><strong>Kling Camera Feed</strong><small>等待 provider adapter 与有界预算；当前不冒充已生成</small></p></div><div><i>3</i><p><strong>HyperFrames 直播合成</strong><small>可读 UI、流动弹幕、礼物与字幕由代码生成</small></p></div><div><i>4</i><p><strong>独立与人工审阅</strong><small>当前仍不可进入训练集</small></p></div></div></article>
        <article className="agent-message context"><span>当前上下文</span><strong>{selected.name}</strong><p>{playhead.toFixed(1)}s · {stateLabels[currentState?.time || 0] || "直播讲解"}</p><div>{active.slice(0, 3).map(item => <button key={item.id} onClick={() => inspectEvent(item)}>{eventLabel(item)}</button>)}</div></article>
        {notes.slice().reverse().map(note => <article key={note.id} className={`user-message ${note.assetId === selected.id ? "current" : ""}`}><header><span>你 · {note.playhead.toFixed(1)}s · {note.status === "queued" ? "等待执行" : note.status || "已保存"}</span><button aria-label="删除迭代指令" onClick={() => void deleteNote(note.id)}>删除</button></header><p>{note.text}</p></article>)}
        {!notes.length && <article className="agent-hint"><p>直接描述希望怎样修改。系统会自动绑定当前资产和播放时间点，并保存为等待 Runner 领取的 Task。</p></article>}
      </div>
      <div className="agent-composer"><textarea value={draft} onChange={event => setDraft(event.target.value)} placeholder={`告诉 Agent：${playhead.toFixed(1)}s 想怎样修改…`} onKeyDown={event => { if ((event.metaKey || event.ctrlKey) && event.key === "Enter") void addNote(); }} /><div><span><b>{workspaceMode === "review" ? "审阅指令" : "创作指令"}</b> · 不自动触发付费生成</span><button className="send-note" disabled={saving} onClick={() => void addNote()} aria-label="保存迭代指令">{saving ? "…" : "↑"}</button></div></div>
    </aside>

    <section className="timeline">
      <div className="timeline-controls"><div><strong>{data.timeline.duration} 秒时间线</strong><span>点击色块即可定位</span></div><div className="playback-buttons"><button aria-pressed={playing} onClick={() => { setPlaying(value => !value); announce(playing ? "时间线已暂停" : "时间线开始播放"); }}>{playing ? "暂停时间线" : "播放时间线"}</button><button onClick={() => jumpTo(0, "已回到开头")}>回到开头</button></div><input aria-label="时间线播放头" type="range" min="0" max={data.timeline.duration} step="0.1" value={playhead} onChange={event => { setPlayhead(Number(event.target.value)); setPlaying(false); announce(`定位到 ${Number(event.target.value).toFixed(1)} 秒`); }} /></div>
      <div className="timeline-board">
        <div className="ruler">{rulerTimes.map(time => <span key={time} style={{ left: `${time / data.timeline.duration * 100}%` }}>{time}s</span>)}</div>
        <div className="tracks">{TRACK_ORDER.map(track => <div className="track" key={track}><label>{TRACK_LABELS[track]}</label><div className="track-lane">{(data.timeline.tracks[track] || []).map(event => { const start = eventStart(event); const end = eventEnd(event); return <button key={event.id} aria-pressed={focusedEventId === event.id} title={`${eventLabel(event)} · ${start.toFixed(1)}s`} className={`event ${track} ${focusedEventId === event.id ? "focused" : ""}`} style={{ left: `${start / data.timeline.duration * 100}%`, width: `${Math.max((end - start) / data.timeline.duration * 100, 1.1)}%` }} onClick={() => inspectEvent({ ...event, track })}><span>{eventLabel(event)}</span></button>; })}<i className="playhead" style={{ left: `${playhead / data.timeline.duration * 100}%` }} /></div></div>)}</div>
      </div>
    </section>
  </main>;
}
