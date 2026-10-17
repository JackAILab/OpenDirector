from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal


RenderMode = Literal["code_overlay", "neural_plate"]
RENDER_TARGETS: dict[RenderMode, str] = {
    "code_overlay": "hyperframes_vfx",
    "neural_plate": "kling_camera_segment",
}


class LiveFXValidationError(ValueError):
    pass


@dataclass(frozen=True)
class LiveFXStyle:
    payload: dict[str, Any]
    source: Path | None = None

    @property
    def assets(self) -> dict[str, dict[str, Any]]:
        return {str(item["id"]): item for item in self.payload.get("assets", [])}

    @property
    def recipes(self) -> dict[str, dict[str, Any]]:
        return {str(item["id"]): item for item in self.payload.get("motion_recipes", [])}

    @classmethod
    def from_path(cls, path: Path) -> "LiveFXStyle":
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")), source=path.resolve())

    @classmethod
    def from_dict(cls, payload: dict[str, Any], *, source: Path | None = None) -> "LiveFXStyle":
        style = cls(payload=payload, source=source)
        style.validate()
        return style

    def validate(self) -> None:
        if self.payload.get("schema") != "visualagent.live-fx-style.v1":
            raise LiveFXValidationError("unsupported live FX style schema")
        if self.payload.get("training_eligible") is not False:
            raise LiveFXValidationError("new live FX styles must remain training_eligible=false")
        asset_ids: set[str] = set()
        for asset in self.payload.get("assets", []):
            asset_id = str(asset.get("id", "")).strip()
            if not asset_id or asset_id in asset_ids:
                raise LiveFXValidationError(f"missing or duplicate asset id: {asset_id!r}")
            if asset.get("contains_readable_text") is not False:
                raise LiveFXValidationError(f"asset {asset_id} must not contain readable text")
            asset_ids.add(asset_id)
        recipe_ids: set[str] = set()
        for recipe in self.payload.get("motion_recipes", []):
            recipe_id = str(recipe.get("id", "")).strip()
            if not recipe_id or recipe_id in recipe_ids:
                raise LiveFXValidationError(f"missing or duplicate recipe id: {recipe_id!r}")
            phases = recipe.get("phases", [])
            if [phase.get("name") for phase in phases] != [
                "anticipate", "burst", "hero", "settle", "dissipate",
            ]:
                raise LiveFXValidationError(f"recipe {recipe_id} must use the five-phase gift grammar")
            if any(float(phase.get("duration", 0)) <= 0 for phase in phases):
                raise LiveFXValidationError(f"recipe {recipe_id} has a non-positive phase duration")
            recipe_ids.add(recipe_id)

    def validate_event(self, event: dict[str, Any]) -> dict[str, Any]:
        mode = str(event.get("render_mode", "code_overlay"))
        if mode not in RENDER_TARGETS:
            raise LiveFXValidationError(f"unsupported render_mode: {mode}")
        if event.get("asset_id") not in self.assets:
            raise LiveFXValidationError(f"unknown live FX asset: {event.get('asset_id')}")
        if event.get("motion_recipe") not in self.recipes:
            raise LiveFXValidationError(f"unknown motion recipe: {event.get('motion_recipe')}")
        if mode == "neural_plate" and event.get("readable_overlay"):
            raise LiveFXValidationError("neural_plate cannot own readable UI")
        if mode == "neural_plate" and not event.get("segment_id"):
            raise LiveFXValidationError("neural_plate requires an independently reviewable segment_id")
        duration = float(event.get("duration", float(event.get("end", 0)) - float(event.get("start", 0))))
        if not 0.6 <= duration <= 6.0:
            raise LiveFXValidationError("live FX duration must be between 0.6s and 6.0s")
        return {"event_id": event.get("id"), "render_target": RENDER_TARGETS[mode], "duration": duration}

    def audit_events(self, events: list[dict[str, Any]]) -> dict[str, Any]:
        failures: list[dict[str, str]] = []
        routes: list[dict[str, Any]] = []
        intervals: list[tuple[float, float, str]] = []
        for event in events:
            try:
                routes.append(self.validate_event(event))
            except (LiveFXValidationError, TypeError, ValueError) as exc:
                failures.append({"event_id": str(event.get("id", "")), "reason": str(exc)})
                continue
            start = float(event.get("start", 0))
            duration = routes[-1]["duration"]
            intervals.append((start, start + duration, str(event.get("id", ""))))
        peak_overlap = 0
        for start, end, _ in intervals:
            peak_overlap = max(peak_overlap, sum(1 for other_start, other_end, _ in intervals if other_start < end and other_end > start))
        max_overlap = int(self.payload.get("qa", {}).get("max_simultaneous_hero_gifts", 1))
        if peak_overlap > max_overlap:
            failures.append({"event_id": "*", "reason": f"hero gift overlap {peak_overlap} exceeds {max_overlap}"})
        return {"passed": not failures, "routes": routes, "peak_overlap": peak_overlap, "failures": failures}
