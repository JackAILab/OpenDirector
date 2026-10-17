---
format: 1080x1920
duration: 30s
message: "功耗是否够用必须按整机核算；Rubin 散热仅作为明确披露的概念演示。"
arc: 主播开场 → 观众追问功耗 → 主播回应 → Rubin 散热概念 → 礼物与购物车状态 → 整机验证收尾
audience: PC hardware enthusiasts on vertical livestream platforms
mode: collaborative
---

## Frame 1 — 开场持卡

- status: built
- duration: 7.5s
- poster: 0.8s
- scene: 主播直视镜头，单张双风扇显卡竖直持于胸前；固定身份区和右侧按钮已由代码层占位。
- assets: reference_elements/host.png, reference_elements/gpu.png, reference_elements/studio.png, camera_references/first-v2.png

Kling 只生成主播、显卡、真实布景与自然口播动作。左上身份、右侧四按钮、披露、弹幕均不进入神经底片。

## Frame 2 — 功耗提问

- status: outline
- duration: 7.5s
- poster: 7.5s
- scene: 主播注意到左下功耗弹幕并点头，显卡保持稳定；弹幕由代码层在 6.6 秒出现。
- effects: comment_power, hearts

动作必须紧凑，避免指向固定 UI 区域。

## Frame 3 — Rubin 散热概念

- status: outline
- duration: 7.5s
- poster: 15s
- scene: 主播指向开放式主机的物理散热路径；12–18 秒购物车抽屉、16.8 秒火箭由代码层生成。
- effects: commerce_drawer, rocket

Rubin 只能以“概念演示”表达，不能伪装成官方产品规格或黄仁勋真实发布。

## Frame 4 — 跑车礼物与墨镜 AR

- status: outline
- duration: 7.5s
- poster: 22.5s
- scene: 主播回正显卡并短暂停稳，为 22.8–26.2 秒眼部锚定墨镜提供稳定姿态；跑车礼物穿过画面。
- effects: sports_car, face_anchor_sunglasses

跑车和墨镜都是独立可重渲染效果层，不要求 Kling 画进人脸或场景。

## Frame 5 — 整机验证收尾

- status: outline
- duration: 0s
- poster: 29.4s
- scene: 主播轻转同一张双风扇显卡，回看镜头点头；固定 UI 保持到 30 秒。
- effects: commerce_drawer, final_hearts

结束帧继续保留完整披露，成片默认 human_review=pending、training_eligible=false。
