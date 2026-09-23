"""Precision / Recall / F0.5 for a manually-annotated CarePlan.

Methodology (see conversation history for the reasoning):
- Unit of counting = one atomic claim (a ClaimAnnotation row), not a
  sentence or bullet — keeps the score stable across writing-style changes.
- Precision excludes "unverifiable" claims from the denominator entirely,
  rather than guessing whether they're right.
- Recall is computed against ExpectedFact rows for the same
  (drug_name, primary_diagnosis) scenario, so the same checklist backs every
  prompt-version comparison for that scenario.
- must_have_recall is reported separately — a blended Recall number can
  hide a missed safety-critical fact behind a pile of covered nice-to-haves.
- F0.5 (not F1) because in this domain a false claim (Precision error) is
  treated as costlier than an omission (Recall error) — see conversation.
"""
from .models import CarePlan, ClaimAnnotation, ExpectedFact


def _f_beta(precision: float | None, recall: float | None, beta: float) -> float | None:
    if precision is None or recall is None or (precision == 0 and recall == 0):
        return None
    beta_sq = beta ** 2
    return (1 + beta_sq) * precision * recall / (beta_sq * precision + recall)


def evaluate_care_plan(care_plan: CarePlan) -> dict:
    claims = care_plan.claims.all()
    verifiable = claims.exclude(verdict="unverifiable")
    correct = verifiable.filter(verdict="correct")

    precision = correct.count() / verifiable.count() if verifiable.exists() else None

    expected = ExpectedFact.objects.filter(
        drug_name=care_plan.drug_name, primary_diagnosis=care_plan.primary_diagnosis
    )
    matched_ids = set(correct.exclude(matched_expected_fact=None).values_list("matched_expected_fact_id", flat=True))

    def recall_for(qs):
        ids = set(qs.values_list("id", flat=True))
        return len(matched_ids & ids) / len(ids) if ids else None

    recall = recall_for(expected)
    must_have_recall = recall_for(expected.filter(severity="must_have"))

    return {
        "care_plan_id": care_plan.id,
        "claim_count": claims.count(),
        "unverifiable_count": claims.filter(verdict="unverifiable").count(),
        "hallucinated_count": claims.filter(verdict="hallucinated").count(),
        "precision": precision,
        "recall": recall,
        "must_have_recall": must_have_recall,
        "f0_5": _f_beta(precision, recall, beta=0.5),
        "expected_fact_count": expected.count(),
        "must_have_fact_count": expected.filter(severity="must_have").count(),
    }
