from dataclasses import dataclass, field


@dataclass
class VideoEvent:
    seconds: float
    label: str
    confidence: float | None = None


@dataclass
class VideoAnalysis:
    source: str
    events: list[VideoEvent] = field(default_factory=list)
    scene_spec: dict = field(default_factory=dict)
