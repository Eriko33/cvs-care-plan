"""Run the fixed test-case suite against a given prompt version.

Usage:
    python manage.py run_eval_suite --prompt-version v3
    python manage.py run_eval_suite --prompt-version v2

Prints a per-case summary and writes the full results to
eval_results/<version>_<timestamp>.json so you can diff runs across prompt
versions later.
"""
import json
import re
from datetime import datetime
from pathlib import Path

from django.core.management.base import BaseCommand

from careplan.harness import check_dose_math, check_format, check_keyword_coverage
from careplan.llm import generate_care_plan
from careplan.test_cases import TEST_CASES

RESULTS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "eval_results"


def _parse_weight_kg(weight_str: str) -> float:
    match = re.search(r"(\d+(?:\.\d+)?)", weight_str)
    return float(match.group(1)) if match else 0.0


class Command(BaseCommand):
    help = "Run the fixed eval suite (careplan/test_cases.py) against a prompt version."

    def add_arguments(self, parser):
        parser.add_argument("--prompt-version", default=None, help="Prompt version, e.g. v2, v3. Default: config.yaml's active version.")

    def handle(self, *args, **options):
        version = options["prompt_version"]
        run_results = []

        for case in TEST_CASES:
            self.stdout.write(f"\n=== {case['name']} ===")
            max_tokens = case["data"].get("max_tokens", 8000)
            data = {k: v for k, v in case["data"].items() if k != "max_tokens"}

            result = generate_care_plan(data, version=version, max_tokens=max_tokens)
            log = result.log

            weight_kg = _parse_weight_kg(case["data"]["weight"])
            format_result = check_format(result.text, stop_reason=log.stop_reason)
            dose_result = check_dose_math(result.text, weight_kg, case["dose_per_kg"])
            coverage_result = check_keyword_coverage(result.text, case["expected_keywords"])

            case_result = {
                "case_name": case["name"],
                "prompt_version": result.prompt_version,
                "format": format_result,
                "dose_math": dose_result,
                "keyword_coverage": coverage_result,
                "tokens": {"input": log.input_tokens, "output": log.output_tokens, "max_tokens": max_tokens},
                "duration_ms": log.duration_ms,
                "stop_reason": log.stop_reason,
                "care_plan_id": log.care_plan_id,
            }
            run_results.append(case_result)

            self.stdout.write(f"  format complete: {format_result['complete']} (truncated: {format_result['truncated']})")
            if format_result["numbering_issues"]:
                self.stdout.write(f"  numbering issues: {format_result['numbering_issues']}")
            self.stdout.write(f"  dose match ({dose_result['expected_total_g']}g expected): {dose_result['match_found']}")
            self.stdout.write(f"  keyword coverage: {coverage_result['coverage_ratio']:.2f} {coverage_result['hits']}")
            self.stdout.write(
                f"  tokens: in={log.input_tokens} out={log.output_tokens}/{max_tokens} "
                f"| stop_reason={log.stop_reason} | duration={log.duration_ms}ms"
            )

        RESULTS_DIR.mkdir(exist_ok=True)
        out_path = RESULTS_DIR / f"{version or 'default'}_{datetime.now():%Y%m%d_%H%M%S}.json"
        out_path.write_text(json.dumps(run_results, indent=2), encoding="utf-8")
        self.stdout.write(self.style.SUCCESS(f"\nSaved results to {out_path}"))
