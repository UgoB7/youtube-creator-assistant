from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from youtube_creator_assistant.core.config import Settings
from youtube_creator_assistant.providers.openai_client import OpenAIProvider
from youtube_creator_assistant.providers.replicate import ReplicateProvider


class ShepherdReplicateService:
    def __init__(
        self,
        settings: Settings,
        openai_provider: OpenAIProvider | None = None,
        replicate_provider: ReplicateProvider | None = None,
    ):
        self.settings = settings
        self.openai_provider = openai_provider or OpenAIProvider()
        self.replicate_provider = replicate_provider or ReplicateProvider(settings)

    def generate_visual_stack(self, target_dir: Path) -> tuple[str, Path, Path]:
        seeds = self._load_prompt_seeds(self.settings.replicate.prompt_seed_path)
        prompt = self._openai_generate_prompt(seeds)

        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        image_ext = (self.settings.replicate.image_output_format or "png").lower().lstrip(".")
        image_path = target_dir / f"shepherd_image_{stamp}.{image_ext}"
        image_path.write_bytes(self.replicate_provider.generate_image_bytes(prompt))

        video_path = target_dir / f"shepherd_video_{stamp}.mp4"
        video_path.write_bytes(self.replicate_provider.generate_video_bytes(image_path))
        return prompt, image_path, video_path

    def _load_prompt_seeds(self, path: Path) -> list[str]:
        if not path.exists():
            raise FileNotFoundError(f"Prompt seed file not found: {path}")
        lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
        seeds = [line for line in lines if line]
        if not seeds:
            raise RuntimeError(f"Prompt seed file is empty: {path}")
        return seeds

    def _openai_generate_prompt(self, examples: list[str]) -> str:
        prompt = self._build_prompt_generation_prompt(examples)
        for _ in range(2):
            response = self.openai_provider.client().responses.create(
                model=self.settings.openai.model,
                input=[{"role": "user", "content": prompt}],
            )
            raw = (response.output_text or "").strip()
            options = self._parse_prompt_options(raw, 1)
            if options:
                return options[0]
        raise RuntimeError("OpenAI did not return a usable shepherd image prompt.")

    def _build_prompt_generation_prompt(self, examples: list[str]) -> str:
        lines = [
            "Generate one image prompt similar to the examples, on the theme of Jesus.",
            "Constraint: Jesus must be sleeping.",
            "Clearly describe that Jesus is asleep so there is no ambiguity.",
            "",
            "Examples:",
            *[f"- {example}" for example in examples],
        ]
        return "\n".join(lines)

    def _parse_prompt_options(self, raw: str, count: int) -> list[str]:
        raw = (raw or "").strip()
        if not raw:
            return []
        if raw.startswith("```"):
            raw = raw.strip("`").strip()
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                options = data.get("options")
                if isinstance(options, list):
                    cleaned = [str(item).strip() for item in options if str(item).strip()]
                    if cleaned:
                        return cleaned[:count]
            if isinstance(data, list):
                cleaned = [str(item).strip() for item in data if str(item).strip()]
                if cleaned:
                    return cleaned[:count]
        except Exception:
            pass
        lines = [line.strip("-* \t") for line in raw.splitlines() if line.strip()]
        return lines[:count]
