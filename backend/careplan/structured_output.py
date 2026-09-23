"""Structured JSON output from the LLM, constrained to CarePlanOutput's schema.

The API guarantees the response is well-formed JSON matching the schema's
shape at generation time (constrained decoding) — but a few Pydantic-only
rules (like `min_length` on the lists) aren't part of what the API enforces,
so the model can still return content that fails OUR validation even though
the API considered it valid JSON. generate_care_plan_with_retry() is the
recovery loop for that case: feed the validation errors back to the model
and ask it to fix them, instead of failing outright.
"""
import json

import anthropic
from django.conf import settings

from .llm_logging import LLMCallRecorder
from .schema import CarePlanOutput, validate_care_plan

MAX_RETRIES = 2  # 1 initial attempt + up to 2 retries = 3 calls max


def generate_structured_care_plan_claude(prompt: str) -> CarePlanOutput:
    """Anthropic Messages API — `output_config.format` (or the `.parse()` helper)."""
    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    # Convenience path: pass the Pydantic model directly, get one back.
    response = client.messages.parse(
        model=settings.ANTHROPIC_MODEL,
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
        output_format=CarePlanOutput,
    )
    return response.parsed_output

    # Equivalent lower-level form, if you need the raw JSON schema instead
    # of handing Pydantic straight to the SDK:
    #
    # response = client.messages.create(
    #     model=settings.ANTHROPIC_MODEL,
    #     max_tokens=2000,
    #     messages=[{"role": "user", "content": prompt}],
    #     output_config={
    #         "format": {
    #             "type": "json_schema",
    #             "schema": CarePlanOutput.model_json_schema(),
    #         }
    #     },
    # )
    # text = next(b.text for b in response.content if b.type == "text")
    # return CarePlanOutput.model_validate_json(text)


def generate_care_plan_with_retry(prompt: str, max_tokens: int = 2000) -> dict:
    """Generate + validate, retrying on failure by feeding the errors back to the model.

    Returns one of:
      {"success": True, "care_plan": CarePlanOutput, "attempts": N, "log": LLMCallLog}
      {"success": False, "parse_failed": True, "raw_output": str, "errors": [...], "attempts": N, "log": LLMCallLog}

    The returned `log` is already saved; link it to a CarePlan/order with
    `log.care_plan = obj; log.save(update_fields=["care_plan"])` once one exists.
    """
    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    schema = CarePlanOutput.model_json_schema()

    messages = [{"role": "user", "content": prompt}]
    raw_output = None
    errors = None
    attempt_records = []  # every attempt's raw output, kept for the full audit trail

    with LLMCallRecorder(
        prompt_name="care_plan_structured",
        model=settings.ANTHROPIC_MODEL,
        max_tokens=max_tokens,
    ) as recorder:
        for attempt in range(1, MAX_RETRIES + 2):
            response = client.messages.create(
                model=settings.ANTHROPIC_MODEL,
                max_tokens=max_tokens,
                messages=messages,
                output_config={"format": {"type": "json_schema", "schema": schema}},
            )
            raw_output = "".join(block.text for block in response.content if block.type == "text")
            attempt_records.append({
                "attempt": attempt,
                "raw_output": raw_output,
                "stop_reason": response.stop_reason,
                "usage": (
                    {"input_tokens": response.usage.input_tokens, "output_tokens": response.usage.output_tokens}
                    if response.usage
                    else None
                ),
            })

            try:
                data = json.loads(raw_output)
            except json.JSONDecodeError as exc:
                errors = [{"field": "<root>", "problem": f"Invalid JSON: {exc}", "got": raw_output[:500]}]
            else:
                care_plan, errors = validate_care_plan(data)
                if not errors:
                    recorder.record_request(json.dumps(messages, indent=2))
                    recorder.log.raw_response = attempt_records
                    recorder.log.output_text = raw_output
                    recorder.log.attempts = attempt
                    recorder.log.parse_succeeded = True
                    return {"success": True, "care_plan": care_plan, "attempts": attempt, "log": recorder.log}

            if attempt <= MAX_RETRIES:
                messages.append({"role": "assistant", "content": raw_output})
                messages.append({
                    "role": "user",
                    "content": (
                        "Your previous JSON output failed validation:\n"
                        f"{json.dumps(errors, indent=2)}\n\n"
                        "Please regenerate the full JSON, fixing these issues."
                    ),
                })

        recorder.record_request(json.dumps(messages, indent=2))
        recorder.log.raw_response = attempt_records
        recorder.log.output_text = raw_output
        recorder.log.attempts = MAX_RETRIES + 1
        recorder.log.parse_succeeded = False
        recorder.log.validation_errors = errors

    return {
        "success": False,
        "parse_failed": True,
        "raw_output": raw_output,
        "errors": errors,
        "attempts": MAX_RETRIES + 1,
        "log": recorder.log,
    }
