const root = document.querySelector(".composition");
if (!root) throw new Error("VisualAgent v4 composition root is missing");
if (!window.gsap) throw new Error("GSAP did not load");

const locale = root.dataset.locale;
const layout = root.dataset.layout;
const isZh = locale === "zh";
const isPortrait = layout === "portrait";
root.classList.add(`locale-${locale}`);

const copy = isZh ? {
  host: "VisualAgent 硬件演示",
  meta: "代码界面 · 迁移媒体",
  demo: "演示流",
  disclosure: "AI 合成画面 · 界面文字由代码生成",
  rail: "实时讨论",
  railMeta: "演示",
  system: "这是可复现的合成直播演示。弹幕、按钮、计数与商品信息均由 HTML 生成。",
  composer: "说点什么…",
  like: "点赞",
  share: "分享",
  bag: "样机",
  productKicker: "参考样机 · 非销售承诺",
  productTitle: "GPU 演示画面",
  productCopy: "参数、价格与库存请以官方资料为准；本界面只展示排版和互动节奏。",
  gifts: {
    rocket: ["render_farm 送出", "星际火箭", "×1"],
    car: ["small_case 送出", "霓虹跑车", "×1"],
    glasses: ["vision_lab 送出", "AR 墨镜", "×1"]
  },
  stage: "迁移媒体 · 60 秒 · 9:16 源",
  comments: [
    [1.2,"机箱观察员","显卡功耗这么高，电源真的够用吗？","18"],
    [5.6,"风道研究所","先讲散热还是接口？","25"],
    [9.4,"装机新手","新一代架构最值得注意什么？","12"],
    [13.3,"线材整理员","这个清单能按步骤再过一遍吗？","37"],
    [17.2,"像素追踪者","刚才的镜头是演示画面吗？","16"],
    [21.0,"边界检查员","产品靠近镜头时细节很清楚","22"],
    [25.2,"接口地图","供电接口要怎样确认？","31"],
    [29.7,"散热笔记","风道方向能画出来吗？","14"],
    [34.0,"小机箱玩家","长度和侧板距离都要量吗？","28"],
    [38.4,"稳定帧率","请继续讲线材转弯空间","19"],
    [43.7,"硬件问答","这些文字都是后期代码层吗？","33"],
    [48.1,"清单收藏家","演示信息很容易扫读","21"],
    [53.2,"装机复盘","最后能再总结一次吗？","26"],
    [57.1,"画面质检","收到，等人工审核","11"]
  ]
} : {
  host: "VisualAgent Hardware Demo",
  meta: "CODE UI · MIGRATED MEDIA",
  demo: "DEMO FEED",
  disclosure: "AI-generated scene · readable UI rendered in code",
  rail: "Live discussion",
  railMeta: "DEMO",
  system: "This is a reproducible synthetic live demo. Comments, controls, counters and product labels are rendered in HTML.",
  composer: "Add a comment…",
  like: "Like",
  share: "Share",
  bag: "Demo",
  productKicker: "REFERENCE UNIT · NO SALES CLAIM",
  productTitle: "GPU visual demonstration",
  productCopy: "Verify specifications, pricing and availability with official sources. This layer demonstrates layout and interaction only.",
  gifts: {
    rocket: ["render_farm sent", "Stellar Rocket", "×1"],
    car: ["small_case sent", "Neon Sports Car", "×1"],
    glasses: ["vision_lab sent", "AR Sunglasses", "×1"]
  },
  stage: "MIGRATED MEDIA · 60 SEC · 9:16 SOURCE",
  comments: [
    [1.2,"power_trace","Is the power headroom enough for this build?","18"],
    [5.6,"airflow_lab","Cooling first, or should we check connectors?","25"],
    [9.4,"build_newbie","What matters most in the new architecture?","12"],
    [13.3,"cable_route","Can you walk through the checklist again?","37"],
    [17.2,"pixel_watch","Is the current shot part of the demo footage?","16"],
    [21.0,"edge_check","The close-up makes the physical details clear.","22"],
    [25.2,"port_map","How should we verify the power connector?","31"],
    [29.7,"thermal_notes","Could you map the airflow direction?","14"],
    [34.0,"small_case","Should we measure length and side-panel space?","28"],
    [38.4,"steady_frames","Please cover cable bend clearance next.","19"],
    [43.7,"hardware_qna","Is every readable label a code layer?","33"],
    [48.1,"list_keeper","The information is easy to scan.","21"],
    [53.2,"build_recap","Could you close with a quick recap?","26"],
    [57.1,"visual_qa","Got it — pending human review.","11"]
  ]
};

const ui = root.querySelector(".ui-root");
ui.innerHTML = `
  <div class="video-grade"></div>
  <header class="topbar">
    <div class="identity"><div class="avatar">VA</div><div class="identity-copy"><div class="host-name">${copy.host}</div><div class="host-meta">${copy.meta}</div></div></div>
    <div class="live-pill"><i></i>LIVE</div><div class="demo-pill">${copy.demo}</div>
  </header>
  <div class="disclosure"><strong>AI</strong><span>${copy.disclosure}</span></div>
  <aside class="action-rail" aria-label="Live actions">
    <div class="action"><div class="action-button">♡</div><span class="action-label">${copy.like}</span></div>
    <div class="action"><div class="action-button">↗</div><span class="action-label">${copy.share}</span></div>
    <div class="action"><div class="action-button">▣</div><span class="action-label">${copy.bag}</span></div>
  </aside>
  <aside class="discussion-rail"><div class="rail-head"><strong>${copy.rail}</strong><span>${copy.railMeta}</span></div><div class="system-note">${copy.system}</div></aside>
  <section class="comments" aria-label="${copy.rail}"></section>
  <article class="priority-card" aria-label="Product information" data-layout-allow-overlap data-layout-allow-overflow><span class="demo-chip">DEMO</span><div class="product-kicker">${copy.productKicker}</div><div class="product-title">${copy.productTitle}</div><div class="product-copy">${copy.productCopy}</div></article>
  <div class="gift-stage" aria-label="Code-rendered gift effects" data-layout-ignore>
    <div id="gift-rocket" class="gift-hero gift-rocket"><img src="assets/live_fx/rocket-premium-v1.png" alt=""></div>
    <div id="gift-car" class="gift-hero gift-car"><img src="assets/live_fx/sports-car-premium-v1.png" alt=""></div>
    <div id="gift-glasses" class="gift-glasses" aria-hidden="true"><svg viewBox="0 0 310 118"><defs><linearGradient id="lens-${root.id}" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#111716"></stop><stop offset=".62" stop-color="#355348"></stop><stop offset="1" stop-color="#b7f52a" stop-opacity=".54"></stop></linearGradient></defs><path class="glasses-arm" d="M10 28L0 16M300 28l10-12"></path><path class="lens" style="fill:url(#lens-${root.id})" d="M13 28h122v42c0 27-20 40-55 40-38 0-57-19-60-51z"></path><path class="lens" style="fill:url(#lens-${root.id})" d="M175 28h122l-7 31c-3 32-22 51-60 51-35 0-55-13-55-40z"></path><path class="bridge" d="M135 45c14-8 26-8 40 0"></path></svg></div>
    <div id="gift-impact" class="gift-impact"></div>
    <i class="speed-line s1"></i><i class="speed-line s2"></i><i class="speed-line s3"></i>
    ${Array.from({length: 12}, (_, index) => `<i class="gift-particle p${index + 1}"></i>`).join("")}
  </div>
  <aside id="gift-banner" class="gift-banner"><div class="gift-emblem"><img src="assets/live_fx/crystal-gift-box-v1.png" alt=""></div><div><div class="gift-user"></div><div class="gift-name"></div></div><strong class="gift-count"></strong></aside>
  <div class="stage-label">${copy.stage}</div><div class="stage-rule"></div>
  <footer class="composer"><div class="composer-input">${copy.composer}</div><div class="composer-button">☺</div><div class="composer-button">♡</div></footer>
  <span class="heart h1" data-layout-allow-overlap>♥</span><span class="heart h2" data-layout-allow-overlap>♥</span><span class="heart h3" data-layout-allow-overlap>♥</span><span class="heart h4" data-layout-allow-overlap>♥</span>
`;

const commentHost = ui.querySelector(".comments");
const commentNodes = copy.comments.map(([at, user, body, badge], index) => {
  const node = document.createElement("article");
  node.className = "comment";
  node.dataset.at = String(at);
  node.style.setProperty("--avatar-hue", String((index * 47 + 168) % 360));
  node.innerHTML = `<div class="comment-avatar">${user.slice(0, 1).toUpperCase()}</div><div class="comment-line" data-layout-allow-overlap><span class="comment-head"><span class="comment-badge">${badge}</span><span class="comment-user">${user}</span></span><span class="comment-text">${body}</span></div>`;
  commentHost.appendChild(node);
  return node;
});

const tl = gsap.timeline({ paused: true });
const maxVisible = isPortrait ? (isZh ? 4 : 3) : 6;
const rowGap = isPortrait ? (isZh ? 96 : 156) : (isZh ? 78 : 124);
gsap.set([".priority-card", ".gift-hero", ".gift-glasses", ".gift-impact", ".speed-line", ".gift-particle", ".gift-banner", ".heart"], { opacity: 0 });
gsap.set(commentNodes, { opacity: isPortrait ? 0 : 1, visibility: "hidden" });

copy.comments.forEach(([at], index) => {
  const node = commentNodes[index];
  const entryAt = isPortrait && !isZh ? at + .08 : at;
  const firstActive = Math.max(0, index - maxVisible + 1);
  for (let previous = firstActive; previous < index; previous += 1) {
    tl.to(commentNodes[previous], { y: -rowGap * (index - previous), duration: .22, ease: "power3.out" }, Math.max(0, at - .22));
  }
  if (index >= maxVisible) {
    const retiring = commentNodes[index - maxVisible];
    if (isPortrait) {
      tl.to(retiring, { opacity: 0, y: -rowGap * maxVisible - 22, duration: .18, ease: "power2.in" }, at - .22);
      tl.set(retiring, { visibility: "hidden" }, at - .04);
    } else {
      tl.set(retiring, { visibility: "hidden" }, at - .22);
    }
  }
  tl.set(node, { visibility: "visible" }, entryAt);
  tl.fromTo(node, { opacity: isPortrait ? 0 : 1, y: 28, scale: .985 }, { opacity: 1, y: 0, scale: 1, duration: .24, ease: "power3.out" }, entryAt);
});
tl.to(commentNodes.at(-1), { opacity: isPortrait ? 0 : 1, y: -24, duration: .26, ease: "power2.in" }, 59.25);
tl.set(commentNodes.at(-1), { visibility: "hidden" }, 59.51);

const productWindows = [[12.0,15.6],[24.0,27.5],[34.0,37.2],[48.0,51.5]];
const giftWindows = [[18.0,20.34],[41.0,43.32],[22.76,23.65]];
const yieldComments = (start, end) => {
  tl.to(".comments", { opacity: 0, duration: .12, ease: "power2.out" }, start - .14);
  tl.set(".comments", { visibility: "hidden" }, start);
  tl.set(".comments", { visibility: "visible" }, end);
  tl.to(".comments", { opacity: 1, duration: .2, ease: "power2.out" }, end);
};
productWindows.forEach(([start, end]) => {
  tl.fromTo(".priority-card", { opacity: 1, x: isPortrait ? -790 : -520, y: 10 }, { opacity: 1, x: 0, y: 0, duration: .3, ease: "power3.out" }, start);
  tl.to(".priority-card", { opacity: 1, x: isPortrait ? -790 : -520, duration: .24, ease: "power2.in" }, end - .24);
  tl.set(".priority-card", { opacity: 0 }, end);
  yieldComments(start, end);
});
const bannerNodes = {
  user: ui.querySelector(".gift-user"),
  name: ui.querySelector(".gift-name"),
  count: ui.querySelector(".gift-count")
};
const setGiftCopy = (kind, at) => {
  const [user, name, count] = copy.gifts[kind];
  tl.set(bannerNodes.user, { textContent: user }, at);
  tl.set(bannerNodes.name, { textContent: name }, at);
  tl.set(bannerNodes.count, { textContent: count }, at);
};
const showGiftBanner = (kind, start, end) => {
  setGiftCopy(kind, start - .01);
  tl.fromTo("#gift-banner", { opacity: 0, x: isPortrait ? -74 : -34, y: 12, scale: .82 }, { opacity: 1, x: 0, y: 0, scale: 1, duration: .32, ease: "back.out(1.7)" }, start + .2);
  tl.to("#gift-banner", { opacity: 0, y: -14, scale: .96, duration: .28, ease: "power2.in" }, end - .28);
};
const particleVectors = [
  [-238,-132],[-178,-214],[-92,-262],[22,-280],[126,-244],[214,-164],
  [252,-62],[224,54],[152,118],[52,144],[-64,130],[-166,72]
];
const burstParticles = (start, speed = 1) => ui.querySelectorAll(".gift-particle").forEach((node, index) => {
  const [dx, dy] = particleVectors[index];
  tl.fromTo(node, { x: 0, y: 0, scale: 0, rotation: index * 17, opacity: 0 }, { x: dx, y: dy, scale: 1, rotation: index * 43, opacity: .95, duration: .58 * speed, ease: "power3.out" }, start + index * .012 * speed);
  tl.to(node, { x: dx * 1.16, y: dy * 1.2 + 56, scale: .2, opacity: 0, duration: .4 * speed, ease: "power2.in" }, start + .58 * speed + index * .012 * speed);
});
const animateRocket = (start, end) => {
  showGiftBanner("rocket", start, end);
  tl.fromTo("#gift-rocket", { x: -340, y: 280, rotation: -18, scale: .34, opacity: 0 }, { x: -270, y: 225, rotation: -12, scale: .7, opacity: 1, duration: .16, ease: "power2.in" }, start);
  tl.to("#gift-rocket", { x: -205, y: 165, rotation: -7, scale: 1.06, duration: .22, ease: "back.out(2.0)" }, start + .16);
  tl.to("#gift-rocket", { x: isPortrait ? 350 : 810, y: isPortrait ? -760 : -520, rotation: 9, scale: .96, duration: .9, ease: "power3.inOut" }, start + .38);
  tl.to("#gift-rocket", { x: isPortrait ? 390 : 930, y: isPortrait ? -920 : -610, rotation: 11, scale: 1.01, duration: .7, ease: "power2.out" }, start + 1.28);
  tl.to("#gift-rocket", { x: isPortrait ? 430 : 1120, y: isPortrait ? -1120 : -720, scale: .82, opacity: 0, duration: .34, ease: "power3.in" }, end - .34);
  burstParticles(start + .18);
};
const animateCar = (start, end) => {
  showGiftBanner("car", start, end);
  tl.fromTo("#gift-car", { x: isPortrait ? -940 : -820, y: 105, rotation: -4, scale: .54, opacity: 0 }, { x: isPortrait ? -760 : -650, y: 74, rotation: -2, scale: .72, opacity: 1, duration: .14, ease: "power2.in" }, start);
  tl.to("#gift-car", { x: isPortrait ? -555 : -410, y: 28, rotation: 1, scale: 1.08, duration: .24, ease: "back.out(2.2)" }, start + .14);
  tl.to("#gift-car", { x: isPortrait ? 62 : 170, y: 0, rotation: 0, scale: 1.02, duration: .8, ease: "power4.out" }, start + .38);
  tl.to("#gift-car", { x: isPortrait ? 105 : 220, y: -7, scale: 1, duration: .78, ease: "power2.out" }, start + 1.18);
  tl.to("#gift-car", { x: isPortrait ? 980 : 1420, y: -30, scale: .9, opacity: 0, duration: .34, ease: "power3.in" }, end - .34);
  tl.fromTo("#gift-impact", { scale: .22, opacity: 0 }, { scale: 1, opacity: .82, duration: .24, ease: "back.out(1.8)" }, start + .22);
  tl.to("#gift-impact", { scale: 1.58, opacity: 0, duration: .52, ease: "power2.out" }, start + .46);
  tl.fromTo(".speed-line", { x: -360, opacity: 0 }, { x: isPortrait ? 690 : 960, opacity: .88, duration: .72, stagger: .045, ease: "power3.out" }, start + .12);
  tl.to(".speed-line", { x: isPortrait ? 960 : 1340, opacity: 0, duration: .34, stagger: .025, ease: "power2.in" }, start + .92);
  burstParticles(start + .26);
};
const animateGlasses = (start, end) => {
  showGiftBanner("glasses", start, end);
  tl.fromTo("#gift-glasses", { opacity: 0, scale: .7, y: -15, rotation: -3 }, { opacity: 1, scale: 1, y: 0, rotation: 0, duration: .34, ease: "back.out(1.25)" }, start + .18);
  tl.to("#gift-glasses", { scale: 1.035, duration: .72, ease: "sine.inOut" }, start + .52);
  tl.to("#gift-glasses", { opacity: 0, scale: .91, y: -8, duration: .28, ease: "power2.in" }, end - .28);
  burstParticles(start + .2, .45);
};
animateRocket(...giftWindows[0]);
animateCar(...giftWindows[1]);
animateGlasses(...giftWindows[2]);
giftWindows.forEach(([start, end]) => yieldComments(start, end));

[[9.7,0],[27.2,1],[45.0,2],[56.9,3]].forEach(([start, offset]) => {
  document.querySelectorAll(".heart").forEach((heart, index) => {
    const drift = (index - 1.5) * 24 + offset * 5;
    tl.fromTo(heart, { opacity: 0, x: 0, y: 0, scale: .35, rotation: 0 }, { opacity: .94, x: drift, y: -250 - index * 38, scale: .72 + index * .08, rotation: drift / 2, duration: 1.2 + index * .09, ease: "power2.out" }, start + index * .11);
    tl.to(heart, { opacity: 0, y: -320 - index * 42, duration: .32, ease: "power2.in" }, start + 1.28 + index * .1);
  });
});

const softenBoundary = (seconds) => {
  const enter = seconds - .13;
  tl.fromTo(".continuity-veil", { opacity: 0, backdropFilter: "blur(0px) saturate(.9)" }, { opacity: .52, backdropFilter: "blur(9px) saturate(.88)", duration: .13, ease: "power1.in" }, enter);
  tl.to(".continuity-veil", { opacity: 0, backdropFilter: "blur(0px) saturate(.94)", duration: .18, ease: "power1.out" }, seconds);
  tl.to(".camera-video", { scale: 1.005, duration: .13, ease: "power1.in" }, enter);
  tl.to(".camera-video", { scale: 1, duration: .18, ease: "power1.out" }, seconds);
};
[7.5, 15, 22.5, 30, 37.5, 45, 52.5].forEach(softenBoundary);

tl.to(".video-grade", { opacity: .82, duration: 59.6, ease: "none" }, .2);
window.__timelines = window.__timelines || {};
window.__timelines[root.id] = tl;
