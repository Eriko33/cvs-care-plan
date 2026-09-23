"""assess_complexity() — pure Python, no framework dependency.

Classifies a patient record as "simple" or "complex" and maps that to a
generation strategy (which prompt version + which model to use). The rule
and the strategy mapping are both plain module-level data, so they're easy
to see and change without touching the function logic.
"""
from dataclasses import dataclass, field

# Tune the strategy per complexity tier here — cheaper/faster model + the
# plain prompt for simple cases, the strongest model + the RAG-grounded,
# goal-quality prompt for anything more involved.
STRATEGIES = {
    "simple": {"prompt_version": "v1", "model": "claude-haiku-4-5-20251001"},
    "complex": {"prompt_version": "v3", "model": "claude-sonnet-5"},
}

_NO_ALLERGY_PHRASES = {"", "none known", "nka", "no known allergies", "none"}


def _has_allergies(allergies) -> bool:
    """Accepts a list of allergies, or a free-text string like 'None known'."""
    if not allergies:
        return False
    if isinstance(allergies, str):
        return allergies.strip().lower() not in _NO_ALLERGY_PHRASES
    return len(allergies) > 0


@dataclass
class ComplexityStrategy:
    complexity: str  # "simple" or "complex"
    prompt_version: str
    model: str
    decision_log: list[str] = field(default_factory=list)


def assess_complexity(patient_record: dict) -> ComplexityStrategy:
    """
    patient_record expects:
      diagnoses:   list[str]
      medications: list[str]
      allergies:   list[str] | str (free text such as "None known" is fine)
      labs:        dict (accepted for future rules; not used by this one)

    Rule: diagnoses <= 1 AND medications <= 2 AND no allergy history -> simple,
    otherwise -> complex.
    """
    diagnoses = patient_record.get("diagnoses", [])
    medications = patient_record.get("medications", [])
    allergies = patient_record.get("allergies", [])
    labs = patient_record.get("labs")

    diagnosis_count = len(diagnoses)
    medication_count = len(medications)
    has_allergies = _has_allergies(allergies)

    diagnosis_ok = diagnosis_count <= 1
    medication_ok = medication_count <= 2
    allergy_ok = not has_allergies
    is_simple = diagnosis_ok and medication_ok and allergy_ok

    decision_log = [
        f"diagnosis_count={diagnosis_count} (<=1 required): {'pass' if diagnosis_ok else 'fail'}",
        f"medication_count={medication_count} (<=2 required): {'pass' if medication_ok else 'fail'}",
        f"has_allergies={has_allergies} (must be False): {'pass' if allergy_ok else 'fail'}",
        f"labs_provided={labs is not None} (not used by this rule)",
        f"=> {'simple' if is_simple else 'complex'} "
        f"({'all checks passed' if is_simple else 'at least one check failed'})",
    ]

    complexity = "simple" if is_simple else "complex"
    strategy = STRATEGIES[complexity]

    return ComplexityStrategy(
        complexity=complexity,
        prompt_version=strategy["prompt_version"],
        model=strategy["model"],
        decision_log=decision_log,
    )
