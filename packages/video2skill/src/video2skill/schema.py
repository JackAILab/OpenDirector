from typing import Literal
from urllib.parse import urlsplit
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False, str_strip_whitespace=True)

class Source(Strict):
    title: str = Field(min_length=1, max_length=200)
    source_url: str = Field(default='', max_length=1000)
    source_name: str = Field(default='local', max_length=100)
    rights: Literal['owned', 'permission', 'review-only'] = 'review-only'

    @field_validator('source_url')
    @classmethod
    def public_citation(cls, value):
        if value:
            url = urlsplit(value)
            if url.scheme not in ('https', 'http') or not url.hostname or url.username or url.password or url.query or url.fragment:
                raise ValueError('Use a public citation URL without credentials, query or fragment')
        return value

class Beat(Strict):
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    frames: list[int] = Field(min_length=1, max_length=24)
    observation: str = Field(min_length=1, max_length=1000)
    purpose: str = Field(min_length=1, max_length=700)

    @model_validator(mode='after')
    def ordered(self):
        if self.end <= self.start:
            raise ValueError('Beat end must follow start')
        return self

class Analysis(Strict):
    media_role: Literal['original_ad', 'tutorial', 'case_film', 'music_video', 'mixed', 'unknown']
    confidence: Literal['high', 'medium', 'low']
    principle: str = Field(min_length=1, max_length=200)
    mechanism: str = Field(min_length=1, max_length=2000)
    beats: list[Beat] = Field(min_length=2, max_length=12)
    questions: list[str] = Field(min_length=1, max_length=12)
    transfer_rules: list[str] = Field(min_length=1, max_length=12)
    avoid: list[str] = Field(min_length=1, max_length=12)

    @field_validator('questions', 'transfer_rules', 'avoid')
    @classmethod
    def bounded_text(cls, values):
        if any(not v.strip() or len(v) > 700 for v in values):
            raise ValueError('Empty or oversized rule')
        return values

class Method(Strict):
    kind: Literal['manual', 'sampled-vision'] = 'manual'
    model: str = Field(default='', max_length=200)
    prompt_sha256: str = Field(default='', pattern=r'^$|^[a-f0-9]{64}$')
    pipeline_version: Literal['0.1.0'] = '0.1.0'

class Evidence(Strict):
    source: Source
    method: Method = Field(default_factory=Method)
    media_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    duration: float = Field(gt=0, le=600)
    frame_times: list[float] = Field(min_length=2, max_length=24)
    has_audio: bool = False
    analysis: Analysis

    @model_validator(mode='after')
    def grounded(self):
        if self.frame_times != sorted(set(self.frame_times)):
            raise ValueError('Frame times must be unique and sorted')
        if any(not 0 <= t < self.duration for t in self.frame_times):
            raise ValueError('Frame outside video')
        for beat in self.analysis.beats:
            if beat.end > self.duration or len(set(beat.frames)) != len(beat.frames):
                raise ValueError('Invalid evidence window')
            if any(i < 0 or i >= len(self.frame_times) or not beat.start <= self.frame_times[i] <= beat.end for i in beat.frames):
                raise ValueError('Beat is not grounded in its cited frames')
        return self
