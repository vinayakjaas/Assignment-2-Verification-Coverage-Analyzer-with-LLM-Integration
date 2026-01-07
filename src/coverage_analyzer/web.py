from __future__ import annotations

import json
from pathlib import Path

import streamlit as st

from coverage_analyzer.parser import parse_coverage_report
from coverage_analyzer.prioritizer import Prioritizer
from coverage_analyzer.suggester import SuggestionGenerator
from coverage_analyzer.predictor import ClosurePredictor

st.set_page_config(page_title="Coverage Analyzer", layout="wide")
st.title("Verification Coverage Analyzer")
st.markdown("**Parse coverage reports, identify holes, and generate test suggestions using LLM.**")


def load_report_from_input() -> str:
    uploaded = st.file_uploader("Upload coverage report", type=["txt", "log"])
    default_path = Path(__file__).resolve().parents[2] / "examples" / "sample_report.txt"
    default_text = default_path.read_text() if default_path.exists() else ""

    text = ""
    if uploaded is not None:
        text = uploaded.read().decode("utf-8")
    else:
        text = st.text_area("Or paste report text", value=default_text, height=300)
    return text


def render_part1_parser(report):
    """Part 1: Coverage Report Parser Results"""
    st.header("Part 1: Coverage Report Parser")
    st.markdown("**Parsed coverage data from the report**")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Design", report.design)
    with col2:
        st.metric("Overall Coverage", f"{report.overall_coverage}%")
    with col3:
        uncovered_count = len(report.uncovered_bins) + sum(len(c.uncovered) for c in report.cross_coverage)
        st.metric("Uncovered Bins", uncovered_count)
    
    st.subheader("Covergroups")
    for cg in report.covergroups:
        with st.expander(f"📊 {cg.name} — Coverage: {cg.coverage}%", expanded=False):
            for cp in cg.coverpoints:
                st.markdown(f"**Coverpoint: {cp.name}**")
                covered_bins = [b for b in cp.bins if b.covered]
                uncovered_bins = [b for b in cp.bins if not b.covered]
                
                if covered_bins:
                    st.markdown("✅ **Covered Bins:**")
                    covered_data = [
                        {"bin": f"{b.name}{b.range or ''}", "hits": b.hits, "status": "✅ Covered"}
                        for b in covered_bins
                    ]
                    st.dataframe(covered_data, hide_index=True, use_container_width=True)
                
                if uncovered_bins:
                    st.markdown("❌ **Uncovered Bins:**")
                    uncovered_data = [
                        {"bin": f"{b.name}{b.range or ''}", "hits": b.hits, "status": "❌ Uncovered"}
                        for b in uncovered_bins
                    ]
                    st.dataframe(uncovered_data, hide_index=True, use_container_width=True)
    
    if report.cross_coverage:
        st.subheader("Cross Coverage")
        for cross in report.cross_coverage:
            with st.expander(f"🔀 {cross.name} — Coverage: {cross.coverage}%", expanded=False):
                covered_cross = [b for b in cross.bins if b.covered]
                uncovered_cross = [b for b in cross.bins if not b.covered]
                
                if covered_cross:
                    st.markdown("✅ **Covered Tuples:**")
                    covered_data = [
                        {"tuple": b.label, "hits": b.hits, "status": "✅ Covered"}
                        for b in covered_cross
                    ]
                    st.dataframe(covered_data, hide_index=True, use_container_width=True)
                
                if uncovered_cross:
                    st.markdown("❌ **Uncovered Tuples:**")
                    uncovered_data = [
                        {"tuple": b.label, "hits": b.hits, "status": "❌ Uncovered"}
                        for b in uncovered_cross
                    ]
                    st.dataframe(uncovered_data, hide_index=True, use_container_width=True)
    
    st.divider()


def render_part2_suggestions(report, suggestions):
    """Part 2: LLM-Based Test Suggestion Generator"""
    st.header("Part 2: LLM-Based Test Suggestion Generator")
    st.markdown("**Natural-language test suggestions generated using LLM**")
    
    if not suggestions:
        st.warning("No suggestions generated.")
        return
    
    llm_provider = st.session_state.get('llm_provider', 'heuristic')
    if llm_provider and llm_provider != 'heuristic':
        st.success(f"✅ Using LLM: {llm_provider.upper()}")
    else:
        st.info("ℹ️ Using heuristic fallback (set OPENAI_API_KEY environment variable for LLM suggestions)")
    
    col1, col2 = st.columns(2)
    with col1:
        priority_filter = st.multiselect("Filter by Priority", ["high", "medium", "low"], default=["high", "medium", "low"])
    with col2:
        difficulty_filter = st.multiselect("Filter by Difficulty", ["easy", "medium", "hard"], default=["easy", "medium", "hard"])
    
    filtered_suggestions = [
        s for s in suggestions
        if s.priority in priority_filter and s.difficulty in difficulty_filter
    ]
    
    st.metric("Total Suggestions", len(filtered_suggestions))
    for idx, s in enumerate(filtered_suggestions, 1):
        with st.expander(f"💡 {idx}. {s.target_bin} | Priority: {s.priority} | Difficulty: {s.difficulty} | Score: {s.priority_score:.2f}", expanded=False):
            st.markdown(f"**Suggestion:**\n{s.suggestion}")
            
            st.markdown("**Test Outline:**")
            for step in s.test_outline:
                st.markdown(f"- {step}")
            
            if s.dependencies:
                st.markdown("**Dependencies:**")
                for dep in s.dependencies:
                    st.markdown(f"- {dep}")
            
            st.markdown(f"**Reasoning:**\n{s.reasoning}")
    
    st.divider()


def render_part3_prioritization(report, suggestions):
    """Part 3: Prioritization Algorithm Results"""
    st.header("Part 3: Prioritization Algorithm")
    st.markdown("**Suggestions sorted by priority score**")
    
    if not suggestions:
        st.warning("No suggestions to prioritize.")
        return
    
    with st.expander("ℹ️ Priority Score Formula", expanded=False):
        st.markdown("""
        **Priority Score = (Coverage Impact × 0.4) + (Inverse Difficulty × 0.3) + (Dependency Score × 0.3)**
        
        - **Coverage Impact**: How much overall coverage improves (0.0 to 1.0)
        - **Inverse Difficulty**: 1/difficulty (easy=1.0, medium=0.5, hard=0.33)
        - **Dependency Score**: 1.0 if no dependencies, 0.5 if dependencies exist
        """)
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        avg_score = sum(s.priority_score or 0 for s in suggestions) / len(suggestions)
        st.metric("Average Priority Score", f"{avg_score:.2f}")
    with col2:
        high_priority = sum(1 for s in suggestions if s.priority == "high")
        st.metric("High Priority", high_priority)
    with col3:
        easy_difficulty = sum(1 for s in suggestions if s.difficulty == "easy")
        st.metric("Easy Difficulty", easy_difficulty)
    with col4:
        no_deps = sum(1 for s in suggestions if not s.dependencies)
        st.metric("No Dependencies", no_deps)
    
    st.subheader("Prioritized Suggestions Table")
    rows = []
    for s in suggestions:
        rows.append(
            {
                "Rank": f"#{suggestions.index(s) + 1}",
                "Target Bin": s.target_bin,
                "Priority": s.priority,
                "Difficulty": s.difficulty,
                "Priority Score": f"{s.priority_score:.3f}",
                "Coverage Impact": f"{s.coverage_impact:.3f}" if s.coverage_impact else "N/A",
                "Dependency Score": f"{s.dependency_score:.3f}" if s.dependency_score else "N/A",
                "Dependencies": len(s.dependencies),
            }
        )
    st.dataframe(rows, hide_index=True, use_container_width=True)
    
    st.divider()


def render_part4_prediction(report, suggestions):
    """Part 4: Coverage Closure Prediction"""
    st.header("Part 4: Coverage Closure Prediction (Bonus)")
    st.markdown("**Predicts time to closure, probability, and blocking bins**")
    
    predictor = ClosurePredictor(report)
    prediction = predictor.predict(suggestions)
    
    # Key metrics
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Estimated Hours to Closure", f"{prediction.estimated_hours_to_closure:.1f}")
    with col2:
        st.metric("Closure Probability", f"{prediction.closure_probability * 100:.1f}%")
    with col3:
        st.metric("Blocking Bins", len(prediction.blocking_bins))
    
    with st.expander("📋 Detailed Prediction", expanded=True):
        st.json(json.loads(prediction.model_dump_json()))
    
    if prediction.blocking_bins:
        st.subheader("⚠️ Blocking Bins (May Require Testbench Changes)")
        st.warning("These bins may be impossible to cover without testbench infrastructure changes.")
        for bin_name in prediction.blocking_bins:
            st.markdown(f"- `{bin_name}`")
    
    st.divider()


def main():
    with st.sidebar:
        st.header("⚙️ Configuration")
        
        import os
        has_openai = bool(os.getenv("OPENAI_API_KEY"))
        has_anthropic = bool(os.getenv("ANTHROPIC_API_KEY"))
        
        if has_openai:
            default_idx = 0
            default_provider = "openai"
        elif has_anthropic:
            default_idx = 1
            default_provider = "anthropic"
        else:
            default_idx = 2
            default_provider = "heuristic"
        
        if has_openai or has_anthropic:
            st.success("✅ API key detected!")
            if has_openai:
                st.info("🔑 OpenAI API key found")
            if has_anthropic:
                st.info("🔑 Anthropic API key found")
        else:
            st.warning("⚠️ No API key found - using heuristics")
        
        llm_provider = st.selectbox(
            "LLM Provider",
            ["openai", "anthropic", "heuristic"],
            index=default_idx,
            help="Select LLM provider or use heuristics. Auto-detects if API key is set."
        )
        st.session_state['llm_provider'] = llm_provider
        
        if llm_provider != "heuristic":
            api_key = st.text_input(
                f"{llm_provider.upper()} API Key",
                value=os.getenv(f"{llm_provider.upper()}_API_KEY", ""),
                type="password",
                help=f"Enter your {llm_provider.upper()} API key (or set environment variable)"
            )
            if api_key:
                os.environ[f"{llm_provider.upper()}_API_KEY"] = api_key
                os.environ["COVERAGE_LLM_PROVIDER"] = llm_provider
    text = load_report_from_input()
    if not text.strip():
        st.info("📤 Upload or paste a coverage report to begin.")
        return

    try:
        report = parse_coverage_report(text)
    except Exception as exc:  # pragma: no cover - UI level defensive
        st.error(f"❌ Failed to parse report: {exc}")
        return

    st.success(f"✅ Successfully parsed: **{report.design}** | Overall Coverage: **{report.overall_coverage}%**")
    
    if 'suggestions' not in st.session_state or st.session_state.get('report_hash') != hash(text):
        with st.spinner("🔄 Generating suggestions..."):
            provider = None if llm_provider == "heuristic" else llm_provider
            generator = SuggestionGenerator(report, provider=provider)
            suggestions = generator.generate()
            prioritized = Prioritizer(report).score(suggestions)
            st.session_state['suggestions'] = prioritized
            st.session_state['report_hash'] = hash(text)
            st.session_state['llm_provider'] = generator.llm.provider or "heuristic"
    else:
        prioritized = st.session_state['suggestions']
    
    render_part1_parser(report)
    render_part2_suggestions(report, prioritized)
    render_part3_prioritization(report, prioritized)
    render_part4_prediction(report, prioritized)
    
    st.header("💾 Download Results")
    col1, col2 = st.columns(2)
    
    with col1:
        st.download_button(
            "📥 Download Parsed Report JSON",
            data=report.model_dump_json(indent=2),
            file_name=f"{report.design}_parsed_report.json",
            mime="application/json",
            help="Download the parsed coverage report data",
        )
    
    with col2:
        st.download_button(
            "📥 Download Suggestions JSON",
            data=json.dumps({"suggestions": [s.model_dump() for s in prioritized]}, indent=2),
            file_name=f"{report.design}_suggestions.json",
            mime="application/json",
            help="Download the test suggestions with prioritization",
        )


if __name__ == "__main__":
    main()

