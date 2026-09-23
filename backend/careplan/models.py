import uuid

from django.db import models


class CarePlan(models.Model):
    patient_name = models.CharField(max_length=255)
    patient_dob = models.CharField(max_length=50)
    mrn = models.CharField(max_length=50)
    weight = models.CharField(max_length=50, blank=True)
    allergies = models.CharField(max_length=255, blank=True)
    primary_diagnosis = models.CharField(max_length=255, blank=True)
    drug_name = models.CharField(max_length=255)
    home_meds = models.CharField(max_length=500, blank=True)
    patient_records = models.TextField(blank=True)
    provider_name = models.CharField(max_length=255)
    npi = models.CharField(max_length=50)
    content = models.TextField()
    prompt_version = models.CharField(max_length=50, blank=True)
    reference_material = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.patient_name} - {self.drug_name}"


class LLMCallLog(models.Model):
    """Full record of one LLM call, for debugging and audit.

    Exists independently of CarePlan (care_plan is nullable) so a call that
    errored out or failed validation before a CarePlan could be created is
    still captured — those are often the ones you most need to diagnose.
    """

    request_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    care_plan = models.ForeignKey(
        CarePlan, on_delete=models.SET_NULL, null=True, blank=True, related_name="llm_calls"
    )

    # Generation config
    prompt_name = models.CharField(max_length=100, blank=True)
    prompt_version = models.CharField(max_length=50, blank=True)
    model = models.CharField(max_length=100, blank=True)
    max_tokens = models.IntegerField(null=True, blank=True)

    # Retrieval (RAG)
    search_query = models.TextField(blank=True)
    retrieved_chunks = models.JSONField(null=True, blank=True)
    reference_material = models.TextField(blank=True)

    # Input / output, in full
    rendered_prompt = models.TextField(blank=True)
    raw_response = models.JSONField(null=True, blank=True)
    output_text = models.TextField(blank=True)
    stop_reason = models.CharField(max_length=50, blank=True)

    # Token usage
    input_tokens = models.IntegerField(null=True, blank=True)
    output_tokens = models.IntegerField(null=True, blank=True)

    # Retry / validation outcome
    attempts = models.IntegerField(default=1)
    parse_succeeded = models.BooleanField(null=True, blank=True)  # None = not applicable (free-text flow)
    validation_errors = models.JSONField(null=True, blank=True)

    # Failure
    error = models.TextField(blank=True)

    # Timing
    started_at = models.DateTimeField()
    finished_at = models.DateTimeField(null=True, blank=True)
    duration_ms = models.IntegerField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-started_at"]

    def __str__(self):
        return f"LLMCallLog {self.request_id} ({self.model})"


class ExpectedFact(models.Model):
    """One item of the 'answer key' for a (drug, diagnosis) scenario.

    Reusable across generations/prompt versions for the same scenario, so
    the same checklist backs every Recall calculation you compare against
    each other.
    """

    SEVERITY_CHOICES = [
        ("must_have", "Must have"),
        ("nice_to_have", "Nice to have"),
    ]

    drug_name = models.CharField(max_length=255)
    primary_diagnosis = models.CharField(max_length=255)
    text = models.TextField(help_text="One specific, checkable fact the care plan should cover.")
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES, default="nice_to_have")
    source = models.CharField(
        max_length=255, blank=True, help_text="Where this came from, e.g. 'Privigen label — Contraindications'"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["drug_name", "primary_diagnosis", "-severity"]

    def __str__(self):
        return f"[{self.severity}] {self.drug_name}/{self.primary_diagnosis}: {self.text[:60]}"


class ClaimAnnotation(models.Model):
    """One atomic claim extracted from a generated CarePlan, with its verdict."""

    VERDICT_CHOICES = [
        ("correct", "Correct"),
        ("hallucinated", "Hallucinated"),
        ("unverifiable", "Unverifiable"),
    ]

    care_plan = models.ForeignKey(CarePlan, on_delete=models.CASCADE, related_name="claims")
    text = models.TextField(help_text="The atomic claim, as pulled out of the generated content.")
    verdict = models.CharField(max_length=20, choices=VERDICT_CHOICES)
    matched_expected_fact = models.ForeignKey(
        ExpectedFact, on_delete=models.SET_NULL, null=True, blank=True,
        help_text="Set this when the claim correctly covers one of the checklist items — that's what Recall counts.",
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.get_verdict_display()}: {self.text[:60]}"
