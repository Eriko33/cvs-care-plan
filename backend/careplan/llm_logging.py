"""Recording layer for LLMCallLog — one recorder instance per LLM call.

Usage:
    with LLMCallRecorder(prompt_name="care_plan", prompt_version=v, model=m, max_tokens=3000) as rec:
        rec.record_retrieval(chunks, query=query, reference_material=ref)
        rec.record_request(rendered_prompt)
        response = client.messages.create(...)
        rec.record_response(response)
    # rec.log is saved (including on exception) by the time the `with` block exits
"""
from django.utils import timezone

from .models import LLMCallLog


def _block_to_dict(block) -> dict:
    if hasattr(block, "model_dump"):
        return block.model_dump(mode="json")
    return {"repr": repr(block)}


class LLMCallRecorder:
    def __init__(self, *, prompt_name="", prompt_version="", model="", max_tokens=None, care_plan=None):
        self.log = LLMCallLog(
            care_plan=care_plan,
            prompt_name=prompt_name,
            prompt_version=prompt_version,
            model=model,
            max_tokens=max_tokens,
            started_at=timezone.now(),
        )

    def __enter__(self):
        return self

    def record_retrieval(self, chunks, query: str = "", reference_material: str = ""):
        self.log.search_query = query
        self.log.reference_material = reference_material
        self.log.retrieved_chunks = [
            {
                "drug_name": c.drug_name,
                "section_name": c.section_name,
                "loinc_code": c.loinc_code,
                "distance": float(c.distance),
            }
            for c in chunks
        ]

    def record_request(self, rendered_prompt: str):
        self.log.rendered_prompt = rendered_prompt

    def record_response(self, response, attempts: int = 1):
        self.log.raw_response = [_block_to_dict(b) for b in response.content]
        self.log.output_text = "".join(b.text for b in response.content if b.type == "text")
        self.log.stop_reason = response.stop_reason
        if response.usage:
            self.log.input_tokens = response.usage.input_tokens
            self.log.output_tokens = response.usage.output_tokens
        self.log.attempts = attempts

    def record_parse_result(self, success: bool | None, errors=None):
        self.log.parse_succeeded = success
        self.log.validation_errors = errors

    def link_care_plan(self, care_plan):
        self.log.care_plan = care_plan
        self.log.save(update_fields=["care_plan"])

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.log.finished_at = timezone.now()
        self.log.duration_ms = int((self.log.finished_at - self.log.started_at).total_seconds() * 1000)
        if exc_type is not None:
            self.log.error = f"{exc_type.__name__}: {exc_val}"
        self.log.save()
        return False  # never swallow the exception
