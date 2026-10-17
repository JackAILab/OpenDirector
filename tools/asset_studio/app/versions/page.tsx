import type { Metadata } from "next";
import data from "../data/studio-data.json";

export const metadata: Metadata = {
  title: "四版本入口 · VisualAgent",
  description: "从一个入口进入四个 VisualAgent 直播版本的无限画布工作台。",
};

const variants = [
  {
    id: "portrait-zh",
    tag: "9:16 · ZH-CN · LEGACY",
    title: "中文竖屏",
    description: "UI 与素材可审；当前为旧版中文竖屏媒体，v5 原生 Camera Feed 待生成。",
  },
  {
    id: "portrait-en",
    tag: "9:16 · EN · PLACEHOLDER",
    title: "English Portrait",
    description: "UI review only. The migrated Camera Feed still contains Chinese speech; native English media is pending.",
  },
  {
    id: "landscape-zh",
    tag: "16:9 · ZH-CN · PLACEHOLDER",
    title: "中文横屏",
    description: "UI 与素材可审；当前仍复用竖屏 Camera Feed，16:9 原生媒体待生成。",
  },
  {
    id: "landscape-en",
    tag: "16:9 · EN · PLACEHOLDER",
    title: "English Landscape",
    description: "UI review only. It still reuses portrait media with Chinese speech; native 16:9 English media is pending.",
  },
] as const;

function snapshotUrl(variant: string) {
  const prefix = `/jensen_rubin_live_60s_v4_multiformat/${variant}/snapshots/`;
  const preferred = data.assets.find(asset => asset.path.includes(prefix) && asset.name === "frame-04-at-59.0s.png");
  return preferred?.url || data.assets.find(asset => asset.path.includes(prefix))?.url;
}

export default function VersionsPage() {
  return (
    <main className="versions-page" data-page="visualagent-versions-v1">
      <header className="versions-header">
        <div>
          <p>VisualAgent · Live UI Review</p>
          <h1>一个地址，进入四个无限画布</h1>
          <span>点击任一版本即可查看对应设置、迁移媒体、关键画面、时间线和审阅状态。</span>
        </div>
        <aside><i />工作台可访问 · 原生媒体待生成</aside>
      </header>

      <a className="cybercab-entry" href="/cybercab">
        <div><small>NEW CASE · REVIEW BUILD READY</small><h2>Cybercab 直播审片</h2><p>60 秒竖屏中文审片版已接入：5 张参考状态、3 个保留视频段、确定性桥接、中文安全配音与 HTML 礼物/弹幕层。</p></div>
        <aside><span>9 / 9 次付费调用已使用</span><span>运动语义未通过 · 训练锁定</span><strong>打开互动审片工作台 ↗</strong></aside>
      </a>

      <a className="cybercab-entry iphone18-entry" href="/iphone18?variant=portrait-zh">
        <div><small>NEW CASE · BILINGUAL PREPRODUCTION</small><h2>iPhone 18 / 折叠屏概念直播</h2><p>中文与英文两条独立竖屏脚本、十二轮观众提问与主播回应、代码礼物层、事实/传闻边界和完整五轨时间线。</p></div>
        <aside><span>Apple 仅确认 9 月 9 日特别活动</span><span>神经相机待明确付费调用上限</span><strong>打开双语无限画布 ↗</strong></aside>
      </a>

      <section className="versions-grid" aria-label="四个直播版本">
        {variants.map(variant => (
          <a className="version-card" href={`/?variant=${variant.id}`} key={variant.id}>
            <div className={`version-thumb ${variant.id.startsWith("portrait") ? "portrait" : "landscape"}`}>
              {snapshotUrl(variant.id) && <img src={snapshotUrl(variant.id)} alt={`${variant.title} 合成快照`} />}
            </div>
            <div className="version-copy">
              <small>{variant.tag}</small>
              <h2>{variant.title}</h2>
              <p>{variant.description}</p>
              <strong>进入无限画布 <b aria-hidden="true">↗</b></strong>
            </div>
          </a>
        ))}
      </section>

      <footer className="versions-footer">
        <span>四个入口和工作台现在共用固定端口 50442</span>
        <span>training_eligible=false · 等待独立审阅与人工批准</span>
      </footer>
    </main>
  );
}
