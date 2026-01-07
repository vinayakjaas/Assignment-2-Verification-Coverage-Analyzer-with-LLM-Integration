from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer
from rich import print
from rich.console import Console
from rich.table import Table

from .parser import load_report, save_report
from .prioritizer import Prioritizer
from .suggester import SuggestionGenerator
from .predictor import ClosurePredictor

app = typer.Typer(help="Verification coverage analyzer CLI")
console = Console()


def _load(path: Path):
    if not path.exists():
        raise typer.BadParameter(f"File not found: {path}")
    return load_report(path)


@app.command()
def parse(
    path: Path,
    out: Optional[Path] = typer.Option(None, "--out", "-o", help="Save parsed report JSON to file"),
):
    """Parse coverage report and print structured JSON."""
    report = _load(path)
    json_output = report.model_dump_json(indent=2)
    print(json_output)
    
    if out:
        save_report(report, out)
        console.print(f"[green] Saved parsed report to {out}")


@app.command()
def suggest(path: Path, out: Optional[Path] = typer.Option(None, help="Write suggestions JSON here")):
    """Generate suggestions (heuristic or LLM-backed) and show prioritized list."""
    report = _load(path)
    generator = SuggestionGenerator(report)
    suggestions = generator.generate()
    prioritized = Prioritizer(report).score(suggestions)

    table = Table(title="Suggestions", show_lines=True)
    table.add_column("Target", style="cyan", overflow="fold")
    table.add_column("Priority", style="magenta")
    table.add_column("Difficulty", style="yellow")
    table.add_column("Score", style="green")
    table.add_column("Suggestion", style="white", overflow="fold")
    for s in prioritized:
        table.add_row(
            s.target_bin,
            s.priority,
            s.difficulty,
            f"{(s.priority_score or 0):.2f}",
            s.suggestion,
        )
    console.print(table)

    output = {"suggestions": [s.model_dump() for s in prioritized]}
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(output, indent=2))
        console.print(f"[green]Saved suggestions to {out}")


@app.command()
def predict(path: Path):
    """Predict closure time/probability using current report and suggestions."""
    report = _load(path)
    generator = SuggestionGenerator(report)
    suggestions = Prioritizer(report).score(generator.generate())
    prediction = ClosurePredictor(report).predict(suggestions)
    print(prediction.model_dump_json(indent=2))


@app.command()
def demo(path: Path = typer.Option(Path("examples/sample_report.txt"), help="Report to parse for demo")):
    """Show a quick end-to-end demo summary."""
    report = _load(path)
    generator = SuggestionGenerator(report)
    prioritized = Prioritizer(report).score(generator.generate())
    prediction = ClosurePredictor(report).predict(prioritized)

    console.rule("Coverage Summary")
    console.print(f"Design: {report.design}")
    console.print(f"Overall: {report.overall_coverage}%")
    console.print(f"Uncovered bins: {len(report.uncovered_bins)} + cross {sum(len(c.uncovered) for c in report.cross_coverage)}")
    console.rule("Top Suggestions")
    for s in prioritized[:5]:
        console.print(f"[cyan]{s.target_bin}[/cyan] | priority {s.priority} | score {(s.priority_score or 0):.2f}")
        console.print(f"  {s.suggestion}")
    console.rule("Prediction")
    console.print(prediction.model_dump_json(indent=2))


if __name__ == "__main__":
    app()

