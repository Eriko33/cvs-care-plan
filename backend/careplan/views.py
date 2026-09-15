from django.shortcuts import render

from .llm import generate_care_plan
from .models import CarePlan


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
        content = generate_care_plan(data)
        care_plan = CarePlan.objects.create(content=content, **data)

    return render(request, "careplan/index.html", {"care_plan": care_plan})
