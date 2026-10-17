from __future__ import annotations

import hashlib
import json
import re
import subprocess
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image

from .base import ImageModel, ImageRequest, ImageResult
from .kling_video import KlingGenerationError, _first, _task_status


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class KlingImageModel(ImageModel):
    """Official Kling CLI image adapter with non-overwriting safe provenance."""

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
            message = re.sub(r"https?://[^\s\"'<>]+", "<temporary-url-redacted>", message)
            message = re.sub(r'"url":"[^"]+"', '"url":"<temporary-url-redacted>"', message)
            excerpt = message if len(message) <= 2400 else message[:1200] + "\n...<truncated>...\n" + message[-800:]
            raise RuntimeError(f"Kling CLI failed ({process.returncode}): {excerpt}")
        try:
            return json.loads(process.stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Kling CLI returned non-JSON output") from exc

    @staticmethod
    def build_command(request: ImageRequest) -> list[str]:
        trace_id = str(request.metadata.get("task_trace_id", "")).strip()
        command: list[str] = []
        if trace_id:
            command.extend(["--task-trace-id", trace_id])
        command.append("image_to_image")
        for image in request.reference_images:
            command.extend(["--image", str(image.resolve())])
        if request.model in {None, "omni", "kling-image-o1"}:
            command.append("--omni")
        else:
            command.extend(["--model", request.model])
        width, height = (int(value) for value in request.size.lower().split("x", 1))
        aspect = "9:16" if height > width else "16:9" if width > height else "1:1"
        resolution = "2k" if request.quality == "high" else "1k"
        command.extend([
            "--imgResolution", resolution, "--aspectRatio", aspect, "--imageCount", "1",
            "--skill-name", "kling-cli", "--skill-version", "0.1.3", request.prompt, "--quiet",
        ])
        return command

    def create(self, request: ImageRequest) -> ImageResult:
        output = request.output.resolve()
        provenance = output.with_suffix(".provenance.json")
        if output.exists() or provenance.exists():
            raise FileExistsError(f"refusing to overwrite paid artifact: {output}")
        if not request.reference_images:
            raise ValueError("Kling image-to-image requires at least one reference image")
        missing = [str(path) for path in request.reference_images if not path.is_file()]
        if missing:
            raise FileNotFoundError("missing reference images: " + ", ".join(missing))
        output.parent.mkdir(parents=True, exist_ok=True)
        submitted = self._run(self.build_command(request))
        generation_id = str(_first(submitted, ("generation_id", "generationId", "task_id")) or "")
        if not generation_id:
            raise RuntimeError("Kling submission did not return a generation id")
        completed = self._run([
            "query_tasks", "--poll", str(self.timeout_seconds), generation_id,
            "--skill-name", "kling-cli", "--skill-version", "0.1.3", "--quiet",
        ])
        status = _task_status(completed)
        if status and status not in {"COMPLETED", "PARTIAL_COMPLETED", "SUCCEEDED", "SUCCESS", "FINISHED"}:
            raise KlingGenerationError(generation_id, f"Kling generation_id={generation_id} ended with status {status}")
        url = _first(completed, ("urlWithoutWatermark", "url_without_watermark", "image_url", "url"))
        if not isinstance(url, str) or not url.startswith(("http://", "https://")):
            raise RuntimeError("Kling completed without a downloadable image URL")
        try:
            with urllib.request.urlopen(url, timeout=600) as response:
                output.write_bytes(response.read())
            with Image.open(output) as image:
                image.verify()
            with Image.open(output) as image:
                dimensions = image.size
            sha256 = _sha256(output)
            credits = _first(submitted, ("credits_consumed", "creditsConsumed", "consume", "cost"))
            credits = int(credits) if isinstance(credits, (int, float, str)) and str(credits).isdigit() else None
            record = {
                "schema": "visualagent.image-generation-provenance.v1",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "provider": "Kling AI via official CLI", "model": request.model or "omni",
                "operation": "image_to_image", "generation_id": generation_id,
                "status": status or "COMPLETED",
                "parameters": {"size": request.size, "quality": request.quality, "image_count": 1},
                "prompt_sha256": hashlib.sha256(request.prompt.encode("utf-8")).hexdigest(),
                "references": [{"name": path.name, "sha256": _sha256(path)} for path in request.reference_images],
                "output": {"name": output.name, "sha256": sha256, "bytes": output.stat().st_size,
                           "dimensions": list(dimensions)},
                "credits_consumed": credits, "task_trace_id": request.metadata.get("task_trace_id"),
                "temporary_urls_stored": False, "raw_provider_payload_stored": False,
                "metadata": request.metadata, "training_eligible": False,
            }
            provenance.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        except Exception:
            output.unlink(missing_ok=True)
            provenance.unlink(missing_ok=True)
            raise
        return ImageResult(
            output, provenance, sha256, dimensions, request.model or "omni", "image_to_image",
            generation_id, credits,
        )
