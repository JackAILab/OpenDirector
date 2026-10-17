#!/usr/bin/env python3
"""Index one live-production case for the interactive asset studio.

The studio is a read-only projection of canonical artifacts. It never becomes
the source of truth and never marks an artifact approved or training eligible.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "tools/asset_studio"
PUBLIC = SITE / "public/case-assets"
DATA = SITE / "app/data/studio-data.json"
CYBERCAB_DATA = SITE / "app/data/cybercab-studio-data.json"
CASE_ID = "jensen_rubin_live_60s_v1"
TIMELINE = ROOT / "data/tasks/jensen_rubin_live_60s_v1.timeline.json"
CYBERCAB_CASE_ID = "cybercab_live_60s_v2"
CYBERCAB_TIMELINE = ROOT / "data/tasks/cybercab_live_60s_v2.timeline.json"

SOURCES = [
    ROOT / "outputs/artifacts/jensen_rtx5090_live_v2_20260820/reference_elements",
    ROOT / "outputs/artifacts/jensen_rtx5090_live_v2_20260820/camera_references",
    ROOT / "outputs/artifacts/jensen_rtx5090_live_v2_20260820/review",
    ROOT / "outputs/artifacts/jensen_rtx5090_live_v1_20260819/audio",
    ROOT / "outputs/artifacts/jensen_rtx5090_live_v1_20260819/overlays",
    ROOT / "productions/jensen_rtx5090_live_v1/renders",
    ROOT / "productions/jensen_rtx5090_live_v1/snapshots/review-v1",
    ROOT / "productions/jensen_rubin_live_30s_v2/snapshots",
    ROOT / "productions/jensen_rubin_live_30s_v2/renders",
    ROOT / "outputs/artifacts/jensen_rubin_live_30s_v2/camera_segments",
    ROOT / "outputs/artifacts/jensen_rubin_live_30s_v2/review",
    ROOT / "outputs/artifacts/jensen_rubin_live_30s_v2/layers",
    ROOT / "outputs/artifacts/jensen_rubin_live_30s_v2/audio",
    ROOT / "outputs/artifacts/jensen_rubin_live_30s_v2/final",
    ROOT / "outputs/artifacts/jensen_rubin_live_30s_v2/camera",
    ROOT / "outputs/artifacts/jensen_rubin_live_60s_v1/camera_references",
    ROOT / "outputs/artifacts/jensen_rubin_live_60s_v1/camera_segments",
    ROOT / "outputs/artifacts/jensen_rubin_live_60s_v1/camera",
    ROOT / "outputs/artifacts/jensen_rubin_live_60s_v1/review",
    ROOT / "outputs/artifacts/jensen_rubin_live_60s_v1/final",
    ROOT / "productions/jensen_rubin_live_60s_v1/snapshots",
    ROOT / "productions/jensen_rubin_live_60s_v1/renders",
    ROOT / "outputs/artifacts/jensen_rubin_live_60s_v2/live_fx",
    ROOT / "outputs/artifacts/jensen_rubin_live_60s_v2/audio",
    ROOT / "productions/jensen_rubin_live_60s_v2_audio_fx/snapshots",
    ROOT / "productions/jensen_rubin_live_60s_v2_audio_fx/renders",
    ROOT / "productions/jensen_rubin_live_60s_v3_tiktok_text/snapshots",
    ROOT / "productions/jensen_rubin_live_60s_v3_tiktok_text/renders",
    ROOT / "productions/jensen_rubin_live_60s_v4_multiformat/portrait-zh/snapshots",
    ROOT / "productions/jensen_rubin_live_60s_v4_multiformat/portrait-en/snapshots",
    ROOT / "productions/jensen_rubin_live_60s_v4_multiformat/landscape-zh/snapshots",
    ROOT / "productions/jensen_rubin_live_60s_v4_multiformat/landscape-en/snapshots",
    ROOT / "outputs/artifacts/cybercab_live_60s_v1",
    ROOT / "productions/cybercab_live_60s_v1/snapshots",
    ROOT / "outputs/artifacts/cybercab_live_60s_v2",
    ROOT / "productions/cybercab_live_60s_v2",
]
EXPLICIT = [
    TIMELINE,
    ROOT / "productions/pilot_ads_15s_v1/renders/visualagent-gpu-15s-v2.mp4",
    ROOT / "productions/pilot_ads_15s_v1/renders/visualagent-phone-15s-v2.mp4",
    ROOT / "productions/pilot_ads_15s_v1/renders/visualagent-mobility-15s-v2.mp4",
    ROOT / "productions/pilot_ads_15s_v1/assets/plates/gpu-host-v1.png",
    ROOT / "productions/pilot_ads_15s_v1/assets/plates/phone-concept-v1.png",
    ROOT / "productions/pilot_ads_15s_v1/assets/plates/mobility-concept-v1.png",
    ROOT / "productions/pilot_ads_15s_v1/DESIGN.md",
    ROOT / "productions/pilot_ads_15s_v1/STORYBOARD.md",
    ROOT / "productions/jensen_rubin_live_60s_v1/renders/jensen_rubin_live_60s_v1.final.mp4",
    ROOT / "outputs/artifacts/jensen_rubin_live_60s_v1/review/final-60s-contact-sheet.jpg",
    ROOT / "outputs/artifacts/jensen_rubin_live_60s_v1/review/final_hyperframes_qa.json",
    ROOT / "data/tasks/jensen_rubin_live_30s_v2.timeline.json",
    ROOT / "configs/tasks/jensen_rubin_live_30s_v2.segments.json",
    ROOT / "configs/tasks/jensen_rubin_live_60s_v1.segments.json",
    ROOT / "configs/tasks/jensen_rubin_live_60s_v1.references.json",
    ROOT / "configs/live_fx/tiktok_live_v1.json",
    ROOT / "configs/live_ui/tiktok_live_text_v2.json",
    ROOT / "configs/schemas/live_fx_style.schema.json",
    ROOT / "docs/research/tiktok_live_text_ui_20260826.md",
    ROOT / "productions/jensen_rubin_live_60s_v3_tiktok_text/DESIGN.md",
    ROOT / "productions/jensen_rubin_live_60s_v3_tiktok_text/STORYBOARD.md",
    ROOT / "productions/jensen_rubin_live_60s_v4_multiformat/DESIGN.md",
    ROOT / "configs/live_ui/mobile_live_text_zh_portrait_v4.json",
    ROOT / "configs/live_ui/mobile_live_text_en_portrait_v4.json",
    ROOT / "configs/live_ui/desktop_live_text_zh_landscape_v4.json",
    ROOT / "configs/live_ui/desktop_live_text_en_landscape_v4.json",
    ROOT / "configs/tasks/jensen_rubin_live_60s_v4.continuity-repair.plan.json",
    ROOT / "configs/tasks/synthetic_gpu_presenter_live_60s_v5.native-variants.plan.json",
    ROOT / "configs/tasks/cybercab_live_60s_v1.plan.json",
    ROOT / "configs/tasks/cybercab_live_60s_v1.generation.json",
    ROOT / "configs/tasks/cybercab_live_60s_v1.review.json",
    ROOT / "data/tasks/cybercab_live_60s_v1.timeline.json",
    ROOT / "productions/cybercab_live_60s_v1/DESIGN.md",
    ROOT / "productions/cybercab_live_60s_v1/index.html",
    ROOT / "productions/cybercab_live_60s_v1/live-room.css",
    ROOT / "productions/cybercab_live_60s_v1/live-room.js",
    ROOT / "productions/cybercab_live_60s_v1/hyperframes.json",
    ROOT / "configs/tasks/cybercab_live_60s_v2.omni-native-av.plan.json",
    ROOT / "configs/tasks/cybercab_live_60s_v2.seam-repair.plan.json",
    ROOT / "data/tasks/cybercab_live_60s_v2.timeline.json",
    ROOT / "configs/audio/jensen_rubin_live_60s_v4.presenter-voice-contract.json",
    ROOT / "docs/api_mcp.md",
    ROOT / "outputs/artifacts/jensen_rubin_live_60s_v1/review/continuity-audit-v1/audit.json",
    ROOT / "outputs/artifacts/jensen_rubin_live_60s_v1/review/continuity-audit-v1/boundary-075-previous-tail.png",
    ROOT / "outputs/artifacts/jensen_rubin_live_60s_v1/review/continuity-audit-v1/boundary-225-previous-tail.png",
    ROOT / "outputs/artifacts/jensen_rubin_live_60s_v1/review/continuity-audit-v1/contact-sheet.png",
    ROOT / "outputs/artifacts/jensen_rubin_live_60s_v1/review/continuity-audit-v1/temporal-samples.png",
    ROOT / "outputs/artifacts/jensen_rubin_live_60s_v1/review/continuity-audit-v2/audit.json",
    ROOT / "outputs/artifacts/jensen_rubin_live_60s_v1/review/continuity-audit-v2/semantic-review.json",
    ROOT / "outputs/artifacts/jensen_rubin_live_60s_v1/review/continuity-audit-v2/scan-30-34-contact-sheet.jpg",
    ROOT / "outputs/artifacts/jensen_rubin_live_60s_v1/review/continuity-audit-v2/seam-30-contact-sheet.jpg",
    ROOT / "data/tasks/jensen_rubin_live_60s_v2_audio_fx.timeline.json",
    ROOT / "configs/tasks/jensen_rubin_live_30s_v2.kling-v3-preview.json",
    ROOT / "configs/tasks/jensen_rubin_live_30s_v2.kling-v3-single-frame-preview.json",
    ROOT / "configs/tasks/jensen_rubin_live_30s_v2.kling-v3-subject-reference-preview.json",
    ROOT / "configs/tasks/jensen_rubin_live_30s_v2.omni-retry-02.json",
    ROOT / "configs/tasks/jensen_rubin_live_30s_v2.omni-vertical-lock-03.json",
    ROOT / "configs/tasks/jensen_rtx5090_reference_v2.json",
    ROOT / "configs/tasks/jensen_rtx5090_live_v1.json",
    ROOT / "productions/jensen_rubin_live_30s_v2/STORYBOARD.md",
    ROOT / "productions/jensen_rubin_live_60s_v1/STORYBOARD.md",
    ROOT / "outputs/trajectories/b4dbacd71c434d3fa74e5ef5c8612140.json",
    ROOT / "outputs/trajectories/2bf80129933e4589b684d99088178bd4.json",
    ROOT / "outputs/trajectories/131b95015fe243748f7a2ef86bbd81a9.json",
    ROOT / "outputs/trajectories/4b5ec211edb44c34a8bf5f940011e237.json",
    ROOT / "outputs/trajectories/c7ab4fb3be0248e084edae19c69078eb.json",
    ROOT / "outputs/trajectories/ce0fd18cd2934b14abf22201b8ccef28.json",
    ROOT / "outputs/trajectories/7084da0e719546efa3bf1d2731818967.json",
    ROOT / "outputs/trajectories/6faf475bde704212b8ea0988244dfae5.json",
    ROOT / "outputs/trajectories/67607d464a3d456aa766a11c39bfe41f.json",
    ROOT / "outputs/trajectories/9b1e7aec03ac46268c2b14b7a158a739.json",
    ROOT / "outputs/trajectories/62f754d32457429f889b7e8723f62b48.json",
]
VIEWABLE = {".png", ".jpg", ".jpeg", ".webp", ".mp4", ".webm", ".mov", ".wav", ".mp3", ".json", ".md"}
TRANSIENT_PARTS = {"captured-frames", "chunk-encode"}


def is_studio_asset(path: Path) -> bool:
    """Keep render internals out of the human-review asset projection."""
    relative_parts = path.relative_to(ROOT).parts
    return not any(part in TRANSIENT_PARTS or part.startswith("work-") for part in relative_parts)


def iter_studio_assets(source: Path):
    """Walk canonical asset trees without descending into renderer scratch directories."""
    for directory, dirnames, filenames in os.walk(source):
        dirnames[:] = [
            name for name in dirnames
            if name not in TRANSIENT_PARTS and not name.startswith("work-")
        ]
        parent = Path(directory)
        for filename in filenames:
            path = parent / filename
            if path.suffix.lower() in VIEWABLE and is_studio_asset(path):
                yield path


def prune_transient_staging() -> int:
    """Remove only reproducible render-work files from the generated public staging area."""
    if not PUBLIC.is_dir():
        return 0
    removed = 0
    for path in PUBLIC.iterdir():
        if path.is_file() and (
            "__renders__work-" in path.name
            or "__captured-frames__" in path.name
            or "__chunk-encode__" in path.name
        ):
            path.unlink()
            removed += 1
    return removed


def prune_stale_staging(expected_names: set[str]) -> int:
    """Make the generated staging directory an exact projection of the current manifest."""
    if not PUBLIC.is_dir():
        return 0
    removed = 0
    for path in PUBLIC.iterdir():
        if path.is_file() and path.name not in expected_names:
            path.unlink()
            removed += 1
    return removed


def staged_file_is_current(path: Path, target: Path) -> bool:
    if not target.is_file():
        return False
    source_stat = path.stat()
    target_stat = target.stat()
    if source_stat.st_size != target_stat.st_size:
        return False
    try:
        return os.path.samefile(path, target) or source_stat.st_mtime_ns == target_stat.st_mtime_ns
    except OSError:
        return False


def previous_assets() -> dict[str, dict]:
    if not DATA.is_file():
        return {}
    try:
        payload = json.loads(DATA.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {asset["path"]: asset for asset in payload.get("assets", []) if asset.get("path")}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def classify(path: Path) -> tuple[str, str, str]:
    text = str(path).lower()
    if "pilot_ads_15s_v1/assets/plates" in text:
        return "keyframe", "keyframes", "GPT Image 2"
    if "pilot_ads_15s_v1/snapshots" in text:
        return "composition snapshot", "layers", "HyperFrames"
    if path.name == "api_mcp.md":
        return "provider capability research", "specs", "Research"
    if "native-variants.plan" in text or "configs/tasks/cybercab_live_60s" in text:
        return "generation plan", "specs", "Task / Agent"
    if "continuity-audit-v1" in text or "continuity-audit-v2" in text:
        return "continuity audit", "provenance", "Code / FFmpeg"
    if "presenter-voice-contract" in text:
        return "presenter voice contract", "specs", "Task / Audio"
    if path.name.endswith((".provenance.json", ".receipt.json", ".manifest.json")):
        return "provenance", "provenance", "Harness"
    if "live_ui" in text:
        return "live text style", "specs", "Code / HyperFrames"
    if "tiktok_live_text_ui" in text:
        return "UI research", "specs", "Research"
    if "live_fx" in text and path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
        return "live gift asset", "references", "GPT Image 2"
    if "reference_elements" in text:
        return "reference element", "references", "GPT Image 2"
    if "jensen_rubin_live_30s_v2/snapshots" in text:
        return "composition snapshot", "layers", "HyperFrames"
    if "jensen_rubin_live_60s_v4_multiformat" in text and "snapshots" in text:
        return "composition snapshot", "layers", "HyperFrames"
    if "camera_references" in text or "reference_states" in text or "review" in text and path.suffix.lower() in {".png", ".jpg"}:
        return "keyframe", "keyframes", "GPT Image 2"
    if path.suffix.lower() in {".webm", ".mov"} or "overlay" in text:
        return "overlay", "layers", "Code / HyperFrames"
    if path.suffix.lower() in {".wav", ".mp3", ".m4a", ".aac"}:
        return "audio", "audio", "Native voice / Code mix"
    if path.suffix.lower() == ".mp4":
        return "video", "video", "Composite / Review"
    if "trajectories" in text:
        return "trajectory", "provenance", "Harness"
    if "timeline" in path.name:
        return "timeline", "specs", "Task"
    if path.suffix.lower() == ".md":
        return "storyboard", "specs", "Creative"
    return "metadata", "provenance", "Harness"


def status(path: Path) -> str:
    text = path.name.lower()
    if "trajectories" in str(path).lower() and path.suffix.lower() == ".json":
        try:
            run_status = json.loads(path.read_text(encoding="utf-8")).get("status")
            if run_status in {"failed", "completed", "max_steps"}:
                return "failed" if run_status != "completed" else "generated"
        except (OSError, json.JSONDecodeError):
            pass
    if "first-repaired" in text or "tail-repaired" in text or "static_camera" in text:
        return "rejected"
    if text in {"state-150.png", "state-150-v2.png", "state-150-v3.png", "state-150-v4.png"}:
        return "rejected"
    if text in {"first-v2.png", "state-075-dynamic-v2.png", "state-150-dynamic-v2.png", "state-225-dynamic-v2.png", "state-300-dynamic-v2.png"}:
        return "candidate"
    if path.suffix.lower() in {".mp4", ".webm", ".mov"}:
        return "review"
    return "generated"


def public_name(path: Path) -> str:
    rel = path.relative_to(ROOT)
    flat = "__".join(rel.parts)
    return flat.replace(" ", "-")


def stage_file(path: Path) -> str:
    target = PUBLIC / public_name(path)
    if staged_file_is_current(path, target):
        return f"/case-assets/{target.name}"
    if target.exists():
        target.unlink()
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(path, target)
    except OSError:
        shutil.copy2(path, target)
    return f"/case-assets/{target.name}"


def project_cybercab_live_preview() -> int:
    """Project the reviewed camera, audio and code UI into one same-origin page."""
    preview = PUBLIC.parent / "cybercab-live"
    sources = {
        Path("index.html"): ROOT / "productions/cybercab_live_60s_v2/index.html",
        Path("live-room.css"): ROOT / "productions/cybercab_live_60s_v2/live-room.css",
        Path("live-room.js"): ROOT / "productions/cybercab_live_60s_v2/live-room.js",
        Path("assets/camera/camera_feed_60s-omni-native-av-v2-departure-repaired.mp4"): ROOT / "outputs/artifacts/cybercab_live_60s_v2/camera/camera_feed_60s-omni-native-av-v2-departure-repaired.mp4",
        Path("assets/live_fx/rocket-premium-v1.png"): ROOT / "productions/cybercab_live_60s_v2/assets/live_fx/rocket-premium-v1.png",
        Path("assets/live_fx/sports-car-premium-v1.png"): ROOT / "productions/cybercab_live_60s_v2/assets/live_fx/sports-car-premium-v1.png",
    }
    expected = {preview / relative for relative in sources}
    if preview.is_dir():
        for staged in preview.rglob("*"):
            if staged.is_file() and staged not in expected:
                staged.unlink()
    projected = 0
    for relative, source in sources.items():
        if not source.is_file():
            continue
        target = preview / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if staged_file_is_current(source, target):
            projected += 1
            continue
        if target.exists():
            target.unlink()
        try:
            os.link(source, target)
        except OSError:
            shutil.copy2(source, target)
        projected += 1
    return projected


def main() -> int:
    pruned = prune_transient_staging()
    cached_assets = previous_assets()
    files: set[Path] = {path for path in EXPLICIT if path.is_file()}
    for source in SOURCES:
        if source.is_dir():
            files.update(iter_studio_assets(source))
    pruned_stale = prune_stale_staging({public_name(path) for path in files})
    assets = []
    for index, path in enumerate(sorted(files)):
        relative_path = str(path.relative_to(ROOT))
        kind, group, owner = classify(path)
        provenance = path.with_suffix(".provenance.json")
        if not provenance.is_file() and path.suffix.lower() == ".mp4":
            provenance = path.with_suffix(".receipt.json")
        model = None
        operation = None
        if provenance.is_file() and provenance != path:
            payload = json.loads(provenance.read_text(encoding="utf-8"))
            model = payload.get("model")
            operation = payload.get("operation")
        cached = cached_assets.get(relative_path)
        cached_sha = cached.get("sha256") if cached and cached.get("bytes") == path.stat().st_size else None
        target = PUBLIC / public_name(path)
        cache_matches_stage = bool(cached_sha and staged_file_is_current(path, target))
        url = stage_file(path)
        if "productions/pilot_ads_15s_v1/renders/" in relative_path and path.suffix.lower() == ".mp4":
            url = f"/api/media/{path.name}"
        assets.append({
            "id": f"asset-{index:03d}",
            "name": path.name,
            "path": relative_path,
            "url": url,
            "kind": kind, "group": group, "owner": owner,
            "status": status(path), "model": model, "operation": operation,
            "bytes": path.stat().st_size,
            "sha256": cached_sha if cache_matches_stage else sha256(path),
            "trainingEligible": False, "humanReview": "pending",
        })
    timeline = json.loads(TIMELINE.read_text(encoding="utf-8"))
    payload = {
        "schema": "visualagent.asset-studio.v1",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "caseId": CASE_ID, "assets": assets, "timeline": timeline,
        "counts": {group: sum(asset["group"] == group for asset in assets) for group in sorted({asset["group"] for asset in assets})},
    }
    DATA.parent.mkdir(parents=True, exist_ok=True)
    DATA.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    cybercab_assets = [
        asset for asset in assets
        if "cybercab_live_60s" in asset["path"] or "cybercab-live-60s" in asset["path"]
    ]
    cybercab_timeline = json.loads(CYBERCAB_TIMELINE.read_text(encoding="utf-8"))
    cybercab_payload = {
        "schema": "visualagent.asset-studio.v1",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "caseId": CYBERCAB_CASE_ID,
        "assets": cybercab_assets,
        "timeline": cybercab_timeline,
        "counts": {
            group: sum(asset["group"] == group for asset in cybercab_assets)
            for group in sorted({asset["group"] for asset in cybercab_assets})
        },
    }
    CYBERCAB_DATA.write_text(
        json.dumps(cybercab_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    cybercab_preview_files = project_cybercab_live_preview()
    print(json.dumps({
        "assets": len(assets),
        "pruned_transient": pruned,
        "pruned_stale": pruned_stale,
        "data": str(DATA),
        "cybercab_data": str(CYBERCAB_DATA),
        "cybercab_assets": len(cybercab_assets),
        "public": str(PUBLIC),
        "cybercab_preview_files": cybercab_preview_files,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
