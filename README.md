# Assignment-2-Verification-Coverage-Analyzer-with-LLM-Integration

# Verification Coverage Analyzer

An intelligent agent that parses functional coverage reports, identifies uncovered bins, generates targeted test suggestions using LLM, prioritizes them, and predicts coverage closure metrics.

---

## 🚀 Project Setup

### Prerequisites
- Python 3.9 or higher
- pip package manager

### Installation Steps

1. **Clone/Navigate to the project directory**
   ```bash
   cd /Users/vinayakpc/Desktop/assignment
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Set up API keys (Optional - for LLM features)**
   ```bash
   source setup_api_key.sh
   ```
   Or manually:
   ```bash
   export OPENAI_API_KEY="sk-proj-your-key-here"
   export COVERAGE_LLM_PROVIDER="openai"
   ```
   > **Note**: The system works without API keys using heuristic fallbacks, but LLM integration provides better suggestions.

4. **Install package in editable mode (Optional)**
   ```bash
   pip install -e .
   ```
   Or use `PYTHONPATH=src` prefix for commands.

---

## 🛠️ Tech Stack

### Core Technologies
- **Python 3.9+** - Programming language
- **Pydantic 2.7.1** - Data validation and models
- **Typer 0.12.3** - CLI framework
- **Rich 13.7.1** - Terminal formatting and tables

### LLM Integration
- **OpenAI 1.23.6** - GPT-4o-mini for test suggestions
- **Anthropic 0.25.4** - Claude 3.5 Sonnet alternative
- **httpx 0.27.0** - HTTP client for API calls

### Web Interface
- **Streamlit 1.33.0** - Interactive web UI

### Utilities
- **python-dotenv 1.0.1** - Environment variable management

### Architecture Patterns
- **Regex-based parsing** - Pattern matching for report extraction
- **State machine parser** - Line-by-line parsing with context tracking
- **Heuristic fallbacks** - Local suggestions when LLM unavailable
- **Pydantic models** - Type-safe data structures

---

## 📋 Part-Wise Running Steps

### Part 1: Coverage Report Parser

**Command:**
```bash
PYTHONPATH=src python3 -m coverage_analyzer.cli parse examples/sample_report.txt
```

**What it does:**
- Parses coverage report text file
- Extracts design name, overall coverage, covergroups, coverpoints, bins, and cross-coverage
- Outputs structured JSON with all parsed data

**Example Output:**
```json
{
  "design": "dma_controller",
  "overall_coverage": 54.84,
  "covergroups": [
    {
      "name": "cg_transfer_size",
      "coverage": 75.0,
      "coverpoints": [
        {
          "name": "cp_size",
          "bins": [
            {
              "name": "small",
              "range": "[0:255]",
              "hits": 1523,
              "covered": true
            },
            {
              "name": "max",
              "range": "[4096]",
              "hits": 0,
              "covered": false
            }
          ]
        }
      ]
    }
  ],
  "cross_coverage": [...],
  "uncovered_bins": [...]
}
```

**How it's solved:**
- Uses regex patterns to identify key sections (design, coverage percentages, bins)
- Implements state machine to track current covergroup/coverpoint context
- Automatically identifies uncovered bins
- Returns Pydantic models for type safety

**Save parsed output:**
```bash
PYTHONPATH=src python3 -m coverage_analyzer.cli parse examples/sample_report.txt --out parsed_data/sample_parsed.json
```

---

### Part 2: LLM-Based Test Suggestions

**Command:**
```bash
PYTHONPATH=src python3 -m coverage_analyzer.cli suggest examples/sample_report.txt --out examples/sample_output.json
```

**What it does:**
- Generates natural-language test suggestions for each uncovered bin
- Uses LLM (OpenAI/Anthropic) for intelligent suggestions
- Falls back to heuristic-based suggestions if no API key

**Example Output:**
```
                                  Suggestions                                   
┏━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━┓
┃ Target                ┃ Priority ┃ Difficulty ┃ Score ┃ Suggestion           ┃
┡━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━┩
│ cross_size_burst.medi │ medium   │ easy       │ 0.80  │ Set burst type to    │
│ um, fixed             │          │            │       │ MEDIUM, FIXED mode   │
│                       │          │            │       │ (register offset     │
│                       │          │            │       │ 0x04, value 0x3)...  │
├───────────────────────┼──────────┼────────────┼───────┼──────────────────────┤
│ cross_size_burst.larg │ medium   │ easy       │ 0.80  │ Set burst type to    │
│ e, incr               │          │            │       │ LARGE, INCR mode...  │
└───────────────────────┴──────────┴────────────┴───────┴──────────────────────┘
```

The JSON output file contains detailed suggestions with test outlines:
```json
{
  "suggestions": [
    {
      "target_bin": "cross_size_burst.medium, fixed",
      "priority": "medium",
      "difficulty": "easy",
      "priority_score": 0.8,
      "suggestion": "Set burst type to MEDIUM, FIXED mode...",
      "test_outline": [
        "1. Configure DMA channel 0...",
        "2. Set source address...",
        "3. Set transfer length...",
        "4. Verify address sequence..."
      ],
      "reasoning": "Basic burst type coverage...",
      "dependencies": []
    }
  ]
}
```

**How it's solved:**
- **LLM Integration**: Sends prompts with design context, uncovered bin details, and covered examples for pattern analysis
- **Prompt Engineering**: Includes covered bins as examples to help LLM understand patterns
- **Heuristic Fallback**: Keyword-based pattern matching (e.g., "wrap" → wrap burst tests, "timeout" → timeout scenarios)
- **Context Building**: Analyzes related covered bins to generate targeted suggestions
- Outputs structured JSON with suggestion, reasoning, test outline, difficulty, and dependencies

---

### Part 3: Prioritization Algorithm

**Command:**
```bash
# Prioritization is automatically included in Part 2 output
# Verify with:
cat examples/sample_output.json | python3 -c "import json,sys; d=json.load(sys.stdin); [print(f\"{s['target_bin']}: {s['priority_score']:.3f}\") for s in sorted(d['suggestions'], key=lambda x: x['priority_score'], reverse=True)[:5]]"
```

**What it does:**
- Scores and prioritizes test suggestions
- Sorts suggestions by priority score (highest first)

**Example Output:**
The suggestions table (shown in Part 2) is automatically sorted by priority score. You can verify top scores:
```bash
$ cat examples/sample_output.json | python3 -c "import json,sys; d=json.load(sys.stdin); [print(f\"{s['target_bin']}: {s['priority_score']:.3f}\") for s in sorted(d['suggestions'], key=lambda x: x['priority_score'], reverse=True)[:5]]"

cross_size_burst.medium, fixed: 0.800
cross_size_burst.large, incr: 0.800
cross_size_burst.large, fixed: 0.800
cg_error_scenarios.cp_error_recovery.retry_success: 0.720
cg_error_scenarios.cp_error_recovery.abort: 0.720
```

**How it's solved:**
- **Formula**: `Priority Score = (Coverage Impact × 0.4) + (Inverse Difficulty × 0.3) + (Dependency Score × 0.3)`
- **Coverage Impact**: Calculates gap in coverage (1.0 - current_coverage/100) - higher gap = higher impact
- **Inverse Difficulty**: Easy=1.0, Medium=0.5, Hard=0.33
- **Dependency Score**: 1.0 if no dependencies, 0.5 if dependencies exist
- Bins in low-coverage groups get higher priority

---

### Part 4: Coverage Closure Prediction

**Command:**
```bash
PYTHONPATH=src python3 -m coverage_analyzer.cli predict examples/sample_report.txt
```

**What it does:**
- Predicts estimated time to closure
- Calculates closure probability
- Identifies potentially blocking bins

**Example Output:**
```json
{
  "estimated_hours_to_closure": 2.8,
  "closure_probability": 0.6,
  "blocking_bins": [
    "cg_error_scenarios.cp_error_recovery.retry_success",
    "cg_error_scenarios.cp_error_recovery.abort",
    "cg_error_scenarios.cp_error_type.decode_error",
    "cg_error_scenarios.cp_error_type.timeout",
    "cross_size_burst.small, wrap",
    "cross_size_burst.medium, wrap",
    "cross_size_burst.large, wrap",
    "cg_channel_arbitration.cp_active_channels.all_eight",
    "cg_transfer_size.cp_burst_type.wrap"
  ]
}
```

**How it's solved:**
- **Time Estimation**: `Time = uncovered_bins_count / velocity` (default velocity: 5 bins/hour)
- **Probability Calculation**: 
  - Few bins (<5): 90% probability
  - Medium (5-14): 75% probability
  - Many (15+): 60% probability
  - Hard bins reduce probability by 15%
- **Blocking Detection**: Identifies bins marked as "hard" or with dependencies as potentially blocking

---

## 🎯 Complete Demo (All Parts)

**Run end-to-end demo:**
```bash
PYTHONPATH=src python3 -m coverage_analyzer.cli demo --path examples/sample_report.txt
```

**Example Output:**
```
─────────────────────────────── Coverage Summary ───────────────────────────────
Design: dma_controller
Overall: 54.84%
Uncovered bins: 8 + cross 6
─────────────────────────────── Top Suggestions ────────────────────────────────
cross_size_burst.medium, fixed | priority medium | score 0.80
  Set burst type to MEDIUM, FIXED mode (register offset 0x04, value 0x3) and run
a minimal transfer. Configure DMA channel 0 with source address 0x10000000...
cross_size_burst.large, incr | priority medium | score 0.80
  Set burst type to LARGE, INCR mode (register offset 0x04, value 0x1) and run a
minimal transfer. Configure DMA channel 0 with source address 0x10000000...
────────────────────────────────── Prediction ──────────────────────────────────
{
  "estimated_hours_to_closure": 2.8,
  "closure_probability": 0.6,
  "blocking_bins": [...]
}
```

This runs all 4 parts and displays:
- Coverage summary
- Top 5 prioritized suggestions
- Closure prediction

---

## 🌐 Web UI

**Launch Streamlit interface:**
```bash
PYTHONPATH=src streamlit run src/coverage_analyzer/web.py
```

Then open: http://localhost:8501

The web UI provides:
- Interactive report upload
- Visual display of all 4 parts
- Real-time suggestion generation
- Prioritized results table

---

## 📁 Project Structure

```
assignment/
├── src/coverage_analyzer/
│   ├── parser.py          # Part 1: Report parsing
│   ├── suggester.py       # Part 2: LLM suggestions
│   ├── prioritizer.py     # Part 3: Prioritization
│   ├── predictor.py       # Part 4: Closure prediction
│   ├── models.py          # Pydantic data models
│   ├── cli.py             # CLI interface
│   └── web.py             # Streamlit web UI
├── examples/              # Sample reports and outputs
├── parsed_data/          # Parsed JSON outputs
├── requirements.txt       # Python dependencies
└── README.md             # This file
```


## 🎓 Summary

This project implements a complete coverage analysis pipeline:
1. **Parser** extracts structured data from text reports using regex and state machines
2. **Suggester** generates intelligent test suggestions using LLM with heuristic fallbacks
3. **Prioritizer** scores suggestions using coverage impact, difficulty, and dependencies
4. **Predictor** estimates closure time and probability based on uncovered bins

All parts work together seamlessly through the CLI or web interface, providing a comprehensive solution for verification coverage analysis.
