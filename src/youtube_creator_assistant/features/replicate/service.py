from __future__ import annotations

import concurrent.futures
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from youtube_creator_assistant.core.config import Settings
from youtube_creator_assistant.core.models import ReplicateImageBatch, ReplicateImageCandidate
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

    def generate_candidate_batch(self, target_dir: Path, count: int | None = None) -> ReplicateImageBatch:
        requested = max(1, int(count or self.settings.replicate.candidate_count or 10))
        seeds = self._load_prompt_seeds(self.settings.replicate.prompt_seed_path)
        prompts = self._openai_generate_prompts(seeds, requested)

        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        batch_id = f"shepherd-candidates-{stamp}"
        batch_dir = target_dir / batch_id
        batch_dir.mkdir(parents=True, exist_ok=True)
        image_ext = (self.settings.replicate.image_output_format or "png").lower().lstrip(".")

        candidates: list[ReplicateImageCandidate] = []
        for index, prompt in enumerate(prompts, start=1):
            image_path = batch_dir / f"candidate_{index:02d}.{image_ext}"
            image_path.write_bytes(self.replicate_provider.generate_image_bytes(prompt))
            candidates.append(
                ReplicateImageCandidate(
                    candidate_id=f"candidate-{index:02d}",
                    prompt=prompt,
                    image_path=image_path,
                )
            )

        batch = ReplicateImageBatch(
            batch_id=batch_id,
            profile_id=self.settings.profile.id,
            batch_dir=batch_dir,
            created_at=datetime.now(timezone.utc).isoformat(),
            candidates=candidates,
        )
        (batch.batch_dir / "batch.json").write_text(json.dumps(batch.to_dict(), indent=2), encoding="utf-8")
        return batch

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
        prompts = self._openai_generate_prompts(examples, 1)
        if prompts:
            return prompts[0]
        raise RuntimeError("OpenAI did not return a usable shepherd image prompt.")

    def _openai_generate_prompts(self, examples: list[str], count: int) -> list[str]:
        def _normalize_prompt(text: str) -> str:
            return re.sub(r"\s+", " ", text).strip().casefold()

        def _one_prompt(ordinal: int) -> str:
            prompt = self._build_prompt_generation_prompt(examples, ordinal=ordinal, total=count)
            for _ in range(2):
                response = self.openai_provider.client().responses.create(
                    model=self.settings.openai.model,
                    input=[{"role": "user", "content": prompt}],
                )
                raw = (response.output_text or "").strip()
                options = self._parse_prompt_options(raw, 1)
                if options:
                    return options[0]
            raise RuntimeError(f"OpenAI did not return a usable shepherd image prompt (item {ordinal}/{count}).")

        max_workers = max(1, min(count, 4))
        slots: list[str | None] = [None] * count
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_index = {
                executor.submit(_one_prompt, index + 1): index
                for index in range(count)
            }
            for future in concurrent.futures.as_completed(future_to_index):
                index = future_to_index[future]
                slots[index] = future.result()

        seen: set[str] = set()
        prompts: list[str] = []
        for item in slots:
            if not item:
                continue
            normalized = _normalize_prompt(item)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            prompts.append(item)

        extra_ordinal = count + 1
        extra_attempts = 0
        max_extra_attempts = max(4, count * 3)
        while len(prompts) < count and extra_attempts < max_extra_attempts:
            extra_attempts += 1
            response = self.openai_provider.client().responses.create(
                model=self.settings.openai.model,
                input=[{"role": "user", "content": self._build_prompt_generation_prompt(examples, ordinal=extra_ordinal, total=count)}],
            )
            raw = (response.output_text or "").strip()
            options = self._parse_prompt_options(raw, 1)
            extra_ordinal += 1
            if not options:
                continue
            item = options[0]
            normalized = _normalize_prompt(item)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            prompts.append(item)

        if prompts:
            return prompts[:count]
        raise RuntimeError("OpenAI did not return usable shepherd image prompts.")

    def _build_prompt_generation_prompt(self, examples: list[str], ordinal: int, total: int) -> str:
        lines = [
            f"Generate one image prompt similar to the examples, on the theme of Jesus (item {ordinal}/{total}).",
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
