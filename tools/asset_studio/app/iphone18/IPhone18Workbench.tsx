"use client";

import { useMemo, useState } from "react";
import Link from "next/link";

type Variant = "portrait-zh" | "portrait-en";

const tracks = [
  { label: "镜头", color: "#8ec5e2", items: [[0,15,"双机开场"],[15,15,"直板对比"],[30,15,"折叠形态"],[45,15,"购买清单"]] },
  { label: "口播", color: "#c9a9dd", items: [[0,5,"身份披露"],[5,10,"差异回应"],[15,10,"下单与参数"],[25,10,"多任务与相机"],[35,10,"耐用与选择"],[45,15,"价格与复盘"]] },
  { label: "弹幕", color: "#aab4aa", items: [[1.6,12,"连续提问"],[17.4,12,"购买问题"],[32.3,12,"影像/维修"],[48,10,"价格/发布会"]] },
  { label: "界面", color: "#badc54", items: [[0,6,"官方事实卡"],[15,6,"不可下单"],[30,6,"传闻边界"],[45,6,"购买清单"]] },
  { label: "礼物", color: "#ef8c82", items: [[33,3.5,"未来之光"]] },
] as const;

export default function IPhone18Workbench({ initialVariant }: { initialVariant?: string }) {
  const [variant, setVariant] = useState<Variant>(initialVariant === "portrait-en" ? "portrait-en" : "portrait-zh");
  const [playhead, setPlayhead] = useState(0);
  const [mode, setMode] = useState<"canvas" | "research">("canvas");
  const [previewKey, setPreviewKey] = useState(0);
  const locale = variant === "portrait-zh" ? "中文" : "English";
  const iframeUrl = useMemo(() => `/iphone18-live/index.html?variant=${variant}&run=${previewKey}`, [variant, previewKey]);
  const chooseVariant = (next: Variant) => {
    setVariant(next); setPlayhead(0); setPreviewKey(value => value + 1);
    window.history.replaceState(null, "", `/iphone18?variant=${next}`);
  };

  return <main className="iphone-workbench" data-studio="visualagent-iphone18-canvas-v1">
    <aside className="iphone-side">
      <Link className="iphone-brand" href="/versions"><span>VA</span><div><strong>VisualAgent</strong><small>LIVE STUDIO</small></div></Link>
      <nav><button className={mode === "canvas" ? "active" : ""} onClick={() => setMode("canvas")}>▱ 项目画布</button><button className={mode === "research" ? "active" : ""} onClick={() => setMode("research")}>◫ 事实与素材</button><Link href="/cybercab">EV Cybercab</Link><Link href="/">GPU 直播</Link></nav>
      <section><small>当前项目</small><h2>iPhone 18 概念直播</h2><p>60s · 中文/英文 · 9:16</p></section>
      <div className="iphone-variants"><button className={variant === "portrait-zh" ? "active" : ""} onClick={() => chooseVariant("portrait-zh")}><b>中文竖屏</b><span>独立中文脚本</span></button><button className={variant === "portrait-en" ? "active" : ""} onClick={() => chooseVariant("portrait-en")}><b>English Portrait</b><span>independent English script</span></button></div>
      <section className="iphone-assets"><small>资产组</small><button>◇ 设计系统 <b>1</b></button><button>≋ 双语脚本 <b>2</b></button><button>▱ 直播界面 <b>3</b></button><button>⚙ 时间线合同 <b>1</b></button><button>▶ 神经相机 <b>0</b></button></section>
      <footer><i></i> training_eligible=false</footer>
    </aside>

    <header className="iphone-header"><div><span>项目 / iPhone 18 概念直播 / </span><strong>{locale}竖屏</strong><em>发布会前预演</em></div><nav><button className={mode === "canvas" ? "active" : ""} onClick={() => setMode("canvas")}>画布</button><button className={mode === "research" ? "active" : ""} onClick={() => setMode("research")}>事实边界</button></nav><Link href="/versions">全部项目</Link></header>

    <section className="iphone-canvas">
      {mode === "canvas" ? <>
        <div className="iphone-canvas-tools"><button onClick={() => setPreviewKey(value => value + 1)}>↻ 从头播放</button><span>100%</span><b>点阵画布 · 自动保存</b></div>
        <div className="iphone-flow">
          <article className="iphone-preview-node"><header><div><span>LIVE UI</span><strong>{variant === "portrait-zh" ? "中文直播预演" : "English live preview"}</strong></div><em>可审</em></header><div className="iphone-frame"><iframe key={previewKey} src={iframeUrl} title={`${locale} iPhone 18 concept live preview`} /></div><footer><span><i></i>HyperFrames prototype</span><b>神经相机画面尚未生成</b></footer></article>
          <article className="iphone-truth-node"><small>当前事实状态</small><h2>产品未由苹果正式公布</h2><p>截至 2026-09-06，苹果只确认 9 月 9 日特别活动。所有 iPhone 18 Pro Max 与折叠屏命名、规格和价格均等待官方确认。</p><div><b>OFFICIAL</b><span>活动时间</span></div><div><b>UNCONFIRMED</b><span>产品名称、规格、价格、库存</span></div></article>
          <article className="iphone-contract-node"><small>双语原生媒体合同</small><h2>不是翻译同一条视频</h2><ul><li>中文与英文各自独立 native speech</li><li>每段镜头绑定对应语言台词与观众问题</li><li>所有文字、弹幕、价格与按钮由代码生成</li><li>付费生成需单独给出具体最大调用次数</li></ul></article>
        </div>
      </> : <div className="iphone-research"><header><small>RESEARCH SNAPSHOT · 2026-09-06</small><h1>官方事实与传闻分层</h1><p>工作台不会把发布会前的传闻伪装成现货销售参数。</p></header><div><article><b>苹果官方</b><h2>9 月 9 日特别活动</h2><p>活动已确认；现有官网产品阵容仍是 iPhone 17 系列、iPhone Air 与 iPhone 16。</p><a href="https://developer.apple.com/hello/september26/" target="_blank" rel="noreferrer">打开 Apple 官方活动页 ↗</a></article><article><b>媒体传闻</b><h2>Pro Max 与折叠形态</h2><p>名称、规格、售价、上市节奏均未获苹果确认，只能作为镜头创意参考，不能进入购买承诺。</p><a href="https://www.apple.com/iphone/" target="_blank" rel="noreferrer">核对 Apple 当前阵容 ↗</a></article><article><b>直播交互</b><h2>问题必须被主播回答</h2><p>十二条弹幕中十条是问题；每个口播段绑定一组观众问题，并在回答前提升为 pinned question。</p><a href="/iphone18-live/index.html?variant=portrait-zh" target="_blank">打开纯直播预演 ↗</a></article></div></div>}
    </section>

    <section className="iphone-timeline"><div className="timeline-master"><button onClick={() => setPreviewKey(value => value + 1)}>▶ 播放预演</button><button onClick={() => { setPlayhead(0); setPreviewKey(value => value + 1); }}>回到开头</button><input type="range" min="0" max="60" step="0.1" value={playhead} onChange={event => setPlayhead(Number(event.target.value))}/><b>{playhead.toFixed(1)} / 60.0s</b></div><div className="iphone-tracks"><div className="iphone-ruler">{[0,10,20,30,40,50,60].map(time => <span key={time} style={{left:`${time/60*100}%`}}>{time}s</span>)}</div>{tracks.map(track => <div className="iphone-track" key={track.label}><label>{track.label}</label><div>{track.items.map(([start,duration,text]) => <button key={`${track.label}-${start}`} style={{left:`${start/60*100}%`,width:`${duration/60*100}%`,background:track.color}} onClick={() => setPlayhead(start)}>{text}</button>)}<i style={{left:`${playhead/60*100}%`}}></i></div></div>)}</div></section>
  </main>;
}
