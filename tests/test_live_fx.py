from __future__ import annotations

from pathlib import Path

import pytest

from harness.evaluators.live import parse_silencedetect
from harness.live.fx import LiveFXStyle, LiveFXValidationError


ROOT = Path(__file__).resolve().parents[1]


def test_tiktok_live_style_and_code_overlay_route() -> None:
    style = LiveFXStyle.from_path(ROOT / "configs/live_fx/tiktok_live_v1.json")
    audit = style.audit_events([{
        "id": "gift_car", "start": 21.4, "duration": 2.3,
        "render_mode": "code_overlay", "asset_id": "sports_car_premium_v1",
        "motion_recipe": "anticipate-impact-glide-settle",
        "readable_overlay": {"username": "small_case", "gift_name": "概念跑车", "count": 1},
    }])
    assert audit["passed"] is True
    assert audit["routes"][0]["render_target"] == "hyperframes_vfx"


def test_neural_plate_cannot_own_readable_text() -> None:
    style = LiveFXStyle.from_path(ROOT / "configs/live_fx/tiktok_live_v1.json")
    with pytest.raises(LiveFXValidationError, match="readable UI"):
        style.validate_event({
            "id": "gift_car_neural", "start": 5.0, "duration": 1.0,
            "render_mode": "neural_plate", "segment_id": "seg_050_060",
            "asset_id": "sports_car_premium_v1", "motion_recipe": "anticipate-impact-glide-settle",
            "readable_overlay": {"gift_name": "跑车"},
        })


def test_overlapping_hero_gifts_fail_density_gate() -> None:
    style = LiveFXStyle.from_path(ROOT / "configs/live_fx/tiktok_live_v1.json")
    base = {
        "duration": 2.3, "render_mode": "code_overlay", "asset_id": "sports_car_premium_v1",
        "motion_recipe": "anticipate-impact-glide-settle",
    }
    audit = style.audit_events([{**base, "id": "one", "start": 1.0}, {**base, "id": "two", "start": 2.0}])
    assert audit["passed"] is False
    assert audit["peak_overlap"] == 2


def test_parse_silencedetect_pairs_intervals() -> None:
    output = "silence_start: 24.731\nsilence_end: 25.744 | silence_duration: 1.013\n"
    assert parse_silencedetect(output) == [{"start": 24.731, "end": 25.744, "duration": 1.013}]
