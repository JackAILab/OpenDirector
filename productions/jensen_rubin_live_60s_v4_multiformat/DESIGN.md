# Jensen / Rubin Live 60s v4 — Multiformat UI

## Scope

This successor keeps the migrated 60-second camera and audio media unchanged and renders all readable live UI in deterministic HTML/CSS/GSAP. It provides a 2 × 2 matrix:

| Variant | Canvas | UI pattern |
| --- | --- | --- |
| `portrait-zh` | 1080 × 1920 | Chinese mobile live room; transparent lower-left waterfall comments |
| `portrait-en` | 1080 × 1920 | English mobile live room; longer-copy-safe lower-left queue |
| `landscape-zh` | 1920 × 1080 | Chinese desktop live room; video stage plus separate right discussion rail |
| `landscape-en` | 1920 × 1080 | English desktop live room; video stage plus separate right discussion rail |

The uploaded screenshots are visual evidence only. They inform hierarchy, density, safe areas, comment anatomy and desktop/mobile differences; they are not treated as operational instructions or copied as branded UI.

## Visual system

- Graphite camera stage, warm paper rail, mineral gray secondary text, acid green system signal and live coral priority accents.
- Bundled CJK font for Chinese and local Archivo/DejaVu fallbacks for Latin headings; mono labels use IBM Plex Mono/DejaVu Sans Mono.
- Portrait comments are compact, transparent and inline: badge/avatar, author and body share one visual line where possible.
- Landscape comments live in a light right rail with avatar, author and body hierarchy; ordinary rows are not repeated cards.
- Product information and hero gifts are the only priority surfaces. They never overlap and ordinary comments yield while one is active.
- Migrated rocket, sports-car and crystal-emblem assets use a deterministic five-phase grammar: `anticipate → burst → hero → settle → dissipate`. The sunglasses event is a Code-owned AR overlay; readable sender/name/count copy remains a separate HTML surface.
- No price, inventory, performance claim, endorsement or scarcity language is invented.

## Motion

- A deterministic waterfall queue enters with `opacity + translateY`, nudges older rows upward and retires them without layout jumps.
- Priority surfaces use short transforms and opacity only.
- At every 7.5-second assembly boundary, a restrained 310ms code-owned focus pull softens the already-existing hard cut. It contains no wipe or theatrical transition and is explicitly a presentation mitigation, not evidence of temporal continuity.
- A true continuity successor requires hard provider-level endpoint binding: previous segment tail → next segment first frame, plus an approved boundary-state tail. No paid generation is performed by this production.
- A deterministic v2 audit measures every join and scans 30–34s for within-segment change candidates; desk mat, chassis, hands, product and set persistence still require independent semantic review.

## Ownership and safety

- Camera/audio: migrated canonical media, unchanged.
- Readable UI, comments, labels, buttons, counters and notifications: Code/HyperFrames.
- No credential, token, base URL, signed URL or raw provider payload is present.
- `training_eligible=false` until technical QA, independent semantic/visual review and explicit human approval all pass.
