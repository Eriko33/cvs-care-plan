import anthropic
from django.conf import settings

PROMPT_TEMPLATE = """You are a clinical pharmacist. Write a Care Plan for the following prescription order.

Patient name: {patient_name}
Patient DOB: {patient_dob}
Patient MRN: {mrn}
Medication: {drug_name}
Prescriber: {provider_name}
Prescriber NPI: {npi}

Write the Care Plan with exactly these four sections, each with a clear heading:
1. Problem List
2. Goals
3. Pharmacist Interventions
4. Monitoring Plan
"""


def generate_care_plan(data: dict) -> str:
    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    prompt = PROMPT_TEMPLATE.format(**data)
    message = client.messages.create(
        model=settings.ANTHROPIC_MODEL,
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text
