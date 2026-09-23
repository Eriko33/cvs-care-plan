from dataclasses import dataclass

import anthropic
from django.conf import settings

from prompts import PromptManager
from rag.search import search

from .llm_logging import LLMCallRecorder
from .models import LLMCallLog

prompt_manager = PromptManager()

MAX_TOKENS = 3000


@dataclass
class GenerationResult:
    text: str
    prompt_version: str
    reference_material: str
    log: LLMCallLog


def build_reference_material(chunks) -> str:
    if not chunks:
        return "No reference material was found for this medication."
    # Each chunk's text already carries a "[Drug — Section]" header
    # (see rag/chunk_label.py), which doubles as the citation source.
    return "\n\n".join(chunk.text for chunk in chunks)


def generate_care_plan(data: dict, version: str | None = None, max_tokens: int = MAX_TOKENS) -> GenerationResult:
    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    query = f"{data['drug_name']} {data['primary_diagnosis']}"
    chunks = search(query, top_k=5)
    reference_material = build_reference_material(chunks)

    rendered = prompt_manager.render(
        "care_plan",
        version=version,
        reference_material=reference_material,
        **data,
    )

    with LLMCallRecorder(
        prompt_name="care_plan",
        prompt_version=rendered.version,
        model=settings.ANTHROPIC_MODEL,
        max_tokens=max_tokens,
    ) as recorder:
        recorder.record_retrieval(chunks, query=query, reference_material=reference_material)
        recorder.record_request(rendered.text)

        message = client.messages.create(
            model=settings.ANTHROPIC_MODEL,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": rendered.text}],
        )
        recorder.record_response(message)

        # The response can include non-text blocks (e.g. thinking) before the
        # actual answer, so pick out the text block(s) rather than assuming
        # content[0] is text.
        text = "".join(block.text for block in message.content if block.type == "text")

    return GenerationResult(
        text=text,
        prompt_version=rendered.version,
        reference_material=reference_material,
        log=recorder.log,
    )
