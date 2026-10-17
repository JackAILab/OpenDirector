# AI 硬件直播间 v3 — TikTok-inspired Text Layout

本版本不是 TikTok 官方界面或像素级复刻。它只从公开移动端直播样本中提取信息层级、文字密度、消息队列、safe area 与 priority surface 避让规律，并继续使用 VisualAgent 自有视觉资产与中性文案。

## v3 文字编排原则

- 普通评论是透明瀑布流：头像、昵称、正文属于同一轻量信息流，不重复包裹完整玻璃卡。
- 同屏最多四条评论；新消息从底部进入，旧消息按固定 68px slot 上移。
- “正在回应”、商品卡、礼物通知才是 localized priority surface；可读 priority surface 同时最多一个。
- 商品或礼物出现时，普通评论主动降低视觉权重，不与重点信息争夺视线。
- 顶部身份条、右侧功能 rail 与底部 composer 都保持窄、圆、轻，不做 dashboard 式大面板。
- 所有可读中文、计数、商品说明、按钮与礼物通知由 Code / HyperFrames 生成；Kling 只负责人物、商品、物理布景和镜头运动。
- `training_eligible=false`，技术 QA、独立视觉 review 与人工确认前不得进入训练集。

## Style Prompt

A premium vertical hardware livestream that feels broadcast-designed rather than app-mocked: dense but disciplined, tactile graphite and smoked glass over a cinematic studio feed, warm human skin and product highlights, with one restrained acid-green signal color. The interface should feel like precision hardware packaging translated into motion—thin machined rules, deliberate asymmetric zones, compact data typography, editorial product hierarchy, and physically weighted transitions. It must remain legible at phone size while preserving clear sightlines to the host and GPU.

## Colors

- `#0B0D0C` — graphite black; deep panels and edge falloff, never a flat full-frame fill.
- `#F2F3ED` — warm white; primary copy and icons.
- `#AEB4AA` — mineral gray; secondary metadata and quiet controls.
- `#B7F52A` — acid signal; live state, verification, selected product, and causal response cues only.
- `#FF5A67` — restrained live red; LIVE badge and like/gift feedback only.

All glass surfaces use graphite-tinted transparency, a 1px warm-white highlight at low opacity, localized blur, and a soft black shadow. No rainbow gradients. No cyan/purple neon.

## Typography

- Display / product voice: `Archivo Black`, 900 weight, tight tracking (`-0.035em`). It speaks with engineered mass and is reserved for `RTX 5090`, product moments, and decisive numeric emphasis.
- Interface / Chinese voice: `IBM Plex Sans SC`, 300/500/700 weights with generous dark-canvas leading. It handles names, comments, disclosure, and supporting copy.
- Data voice: `IBM Plex Mono`, 500/600 weights with tabular numerals for viewers, likes, timecode, and technical labels.

If `IBM Plex Sans SC` is unavailable, use the bundled Chinese font only for Chinese glyphs while preserving the size, weight, spacing, and hierarchy above. Do not substitute a generic web UI system font for the complete composition.

## Layout System

- Canvas: 1080×1920, 9:16, 30 fps, 60 seconds.
- Safe edge: 42px minimum; key controls stay 58px from the physical edge.
- Top 260px: host identity, true disclosure, live/viewer state. Keep this narrow and optically light.
- Center: protected camera feed. No opaque UI over face, hands, or the GPU silhouette.
- Right rail: four vertically spaced circular actions, each 72–82px with distinct icon geometry and compact counters.
- Lower-left: comment stack, maximum three full comments plus one emerging comment. Width 640px; depth is created through scale, opacity, blur, and vertical cadence—not identical rectangles.
- Lower-right: product card from 8.8–14.2s, 610×270px maximum. It must show product identity and disclosure, but no invented price, inventory, CTA, endorsement, or performance claim.
- Bottom 120px: quiet input/navigation strip with strong side breathing room.

## Material & Asset Treatment

- Avatars are authored vector portraits/marks with varied color fields, rings, and crop shapes; never plain initials in identical circles.
- Icons are custom inline SVG strokes with round joins and optical correction. Emoji and Unicode glyphs are forbidden for primary controls.
- The gift rocket is a multi-part vector asset: metal body, viewport, fins, engine glow, exhaust ribbons, particles, and a labeled gift capsule. It must read as a designed broadcast asset, not a triangle.
- Hearts use authored SVG paths with scale, depth, blur, rotation, and stagger variation.
- Product imagery may only show the actual camera-feed GPU or an abstract hardware silhouette; do not fabricate readable specs.
- Add subtle grain, localized edge glows, hairline calibration marks, and one slow scanning highlight to keep the frame alive without becoming a HUD parody.

## Motion Vocabulary

- UI enters with confident `expo.out` or `power4.out`; glass has weight and should take 0.45–0.75s to settle.
- Counters use vertical odometer motion with tabular figures and a short acid-green confirmation flash.
- Comments arrive from distinct vectors and settle into a depth stack; the power-supply question receives a restrained green response rail at 3.4s, making the later host response causally legible.
- Product card uses a masked horizontal reveal, a slower metal highlight sweep, and asymmetric child entrances.
- Hearts rise in curved, varied paths and dissolve; never use a uniform fountain.
- Rocket gift crosses the frame on an arcing diagonal, with anticipation, fast travel, overshoot, and a short exhaust decay. No elastic/cartoon bounce.
- Ambient motion is limited to one slow scan line, slight status pulse, and restrained icon feedback.
- All timelines are deterministic, finite, paused, and seek-safe.

## What NOT to Do

- Do not use Pillow-style rounded rectangles as the whole design language.
- Do not use primitive triangle/ellipse rockets, emoji controls, generic icon fonts, or placeholder avatars.
- Do not stack four identical black comment pills with identical entrance motion.
- Do not cover the host’s face, hands, or GPU with opaque UI.
- Do not use empty black areas, web-dashboard card grids, centered landing-page layouts, gradient text, or cyan/purple AI aesthetics.
- Do not invent a price, stock count, sale countdown, benchmark claim, sponsorship, endorsement, or purchase button.
- Do not call a static camera loop a generated livestream video.
- Do not remove or abbreviate `AI 合成演示 · 非真实直播或代言`; it remains visible throughout.
