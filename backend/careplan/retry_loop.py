"""generate_with_retry_loop() — pure Python, no framework.

This is the generic "generate -> check -> feed hallucinations back -> retry"
skeleton. It does NOT decide what counts as a hallucination — that's
injected via `check_fn`, so you can plug in whatever detector you trust
today (a keyword heuristic, your ClaimAnnotation review results) without
this loop's logic caring which one. See the conversation history for why an
automated LLM-judge isn't wired in by default: it just moves the "who
verifies the verifier" problem, and isn't worth the cost at this project's
current scale.
"""
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class Hallucination:
    claim: str
    reason: str


@dataclass
class GenerationAttempt:
    round_number: int
    output_text: str
    hallucinations: list[Hallucination]
    cost_usd: float


@dataclass
class RetryLoopResult:
    final_output: str
    success: bool  # True only if the final round had zero detected hallucinations
    attempts: list[GenerationAttempt]
    total_cost_usd: float
    decision_log: list[str] = field(default_factory=list)


def generate_with_retry_loop(
    prompt: str,
    generate_fn: Callable[[str], tuple[str, float]],
    check_fn: Callable[[str], list[Hallucination]],
    max_retries: int = 2,
) -> RetryLoopResult:
    """
    generate_fn(prompt) -> (output_text, cost_usd)  — your actual LLM call
    check_fn(output_text) -> list[Hallucination]      — your hallucination detector, [] = clean

    Runs 1 initial attempt + up to `max_retries` retries (3 calls total by
    default). Stops early the moment a round comes back clean.
    """
    attempts: list[GenerationAttempt] = []
    decision_log: list[str] = []
    total_cost = 0.0
    current_prompt = prompt
    previous_count = None

    for round_number in range(1, max_retries + 2):
        output_text, cost = generate_fn(current_prompt)
        hallucinations = check_fn(output_text)
        total_cost += cost

        attempts.append(GenerationAttempt(round_number, output_text, hallucinations, cost))

        count = len(hallucinations)
        if previous_count is None:
            trend = ""
        elif count < previous_count:
            trend = f" (down from {previous_count}, improved)"
        elif count > previous_count:
            trend = f" (up from {previous_count}, worse)"
        else:
            trend = f" (unchanged from {previous_count})"

        decision_log.append(
            f"round {round_number}: hallucinations={count}{trend} | "
            f"cost=${cost:.4f} | running_total=${total_cost:.4f}"
        )

        if count == 0:
            decision_log.append(f"=> stopping: round {round_number} came back clean")
            return RetryLoopResult(output_text, True, attempts, total_cost, decision_log)

        if round_number == max_retries + 1:
            decision_log.append(
                f"=> stopping: hit max_retries={max_retries}, "
                f"{count} hallucination(s) still unresolved"
            )
            return RetryLoopResult(output_text, False, attempts, total_cost, decision_log)

        feedback = "\n".join(f"- {h.claim} — {h.reason}" for h in hallucinations)
        current_prompt = (
            f"{prompt}\n\n"
            f"Your previous response made the following unsupported claims. "
            f"Correct them, and state only what the reference material actually supports:\n{feedback}"
        )
        previous_count = count

    raise AssertionError("unreachable")  # loop always returns before exhausting the range
