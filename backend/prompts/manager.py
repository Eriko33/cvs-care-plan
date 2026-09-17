from dataclasses import dataclass
from pathlib import Path

import yaml

PROMPTS_DIR = Path(__file__).resolve().parent
CONFIG_FILE = "config.yaml"


@dataclass
class RenderedPrompt:
    text: str
    name: str
    version: str


class PromptManager:
    def __init__(self, prompts_dir: Path = PROMPTS_DIR, config_file: str = CONFIG_FILE):
        self.prompts_dir = Path(prompts_dir)
        with open(self.prompts_dir / config_file, encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
        self.active_versions = config.get("active_versions", {})

    def _resolve_version(self, name: str, version: str | None) -> str:
        if version:
            return version
        if name not in self.active_versions:
            raise ValueError(f"No active version configured for prompt '{name}' in {CONFIG_FILE}")
        return self.active_versions[name]

    def list_versions(self, name: str) -> list[str]:
        return sorted(p.stem for p in (self.prompts_dir / name).glob("*.txt"))

    def load(self, name: str, version: str | None = None) -> tuple[str, str]:
        resolved_version = self._resolve_version(name, version)
        path = self.prompts_dir / name / f"{resolved_version}.txt"
        return path.read_text(encoding="utf-8"), resolved_version

    def render(self, name: str, version: str | None = None, **variables) -> RenderedPrompt:
        template, resolved_version = self.load(name, version)
        text = template.format(**variables)
        return RenderedPrompt(text=text, name=name, version=resolved_version)
