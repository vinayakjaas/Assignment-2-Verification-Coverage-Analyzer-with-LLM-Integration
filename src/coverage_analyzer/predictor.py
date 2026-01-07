from __future__ import annotations

from typing import List

from .models import CoverageReport, Prediction, Suggestion


class ClosurePredictor:
    def __init__(self, report: CoverageReport):
        self.report = report

    def estimate_velocity(self, recent_bins_per_hour: float = 5.0) -> float:
        """Simple heuristic: assume N bins/hour default if no data."""
        return max(recent_bins_per_hour, 1.0)

    def estimate_time_to_close(self, uncovered_count: int, velocity: float) -> float:
        return uncovered_count / velocity

    def probability(self, uncovered_count: int, has_hard_bins: bool) -> float:
        base = 0.9 if uncovered_count < 5 else 0.75 if uncovered_count < 15 else 0.6
        if has_hard_bins:
            base -= 0.15
        return max(0.1, min(0.95, base))

    def blocking_bins(self, suggestions: List[Suggestion]) -> List[str]:
        blocked = []
        for s in suggestions:
            token = s.target_bin.lower()
            if any(keyword in token for keyword in ["decode", "timeout", "wrap", "eight", "error"]):
                blocked.append(s.target_bin)
        return blocked

    def predict(self, suggestions: List[Suggestion]) -> Prediction:
        uncovered_count = len(self.report.uncovered_bins) + sum(len(c.uncovered) for c in self.report.cross_coverage)
        velocity = self.estimate_velocity()
        hours = self.estimate_time_to_close(uncovered_count, velocity)
        has_hard = any(s.difficulty == "hard" for s in suggestions)
        probability = self.probability(uncovered_count, has_hard)
        blocked = self.blocking_bins(suggestions)
        return Prediction(
            estimated_hours_to_closure=round(hours, 2),
            closure_probability=round(probability, 2),
            blocking_bins=blocked,
        )

