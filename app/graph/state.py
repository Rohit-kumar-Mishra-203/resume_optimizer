from typing import TypedDict, Optional, List, Dict
from app.core.schema import ResumeFacts, JDRequirements, ResumeCritique


class LoopState(TypedDict):
    jd: JDRequirements
    original_facts: ResumeFacts
    facts: ResumeFacts
    score_breakdown: Optional[Dict]
    critique: Optional[ResumeCritique]
    iteration: int
    max_iterations: int
    target_score: float
    score_history: List[float]
    status: str