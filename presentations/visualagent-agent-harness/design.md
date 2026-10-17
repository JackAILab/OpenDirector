---
name: VisualAgent Harness Editorial System
canvas: "1920x1080"
background: "#F2ECDD"
foreground: "#1E251F"
accent: "#2E6B4D"
signal: "#D66B3D"
muted: "#7A8178"
line: "#C9C2B2"
headline_font: "Live Chinese UI"
body_font: "Live Chinese UI"
code_font: "ui-monospace"
corner_radius: "18px"
---

# 视觉方向

这是一套“工程蓝图被印在高质量纸张上”的中文技术 deck：温暖米白底、墨绿结构线、少量橙色风险标记。画面应像 editorial system map，而不是深色 SaaS dashboard，也不使用紫蓝渐变、玻璃卡矩阵或大面积霓虹。

每页保留左上章节索引与右下页码。大标题 72–96px，正文 40–48px；架构节点使用 40px 以上文字。用线、轨道、状态机和层叠纸片制造深度，避免重复的同尺寸卡片网格。

# Motion

- 页面进入：`waterfall-entry`，标题和主视觉在 0.45s 内完成。
- Pipeline fragment：节点逐级点亮，箭头同步推进。
- 系统循环：使用有限次数的 `sine-wave-loop`，不使用无限动画。
- 重点状态：使用 `nudge-curve` 或短促 `press-release`，不使用弹性卡通运动。
