"""Loader for review-protocol files (careplan/review_protocols/*.md).

Same progressive-disclosure pattern as Claude Skills: each file's YAML
frontmatter (name + description) is cheap and always kept in context; the
body is only read when the model decides — via a tool call — that this
specific case needs it.
"""
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

PROTOCOLS_DIR = Path(__file__).resolve().parent / "review_protocols"

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)", re.DOTALL)


@dataclass
class ReviewProtocol:
    name: str
    description: str
    body: str
    file: str


def _parse_protocol_file(path: Path) -> ReviewProtocol:
    raw = path.read_text(encoding="utf-8")
    match = _FRONTMATTER_RE.match(raw)
    if not match:
        raise ValueError(f"{path.name} is missing YAML frontmatter (expected '---\\nname: ...\\n---\\n<body>')")

    frontmatter = yaml.safe_load(match.group(1)) or {}
    for required_key in ("name", "description"):
        if required_key not in frontmatter:
            raise ValueError(f"{path.name}'s frontmatter is missing '{required_key}'")

    return ReviewProtocol(
        name=frontmatter["name"],
        description=frontmatter["description"],
        body=match.group(2).strip(),
        file=path.name,
    )


def _load_all() -> list[ReviewProtocol]:
    return [_parse_protocol_file(f) for f in sorted(PROTOCOLS_DIR.glob("*.md"))]


def list_review_protocols() -> list[dict]:
    """Metadata only (name + description) — this is what goes in the system prompt."""
    return [{"name": p.name, "description": p.description} for p in _load_all()]


def read_review_protocol(name: str) -> str:
    """Full body — called on demand via the read_review_protocol tool."""
    for protocol in _load_all():
        if protocol.name == name:
            return protocol.body
    available = [p.name for p in _load_all()]
    raise ValueError(f"No review protocol named '{name}'. Available: {available}")


def build_protocol_index_text() -> str:
    """The short, always-loaded index text for the system prompt."""
    lines = ["Available review protocols — call read_review_protocol(name) to load one when it applies to this case:"]
    lines += [f"- {p['name']}: {p['description']}" for p in list_review_protocols()]
    return "\n".join(lines)
