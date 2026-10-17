# VisualAgent Live v4 preview hub

All four variants reuse the same migrated camera/audio assets. They are interactive HyperFrames compositions, not rendered MP4 files.

The persistent review entrypoint is a single page on port `3005`:

```text
http://127.0.0.1:3005/
```

The landing page links to portrait Chinese, portrait English, landscape Chinese, and landscape English. `viewer.html` supplies shared play, pause, reset, and seek controls while keeping all four compositions on the same origin and port.

The AWS service listens on loopback and should be reached through one SSH local forward when an in-app browser bridge is unavailable:

```text
-L 3005:127.0.0.1:3005
```

Run `npm run preview:hub` from this directory to start the hub. The player drives the migrated camera/audio media and the deterministic GSAP UI timeline together. It supports MP4 Range requests and does not render or regenerate media.
