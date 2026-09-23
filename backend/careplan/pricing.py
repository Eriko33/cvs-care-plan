"""Configurable per-model token pricing, loaded from pricing.yaml.

Read fresh on every call rather than cached at import time, so editing
pricing.yaml takes effect on the next request — no code change, no restart.
"""
from pathlib import Path

import yaml

PRICING_FILE = Path(__file__).resolve().parent / "pricing.yaml"


def load_pricing() -> dict:
    with open(PRICING_FILE, encoding="utf-8") as f:
        return yaml.safe_load(f).get("models", {})


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float | None:
    """Returns None (not 0) for an unpriced model — don't silently pretend it's free."""
    rates = load_pricing().get(model)
    if not rates:
        return None
    return (input_tokens / 1_000_000) * rates["input"] + (output_tokens / 1_000_000) * rates["output"]
