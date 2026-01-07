from __future__ import annotations

from typing import List

from .models import CoverageReport, Suggestion


DIFFICULTY_MAP = {"easy": 1, "medium": 2, "hard": 3}


class Prioritizer:
    def __init__(self, report: CoverageReport):
        self.report = report

    def _coverage_gap_for_target(self, target_bin: str) -> float:
        """Estimate coverage impact using the covergroup/cross coverage headroom."""
        for cg in self.report.covergroups:
            if target_bin.startswith(f"{cg.name}."):
                if cg.coverage is None:
                    return 0.5
                return max(0.0, 1.0 - cg.coverage / 100.0)
        for cross in self.report.cross_coverage:
            if target_bin.startswith(f"{cross.name}."):
                if cross.coverage is None:
                    return 0.5
                return max(0.0, 1.0 - cross.coverage / 100.0)
        return 0.3

    def score(self, suggestions: List[Suggestion]) -> List[Suggestion]:
        for s in suggestions:
            coverage_impact = self._coverage_gap_for_target(s.target_bin)
            inv_diff = 1.0 / DIFFICULTY_MAP.get(s.difficulty.lower(), 2)
            dep_score = 1.0 if not s.dependencies else 0.5
            priority_score = coverage_impact * 0.4 + inv_diff * 0.3 + dep_score * 0.3

            s.coverage_impact = coverage_impact
            s.dependency_score = dep_score
            s.priority_score = priority_score
        return sorted(suggestions, key=lambda x: x.priority_score or 0.0, reverse=True)

