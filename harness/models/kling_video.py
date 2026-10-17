from __future__ import annotations

import hashlib
import json
import re
import subprocess
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .base import VideoModel, VideoRequest, VideoResult


class KlingGenerationError(RuntimeError):
    """A submitted Kling job reached a terminal failure state."""

    def __init__(self, generation_id: str, message: str) -> None:
        self.generation_id = generation_id
        super().__init__(message)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _walk(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _first(payload: Any, keys: tuple[str, ...]) -> Any:
    for item in _walk(payload):
        for key in keys:
            if key in item and item[key] not in (None, "", []):
                return item[key]
    return None


def _task_status(payload: Any) -> str:
    for item in _walk(payload):
        for key in ("task_status", "state", "status"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip().upper()
    return ""


class KlingVideoModel(VideoModel):
    """Official Kling CLI adapter. Raw payloads and temporary URLs are never persisted."""

    def __init__(self, *, executable: str = "kling", timeout_seconds: int = 2400) -> None:
        self.executable = executable
        self.timeout_seconds = timeout_seconds

    def _run(self, arguments: list[str]) -> dict[str, Any]:
        process = subprocess.run(
            [self.executable, *arguments], check=False, capture_output=True, text=True,
            timeout=self.timeout_seconds,
        )
        if process.returncode:
            message = (process.stderr or process.stdout).strip()
            # Stop at JSON/string delimiters so a compact provider payload keeps the
            # safe error reason after a signed URL instead of losing the whole line.
            message = re.sub(r"https?://[^\s\"'<>]+", "<temporary-url-redacted>", message)
            message = re.sub(r'\"url\":\"[^\"]+\"', '"url":"<temporary-url-redacted>"', message)
            message = re.sub(
                r"\[kling\] 提交 arguments：.*?(?=\n\[kling\] 提交 inputs：)",
                "[kling] submitted arguments: <prompt-and-arguments-redacted>", message, flags=re.S,
            )
            message = re.sub(
                r"\[kling\] 提交 inputs：.*?(?=\n\[kling\] (?:image_to_video|请对照))",
                "[kling] submitted inputs: <temporary-urls-redacted>", message, flags=re.S,
            )
            message = re.sub(
                r'(["\s](?:url|uploadUrl|upload_url|fileUrl|file_url)["\s]*[:=]["\s]*)[^"\s,}]+',
                r'\1<temporary-url-redacted>', message, flags=re.I,
            )
            message = re.sub(
                r'(?i)(?:access|refresh|id)?_?token["\s]*[:=]["\s]*[^"\s,}]+',
                'token=<redacted>', message,
            )
            failure_lines = [
                line for line in message.splitlines()
                if any(marker in line.lower() for marker in (
                    "提交失败", "submit failed", "mcp 工具调用失败", "mcp tool call failed",
                    "invalid value", "moderation", "insufficient", "not supported",
                    "error", "failed",
                ))
            ]
            excerpt = "\n".join(failure_lines[:8]) if failure_lines else (message if len(message) <= 3000 else message[:1200] + "\n...<truncated>...\n" + message[-800:])
            raise RuntimeError(f"Kling CLI failed ({process.returncode}): {excerpt}")
        try:
            return json.loads(process.stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Kling CLI returned non-JSON output") from exc

    @staticmethod
    def build_command(request: VideoRequest) -> list[str]:
        """Compile a provider-specific CLI command without changing user parameters."""
        command = []
        if request.task_trace_id:
            command.extend(["--task-trace-id", request.task_trace_id])
        command.append("image_to_video")
        hard_endpoint_mode = request.metadata.get("input_mode") in {
            "hard_first_and_last_frames", "first_tail_boundary_images",
        }
        if request.model == "kling-video-v3_0" or (
            request.model == "kling-video-v3_0_omni" and hard_endpoint_mode
        ):
            if len(request.reference_images) not in {1, 2}:
                raise ValueError("hard endpoint image-to-video requires one first image and at most one tail image")
            command.extend(["--image", str(request.reference_images[0].resolve())])
            if len(request.reference_images) == 2:
                command.extend(["--tailImage", str(request.reference_images[1].resolve())])
        else:
            for image in request.reference_images:
                command.extend(["--image", str(image.resolve())])
        command.extend([
            "--model", request.model, "--duration", str(request.duration_seconds),
            "--resolution", request.resolution, "--imageCount", str(request.image_count),
            "--prefer_multi_shots", str(request.prefer_multi_shots).lower(),
            "--enable_audio", str(request.enable_audio).lower(),
        ])
        if request.model in {"kling-video-v3_0_omni", "kling-video-o1"}:
            command.extend(["--aspect_ratio", request.aspect_ratio])
        # The Kling subcommand parser treats a following positional as a value for --quiet.
        # Keep the prompt positional before the trailing boolean flag.
        command.extend(["--skill-name", "kling-cli", "--skill-version", "0.1.3", request.prompt, "--quiet"])
        return command

    def create(self, request: VideoRequest) -> VideoResult:
        output = request.output.resolve()
        receipt = output.with_suffix(".receipt.json")
        submission = output.with_suffix(".submission.json")
        if output.exists() or receipt.exists() or submission.exists():
            raise FileExistsError(f"refusing to overwrite paid artifact: {output}")
        if not request.reference_images:
            raise ValueError("Kling image-to-video requires at least one reference image")
        if len(request.reference_images) > 7:
            raise ValueError("Kling Omni supports at most seven reference images")
        missing = [str(path) for path in request.reference_images if not path.is_file()]
        if missing:
            raise FileNotFoundError("missing reference images: " + ", ".join(missing))
        output.parent.mkdir(parents=True, exist_ok=True)
        command = self.build_command(request)
        submitted = self._run(command)
        generation_id = str(_first(submitted, ("generation_id", "generationId", "task_id")) or "")
        if not generation_id:
            raise RuntimeError("Kling submission did not return a generation id")
        # Persist the safe job handle before a potentially long poll. A timeout
        # must never turn into a second paid submission on process restart.
        with submission.open("x", encoding="utf-8") as handle:
            json.dump({
                "schema": "visualagent.video-submission.v1",
                "generation_id": generation_id,
                "model": request.model,
                "prompt_sha256": hashlib.sha256(request.prompt.encode("utf-8")).hexdigest(),
                "created_at": datetime.now(timezone.utc).isoformat(),
                "training_eligible": False,
            }, handle, ensure_ascii=False, indent=2)
        completed = self._run([
            "query_tasks", "--poll", str(self.timeout_seconds), generation_id,
            "--skill-name", "kling-cli", "--skill-version", "0.1.3", "--quiet",
        ])
        status = _task_status(completed)
        if status and status not in {"COMPLETED", "PARTIAL_COMPLETED", "SUCCEEDED", "SUCCESS", "FINISHED"}:
            raise KlingGenerationError(
                generation_id,
                f"Kling generation_id={generation_id} ended with status {status}",
            )
        url = _first(completed, ("urlWithoutWatermark", "url_without_watermark", "video_url", "url"))
        if not isinstance(url, str) or not url.startswith(("http://", "https://")):
            raise RuntimeError("Kling completed without a downloadable video URL")
        try:
            with urllib.request.urlopen(url, timeout=600) as response:
                output.write_bytes(response.read())
            if output.stat().st_size < 1024:
                raise RuntimeError("downloaded Kling artifact is unexpectedly small")
            sha256 = _sha256(output)
            credits = _first(submitted, ("credits_consumed", "creditsConsumed", "consume", "cost"))
            if credits is None:
                credits = _first(completed, ("credits_consumed", "creditsConsumed", "consume", "cost"))
            credits = int(credits) if isinstance(credits, (int, float, str)) and str(credits).isdigit() else None
            record = {
                "schema": "visualagent.video-generation-receipt.v1",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "provider": "Kling AI via official CLI", "model": request.model,
                "generation_id": generation_id, "status": status or "COMPLETED",
                "parameters": {
                    "duration_seconds": request.duration_seconds, "aspect_ratio": request.aspect_ratio,
                    "resolution": request.resolution, "image_count": request.image_count,
                    "prefer_multi_shots": request.prefer_multi_shots, "enable_audio": request.enable_audio,
                    "input_mode": request.metadata.get("input_mode"),
                },
                "prompt_sha256": hashlib.sha256(request.prompt.encode("utf-8")).hexdigest(),
                "references": [{"name": path.name, "sha256": _sha256(path)} for path in request.reference_images],
                "output": {"name": output.name, "sha256": sha256, "bytes": output.stat().st_size},
                "credits_consumed": credits, "task_trace_id": request.task_trace_id,
                "temporary_urls_stored": False, "raw_provider_payload_stored": False,
                "metadata": request.metadata, "training_eligible": False,
            }
            receipt.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        except Exception:
            output.unlink(missing_ok=True)
            receipt.unlink(missing_ok=True)
            raise
        return VideoResult(output, receipt, sha256, request.model, generation_id, credits)
