import anthropic
from django.conf import settings

from prompts import PromptManager

prompt_manager = PromptManager()


def generate_care_plan(data: dict) -> tuple[str, str]:
    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    rendered = prompt_manager.render("care_plan", **data)
    message = client.messages.create(
        model=settings.ANTHROPIC_MODEL,
        max_tokens=3000,
        messages=[{"role": "user", "content": rendered.text}],
    )
    return message.content[0].text, rendered.version
