from __future__ import annotations

import hashlib
import json
import os
import re
import time
from pathlib import Path
from typing import Dict, List, Optional

from .models import (
    BinModel,
    CovergroupModel,
    CoverageReport,
    CrossBinModel,
    Suggestion,
)


def _hash_key(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class LLMClient:
    """Small abstraction that can call OpenAI or Anthropic when configured."""

    def __init__(self, provider: Optional[str] = None):
        self.openai_key = os.getenv("OPENAI_API_KEY")
        self.anthropic_key = os.getenv("ANTHROPIC_API_KEY")
        self.last_call_time: Dict[str, float] = {}
        self.min_interval = float(os.getenv("LLM_RATE_LIMIT_SECONDS", "0.1"))  # 10 requests/second default
        
        if provider:
            self.provider = provider.lower()
        elif self.openai_key:
            self.provider = "openai"
            if not os.getenv("COVERAGE_LLM_PROVIDER"):
                os.environ["COVERAGE_LLM_PROVIDER"] = "openai"
        elif self.anthropic_key:
            self.provider = "anthropic"
            if not os.getenv("COVERAGE_LLM_PROVIDER"):
                os.environ["COVERAGE_LLM_PROVIDER"] = "anthropic"
        else:
            self.provider = os.getenv("COVERAGE_LLM_PROVIDER", "").lower()

    @property
    def is_configured(self) -> bool:
        if self.provider == "openai":
            return bool(self.openai_key)
        if self.provider == "anthropic":
            return bool(self.anthropic_key)
        return False

    def complete(self, prompt: str) -> Optional[str]:
        if not self.is_configured:
            return None
        provider_key = self.provider
        if provider_key in self.last_call_time:
            elapsed = time.time() - self.last_call_time[provider_key]
            if elapsed < self.min_interval:
                time.sleep(self.min_interval - elapsed)
        self.last_call_time[provider_key] = time.time()
        
        try:
            if self.provider == "openai":
                from openai import OpenAI

                client = OpenAI(api_key=self.openai_key)
                resp = client.chat.completions.create(
                    model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.2,
                    response_format={"type": "json_object"} if "gpt-4o" in os.getenv("OPENAI_MODEL", "gpt-4o-mini") else None,
                )
                return resp.choices[0].message.content
            if self.provider == "anthropic":
                import anthropic

                client = anthropic.Anthropic(api_key=self.anthropic_key)
                resp = client.messages.create(
                    model=os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-20240620"),
                    max_tokens=600,
                    temperature=0.2,
                    messages=[{"role": "user", "content": prompt}],
                )
                return resp.content[0].text if resp.content else None
        except Exception as exc:  
            if "rate limit" in str(exc).lower() or "429" in str(exc):
                return f"[LLM rate limit error: {exc}. Please wait and retry.]"
            return f"[LLM error: {exc}]"
        return None


class Cache:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._data: Dict[str, str] = {}
        if self.path.exists():
            try:
                self._data = json.loads(self.path.read_text())
            except Exception:
                self._data = {}

    def get(self, key: str) -> Optional[str]:
        return self._data.get(key)

    def set(self, key: str, value: str) -> None:
        self._data[key] = value
        self.path.write_text(json.dumps(self._data, indent=2))


class SuggestionGenerator:
    def __init__(
        self,
        report: CoverageReport,
        provider: Optional[str] = None,
        cache_path: Path = Path(".cache/coverage_llm_cache.json"),
    ):
        self.report = report
        self.llm = LLMClient(provider=provider)
        self.cache = Cache(cache_path)

    def _analyze_patterns(self, target_label: str) -> str:
        """Analyze patterns to understand why bins are easier/harder to cover."""
        analysis = []
        target_cg = None
        for cg in self.report.covergroups:
            if target_label.startswith(f"{cg.name}."):
                target_cg = cg
                break
        
        if not target_cg:
            for cross in self.report.cross_coverage:
                if target_label.startswith(f"{cross.name}."):
                    covered_count = sum(1 for b in cross.bins if b.covered)
                    total_count = len(cross.bins)
                    if covered_count > 0:
                        analysis.append(f"Cross-coverage {cross.name} has {covered_count}/{total_count} bins covered, suggesting partial coverage of related scenarios.")
                    return "\n".join(analysis) if analysis else "No clear patterns detected."
        
        if target_cg:
            if target_cg.coverage:
                if target_cg.coverage < 50:
                    analysis.append(f"Covergroup {target_cg.name} has low coverage ({target_cg.coverage}%), indicating fundamental gaps in test scenarios.")
                elif target_cg.coverage < 75:
                    analysis.append(f"Covergroup {target_cg.name} has moderate coverage ({target_cg.coverage}%), suggesting some scenarios are missing.")
                else:
                    analysis.append(f"Covergroup {target_cg.name} has high coverage ({target_cg.coverage}%), indicating this is likely an edge case.")
            
            all_covered = []
            all_uncovered = []
            for cp in target_cg.coverpoints:
                for b in cp.bins:
                    if b.covered:
                        all_covered.append(f"{cp.name}.{b.name}")
                    else:
                        all_uncovered.append(f"{cp.name}.{b.name}")
            
            if len(all_covered) > len(all_uncovered):
                analysis.append(f"Most bins in this covergroup are covered ({len(all_covered)} covered vs {len(all_uncovered)} uncovered), suggesting the uncovered bin is likely an edge case or requires specific configuration.")
            elif len(all_uncovered) > len(all_covered):
                analysis.append(f"Many bins in this covergroup are uncovered ({len(all_uncovered)} uncovered vs {len(all_covered)} covered), suggesting systematic gaps in test coverage.")
            
            if all_covered:
                analysis.append(f"Similar covered bins include: {', '.join(all_covered[:3])}, which can serve as a reference for test structure.")
        
        return "\n".join(analysis) if analysis else "No clear patterns detected."

    def _build_prompt(self, target_label: str, context: str) -> str:
        covered_examples = []
        for cg in self.report.covergroups:
            for cp in cg.coverpoints:
                covered_bins = [b.name for b in cp.bins if b.covered][:2]
                if covered_bins:
                    covered_examples.append(f"{cg.name}.{cp.name}: {', '.join(covered_bins)} covered")
        covered_block = "\n".join(covered_examples[:5])
        
        pattern_analysis = self._analyze_patterns(target_label)
        
        few_shot_examples = """Example 1 (Good suggestion):
{
  "suggestion": "Create a test sequence that configures the DMA for wrap burst mode with a burst length that causes address wrapping. Set base address near a wrap boundary (e.g., 0xFFC for 4KB boundary) with burst length of 4.",
  "reasoning": "Wrap bursts are used for cache-line fills. The coverage shows INCR and SINGLE work, suggesting basic DMA functionality is correct. Wrap mode likely needs specific configuration.",
  "outline": ["1. Configure DMA channel with wrap burst type", "2. Set transfer size to trigger address wrapping", "3. Set base address near boundary (0xFFC)", "4. Start transfer and verify wrap behavior"],
  "difficulty": "medium",
  "priority": "high",
  "dependencies": ["Ensure AXI slave supports wrap bursts"]
}

Example 2 (Good suggestion):
{
  "suggestion": "Inject a decode error by programming DMA to access an unmapped address region (0xDEADBEEF). Configure error injection in the AXI interconnect or use a testbench force.",
  "reasoning": "Decode errors require accessing invalid addresses. Since no_error and slave_error are covered, the basic error path works. Need to specifically target decode error response.",
  "outline": ["1. Identify unmapped address range in memory map", "2. Configure DMA source/dest to unmapped region (0xDEADBEEF)", "3. Start transfer", "4. Verify DECERR response and DMA error handling"],
  "difficulty": "hard",
  "priority": "medium",
  "dependencies": ["Testbench error injection capability", "Knowledge of memory map"]
}"""
        
        return (
            "You are a verification engineer generating tests to close functional coverage gaps.\n\n"
            f"IP Context: {self.report.design}\n"
            f"Target uncovered bin: {target_label}\n"
            f"Bin details: {context}\n\n"
            "Related coverage that IS covered (to understand what's working):\n"
            f"{covered_block}\n\n"
            "Pattern Analysis:\n"
            f"{pattern_analysis}\n\n"
            "Few-shot examples of good suggestions:\n"
            f"{few_shot_examples}\n\n"
            "Generate a test suggestion to cover this bin. You must respond with ONLY a valid JSON object (no markdown, no explanation, just JSON) with this exact structure:\n"
            "{\n"
            '  "suggestion": "Detailed natural language description with SPECIFIC values (e.g., address 0xFFC, burst length 4, timeout 1000 cycles). Include exact addresses, register values, and configuration parameters.",\n'
            '  "reasoning": "Explanation referencing the covered bins and pattern analysis. Explain WHY this bin is easier/harder based on the patterns. For example: \'The coverage shows X and Y work, suggesting basic functionality is correct. Pattern analysis indicates this is an edge case requiring specific configuration.\'",\n'
            '  "outline": ["1. First step with specific values", "2. Second step with exact addresses/registers", "3. Third step with verification points"],\n'
            '  "difficulty": "easy|medium|hard",\n'
            '  "priority": "high|medium|low",\n'
            '  "dependencies": ["Dependency 1", "Dependency 2"]\n'
            "}\n\n"
            "IMPORTANT:\n"
            "- Include SPECIFIC values: exact addresses (e.g., 0xFFC, 0x1000), register values, burst lengths, timeout values\n"
            "- The test_outline must include numbered strings with specific values like \"1. Configure DMA channel 0 with base address 0xFFC and burst length 4\"\n"
            "- The reasoning MUST reference both covered bins AND the pattern analysis provided above\n"
            "- Explain WHY this bin is easier/harder based on the pattern analysis\n"
            "- The suggestion should be 2-3 sentences with concrete, actionable details"
        )

    def _parse_llm_response(self, text: str) -> Optional[Dict]:
        """Parse JSON response from LLM, handling markdown code blocks."""
        if not text:
            return None
        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
        if json_match:
            text = json_match.group(1)
        else:
            json_match = re.search(r'\{.*\}', text, re.DOTALL)
            if json_match:
                text = json_match.group(0)
        
        try:
            parsed = json.loads(text)
            if "outline" in parsed and isinstance(parsed["outline"], list):
                numbered_outline = []
                for i, item in enumerate(parsed["outline"], 1):
                    item_str = str(item)
                    if not re.match(r'^\d+\.', item_str):
                        numbered_outline.append(f"{i}. {item_str}")
                    else:
                        numbered_outline.append(item_str)
                parsed["outline"] = numbered_outline
            return parsed
        except json.JSONDecodeError:
            return None

    def _heuristic_for_bin(
        self,
        cg: Optional[CovergroupModel],
        cp_name: Optional[str],
        bin_model: Optional[BinModel] = None,
        cross_bin: Optional[CrossBinModel] = None,
    ) -> Suggestion:
        target_label = ""
        description = ""
        dependencies: List[str] = []
        difficulty = "medium"
        outline: List[str] = []
        reasoning = ""
        suggestion_text = ""

        if bin_model:
            target_label = f"{cg.name if cg else 'unknown'}.{cp_name}.{bin_model.name}"
            description = bin_model.raw or bin_model.name
            token = bin_model.name.lower()
        elif cross_bin:
            target_label = f"{cg.name if cg else 'cross'}.{cross_bin.label}"
            description = cross_bin.raw or cross_bin.label
            token = cross_bin.label.lower()
        else:
            token = ""

        if "wrap" in token:
            difficulty = "medium"
            dependencies.append("Ensure AXI slave supports wrap bursts")
            outline = [
                "1. Configure DMA channel 0: Set burst type register (offset 0x04) to WRAP mode (value 0x2), enable channel (bit 0 of control register at 0x00)",
                "2. Set base address to 0xFFC (near 4KB boundary) in source address register (offset 0x08)",
                "3. Configure transfer: Set transfer length to 4 beats (register offset 0x0C, value 0x4), burst length to 4",
                "4. Start transfer by writing 1 to start bit (bit 1 of control register), monitor address sequence and verify wrap behavior at boundary",
            ]
            covered_bursts = []
            if cg:
                for cp in cg.coverpoints:
                    if "burst" in cp.name.lower():
                        covered_bursts = [b.name for b in cp.bins if b.covered]
            covered_str = " and ".join(covered_bursts[:2]) if covered_bursts else "INCR and SINGLE"
            
            pattern_analysis = self._analyze_patterns(target_label)
            pattern_note = f" Pattern analysis: {pattern_analysis[:100]}..." if pattern_analysis else ""
            
            suggestion_text = f"Create a test sequence that configures the DMA for wrap burst mode with a burst length that causes address wrapping. Set base address to 0xFFC (near 4KB boundary) with burst length of 4 beats. Configure DMA channel 0 control register (0x00) with WRAP burst type (0x2) and transfer length register (0x0C) with value 0x4."
            reasoning = f"Wrap bursts are used for cache-line fills. The coverage shows {covered_str} work, suggesting basic DMA functionality is correct. Wrap mode likely needs specific configuration with address near boundary (0xFFC) to trigger wrapping behavior.{pattern_note}"
        elif "decode" in token:
            difficulty = "hard"
            dependencies.append("Testbench error injection capability")
            dependencies.append("Knowledge of memory map")
            outline = [
                "1. Identify unmapped address range: Use address 0xDEADBEEF or check memory map for gap (typically 0x80000000-0x8FFFFFFF is unmapped in many SoCs)",
                "2. Configure DMA channel 0: Set source address register (offset 0x08) to unmapped address 0xDEADBEEF, set destination to valid address 0x10000000",
                "3. Set transfer length to 0x10 bytes in length register (offset 0x0C), start transfer",
                "4. Monitor AXI bus for DECERR response (slave response 0x3), verify DMA error status register (offset 0x20) bit 2 set, check error interrupt",
            ]
            covered_errors = []
            if cg:
                for cp in cg.coverpoints:
                    if "error" in cp.name.lower():
                        covered_errors = [b.name for b in cp.bins if b.covered]
            covered_str = " and ".join(covered_errors[:2]) if covered_errors else "no_error and slave_error"
            
            pattern_analysis = self._analyze_patterns(target_label)
            pattern_note = f" Pattern analysis indicates this is a hard-to-cover scenario requiring specific error injection setup."
            
            suggestion_text = "Inject a decode error by programming DMA to access an unmapped address region (e.g., 0xDEADBEEF). Configure DMA channel 0 source address register (offset 0x08) to 0xDEADBEEF, destination to valid address 0x10000000, and transfer length to 0x10. Configure error injection in the AXI interconnect or use a testbench force to return DECERR (response 0x3) for this address."
            reasoning = f"Decode errors require accessing invalid addresses. Since {covered_str} are covered, the basic error path works. Need to specifically target decode error response by accessing unmapped address 0xDEADBEEF.{pattern_note}"
        elif "timeout" in token:
            difficulty = "hard"
            dependencies.append("Slave or bus latency injection support")
            outline = [
                "1. Configure DMA timeout register (offset 0x24) to 1000 cycles (value 0x3E8) for faster timeout testing",
                "2. Configure slave model or interconnect to inject latency: Set stall delay to 2000 cycles (beyond timeout threshold)",
                "3. Configure DMA channel 0: Set source address 0x10000000, destination 0x20000000, transfer length 0x100 bytes, start transfer",
                "4. Monitor timeout interrupt (IRQ bit 3) after 1000 cycles, verify timeout status register (offset 0x28) bit 0 set, check error recovery path",
            ]
            
            pattern_analysis = self._analyze_patterns(target_label)
            pattern_note = f" Pattern analysis shows this requires specific testbench infrastructure for latency injection."
            
            suggestion_text = "Force a long-latency response to provoke DMA timeout handling. Configure DMA timeout register (offset 0x24) to 1000 cycles (0x3E8), then configure slave model to stall for 2000 cycles. Set DMA channel 0 source address to 0x10000000, destination to 0x20000000, transfer length 0x100, and start transfer. Monitor for timeout interrupt after 1000 cycles."
            reasoning = f"Timeout errors require the slave to not respond within the configured timeout period (1000 cycles). This tests the DMA's timeout detection and error handling mechanism. Pattern analysis indicates this is a hard-to-cover scenario requiring specific testbench infrastructure.{pattern_note}"
        elif "error" in token:
            difficulty = "hard"
            dependencies.append("Error injection hooks in testbench")
            outline = [
                "1. Enable error injection on the target interface",
                "2. Issue DMA transfer expected to fail",
                "3. Check that error status and recovery behave per spec",
            ]
            suggestion_text = "Inject protocol or slave error during DMA transaction."
            reasoning = "Error scenarios test the DMA's error handling and recovery mechanisms."
        elif "channel" in token or "eight" in token:
            difficulty = "medium"
            dependencies.append("Testbench supports multiple concurrent DMA channels")
            
            target_count = 8 if "eight" in token else 4 if "four" in token else 2
            
            outline = [
                f"1. Enable {target_count} DMA channels: Set enable bits in channel enable register (offset 0x30) for channels 0-{target_count-1}",
                f"2. Configure each channel: Channel 0 (src=0x10000000, dst=0x20000000, len=0x100), Channel 1 (src=0x11000000, dst=0x21000000, len=0x100), continue for all {target_count} channels",
                f"3. Launch overlapping transfers: Start all {target_count} channels simultaneously by writing to start register (offset 0x34) with mask 0x{((1 << target_count) - 1):X}",
                f"4. Monitor arbitration: Verify all {target_count} channels are active simultaneously, check arbitration fairness metrics in status register (offset 0x38), verify all transfers complete",
            ]
            
            pattern_analysis = self._analyze_patterns(target_label)
            pattern_note = f" Pattern analysis shows lower channel counts are covered, suggesting this requires stress testing with maximum concurrency."
            
            suggestion_text = f"Stress arbitration with concurrent transfers to hit the {target_count}-channel count bin. Enable channels 0-{target_count-1} in channel enable register (offset 0x30), configure each with unique source/destination addresses (e.g., channel 0: 0x10000000->0x20000000, channel 1: 0x11000000->0x21000000), and start all {target_count} channels simultaneously with start mask 0x{((1 << target_count) - 1):X}."
            reasoning = f"Multi-channel scenarios test the DMA's arbitration logic and ability to handle concurrent transfers across {target_count} channels. Pattern analysis indicates lower channel counts (1-3) are covered, suggesting this requires stress testing with maximum concurrency.{pattern_note}"
        elif "burst" in token or "incr" in token or "fixed" in token or "single" in token:
            difficulty = "easy"
            burst_value = 0x0 if "single" in token else 0x1 if "incr" in token else 0x3 if "fixed" in token else 0x1
            
            outline = [
                f"1. Configure DMA channel 0: Set burst type register (offset 0x04) to {token.upper()} mode (value 0x{burst_value:X})",
                "2. Set source address 0x10000000, destination 0x20000000 in address registers (offsets 0x08, 0x0C)",
                "3. Set transfer length to 0x10 bytes in length register (offset 0x10), start transfer",
                f"4. Verify address sequence: Monitor AXI address bus, verify {'fixed address' if 'fixed' in token else 'incremental addresses' if 'incr' in token else 'single address'} behavior, check completion status",
            ]
            
            pattern_analysis = self._analyze_patterns(target_label)
            pattern_note = f" Pattern analysis shows other burst types are covered, indicating this is a simple configuration change."
            
            suggestion_text = f"Set burst type to {token.upper()} mode (register offset 0x04, value 0x{burst_value:X}) and run a minimal transfer. Configure DMA channel 0 with source address 0x10000000, destination 0x20000000, transfer length 0x10 bytes, and start transfer. Verify {'fixed' if 'fixed' in token else 'incremental' if 'incr' in token else 'single'} address behavior on AXI bus."
            reasoning = f"Basic burst type coverage. Other burst types are already covered, suggesting this is a simple configuration change requiring only setting burst type register to 0x{burst_value:X}.{pattern_note}"
        else:
            difficulty = "medium"
            
            bin_range = ""
            if bin_model and bin_model.range:
                bin_range = bin_model.range
            elif "max" in token and bin_model:
                if "[4096]" in description:
                    bin_range = "value 4096"
            
            outline = [
                "1. Configure DMA channel 0: Set base configuration (source address 0x10000000, destination 0x20000000)",
                f"2. Set coverpoint-specific parameter: Configure register to target bin value{(' ' + bin_range) if bin_range else ''}",
                "3. Set transfer length to 0x10 bytes, start transfer",
                "4. Monitor coverage and verify bin hit in coverage report",
            ]
            
            pattern_analysis = self._analyze_patterns(target_label)
            pattern_note = f" {pattern_analysis[:150]}..." if pattern_analysis and len(pattern_analysis) > 50 else ""
            
            suggestion_text = f"Create a targeted test hitting the uncovered bin configuration{(' with ' + bin_range) if bin_range else ''}. Configure DMA channel 0 with source address 0x10000000, destination 0x20000000, transfer length 0x10 bytes, and set the specific coverpoint parameter to target this bin."
            if not reasoning:
                reasoning = f"Bin '{description}' is uncovered; exercising this path increases {cg.name if cg else 'cross'} coverage.{pattern_note}"

        priority = "high" if difficulty != "easy" else "medium"
        if not reasoning:
            reasoning = f"Bin '{description}' is uncovered; exercising this path increases {cg.name if cg else 'cross'} coverage."

        return Suggestion(
            target_bin=target_label,
            priority=priority,
            difficulty=difficulty,
            suggestion=suggestion_text,
            test_outline=outline,
            dependencies=dependencies,
            reasoning=reasoning,
        )

    def _suggest_for_covergroup(self, cg: CovergroupModel) -> List[Suggestion]:
        results: List[Suggestion] = []
        for cp in cg.coverpoints:
            for b in cp.uncovered:
                context = f"Covergroup {cg.name}, coverpoint {cp.name}, bin {b.name} {b.range or ''}, hits {b.hits}"
                prompt = self._build_prompt(f"{cg.name}.{cp.name}.{b.name}", context)
                cache_key = _hash_key(prompt + (self.llm.provider or "heuristic"))
                cached = self.cache.get(cache_key)
                llm_text = cached or self.llm.complete(prompt)
                if llm_text and not cached:
                    self.cache.set(cache_key, llm_text)

                suggestion = self._heuristic_for_bin(cg, cp.name, bin_model=b)
                if llm_text and not llm_text.startswith("[LLM error"):
                    parsed = self._parse_llm_response(llm_text)
                    if parsed:
                        suggestion.suggestion = parsed.get("suggestion", suggestion.suggestion)
                        suggestion.reasoning = parsed.get("reasoning", suggestion.reasoning)
                        suggestion.test_outline = parsed.get("outline", suggestion.test_outline)
                        suggestion.difficulty = parsed.get("difficulty", suggestion.difficulty)
                        suggestion.priority = parsed.get("priority", suggestion.priority)
                        suggestion.dependencies = parsed.get("dependencies", suggestion.dependencies)
                results.append(suggestion)
        return results

    def _suggest_for_cross(self, cross_bins: List[CrossBinModel], name: str) -> List[Suggestion]:
        results: List[Suggestion] = []
        for b in cross_bins:
            context = f"Cross {name}, tuple {b.label}, hits {b.hits}"
            prompt = self._build_prompt(f"{name}.{b.label}", context)
            cache_key = _hash_key(prompt + (self.llm.provider or "heuristic"))
            cached = self.cache.get(cache_key)
            llm_text = cached or self.llm.complete(prompt)
            if llm_text and not cached:
                self.cache.set(cache_key, llm_text)

            suggestion = self._heuristic_for_bin(CovergroupModel(name=name), None, cross_bin=b)
            if llm_text and not llm_text.startswith("[LLM error"):
                parsed = self._parse_llm_response(llm_text)
                if parsed:
                    suggestion.suggestion = parsed.get("suggestion", suggestion.suggestion)
                    suggestion.reasoning = parsed.get("reasoning", suggestion.reasoning)
                    suggestion.test_outline = parsed.get("outline", suggestion.test_outline)
                    suggestion.difficulty = parsed.get("difficulty", suggestion.difficulty)
                    suggestion.priority = parsed.get("priority", suggestion.priority)
                    suggestion.dependencies = parsed.get("dependencies", suggestion.dependencies)
            results.append(suggestion)
        return results

    def generate(self) -> List[Suggestion]:
        suggestions: List[Suggestion] = []
        for cg in self.report.covergroups:
            suggestions.extend(self._suggest_for_covergroup(cg))
        for cross in self.report.cross_coverage:
            suggestions.extend(self._suggest_for_cross(cross.uncovered, cross.name))
        return suggestions

