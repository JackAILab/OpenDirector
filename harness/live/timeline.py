from __future__ import annotations

from dataclasses import dataclass
from typing import Any


TRACKS = ("camera", "speech", "comments", "ui", "vfx", "ar", "subtitles")
SYMBOLIC_TRACKS = {"comments", "ui", "vfx", "subtitles"}


class TimelineValidationError(ValueError):
    pass


@dataclass(frozen=True)
class LiveProductionTimeline:
    payload: dict[str, Any]

    @property
    def duration(self) -> float:
        return float(self.payload["duration"])

    @property
    def tracks(self) -> dict[str, list[dict[str, Any]]]:
        return self.payload["tracks"]

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "LiveProductionTimeline":
        timeline = cls(payload=payload)
        timeline.validate()
        return timeline

    def validate(self) -> None:
        if self.payload.get("schema") != "visualagent.live-production-timeline.v1":
            raise TimelineValidationError("unsupported timeline schema")
        if self.duration <= 0:
            raise TimelineValidationError("duration must be positive")
        tracks = self.payload.get("tracks")
        if not isinstance(tracks, dict):
            raise TimelineValidationError("tracks must be an object")
        unknown = set(tracks) - set(TRACKS)
        if unknown:
            raise TimelineValidationError(f"unknown tracks: {sorted(unknown)}")
        ids: dict[str, tuple[str, float]] = {}
        for track_name in TRACKS:
            events = tracks.get(track_name, [])
            if not isinstance(events, list):
                raise TimelineValidationError(f"track {track_name} must be a list")
            previous = -1.0
            for event in events:
                event_id = str(event.get("id", "")).strip()
                if not event_id or event_id in ids:
                    raise TimelineValidationError(f"missing or duplicate event id: {event_id!r}")
                start = float(event.get("start", event.get("time", -1)))
                end = float(event.get("end", start))
                if start < 0 or end < start or end > self.duration:
                    raise TimelineValidationError(f"event {event_id} is outside timeline bounds")
                if start < previous:
                    raise TimelineValidationError(f"track {track_name} is not time ordered")
                previous = start
                ids[event_id] = (track_name, start)
                if track_name in SYMBOLIC_TRACKS and event.get("model_owned") is True:
                    raise TimelineValidationError(f"symbolic event {event_id} cannot be model_owned")
        for track_name, events in tracks.items():
            for event in events:
                for relation in ("caused_by", "responds_to"):
                    target = event.get(relation)
                    if not target:
                        continue
                    if target not in ids:
                        raise TimelineValidationError(f"event {event['id']} references unknown {relation}={target}")
                    if ids[target][1] > float(event.get("start", event.get("time", 0))):
                        raise TimelineValidationError(f"event {event['id']} occurs before its cause {target}")
                if event.get("responds_to"):
                    cause_track = ids[event["responds_to"]][0]
                    if cause_track != "comments":
                        raise TimelineValidationError(f"event {event['id']} responds_to must reference a comment")


def compile_camera_prompt(timeline: LiveProductionTimeline) -> str:
    """Compile only neural camera semantics; symbolic text never crosses this boundary."""
    scene = timeline.payload.get("scene", {})
    safe_areas = timeline.payload.get("layout", {}).get("safe_areas", [])
    lines = [
        "Generate only a clean neural camera feed for a synthetic livestream.",
        f"Scene: {scene.get('description', '')}".strip(),
    ]
    for event in timeline.tracks.get("camera", []):
        lines.append(f"{event['start']:.1f}-{event['end']:.1f}s: {event['action']}")
    if safe_areas:
        lines.append("Composition constraints: " + "; ".join(str(area["instruction"]) for area in safe_areas))
    lines.append(
        "No readable text, UI, subtitles, comments, counters, prices, product cards, buttons, "
        "floating hearts, gifts, graphics, watermarks, or dynamically appearing logos."
    )
    prompt = "\n".join(line for line in lines if line)
    symbolic_text = [
        str(event.get("text", ""))
        for name in SYMBOLIC_TRACKS for event in timeline.tracks.get(name, [])
        if event.get("text")
    ]
    if any(text and text in prompt for text in symbolic_text):
        raise TimelineValidationError("symbolic track text leaked into camera prompt")
    return prompt
