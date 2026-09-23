"""CarePlanOrchestrator — pure Python, no framework.

Wires assess_complexity() (Router) and generate_with_retry_loop() (Loop)
together. Everything that would need Django (rendering the actual prompt
template, calling the real Anthropic API) is injected as callables, so this
module stays framework-free and the whole pipeline is testable with fakes —
see the bottom of this file's tests for exactly that.
"""
from dataclasses import dataclass, field
from typing import Callable

from .complexity import assess_complexity
from .retry_loop import GenerationAttempt, Hallucination, generate_with_retry_loop


@dataclass
class OrchestratorResult:
    complexity: str
    prompt_version: str
    model: str
    final_output: str
    success: bool
    total_cost_usd: float
    attempts: list[GenerationAttempt]
    decision_log: list[str] = field(default_factory=list)


class CarePlanOrchestrator:
    def __init__(
        self,
        prompt_builder_fn: Callable[[dict, str], str],
        generate_fn_factory: Callable[[str, str], Callable[[str], tuple[str, float]]],
        check_fn: Callable[[str], list[Hallucination]],
        max_retries: int = 2,
    ):
        """
        prompt_builder_fn(patient_record, prompt_version) -> rendered prompt text
        generate_fn_factory(prompt_version, model) -> generate_fn(prompt) -> (text, cost_usd)
        check_fn(output_text) -> list[Hallucination], [] = clean
        """
        self.prompt_builder_fn = prompt_builder_fn
        self.generate_fn_factory = generate_fn_factory
        self.check_fn = check_fn
        self.max_retries = max_retries

    def process(self, patient_record: dict) -> OrchestratorResult:
        decision_log: list[str] = []

        decision_log.append("[Router] assessing complexity")
        strategy = assess_complexity(patient_record)
        decision_log.extend(f"[Router]   {line}" for line in strategy.decision_log)
        decision_log.append(
            f"[Router] => '{strategy.complexity}' strategy: "
            f"prompt_version={strategy.prompt_version}, model={strategy.model}"
        )

        decision_log.append("[Prompt] rendering prompt for this patient record")
        prompt = self.prompt_builder_fn(patient_record, strategy.prompt_version)
        decision_log.append(f"[Prompt] built with version={strategy.prompt_version} ({len(prompt)} chars)")

        decision_log.append(f"[Loop] starting generate/verify/retry (max_retries={self.max_retries})")
        generate_fn = self.generate_fn_factory(strategy.prompt_version, strategy.model)
        loop_result = generate_with_retry_loop(prompt, generate_fn, self.check_fn, max_retries=self.max_retries)
        decision_log.extend(f"[Loop]   {line}" for line in loop_result.decision_log)

        decision_log.append(
            f"[Done] success={loop_result.success} | rounds={len(loop_result.attempts)} | "
            f"total_cost=${loop_result.total_cost_usd:.4f}"
        )

        return OrchestratorResult(
            complexity=strategy.complexity,
            prompt_version=strategy.prompt_version,
            model=strategy.model,
            final_output=loop_result.final_output,
            success=loop_result.success,
            total_cost_usd=loop_result.total_cost_usd,
            attempts=loop_result.attempts,
            decision_log=decision_log,
        )
