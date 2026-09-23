from django.contrib import admin

from .evaluation import evaluate_care_plan
from .models import CarePlan, ClaimAnnotation, ExpectedFact, LLMCallLog


class ClaimAnnotationInline(admin.TabularInline):
    model = ClaimAnnotation
    extra = 3
    fields = ["text", "verdict", "matched_expected_fact", "notes"]


@admin.register(CarePlan)
class CarePlanAdmin(admin.ModelAdmin):
    list_display = ["id", "patient_name", "drug_name", "primary_diagnosis", "prompt_version", "created_at"]
    readonly_fields = ["content", "reference_material", "evaluation_summary"]
    inlines = [ClaimAnnotationInline]

    def evaluation_summary(self, obj):
        if not obj.pk:
            return "(save the care plan first)"
        result = evaluate_care_plan(obj)
        return (
            f"precision={result['precision']} | recall={result['recall']} | "
            f"f0.5={result['f0_5']} | must_have_recall={result['must_have_recall']} | "
            f"claims={result['claim_count']} (hallucinated={result['hallucinated_count']}, "
            f"unverifiable={result['unverifiable_count']})"
        )


@admin.register(ExpectedFact)
class ExpectedFactAdmin(admin.ModelAdmin):
    list_display = ["drug_name", "primary_diagnosis", "severity", "text", "source"]
    list_filter = ["severity", "drug_name"]


@admin.register(ClaimAnnotation)
class ClaimAnnotationAdmin(admin.ModelAdmin):
    list_display = ["care_plan", "verdict", "text", "matched_expected_fact"]
    list_filter = ["verdict"]


admin.site.register(LLMCallLog)
