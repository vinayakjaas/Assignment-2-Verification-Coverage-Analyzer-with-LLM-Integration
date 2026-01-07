#!/bin/bash
# Setup script for OpenAI API key

export OPENAI_API_KEY="sk-proj-your-key-here"
export COVERAGE_LLM_PROVIDER="openai"

echo "✅ API key configured!"
echo "Run commands with:"
echo "  PYTHONPATH=src python3 -m coverage_analyzer.cli suggest examples/sample_report.txt"

