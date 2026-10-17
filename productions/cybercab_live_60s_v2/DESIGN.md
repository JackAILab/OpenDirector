# Cybercab Live 60s v2 — Omni Native A/V Visual System

## Media Lineage

- The camera feed is a 60-second non-overwriting successor assembled from four 15-second Omni native-A/V plates, three 5-second Omni seam plates and one separately retained departure repair.
- The final 12.5 seconds use the departure repair: both doors close and the vehicle changes position against the showroom background.
- The `<video>` and `<audio>` elements reference the same assembled camera container. No external TTS replaces native speech.
- The 32.5-second boundary still fails automatic continuity review; the composition remains review-only and `training_eligible=false`.

## Style Prompt

A premium but candid automotive livestream: graphite camera surround, warm ivory information surfaces, muted gold accents sampled from the vehicle, acid-lime system signals and coral live/gift accents. The interface should feel like a credible mobile live room layered over an uninterrupted showroom camera, not an official Tesla advertisement or a cinematic trailer.

## Colors

- `#111511` — graphite stage and control background
- `#F4F1E8` — warm ivory readable surfaces
- `#D7AD62` — vehicle-gold commerce accent
- `#B7F12A` — system/AI disclosure signal
- `#FF4F68` — live and gift priority accent

## Typography

- Chinese UI/body: `PingFang SC`, `Microsoft YaHei`, sans-serif
- Numeric/data labels: `IBM Plex Mono`, `DejaVu Sans Mono`, monospace
- English fallback: `Archivo`, `Arial Narrow`, sans-serif

## Motion

- Comment queue: waterfall entry plus deterministic upward nudge.
- Priority cards: short spring-free slide and fade; never cover the face or vehicle front quarter.
- Gifts: anticipate → burst → hero → settle → dissipate, with finite GSAP timelines.
- Camera joins: restrained 310 ms focus pull only; never claim it fixes failed physical continuity.

## What NOT to Do

- No official endorsement, price, inventory, delivery promise or scarcity claim.
- No readable text generated inside the neural camera feed.
- No random motion, infinite loops, theatrical wipes or fake road footage.
- No public-figure likeness or voice imitation.
- No promotion to training data before independent and human review.
