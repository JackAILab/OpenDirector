import data from "../data/tvc-benchmark.json";

export const metadata = { title: "十支原创广告 · VisualAgent" };

export default function TvcBenchmark() {
  const cases = [...data.cases].sort((a, b) => Number(Boolean(b.video)) - Number(Boolean(a.video)));
  return <main data-studio="visualagent-tvc-benchmark-v1" style={{ minHeight: "100vh", background: "#101415", color: "#ecf0e9", padding: "40px clamp(16px, 4vw, 64px)", fontFamily: "Studio Chinese, sans-serif" }}>
    <header style={{ maxWidth: 1440, margin: "0 auto 32px" }}>
      <a href="/" style={{ color: "#c2d2bd" }}>← 制作台</a>
      <p style={{ color: "#acbd9c", marginTop: 32 }}>VISUALAGENT / 原创广告实验</p>
      <h1 style={{ fontSize: "clamp(30px, 5vw, 58px)", margin: "10px 0" }}>十个商品，十支广告。</h1>
      <p style={{ color: "#b1bbb3", lineHeight: 1.8 }}>已生成 {data.completed} / 10 支 · 15 秒 · 横屏 1080p · 原生音频</p>
      <a href={data.inputArchive} download style={{ display: "inline-block", padding: "12px 20px", borderRadius: 8, background: "#d3e7b8", color: "#172013", fontWeight: 700 }}>下载十案例对比输入包</a>
      <p style={{ color: "#9ba59e", fontSize: 14 }}>输入包包含简报、主体定义与参考图。审片发现的问题保留在每个案例下方。</p>
    </header>
    <section style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 440px), 1fr))", gap: 24, maxWidth: 1440, margin: "auto" }}>
      {cases.map(item => <article key={item.id} style={{ border: "1px solid #35403a", borderRadius: 16, overflow: "hidden", background: "#1a201d" }}>
        <div style={{ aspectRatio: "16/9", background: "#080b09", display: "grid", placeItems: "center", position: "relative", overflow: "hidden" }}>
          {item.video ? <video controls preload="metadata" playsInline src={item.video} style={{ position: "absolute", inset: 0, width: "100%", height: "100%", objectFit: "contain" }} /> : <span style={{ color: "#a9b5ab" }}>{item.status}</span>}
        </div>
        <div style={{ padding: 24 }}>
          <p style={{ color: "#b8ce9f", fontSize: 13 }}>{item.status}{item.technicalPassed ? " · 媒体检查通过" : ""}</p>
          <h2 style={{ fontSize: 23 }}>{item.title}</h2>
          {item.video && <a href={item.video} download style={{ color: "#d3e7b8" }}>下载视频</a>}
          {item.findings.length > 0 && <ul style={{ paddingLeft: 20, color: "#c0c9c1", lineHeight: 1.8 }}>{item.findings.filter(f => f.severity !== "info").map((f, i) => <li key={i}>{f.detail}</li>)}</ul>}
          <details style={{ marginTop: 20 }}><summary style={{ cursor: "pointer", color: "#d3e7b8" }}>查看统一输入与参考图</summary>
            {item.reference && <img src={item.reference} alt={`${item.title}参考图`} loading="lazy" style={{ width: "100%", marginTop: 16, borderRadius: 8 }} />}
            <p style={{ whiteSpace: "pre-wrap", lineHeight: 1.8, color: "#b1bbb3", fontSize: 14 }}>{item.brief}</p>
          </details>
        </div>
      </article>)}
    </section>
  </main>;
}
