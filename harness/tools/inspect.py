from __future__ import annotations

from pathlib import Path
from typing import Any

from harness.core.state import RunState
from harness.core.types import Observation
from harness.evaluators import ImageArtifactEvaluator, SceneRichnessEvaluator

from .base import Tool


class InspectKeyframesTool(Tool):
    name = "inspect_keyframes"
    layer = "camera_reference_critic"

    def invoke(self, arguments: dict[str, Any]) -> Observation:
        paths = [Path(value) for value in arguments["paths"]]
        state = RunState("inspection", "keyframes", "inspect generated references", {}, {})
        technical = ImageArtifactEvaluator(
            paths, expected_model=str(arguments["expected_model"]),
            min_mean_luma=float(arguments.get("min_mean_luma", 92.0)),
            max_dark_pixel_ratio=float(arguments.get("max_dark_pixel_ratio", 0.34)),
            max_face_highlight_ratio=(
                float(arguments["max_face_highlight_ratio"])
                if arguments.get("max_face_highlight_ratio") is not None else None
            ),
            min_pass_count=len(paths),
        ).evaluate(state)
        richness = SceneRichnessEvaluator(paths, min_pass_count=len(paths)).evaluate(state)
        passed = technical["passed"] and richness["passed"]
        return Observation(ok=passed, content={"technical": technical, "scene_richness": richness, "human_review_required": True}, error=None if passed else "keyframe quality gate failed")
