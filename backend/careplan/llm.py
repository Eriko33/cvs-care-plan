import anthropic
from django.conf import settings

from prompts import PromptManager
from rag.search import search

prompt_manager = PromptManager()


def build_reference_material(chunks) -> str:
    if not chunks:
        return "No reference material was found for this medication."
    # Each chunk's text already carries a "[Drug — Section]" header
    # (see rag/chunk_label.py), which doubles as the citation source.
    return "\n\n".join(chunk.text for chunk in chunks)


def generate_care_plan(data: dict) -> tuple[str, str, str]:
    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    query = f"{data['drug_name']} {data['primary_diagnosis']}"
    chunks = search(query, top_k=5)
    reference_material = build_reference_material(chunks)

    rendered = prompt_manager.render(
        "care_plan",
        reference_material=reference_material,
        **data,
    )
    message = client.messages.create(
        model=settings.ANTHROPIC_MODEL,
        max_tokens=3000,
        messages=[{"role": "user", "content": rendered.text}],
    )
    # The response can include non-text blocks (e.g. thinking) before the
    # actual answer, so pick out the text block(s) rather than assuming
    # content[0] is text.
    text = "".join(block.text for block in message.content if block.type == "text")
    return text, rendered.version, reference_material
