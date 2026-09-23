"""MCP server exposing the care plan system to Claude Desktop (or any MCP client).

Three tools: generate_care_plan(mrn), read_care_plan(mrn), query_labs(mrn, test_name).

Important limitation, by design of the current data model: there is no
separate "patient" record independent of a CarePlan — a patient's
demographics/diagnosis/meds/labs only exist once they've been submitted
through the web form at least once. So generate_care_plan(mrn) can only
REGENERATE for a patient already on file (it reuses their most recent
submitted data); it cannot create a brand-new patient from an MRN alone.

Run inside the Docker container, since it needs Django + Postgres + the
already-indexed pgvector data:
    docker compose exec -T web python -m careplan.mcp_server
"""
import os

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from mcp.server.mcpserver import MCPServer  # noqa: E402

from .llm import generate_care_plan as _generate_care_plan  # noqa: E402
from .models import CarePlan  # noqa: E402

# mcp>=2.0 renamed FastMCP -> MCPServer (this project's mcp package is 2.2.0).
# If you're following older docs/tutorials that show `from mcp.server.fastmcp
# import FastMCP`, that's the pre-2.0 API — swap in MCPServer instead.
mcp = MCPServer("care-plan-system")


def _latest_care_plan_for_mrn(mrn: str) -> CarePlan | None:
    return CarePlan.objects.filter(mrn=mrn).order_by("-created_at").first()


@mcp.tool(name="generate_care_plan")
def generate_care_plan_tool(mrn: str) -> str:
    """Generate a NEW care plan for a patient who already has one on file, by MRN.

    WHEN TO CALL: only when the user explicitly asks to (re)generate a care
    plan — e.g. "regenerate the care plan for MRN 005678", or "make a new
    care plan now that the prompt changed". This reuses the demographics,
    diagnosis, home meds, and clinical notes already on file for that MRN;
    it does not accept new patient data and cannot create a brand-new
    patient. If no care plan exists yet for this MRN, it returns an error —
    the patient must be entered through the web form first.

    Do NOT call this just to see what a patient's plan says (use
    read_care_plan for that — it's free and instant). Each call here makes
    a real LLM API call and costs money.
    """
    existing = _latest_care_plan_for_mrn(mrn)
    if existing is None:
        return (
            f"No prior care plan found for MRN {mrn}. This tool can only regenerate for a "
            f"patient already on file — enter them through the web form first."
        )

    data = {
        "patient_name": existing.patient_name,
        "patient_dob": existing.patient_dob,
        "mrn": existing.mrn,
        "weight": existing.weight,
        "allergies": existing.allergies,
        "primary_diagnosis": existing.primary_diagnosis,
        "drug_name": existing.drug_name,
        "home_meds": existing.home_meds,
        "patient_records": existing.patient_records,
        "provider_name": existing.provider_name,
        "npi": existing.npi,
    }
    result = _generate_care_plan(data)
    new_plan = CarePlan.objects.create(
        content=result.text,
        prompt_version=result.prompt_version,
        reference_material=result.reference_material,
        **data,
    )
    result.log.care_plan = new_plan
    result.log.save(update_fields=["care_plan"])
    return f"Generated new care plan (id={new_plan.id}, prompt_version={result.prompt_version}) for MRN {mrn}:\n\n{new_plan.content}"


@mcp.tool(name="draft_care_plan")
def draft_care_plan_tool(mrn: str) -> str:
    """Generate a DRAFT care plan for review — does NOT save it. By MRN.

    WHEN TO CALL: this is the first step of the generate-then-confirm flow.
    Use this (not generate_care_plan) whenever a human needs to review the
    content before it's persisted. The draft text comes back in the tool
    result, along with the prompt_version used — pass BOTH of those to
    save_care_plan once approved. Costs a real LLM call, same as
    generate_care_plan.
    """
    existing = _latest_care_plan_for_mrn(mrn)
    if existing is None:
        return (
            f"No prior care plan found for MRN {mrn}. This tool can only draft for a "
            f"patient already on file — enter them through the web form first."
        )

    data = {
        "patient_name": existing.patient_name,
        "patient_dob": existing.patient_dob,
        "mrn": existing.mrn,
        "weight": existing.weight,
        "allergies": existing.allergies,
        "primary_diagnosis": existing.primary_diagnosis,
        "drug_name": existing.drug_name,
        "home_meds": existing.home_meds,
        "patient_records": existing.patient_records,
        "provider_name": existing.provider_name,
        "npi": existing.npi,
    }
    result = _generate_care_plan(data)
    return (
        f"DRAFT (not yet saved) for MRN {mrn}, prompt_version={result.prompt_version}:\n\n"
        f"{result.text}"
    )


@mcp.tool(name="save_care_plan")
def save_care_plan_tool(mrn: str, content: str, prompt_version: str) -> str:
    """Persist an already-drafted care plan to the database. By MRN.

    WHEN TO CALL: only after a human has reviewed and approved a draft from
    draft_care_plan. Pass the exact `content` and `prompt_version` the draft
    came back with — this tool does not regenerate anything, it just saves
    what you give it. Reuses the same demographics/diagnosis/meds already on
    file for this MRN (same limitation as draft_care_plan: MRN must already
    exist).
    """
    existing = _latest_care_plan_for_mrn(mrn)
    if existing is None:
        return f"No prior care plan found for MRN {mrn}. Cannot save — patient not on file."

    new_plan = CarePlan.objects.create(
        content=content,
        prompt_version=prompt_version,
        reference_material="",  # not re-derived here; draft_care_plan's result already had it in context
        patient_name=existing.patient_name,
        patient_dob=existing.patient_dob,
        mrn=existing.mrn,
        weight=existing.weight,
        allergies=existing.allergies,
        primary_diagnosis=existing.primary_diagnosis,
        drug_name=existing.drug_name,
        home_meds=existing.home_meds,
        patient_records=existing.patient_records,
        provider_name=existing.provider_name,
        npi=existing.npi,
    )
    return f"Saved care plan id={new_plan.id} for MRN {mrn} (prompt_version={prompt_version})."


@mcp.tool(name="read_care_plan")
def read_care_plan_tool(mrn: str) -> str:
    """Read the most recently generated care plan for a patient, by MRN.

    WHEN TO CALL: whenever the user asks what a patient's care plan says,
    wants to review or summarize it, or asks a question answerable from its
    content. This is read-only, free, and instant — always prefer this over
    generate_care_plan when a plan for this MRN might already exist.
    """
    plan = _latest_care_plan_for_mrn(mrn)
    if plan is None:
        return f"No care plan found for MRN {mrn}."
    return (
        f"Care plan for {plan.patient_name} (MRN {plan.mrn}), generated "
        f"{plan.created_at.isoformat()}, prompt_version={plan.prompt_version}:\n\n{plan.content}"
    )


@mcp.tool(name="query_labs")
def query_labs_tool(mrn: str, test_name: str) -> str:
    """Look up a specific lab value or vital sign for a patient, by MRN.

    WHEN TO CALL: when the user asks about ONE specific lab/vital (e.g.
    "what was this patient's eGFR", "what's their INR", "what was the BP")
    rather than the whole care plan — this is more precise than
    read_care_plan for a single-value question. This searches the free-text
    clinical notes on file line by line for `test_name`; it is plain text
    search, not a structured lab database, so try the test's common
    abbreviation (e.g. "SCr", "eGFR", "INR", "BP") if the full name doesn't
    match anything.
    """
    plan = _latest_care_plan_for_mrn(mrn)
    if plan is None:
        return f"No care plan found for MRN {mrn}, so there are no clinical notes to search."

    matches = [
        line.strip()
        for line in plan.patient_records.splitlines()
        if test_name.lower() in line.lower() and line.strip()
    ]
    if not matches:
        return f"No mention of '{test_name}' found in the clinical notes on file for MRN {mrn}."
    return "\n".join(matches)


if __name__ == "__main__":
    mcp.run()
