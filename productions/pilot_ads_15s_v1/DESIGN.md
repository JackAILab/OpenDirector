# VisualAgent Pilot Ads 15s v1

三支 1080×1920、15 秒竖屏广告样片共用同一套确定性 HyperFrames 编排，通过 variables 切换物理底片、内容与色彩。首批 case 为 `gpu`、`phone` 和 `mobility`。

## Layer ownership

- 模型：虚构人物、商品、物理布景、灯光。
- Code / HyperFrames：所有可读标题、事实卡、评论、按钮、声明与进度。
- Timeline：相机推近、信息出现顺序与 CTA 收束的唯一时钟。

## Motion arc

- 0–3.5s：身份区、AI 声明、主标题建立。
- 3.5–7.2s：观众问题进入，形成直播语境。
- 7.2–10.75s：关键事实卡出现。
- 10.75–15s：行动抽屉进入并保持到结尾。

所有版本保持 `training_eligible=false`，直到 technical、独立 semantic/visual 和明确 human approval 全部通过。
