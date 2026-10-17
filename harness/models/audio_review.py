"""Provider boundary for optional ad audio-semantic review.

Adapters may return a rich in-memory response, but callers must reduce it with
``harness.learning.audio_review`` before anything is persisted.
"""
from abc import ABC, abstractmethod
from pathlib import Path


class AudioSemanticReviewer(ABC):
    """Inspect one media file without granting training eligibility."""

    @abstractmethod
    async def review(self, media: Path, *, media_sha256: str, duration_seconds: float) -> dict:
        raise NotImplementedError
