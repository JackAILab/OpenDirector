from __future__ import annotations

import base64
import hashlib
import json
import os
import urllib.request
from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path

from openai import OpenAI
from PIL import Image

from .base import ImageModel, ImageRequest, ImageResult


def _required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"missing required environment variable: {name}")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class OpenAIImageModel(ImageModel):
    """OpenAI-compatible GPT Image adapter; secrets never enter artifacts."""

    def __init__(
        self, *, model_env: str = "OPENAI_IMAGE_MODEL", base_url_env: str = "OPENAI_BASE_URL",
        api_key_env: str = "OPENAI_API_KEY", expected_model: str | None = None, timeout_seconds: float = 600.0,
    ) -> None:
        self.model_env = model_env
        self.base_url_env = base_url_env
        self.api_key_env = api_key_env
        self.expected_model = expected_model
        self.timeout_seconds = timeout_seconds

    @staticmethod
    def _decode(item: object, output: Path) -> None:
        encoded = getattr(item, "b64_json", None)
        if encoded:
            output.write_bytes(base64.b64decode(encoded))
            return
        url = getattr(item, "url", None)
        if url:
            with urllib.request.urlopen(url, timeout=300) as response:
                output.write_bytes(response.read())
            return
        raise RuntimeError("image response contained neither b64_json nor url")

    def create(self, request: ImageRequest) -> ImageResult:
        output = request.output.resolve()
        output_parent = output.parent
        if output.exists() or output.with_suffix(".provenance.json").exists():
            raise FileExistsError(f"refusing to overwrite paid artifact: {output}")
        missing = [str(path) for path in request.reference_images if not path.is_file()]
        if missing:
            raise FileNotFoundError("missing reference images: " + ", ".join(missing))
        configured_model = _required_env(self.model_env)
        model = request.model or configured_model
        if model != configured_model:
            raise RuntimeError(f"request model {model!r} does not match {self.model_env}")
        if self.expected_model and model != self.expected_model:
            raise RuntimeError(f"configured model must be {self.expected_model!r}")
        output_parent.mkdir(parents=True, exist_ok=True)
        client = OpenAI(
            base_url=_required_env(self.base_url_env), api_key=_required_env(self.api_key_env),
            timeout=self.timeout_seconds, max_retries=0,
        )
        operation = request.operation or ("edit" if request.reference_images else "generate")
        if operation not in {"generate", "edit"}:
            raise ValueError(f"unsupported image operation: {operation}")
        if operation == "edit" and not request.reference_images:
            raise ValueError("edit operation requires at least one reference image")
        if operation == "generate" and request.reference_images:
            raise ValueError("generate operation cannot consume reference images; use edit")
        if operation == "edit":
            with ExitStack() as stack:
                handles = [stack.enter_context(path.open("rb")) for path in request.reference_images]
                response = client.images.edit(
                    model=model, image=handles, prompt=request.prompt, size=request.size, quality=request.quality,
                )
            endpoint = "/v1/images/edits"
        else:
            response = client.images.generate(
                model=model, prompt=request.prompt, size=request.size, quality=request.quality,
            )
            endpoint = "/v1/images/generations"
        try:
            self._decode(response.data[0], output)
            with Image.open(output) as image:
                image.verify()
            with Image.open(output) as image:
                dimensions = image.size
        except Exception:
            output.unlink(missing_ok=True)
            raise
        provenance = output.with_suffix(".provenance.json")
        record = {
            "schema": "visualagent.image-generation-provenance.v1",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "provider": "openai_compatible", "model": model, "operation": operation, "endpoint": endpoint,
            "prompt_sha256": hashlib.sha256(request.prompt.encode("utf-8")).hexdigest(),
            "parameters": {"size": request.size, "quality": request.quality},
            "references": [{"name": path.name, "sha256": _sha256(path)} for path in request.reference_images],
            "output": {"name": output.name, "sha256": _sha256(output), "dimensions": list(dimensions)},
            "metadata": request.metadata,
            "credential_profile": {
                "base_url_env": self.base_url_env, "api_key_env": self.api_key_env, "model_env": self.model_env,
                "credential_values_stored": False, "temporary_urls_stored": False,
            },
        }
        try:
            provenance.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        except Exception:
            output.unlink(missing_ok=True)
            provenance.unlink(missing_ok=True)
            raise
        return ImageResult(
            output=output, provenance=provenance, sha256=record["output"]["sha256"],
            dimensions=dimensions, model=model, operation=operation,
        )
