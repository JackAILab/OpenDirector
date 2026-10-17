const root = document.querySelector(".composition");
if (!root) throw new Error("Cybercab composition root missing");
if (!window.gsap) throw new Error("GSAP did not load");

const comments = [
  [2.0,"未来车库","这台车真的只有两个座位吗？","18"],
  [5.2,"车迷小周","蝴蝶门是这样打开的吗？","25"],
  [9.1,"城市漫游","金色车身在展厅里很醒目","12"],
  [13.4,"体验观察员","这是封闭场地演示对吧？","37"],
  [17.1,"未来乘客","真的没有方向盘和踏板吗？","16"],
  [21.0,"安全带先扣","上车空间看起来很直接","22"],
  [25.0,"座舱研究所","中控会显示路线确认吗？","31"],
  [29.1,"连续性检查","车门关闭过程很连贯","14"],
  [33.0,"安全观察员","出发前会确认安全带吗？","28"],
  [37.2,"画面质检","当前只是合成审片，不是实车广告","19"],
  [41.2,"礼物小队","墨镜效果终于回来了 😎","33"],
  [45.5,"运动审核","车辆开始低速起步了","21"],
  [49.0,"城市漫游","窗外背景在平稳移动","26"],
  [54.0,"语义评审","请继续检查车内物体稳定性","11"],
  [58.0,"人工审核员","原生音画齐全，继续保持训练锁定","42"]
];
const captions = [
  [.6,12.8,"从外观开始，看清关键细节"],
  [15.4,27.8,"无方向盘、无踏板，乘员就是乘客"],
  [30.4,42.8,"确认安全带与行程状态"],
  [45.4,57.8,"封闭路线低速自动行驶演示"]
];
const cards = [
  [9,11.7,"金色双座自动驾驶体验车","合成车辆演示；规格、量产与可用性不作承诺。"],
  [31,37,"封闭场地 · 乘客体验","先确认安全带、乘员状态与演示区域，再进入运动审查。"]
];
const giftCopy = {
  rocket:["星轨观察员 送出","星际火箭","×1"],
  car:["未来乘客 送出","霓虹跑车","×1"],
  glasses:["座舱研究所 送出","酷黑墨镜","×1"]
};

const host = document.querySelector("#comments");
const nodes = comments.map(([at,user,text,badge],index) => {
  const node = document.createElement("article");
  node.className = "comment";
  node.dataset.layoutAllowOverflow = "";
  node.style.setProperty("--h", String((index * 47 + 164) % 360));
  node.innerHTML = `<div class="comment-avatar">${user.slice(0,1)}</div><div class="comment-copy" data-layout-allow-overlap><span class="comment-badge">${badge}</span><span class="comment-user">${user}</span><span class="comment-text">${text}</span></div>`;
  host.appendChild(node);
  return node;
});

const tl = gsap.timeline({paused:true});
gsap.set(nodes,{opacity:0,visibility:"hidden"});
gsap.set(["#info-card","#rocket","#sports-car","#sunglasses","#gift-banner","#impact",".speed-line",".particle","#subtitle"],{opacity:0});

const visible = 4;
comments.forEach(([at],index) => {
  const first = Math.max(0,index-visible+1);
  for(let previous=first; previous<index; previous+=1){
    tl.to(nodes[previous],{y:-98*(index-previous),duration:.24,ease:"power3.out"},Math.max(0,at-.23));
  }
  if(index>=visible){
    const old = nodes[index-visible];
    tl.to(old,{opacity:0,y:-420,duration:.18,ease:"power2.in"},at-.23);
    tl.set(old,{visibility:"hidden"},at-.04);
  }
  tl.set(nodes[index],{visibility:"visible"},at);
  tl.fromTo(nodes[index],{opacity:0,y:28,scale:.985},{opacity:1,y:0,scale:1,duration:.25,ease:"power3.out"},at);
});

const subtitle = document.querySelector("#subtitle");
captions.forEach(([start,end,text]) => {
  tl.set(subtitle,{textContent:text},start-.01);
  tl.fromTo(subtitle,{opacity:0,y:12},{opacity:1,y:0,duration:.2,ease:"power2.out"},start);
  tl.to(subtitle,{opacity:0,y:-8,duration:.2,ease:"power2.in"},end-.2);
});

const card = document.querySelector("#info-card");
cards.forEach(([start,end,title,body]) => {
  tl.set(card.querySelector("h2"),{textContent:title},start-.02);
  tl.set(card.querySelector("p"),{textContent:body},start-.02);
  tl.to("#comments",{opacity:0,duration:.12},start-.12);
  tl.fromTo(card,{opacity:0,x:-820,y:12},{opacity:1,x:0,y:0,duration:.34,ease:"power3.out"},start);
  tl.to(card,{opacity:0,x:-820,duration:.27,ease:"power2.in"},end-.27);
  tl.to("#comments",{opacity:1,duration:.2},end);
});

const banner = document.querySelector("#gift-banner");
const particleVectors=[[-250,-150],[-185,-235],[-92,-285],[35,-298],[142,-250],[234,-160],[260,-40],[168,118]];
function giftBanner(kind,start,end){
  const [user,name,count]=giftCopy[kind];
  tl.set(banner.querySelector("small"),{textContent:user},start-.02);
  tl.set(banner.querySelector("strong"),{textContent:name},start-.02);
  tl.set(banner.querySelector("b"),{textContent:count},start-.02);
  tl.fromTo(banner,{opacity:0,x:-80,y:14,scale:.82},{opacity:1,x:0,y:0,scale:1,duration:.34,ease:"back.out(1.6)"},start+.18);
  tl.to(banner,{opacity:0,y:-14,scale:.96,duration:.28,ease:"power2.in"},end-.28);
}
function yieldComments(start,end){
  tl.to("#comments",{opacity:0,duration:.12,ease:"power2.out"},start-.12);
  tl.set("#comments",{visibility:"hidden"},start);
  tl.set("#comments",{visibility:"visible"},end);
  tl.to("#comments",{opacity:1,duration:.2,ease:"power2.out"},end);
}
function burst(start){
  document.querySelectorAll(".particle").forEach((node,index)=>{
    const [x,y]=particleVectors[index];
    tl.fromTo(node,{opacity:0,x:0,y:0,scale:0},{opacity:.95,x,y,scale:1,duration:.58,ease:"power3.out"},start+index*.014);
    tl.to(node,{opacity:0,x:x*1.15,y:y*1.2+55,scale:.2,duration:.38,ease:"power2.in"},start+.58+index*.014);
  });
}
function rocket(start,end){
  giftBanner("rocket",start,end); burst(start+.2);
  tl.fromTo("#rocket",{opacity:0,x:-350,y:300,rotation:-18,scale:.34},{opacity:1,x:-230,y:190,rotation:-8,scale:1.05,duration:.4,ease:"back.out(1.8)"},start);
  tl.to("#rocket",{x:440,y:-1150,rotation:11,scale:.82,opacity:0,duration:1.55,ease:"power3.inOut"},start+.42);
}
function sportsCar(start,end){
  giftBanner("car",start,end); burst(start+.25);
  tl.fromTo("#sports-car",{opacity:0,x:-980,y:105,rotation:-4,scale:.52},{opacity:1,x:55,y:0,rotation:0,scale:1.02,duration:1.1,ease:"power4.out"},start);
  tl.fromTo("#impact",{opacity:0,scale:.2},{opacity:.82,scale:1,duration:.28,ease:"back.out(1.8)"},start+.24);
  tl.to("#impact",{opacity:0,scale:1.58,duration:.52,ease:"power2.out"},start+.52);
  tl.fromTo(".speed-line",{opacity:0,x:-390},{opacity:.88,x:730,duration:.74,stagger:.045,ease:"power3.out"},start+.12);
  tl.to(".speed-line",{opacity:0,x:1020,duration:.32,stagger:.025},start+.92);
  tl.to("#sports-car",{opacity:0,x:1030,y:-30,scale:.9,duration:.38,ease:"power3.in"},end-.38);
}
function sunglasses(start,end){
  giftBanner("glasses",start,end); burst(start+.22);
  tl.fromTo("#sunglasses",{opacity:0,scale:.68,y:-18,rotation:-3},{opacity:1,scale:1,y:0,rotation:0,duration:.36,ease:"back.out(1.3)"},start+.15);
  tl.to("#sunglasses",{scale:1.04,duration:.7,ease:"sine.inOut"},start+.51);
  tl.to("#sunglasses",{opacity:0,scale:.9,y:-10,duration:.3,ease:"power2.in"},end-.3);
}
rocket(12,14.6); sportsCar(27,29.6); sunglasses(41,43.8);
[[12,14.6],[27,29.6],[41,43.8]].forEach(([start,end])=>yieldComments(start,end));

function softenBoundary(second){
  tl.fromTo(".continuity-veil",{opacity:0,backdropFilter:"blur(0px) saturate(.9)"},{opacity:.52,backdropFilter:"blur(9px) saturate(.88)",duration:.13,ease:"power1.in"},second-.13);
  tl.to(".continuity-veil",{opacity:0,backdropFilter:"blur(0px) saturate(.94)",duration:.18,ease:"power1.out"},second);
  tl.to("#camera-feed",{scale:1.005,duration:.13,ease:"power1.in"},second-.13);
  tl.to("#camera-feed",{scale:1,duration:.18,ease:"power1.out"},second);
}
[15,30,45].forEach(softenBoundary);
window.__timelines[root.id]=tl;
