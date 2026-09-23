"""Automated checks for the eval suite: format, dose math, keyword coverage.

What's automatable vs not (see conversation history for the full reasoning):
- Format completeness: fully mechanical, safe to automate.
- Dose accuracy: only the *arithmetic* (weight x mg/kg = stated total) is
  automatable — whether the surrounding clinical reasoning is correct still
  needs a human.
- Content coverage here is keyword presence, a coarse proxy for Recall. It
  catches a total omission (e.g. "metformin" never mentioned at all) but
  says nothing about whether what WAS said about a topic is accurate — that
  still needs the manual ClaimAnnotation workflow in evaluation.py.
"""
import re

REQUIRED_SECTIONS = ["Problem List", "Goals", "Pharmacist Interventions", "Monitoring Plan"]


def check_format(text: str, stop_reason: str = "") -> dict:
    sections_found = {s: s.lower() in text.lower() for s in REQUIRED_SECTIONS}

    numbering_issues = []
    for section in REQUIRED_SECTIONS:
        match = re.search(rf"{re.escape(section)}.*?(?=\n#{{1,2}}\s|\Z)", text, re.IGNORECASE | re.DOTALL)
        if not match:
            continue
        numbers = [int(n) for n in re.findall(r"^\s*(\d+)\.\s", match.group(), re.MULTILINE)]
        if numbers and numbers != list(range(1, len(numbers) + 1)):
            numbering_issues.append({"section": section, "numbers_found": numbers})

    # A heading string being present doesn't mean that section's content is
    # complete — if generation was cut off by the token limit, the last
    # section can be present-but-truncated. stop_reason is the reliable
    # signal for that, not text pattern-matching.
    truncated = stop_reason == "max_tokens"

    return {
        "sections_found": sections_found,
        "all_sections_present": all(sections_found.values()),
        "truncated": truncated,
        "complete": all(sections_found.values()) and not truncated,
        "numbering_issues": numbering_issues,
    }


def check_dose_math(text: str, weight_kg: float, dose_per_kg: float) -> dict:
    expected_total = round(weight_kg * dose_per_kg, 1)
    stated_values = [float(m) for m in re.findall(r"(\d+(?:\.\d+)?)\s*g\b", text)]
    match_found = any(abs(v - expected_total) < 0.5 for v in stated_values)
    return {
        "expected_total_g": expected_total,
        "stated_g_values_found": sorted(set(stated_values)),
        "match_found": match_found,
    }


def check_keyword_coverage(text: str, expected_keywords: list[str]) -> dict:
    text_lower = text.lower()
    hits = {kw: kw.lower() in text_lower for kw in expected_keywords}
    coverage_ratio = sum(hits.values()) / len(hits) if hits else None
    return {"hits": hits, "coverage_ratio": coverage_ratio}
