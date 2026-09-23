"""Schema + validation for the structured Care Plan JSON output.

Pydantic handles all three requirements out of the box:
- missing required fields -> ValidationError naming the exact field
- type coercion ("72" -> 72.0) -> its default ("lax") mode does this automatically
- per-field error detail -> ValidationError.errors() returns a list of
  {loc, msg, type, input} dicts, one per problem
"""
from pydantic import BaseModel, ConfigDict, Field, ValidationError


class PatientSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")  # -> additionalProperties: false in the JSON schema

    name: str
    weight_kg: float
    diagnosis: str


class CarePlanOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    patient_summary: PatientSummary
    problems: list[str] = Field(min_length=1)
    goals: list[str] = Field(min_length=1)
    interventions: list[str] = Field(min_length=1)


def validate_care_plan(data: dict) -> tuple[CarePlanOutput | None, list[dict]]:
    """Returns (parsed_object, []) on success, or (None, errors) on failure.

    Each error dict has: field (dotted path), problem (message), got (the
    offending input value) — enough to tell you exactly what's wrong and where.
    """
    try:
        return CarePlanOutput.model_validate(data), []
    except ValidationError as exc:
        errors = [
            {
                "field": ".".join(str(p) for p in err["loc"]),
                "problem": err["msg"],
                # For a "missing field" error, pydantic's `input` is the
                # *parent* object (there's no value for the missing field
                # itself) — showing that is noise, not useful detail.
                "got": None if err["type"] == "missing" else err.get("input"),
            }
            for err in exc.errors()
        ]
        return None, errors
