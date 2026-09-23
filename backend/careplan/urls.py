from django.urls import path

from . import views
from .sse_demo import stream_care_plan_demo

urlpatterns = [
    path("", views.index, name="index"),
    path("api/llm-logs", views.llm_logs, name="llm-logs"),
    path("api/care-plans/<int:care_plan_id>/evaluation", views.care_plan_evaluation, name="care-plan-evaluation"),
    path("api/llm-costs", views.llm_costs, name="llm-costs"),
    path("dashboard", views.cost_dashboard, name="cost-dashboard"),
    path("api/stream-demo", stream_care_plan_demo, name="stream-demo"),
]
