---
workflow: slideshow
flow: automation
storyboard: no
message: "VisualAgent Harness 把不可控的模型调用，变成有边界、可审计、可复用的数据生产系统。"
destination: internal_product_explainer
aspect: 16:9
language: zh-CN
audience: "VisualAgent 研发、算法、数据与产品团队"
length: "15 main slides + 1 interactive branch"
angle: "architecture-to-production-to-flywheel"
---

## Intent

制作一套可运行的 HyperFrames 中文 slideshow，完整讲解当前 VisualAgent Agent Harness。主线从为什么需要 harness 开始，解释 `Task → Agent → Runner → Tool/Model → Observation → Trajectory → Evaluator`，再用 30/60 秒直播视频生产作为实例，最后落到 QA、付费预算、训练锁与 data flywheel。

## Assets

- 以仓库当前 `harness/`、`configs/`、`data/`、`docs/architecture.md` 和 `docs/data_design.md` 为事实来源。
- 不引入外部品牌素材；使用代码绘制的架构图、轨道、状态图和指标环。
- 使用项目已有中文字体资产，确保 CJK 显示稳定。

## Customizations

- 米白色 editorial canvas，墨绿色为系统主色，橙色只用于付费边界与风险提示。
- 每页只讲一个结论，用大标题和一个主视觉；细节进入 presenter notes。
- 在核心 pipeline 页加入 fragment reveals。
- 提供一个“仓库边界” hotspot branch，展示代码目录到职责的映射。
- 最终交付为 presenter deck，不渲染成 MP4。

## Notes

- 所有边界必须与当前实现一致，不把未来能力写成已完成能力。
- 真实 provider secret、base URL、临时 URL、个人信息和 raw payload 不进入 slides。
- 强调 `training_eligible=false` 直到 technical、independent semantic/visual 与 human approval 全部通过。
