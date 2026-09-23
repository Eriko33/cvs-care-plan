import json

from django.db.models import Count, Sum
from django.db.models.functions import TruncDate
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render

from .evaluation import evaluate_care_plan
from .llm import generate_care_plan
from .models import CarePlan, LLMCallLog
from .pricing import estimate_cost


def index(request):
    care_plan = None

    if request.method == "POST":
        data = {
            "patient_name": request.POST.get("patient_name", ""),
            "patient_dob": request.POST.get("patient_dob", ""),
            "mrn": request.POST.get("mrn", ""),
            "weight": request.POST.get("weight", ""),
            "allergies": request.POST.get("allergies", ""),
            "primary_diagnosis": request.POST.get("primary_diagnosis", ""),
            "drug_name": request.POST.get("drug_name", ""),
            "home_meds": request.POST.get("home_meds", ""),
            "patient_records": request.POST.get("patient_records", ""),
            "provider_name": request.POST.get("provider_name", ""),
            "npi": request.POST.get("npi", ""),
        }
        result = generate_care_plan(data)
        care_plan = CarePlan.objects.create(
            content=result.text,
            prompt_version=result.prompt_version,
            reference_material=result.reference_material,
            **data,
        )
        result.log.care_plan = care_plan
        result.log.save(update_fields=["care_plan"])

    return render(request, "careplan/index.html", {"care_plan": care_plan})


def _serialize_log(log: LLMCallLog) -> dict:
    return {
        "id": log.id,
        "request_id": str(log.request_id),
        "order_id": log.care_plan_id,
        "prompt_name": log.prompt_name,
        "prompt_version": log.prompt_version,
        "model": log.model,
        "max_tokens": log.max_tokens,
        "search_query": log.search_query,
        "retrieved_chunks": log.retrieved_chunks,
        "reference_material": log.reference_material,
        "rendered_prompt": log.rendered_prompt,
        "raw_response": log.raw_response,
        "output_text": log.output_text,
        "stop_reason": log.stop_reason,
        "input_tokens": log.input_tokens,
        "output_tokens": log.output_tokens,
        "attempts": log.attempts,
        "parse_succeeded": log.parse_succeeded,
        "validation_errors": log.validation_errors,
        "error": log.error,
        "started_at": log.started_at.isoformat() if log.started_at else None,
        "finished_at": log.finished_at.isoformat() if log.finished_at else None,
        "duration_ms": log.duration_ms,
    }


def llm_logs(request):
    order_id = request.GET.get("order_id")

    queryset = LLMCallLog.objects.all()
    if order_id:
        queryset = queryset.filter(care_plan_id=order_id)

    return JsonResponse({"results": [_serialize_log(log) for log in queryset]})


def care_plan_evaluation(request, care_plan_id):
    care_plan = get_object_or_404(CarePlan, id=care_plan_id)
    return JsonResponse(evaluate_care_plan(care_plan))


def _cost_summary(start_date, end_date) -> dict:
    queryset = LLMCallLog.objects.all()
    if start_date:
        queryset = queryset.filter(started_at__date__gte=start_date)
    if end_date:
        queryset = queryset.filter(started_at__date__lte=end_date)

    # Group by (day, model): cost depends on model, and a day can mix models
    # (e.g. right after switching prompt/model config), so this keeps cost
    # accurate without a per-row Python loop over every call.
    grouped = (
        queryset.annotate(date=TruncDate("started_at"))
        .values("date", "model")
        .annotate(calls=Count("id"), input_tokens=Sum("input_tokens"), output_tokens=Sum("output_tokens"))
        .order_by("date")
    )

    daily = {}
    total_calls = 0
    total_input_tokens = 0
    total_output_tokens = 0
    total_cost = 0.0
    unpriced_models = set()

    for row in grouped:
        date_str = str(row["date"])
        input_tokens = row["input_tokens"] or 0
        output_tokens = row["output_tokens"] or 0
        cost = estimate_cost(row["model"], input_tokens, output_tokens)
        if cost is None:
            unpriced_models.add(row["model"])
            cost = 0.0

        entry = daily.setdefault(
            date_str, {"date": date_str, "calls": 0, "input_tokens": 0, "output_tokens": 0, "estimated_cost_usd": 0.0}
        )
        entry["calls"] += row["calls"]
        entry["input_tokens"] += input_tokens
        entry["output_tokens"] += output_tokens
        entry["estimated_cost_usd"] += cost

        total_calls += row["calls"]
        total_input_tokens += input_tokens
        total_output_tokens += output_tokens
        total_cost += cost

    return {
        "start_date": start_date,
        "end_date": end_date,
        "total_calls": total_calls,
        "total_input_tokens": total_input_tokens,
        "total_output_tokens": total_output_tokens,
        "estimated_cost_usd": round(total_cost, 4),
        "unpriced_models": sorted(unpriced_models),
        "daily_trend": [
            {**v, "estimated_cost_usd": round(v["estimated_cost_usd"], 4)}
            for v in sorted(daily.values(), key=lambda d: d["date"])
        ],
    }


def llm_costs(request):
    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")
    return JsonResponse(_cost_summary(start_date, end_date))


def cost_dashboard(request):
    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")
    summary = _cost_summary(start_date, end_date)
    return render(request, "careplan/dashboard.html", {"summary": summary, "summary_json": json.dumps(summary)})
