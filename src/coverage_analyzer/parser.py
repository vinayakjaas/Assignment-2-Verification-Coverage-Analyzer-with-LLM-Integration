from __future__ import annotations

import json
import re
from pathlib import Path
from typing import List, Optional, Tuple

from .models import (
    BinModel,
    CovergroupModel,
    CoverpointModel,
    CoverageReport,
    CrossBinModel,
    CrossCoverageModel,
)


BIN_RE = re.compile(r"^bin\s+([^\s\[]+)(\[[^\]]+\])?\s+hits:\s+(\d+)\s+(covered|UNCOVERED)", re.IGNORECASE)
CROSS_RE = re.compile(r"^<([^>]+)>\s+hits:\s+(\d+)\s+(covered|UNCOVERED)", re.IGNORECASE)
COVERAGE_RE = re.compile(r"Coverage:\s+([0-9]+\.[0-9]+|[0-9]+)", re.IGNORECASE)
OVERALL_RE = re.compile(r"Overall Coverage:\s+([0-9]+\.[0-9]+|[0-9]+)", re.IGNORECASE)
DESIGN_RE = re.compile(r"Design:\s+(.+)", re.IGNORECASE)


def _parse_bin(line: str) -> Optional[Tuple[str, Optional[str], int, bool]]:
    match = BIN_RE.match(line.strip())
    if not match:
        return None
    name, rng, hits, status = match.groups()
    return name, rng, int(hits), status.lower() == "covered"


def _parse_cross_bin(line: str) -> Optional[Tuple[str, int, bool]]:
    match = CROSS_RE.match(line.strip())
    if not match:
        return None
    label, hits, status = match.groups()
    return label, int(hits), status.lower() == "covered"


def parse_coverage_report(text: str) -> CoverageReport:
    design = "unknown"
    overall_coverage: Optional[float] = None
    covergroups: List[CovergroupModel] = []
    cross_covs: List[CrossCoverageModel] = []
    uncovered_bins: List[dict] = []

    current_cg: Optional[CovergroupModel] = None
    current_cp: Optional[CoverpointModel] = None
    current_cross: Optional[CrossCoverageModel] = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("="):
            continue

        design_match = DESIGN_RE.match(line)
        if design_match:
            design = design_match.group(1).strip()
            continue

        overall_match = OVERALL_RE.match(line)
        if overall_match:
            overall_coverage = float(overall_match.group(1))
            continue

        if line.startswith("Covergroup:"):
            name = line.split(":", 1)[1].strip()
            current_cg = CovergroupModel(name=name, coverpoints=[])
            covergroups.append(current_cg)
            current_cp = None
            current_cross = None
            continue

        if line.startswith("Cross Coverage:"):
            name = line.split(":", 1)[1].strip()
            current_cross = CrossCoverageModel(name=name, bins=[])
            cross_covs.append(current_cross)
            current_cg = None
            current_cp = None
            continue

        if line.startswith("Coverpoint:"):
            cp_name = line.split(":", 1)[1].strip()
            current_cp = CoverpointModel(name=cp_name, bins=[])
            if current_cg:
                current_cg.coverpoints.append(current_cp)
            continue

        coverage_match = COVERAGE_RE.match(line)
        if coverage_match and current_cg and current_cross is None and current_cp is None:
            current_cg.coverage = float(coverage_match.group(1))
            continue
        if coverage_match and current_cross is not None:
            current_cross.coverage = float(coverage_match.group(1))
            continue

        if set(line) == {"-"}:
            current_cp = None
            continue

        bin_data = _parse_bin(line)
        if bin_data and current_cp:
            name, rng, hits, covered = bin_data
            bin_model = BinModel(name=name, range=rng, hits=hits, covered=covered, raw=line)
            current_cp.bins.append(bin_model)
            if not covered and current_cg:
                uncovered_bins.append(
                    {"covergroup": current_cg.name, "coverpoint": current_cp.name, "bin": f"{name}{rng or ''}"}
                )
            continue

        cross_data = _parse_cross_bin(line)
        if cross_data and current_cross:
            label, hits, covered = cross_data
            cross_bin = CrossBinModel(label=label, hits=hits, covered=covered, raw=line)
            current_cross.bins.append(cross_bin)
            continue

    return CoverageReport(
        design=design,
        overall_coverage=overall_coverage,
        covergroups=covergroups,
        cross_coverage=cross_covs,
        uncovered_bins=uncovered_bins,
    )


def load_report(path: Path) -> CoverageReport:
    text = Path(path).read_text()
    return parse_coverage_report(text)


def save_report(report: CoverageReport, output_path: Path) -> None:
    """Save parsed coverage report to JSON file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report.model_dump_json(indent=2))


def load_report_from_json(json_path: Path) -> CoverageReport:
    """Load coverage report from previously saved JSON file."""
    data = json.loads(json_path.read_text())
    return CoverageReport(**data)

