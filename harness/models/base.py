from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ImageRequest:
    prompt: str
    output: Path
    reference_images: tuple[Path, ...] = ()
    operation: str | None = None
    model: str | None = None
    size: str = "1024x1824"
    quality: str = "high"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ImageResult:
    output: Path
    provenance: Path
    sha256: str
    dimensions: tuple[int, int]
    model: str
    operation: str
    generation_id: str | None = None
    credits_consumed: int | None = None


class ImageModel(ABC):
    @abstractmethod
    def create(self, request: ImageRequest) -> ImageResult: ...


@dataclass(frozen=True)
class VideoRequest:
    prompt: str
    output: Path
    reference_images: tuple[Path, ...]
    model: str
    duration_seconds: int = 15
    aspect_ratio: str = "9:16"
    resolution: str = "1080p"
    image_count: int = 1
    prefer_multi_shots: bool = False
    enable_audio: bool = False
    task_trace_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class VideoResult:
    output: Path
    receipt: Path
    sha256: str
    model: str
    generation_id: str
    credits_consumed: int | None


class VideoModel(ABC):
    @abstractmethod
    def create(self, request: VideoRequest) -> VideoResult: ...
