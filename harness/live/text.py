from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class LiveTextValidationError(ValueError):
    pass


@dataclass(frozen=True)
class LiveTextStyle:
    """Validated, provider-independent layout contract for readable live UI."""

    payload: dict[str, Any]
    source: Path | None = None

    @classmethod
    def from_path(cls, path: Path) -> "LiveTextStyle":
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")), source=path.resolve())

    @classmethod
    def from_dict(cls, payload: dict[str, Any], *, source: Path | None = None) -> "LiveTextStyle":
        style = cls(payload=payload, source=source)
        style.validate()
        return style

    @property
    def roles(self) -> dict[str, dict[str, Any]]:
        return {str(item["id"]): item for item in self.payload.get("text_roles", [])}

    def validate(self) -> None:
        if self.payload.get("schema") != "visualagent.live-text-style.v1":
            raise LiveTextValidationError("unsupported live text style schema")
        if self.payload.get("training_eligible") is not False:
            raise LiveTextValidationError("new live text styles must remain training_eligible=false")
        if self.payload.get("owner") != "code_hyperframes":
            raise LiveTextValidationError("readable live UI must be owned by code_hyperframes")

        canvas = self.payload.get("canvas", {})
        width = int(canvas.get("width", 0))
        height = int(canvas.get("height", 0))
        orientation = canvas.get("orientation")
        if orientation not in {"portrait", "landscape"}:
            raise LiveTextValidationError("canvas.orientation must be portrait or landscape")
        if width <= 0 or height <= 0 or (orientation == "portrait") != (height > width):
            raise LiveTextValidationError("canvas dimensions do not match the declared orientation")

        required = {"host_name", "viewer_count", "comment_author", "comment_body", "commerce_title", "composer_hint"}
        role_ids = [str(item.get("id", "")).strip() for item in self.payload.get("text_roles", [])]
        if any(not role_id for role_id in role_ids) or len(role_ids) != len(set(role_ids)):
            raise LiveTextValidationError("text role ids must be present and unique")
        missing = sorted(required - set(role_ids))
        if missing:
            raise LiveTextValidationError(f"missing required text roles: {', '.join(missing)}")
        for role in self.payload["text_roles"]:
            if float(role.get("font_size_px", 0)) < 12:
                raise LiveTextValidationError(f"text role {role['id']} is too small for the declared canvas")
            if float(role.get("line_height", 0)) < 1:
                raise LiveTextValidationError(f"text role {role['id']} has invalid line height")

        queue = self.payload.get("comment_queue", {})
        visible = int(queue.get("max_visible", 0))
        if not 2 <= visible <= 6:
            raise LiveTextValidationError("comment_queue.max_visible must be between 2 and 6")
        if queue.get("regular_surface") != "transparent":
            raise LiveTextValidationError("regular comments must not become repeated full-card surfaces")
        if queue.get("motion_recipe") != "waterfall-entry+nudge-curve":
            raise LiveTextValidationError("comment queue must use the deterministic live motion recipe")
        presentation = queue.get("presentation")
        expected_presentation = "camera_overlay" if orientation == "portrait" else "discussion_rail"
        if presentation not in (None, expected_presentation):
            raise LiveTextValidationError(
                f"{orientation} comment queue presentation must be {expected_presentation}"
            )

        hierarchy = self.payload.get("hierarchy", {})
        if int(hierarchy.get("max_simultaneous_priority_surfaces", 0)) != 1:
            raise LiveTextValidationError("only one priority text surface may be active at once")
        if not hierarchy.get("ordinary_comments_yield_to_priority_surface", False):
            raise LiveTextValidationError("ordinary comments must yield to commerce or gift priority surfaces")

    def audit_events(self, events: list[dict[str, Any]]) -> dict[str, Any]:
        priority = []
        failures: list[dict[str, str]] = []
        for event in events:
            if event.get("owner") not in (None, "code", "code_hyperframes"):
                failures.append({"event_id": str(event.get("id", "")), "reason": "readable event owner must be code"})
            if event.get("priority_surface"):
                start = float(event.get("start", 0))
                end = float(event.get("end", start))
                if end <= start:
                    failures.append({"event_id": str(event.get("id", "")), "reason": "invalid event interval"})
                priority.append((start, end, str(event.get("id", ""))))
        peak = 0
        for start, end, _ in priority:
            peak = max(peak, sum(1 for other_start, other_end, _ in priority if other_start < end and other_end > start))
        if peak > 1:
            failures.append({"event_id": "*", "reason": f"priority surface overlap {peak} exceeds 1"})
        return {"passed": not failures, "priority_surface_peak": peak, "failures": failures}
