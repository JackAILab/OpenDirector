from pathlib import Path

import pytest

from harness.live.text import LiveTextStyle, LiveTextValidationError


ROOT = Path(__file__).resolve().parents[1]


def test_tiktok_live_text_style_is_code_owned_and_compact() -> None:
    style = LiveTextStyle.from_path(ROOT / "configs/live_ui/tiktok_live_text_v2.json")
    assert style.roles["comment_body"]["font_size_px"] == 24
    assert style.payload["comment_queue"]["regular_surface"] == "transparent"


def test_priority_text_surfaces_cannot_overlap() -> None:
    style = LiveTextStyle.from_path(ROOT / "configs/live_ui/tiktok_live_text_v2.json")
    audit = style.audit_events([
        {"id": "cart", "start": 12.0, "end": 18.0, "owner": "code", "priority_surface": True},
        {"id": "gift", "start": 16.8, "end": 19.1, "owner": "code", "priority_surface": True},
    ])
    assert audit["passed"] is False
    assert audit["priority_surface_peak"] == 2


def test_repeated_comment_card_surface_is_rejected() -> None:
    payload = dict(LiveTextStyle.from_path(ROOT / "configs/live_ui/tiktok_live_text_v2.json").payload)
    payload["comment_queue"] = {**payload["comment_queue"], "regular_surface": "glass_card"}
    with pytest.raises(LiveTextValidationError, match="regular comments"):
        LiveTextStyle.from_dict(payload)


def test_v3_readable_priority_schedule_has_no_overlap() -> None:
    style = LiveTextStyle.from_path(ROOT / "configs/live_ui/tiktok_live_text_v2.json")
    audit = style.audit_events([
        {"id": "commerce_01", "start": 12.0, "end": 16.54, "owner": "code", "priority_surface": True},
        {"id": "rocket_01", "start": 16.8, "end": 19.14, "owner": "code", "priority_surface": True},
        {"id": "car_01", "start": 21.4, "end": 23.72, "owner": "code", "priority_surface": True},
        {"id": "commerce_02", "start": 24.0, "end": 27.82, "owner": "code", "priority_surface": True},
        {"id": "commerce_03", "start": 32.0, "end": 36.45, "owner": "code", "priority_surface": True},
        {"id": "rocket_02", "start": 41.0, "end": 43.34, "owner": "code", "priority_surface": True},
        {"id": "commerce_04", "start": 47.0, "end": 48.34, "owner": "code", "priority_surface": True},
        {"id": "car_02", "start": 48.6, "end": 50.92, "owner": "code", "priority_surface": True},
    ])
    assert audit == {"passed": True, "priority_surface_peak": 1, "failures": []}


@pytest.mark.parametrize(
    ("name", "orientation", "locale", "presentation", "max_visible"),
    [
        ("mobile_live_text_zh_portrait_v4.json", "portrait", "zh-CN", "camera_overlay", 4),
        ("mobile_live_text_en_portrait_v4.json", "portrait", "en", "camera_overlay", 3),
        ("desktop_live_text_zh_landscape_v4.json", "landscape", "zh-CN", "discussion_rail", 6),
        ("desktop_live_text_en_landscape_v4.json", "landscape", "en", "discussion_rail", 6),
    ],
)
def test_v4_multiformat_styles(
    name: str, orientation: str, locale: str, presentation: str, max_visible: int
) -> None:
    style = LiveTextStyle.from_path(ROOT / "configs/live_ui" / name)
    assert style.payload["canvas"]["orientation"] == orientation
    assert style.payload["locale"] == locale
    assert style.payload["comment_queue"]["presentation"] == presentation
    assert style.payload["comment_queue"]["max_visible"] == max_visible
    assert style.payload["training_eligible"] is False


def test_landscape_style_rejects_camera_overlay_comment_presentation() -> None:
    source = LiveTextStyle.from_path(ROOT / "configs/live_ui/desktop_live_text_en_landscape_v4.json")
    payload = dict(source.payload)
    payload["comment_queue"] = {**source.payload["comment_queue"], "presentation": "camera_overlay"}
    with pytest.raises(LiveTextValidationError, match="discussion_rail"):
        LiveTextStyle.from_dict(payload)
