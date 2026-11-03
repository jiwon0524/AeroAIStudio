from dataclasses import dataclass, field

PAPER_MODES = ("What is this paper saying?", "Video Explanation", "Step-by-Step Explanation", "Total Summary")


@dataclass
class PaperDocument:
    title: str
    source: str
    mode: str = PAPER_MODES[0]
    extracted_text: str = ""
    analysis: dict = field(default_factory=dict)
    experiment_spec: dict = field(default_factory=dict)
