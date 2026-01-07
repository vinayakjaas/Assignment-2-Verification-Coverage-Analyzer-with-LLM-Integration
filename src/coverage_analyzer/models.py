from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field


class BinModel(BaseModel):
    name: str
    range: Optional[str] = Field(default=None, description="Range descriptor if present, e.g. [0:255]")
    hits: int
    covered: bool
    raw: Optional[str] = Field(default=None, description="Original line text")


class CoverpointModel(BaseModel):
    name: str
    bins: List[BinModel] = Field(default_factory=list)

    @property
    def uncovered(self) -> List[BinModel]:
        return [b for b in self.bins if not b.covered]


class CovergroupModel(BaseModel):
    name: str
    coverage: Optional[float] = None
    coverpoints: List[CoverpointModel] = Field(default_factory=list)

    @property
    def uncovered(self) -> List[BinModel]:
        return [b for cp in self.coverpoints for b in cp.uncovered]


class CrossBinModel(BaseModel):
    label: str
    hits: int
    covered: bool
    raw: Optional[str] = None


class CrossCoverageModel(BaseModel):
    name: str
    coverage: Optional[float] = None
    bins: List[CrossBinModel] = Field(default_factory=list)

    @property
    def uncovered(self) -> List[CrossBinModel]:
        return [b for b in self.bins if not b.covered]


class CoverageReport(BaseModel):
    design: str
    overall_coverage: Optional[float] = None
    covergroups: List[CovergroupModel] = Field(default_factory=list)
    cross_coverage: List[CrossCoverageModel] = Field(default_factory=list)
    uncovered_bins: List[dict] = Field(default_factory=list)

    def to_json(self) -> str:
        return self.model_dump_json(indent=2)


class Suggestion(BaseModel):
    target_bin: str
    priority: str
    difficulty: str
    suggestion: str
    test_outline: List[str]
    dependencies: List[str] = Field(default_factory=list)
    reasoning: str
    priority_score: Optional[float] = None
    coverage_impact: Optional[float] = None
    dependency_score: Optional[float] = None


class Prediction(BaseModel):
    estimated_hours_to_closure: float
    closure_probability: float
    blocking_bins: List[str] = Field(default_factory=list)

