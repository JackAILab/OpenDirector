from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass
class ArtifactManifest:
    run_id: str
    artifacts: list[dict[str, Any]] = field(default_factory=list)

    def add(self, *, layer: str, path: Path, kind: str, metadata: dict[str, Any] | None = None) -> None:
        self.artifacts.append({
            "layer": layer, "kind": kind, "name": path.name,
            "sha256": file_sha256(path), "bytes": path.stat().st_size,
            "metadata": metadata or {},
        })

    def write(self, path: Path) -> Path:
        if path.exists():
            raise FileExistsError(f"refusing to overwrite artifact manifest: {path}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "schema": "visualagent.live-artifact-manifest.v1",
            "run_id": self.run_id, "artifacts": self.artifacts,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "training_eligible": False, "human_review": "pending",
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return path
