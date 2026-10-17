const variant = new URLSearchParams(location.search).get("variant") === "portrait-en" ? "portrait-en" : "portrait-zh";
const zh = variant === "portrait-zh";
document.documentElement.lang = zh ? "zh-CN" : "en";

const copy = zh ? {
  room:"新机前瞻实验室",sub:"发布会前概念预演 · 非官方销售",disclosure:"合成人物与概念设备 · 可读界面由代码生成",pre:"距苹果 9 月 9 日发布会还有 3 天 · 参数与名称等待官方确认",pinned:"主播正在回答",like:"点赞",share:"分享",remind:"提醒",
  drawerKicker:"预发布信息卡 · 不提供购买",drawerTitle:"iPhone 18 Pro Max / 折叠屏概念",drawerCopy:"保存对比清单，发布会后按官网信息更新",drawerCta:"设置提醒",composer:"说点什么…",
  facts:[
    ["官方已确认","9 月 9 日特别活动","苹果只确认了活动时间，尚未公布 iPhone 18 产品信息。"],
    ["观众问题回应","现在能下单吗？","不能。本场是概念预演，不展示价格、库存或发货承诺。"],
    ["传闻分层","折叠屏名称未定","“Fold / Ultra”等名称均未获苹果确认，直播只讨论形态可能性。"],
    ["购买建议","等官网规格再比较","发布后重点核对屏幕、续航、相机、重量与保修，再决定。"]
  ],
  comments:[
    [1.6,"镜头控","两个版本有什么不同？",true],[4.3,"果粉阿宁","这真的是苹果官方直播吗？",true],[8.2,"通勤党","折叠屏合起来会不会太厚？",true],[12.6,"影像派","Pro Max 重点看什么？",true],[17.4,"小白买机","今天可以直接下单吗？",true],[22.0,"续航研究员","电池参数确定了吗？",true],[27.1,"桌面玩家","折叠屏适合多任务吗？",true],[32.3,"摄影师Leo","相机升级是真的吗？",true],[37.0,"care达人","维修和折痕怎么判断？",true],[42.6,"理性消费","发布后怎么选？",true],[48.0,"发布会蹲守","什么时候能知道准确价格？",true],[53.4,"VA_support","先设置发布会提醒，规格只认官网。",false]
  ],
  subtitles:[
    [0,5,"先说清楚：这是发布会前的概念预演，不是苹果官方销售直播。"],[5,10,"你问两个版本差在哪？Pro Max 看旗舰直板体验，折叠形态看大屏与便携的取舍。"],[10,15,"折叠屏厚度、重量、铰链寿命，现在都没有官方数据，别把传闻当参数。"],[15,20,"问能不能下单：不能。今天没有价格、库存、预售和发货承诺。"],[20,25,"Pro Max 发布后先核对屏幕、续航、相机和重量，别只看一个芯片名字。"],[25,30,"折叠屏如果成真，核心价值是展开后的多任务，但要同时看折痕、比例和应用适配。"],[30,35,"相机升级传闻很多，发布会前我们不下结论；样张、焦段和视频规格都等官网。"],[35,40,"关心耐用性的朋友，重点看铰链测试、屏幕保护层、AppleCare 条款和维修价格。"],[40,45,"怎么选？重视成熟稳定选直板；重视大屏效率，再评估折叠形态的重量与价格。"],[45,50,"准确价格要等苹果正式公布；任何提前报价都不应该当作下单依据。"],[50,55,"我把观众问得最多的五项整理成清单：尺寸、重量、续航、相机、保修。"],[55,60,"点提醒，发布会后我们用官方页面逐项复盘；现在不要冲动下单。"]
  ],
  gift:["viewer_072 送出未来之光","感谢支持，礼物特效由代码生成，不遮挡产品信息"]
} : {
  room:"Next iPhone Lab",sub:"Pre-event concept preview · not an official sale",disclosure:"Synthetic host and concept devices · readable UI rendered in code",pre:"3 days until Apple’s Sep 9 event · names and specs await official confirmation",pinned:"Host is answering",like:"Like",share:"Share",remind:"Remind",
  drawerKicker:"PRE-RELEASE INFO · NO CHECKOUT",drawerTitle:"iPhone 18 Pro Max / foldable concepts",drawerCopy:"Save the checklist; update it from Apple after the event",drawerCta:"Set reminder",composer:"Add a comment…",
  facts:[
    ["CONFIRMED","September 9 special event","Apple has confirmed the event time, not any iPhone 18 product details."],
    ["VIEWER ANSWER","Can I order today?","No. This is a concept preview with no price, inventory, preorder, or shipping claim."],
    ["RUMOR BOUNDARY","Foldable name unconfirmed","Names such as Fold or Ultra are not confirmed by Apple; only the possible form factor is discussed."],
    ["BUYING CHECKLIST","Compare after official specs","Check display, battery, camera, weight, and warranty before making a decision."]
  ],
  comments:[
    [1.6,"framebyframe","What is the real difference?",true],[4.3,"verifiedplease","Is this an official Apple live?",true],[8.2,"commute_kit","Will the foldable be too thick?",true],[12.6,"camera_trace","What should I watch on Pro Max?",true],[17.4,"firstiphone","Can I order either one today?",true],[22.0,"batterybrief","Are battery figures confirmed?",true],[27.1,"multitasker","Would a foldable help real work?",true],[32.3,"lensnotes","Are the camera upgrades real?",true],[37.0,"repaircheck","What about crease and repairs?",true],[42.6,"buy_smart","How should I choose after launch?",true],[48.0,"eventwatch","When will pricing be accurate?",true],[53.4,"VA_support","Save the event reminder; trust Apple’s product page for specs.",false]
  ],
  subtitles:[
    [0,5,"First: this is a pre-event concept preview, not an official Apple sales stream."],[5,10,"You asked about the difference: Pro Max is the mature flagship slab; a foldable would trade simplicity for a larger canvas."],[10,15,"Thickness, weight, hinge life, and display crease are not official. Do not treat rumors as specifications."],[15,20,"Can you order today? No. We are showing no price, stock, preorder, or shipping promise."],[20,25,"For Pro Max, compare display, battery, camera, and weight after Apple publishes the product page."],[25,30,"A foldable could improve multitasking, but only if the aspect ratio, crease, weight, and app support hold up."],[30,35,"Camera rumors are abundant; wait for official focal lengths, sample images, and video formats."],[35,40,"For durability, check hinge testing, display protection, AppleCare terms, and repair pricing."],[40,45,"Choose the slab for proven simplicity; consider a foldable only if the larger canvas justifies weight and cost."],[45,50,"Accurate pricing starts with Apple’s announcement. Early quotes should never drive a purchase."],[50,55,"Here is the five-point checklist from chat: size, weight, battery, camera, and warranty."],[55,60,"Set the reminder. After the event, we will replace rumors with official facts line by line."]
  ],
  gift:["viewer_072 sent Future Light","Thanks — this gift effect is code-rendered and never covers product details"]
};

const $ = id => document.getElementById(id);
$("room-name").textContent=copy.room;$("room-subtitle").textContent=copy.sub;$("disclosure-text").textContent=copy.disclosure;$("prelaunch-text").textContent=copy.pre;$("pinned-label").textContent=copy.pinned;$("like-label").textContent=copy.like;$("share-label").textContent=copy.share;$("remind-label").textContent=copy.remind;$("drawer-kicker").textContent=copy.drawerKicker;$("drawer-title").textContent=copy.drawerTitle;$("drawer-copy").textContent=copy.drawerCopy;$("drawer-cta").textContent=copy.drawerCta;$("composer-placeholder").textContent=copy.composer;

const tl=gsap.timeline({paused:true}); window.__timelines["iphone18-concept-live-60s-v1"]=tl;
copy.subtitles.forEach(([start,end,text])=>{tl.call(()=>{$("subtitle").textContent=text},[],start).to("#subtitle",{opacity:1,duration:.18},start).to("#subtitle",{opacity:0,duration:.18},end-.2)});
copy.comments.forEach(([time,user,text,question],index)=>{tl.call(()=>{const el=document.createElement("div");el.className=`comment${question?" question":""}`;el.innerHTML=`<b>${user}</b>${text}`;$("comments").append(el);while($("comments").children.length>4)$("comments").firstElementChild.remove();gsap.to(el,{opacity:1,y:0,duration:.28,ease:"power2.out"});if(question){$("pinned-question").querySelector("strong").textContent=text;gsap.fromTo("#pinned-question",{opacity:0,y:-18},{opacity:1,y:0,duration:.28});gsap.to("#pinned-question",{opacity:0,y:-12,duration:.2,delay:3.7});}},[],time); if(index===11)tl.to("#viewer-count",{textContent:"14.1K",duration:.5,snap:{textContent:1}},time)});
[0,15,30,45].forEach((start,index)=>{const [kicker,title,body]=copy.facts[index];tl.call(()=>{const card=$("fact-card");card.querySelector("small").textContent=kicker;card.querySelector("h2").textContent=title;card.querySelector("p").textContent=body;$("fact-state").textContent=index===0?"OFFICIAL EVENT / PRODUCT UNCONFIRMED":index===2?"RUMOR / UNCONFIRMED":"REVIEW CHECKLIST";},[],start+.4).to("#fact-card",{opacity:1,x:0,duration:.35},start+.4).to("#fact-card",{opacity:0,x:-18,duration:.25},start+5.8)});
tl.call(()=>{$("gift-stage").querySelector("small").textContent=copy.gift[0];$("gift-stage").querySelector("strong").textContent=copy.gift[1]},[],33).fromTo("#gift-stage",{opacity:0,scale:.72},{opacity:1,scale:1,duration:.45,ease:"back.out(1.5)"},33).to(".gift-orbit",{rotation:170,duration:2.5,ease:"power1.out"},33).to("#gift-stage",{opacity:0,scale:.92,duration:.35},36.1);
tl.to("#progress-bar",{width:"100%",duration:60,ease:"none"},0);
tl.play(0);
