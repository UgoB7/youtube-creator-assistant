from __future__ import annotations

import concurrent.futures
import json
import re
import shutil
import warnings
from datetime import datetime, timezone
from pathlib import Path

from youtube_creator_assistant.core.config import Settings
from youtube_creator_assistant.core.models import ReplicateImageBatch, ReplicateImageCandidate, VisualAsset
from youtube_creator_assistant.core.utils import dedupe_preserve_order, extract_video_frame, img_to_data_url
from youtube_creator_assistant.providers.openai_client import OpenAIProvider
from youtube_creator_assistant.providers.replicate import ReplicateProvider


class ReplicateWorkflowService:
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
        cached = self._maybe_reuse_candidate_batch(target_dir, requested=requested)
        if cached is not None:
            return cached
        seeds = self._load_prompt_seeds(self.settings.replicate.prompt_seed_path)
        prompts = self._openai_generate_prompts(seeds, requested)

        batch_id, batch_dir = self._create_batch_dir(target_dir)

        candidates: list[ReplicateImageCandidate] = []
        return self._write_candidate_batch(
            batch_id=batch_id,
            batch_dir=batch_dir,
            prompts=prompts,
            source_visual_asset=None,
        )

    def generate_candidate_batch_from_visual(
        self,
        target_dir: Path,
        visual_source: Path,
        count: int | None = None,
    ) -> ReplicateImageBatch:
        prompt_settings = self.settings.replicate.visual_prompt_generation
        if not prompt_settings.enabled:
            raise RuntimeError("Visual prompt generation is disabled for this profile.")

        requested = max(1, int(count or self.settings.replicate.candidate_count or 10))
        cached = self._maybe_reuse_candidate_batch(target_dir, requested=requested)
        if cached is not None:
            return cached
        batch_id, batch_dir = self._create_batch_dir(target_dir)
        source_visual_asset, visual_prompt_parts = self._prepare_visual_source_for_batch(
            visual_source=visual_source,
            batch_dir=batch_dir,
        )
        prompts = self._openai_generate_prompts_from_visual(
            visual_prompt_parts=visual_prompt_parts,
            count=requested,
        )
        return self._write_candidate_batch(
            batch_id=batch_id,
            batch_dir=batch_dir,
            prompts=prompts,
            source_visual_asset=source_visual_asset,
        )

    def generate_visual_stack(self, target_dir: Path) -> tuple[str, Path, Path]:
        seeds = self._load_prompt_seeds(self.settings.replicate.prompt_seed_path)
        prompts = self._openai_generate_prompts(seeds, 1)
        if not prompts:
            raise RuntimeError("OpenAI did not return a usable image prompt.")
        prompt = self._finalize_image_prompt(prompts[0])

        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        profile_id = self.settings.profile.id
        image_ext = (self.settings.replicate.image_output_format or "png").lower().lstrip(".")
        image_path = target_dir / f"{profile_id}_image_{stamp}.{image_ext}"
        image_path.write_bytes(self.replicate_provider.generate_image_bytes(prompt))

        video_path = target_dir / f"{profile_id}_video_{stamp}.mp4"
        video_path.write_bytes(self.replicate_provider.generate_video_bytes(image_path))
        return prompt, image_path, video_path

    def _load_prompt_seeds(self, path: Path) -> list[str]:
        if not path.exists():
            raise FileNotFoundError(f"Prompt seed file not found: {path}")
        lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
        seeds = [line for line in lines if line and not re.fullmatch(r"\d+\s*:", line)]
        if not seeds:
            raise RuntimeError(f"Prompt seed file is empty: {path}")
        return seeds

    def _openai_generate_prompts(self, examples: list[str], count: int) -> list[str]:
        style = (self.settings.replicate.prompt_style or "shepherd_legacy").strip().lower()
        if style == "mercy_legacy":
            return self._openai_generate_prompts_mercy(examples, count)
        return self._openai_generate_prompts_shepherd(examples, count)

    def _openai_generate_prompts_from_visual(
        self,
        visual_prompt_parts: list[dict],
        count: int,
    ) -> list[str]:
        prompt_settings = self.settings.replicate.visual_prompt_generation
        system_prompt = (prompt_settings.system_prompt or "").strip()
        if not system_prompt:
            raise RuntimeError("The profile is missing replicate.visual_prompt_generation.system_prompt.")
        batch_size = self._resolve_prompt_batch_size(count, mode="visual")
        ordinal_batches = self._build_ordinal_batches(count, batch_size)
        slots: list[list[str] | None] = [None] * len(ordinal_batches)

        def _one_batch(batch_index: int, ordinals: list[int]) -> list[str]:
            max_attempts = self._prompt_batch_retry_attempts()
            for attempt in range(1, max_attempts + 1):
                response = self.openai_provider.client().responses.create(
                    model=self.settings.openai.model,
                    input=self._build_visual_prompt_request(
                        system_prompt=system_prompt,
                        visual_prompt_parts=visual_prompt_parts,
                        ordinals=ordinals,
                        total=count,
                    ),
                )
                prompts = self._extract_visual_prompts(response.output_text or "", len(ordinals))
                if len(prompts) >= len(ordinals):
                    return prompts[: len(ordinals)]
                if attempt < max_attempts:
                    self._warn_incomplete_prompt_batch(
                        kind="visual",
                        batch_index=batch_index,
                        total_batches=len(ordinal_batches),
                        expected=len(ordinals),
                        received=len(prompts),
                        attempt=attempt,
                        max_attempts=max_attempts,
                    )
            raise RuntimeError(
                f"OpenAI did not return enough visual prompts for batch {batch_index + 1}/{len(ordinal_batches)}."
            )

        max_workers = self._resolve_prompt_parallel_requests(len(ordinal_batches))
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_index = {
                executor.submit(_one_batch, batch_index, ordinals): batch_index
                for batch_index, ordinals in enumerate(ordinal_batches)
            }
            for future in concurrent.futures.as_completed(future_to_index):
                slots[future_to_index[future]] = future.result()

        prompts = [prompt for batch in slots if batch for prompt in batch]
        if len(prompts) >= count:
            return prompts[:count]
        raise RuntimeError("OpenAI did not return enough visual prompts.")

    def _openai_generate_prompts_shepherd(self, examples: list[str], count: int) -> list[str]:
        def _normalize_prompt(text: str) -> str:
            return re.sub(r"\s+", " ", text).strip().casefold()

        def _one_prompt(ordinal: int) -> str:
            prompt = self._build_shepherd_prompt_generation_prompt(examples, ordinal=ordinal, total=count)
            for _ in range(2):
                response = self.openai_provider.client().responses.create(
                    model=self.settings.openai.model,
                    input=[{"role": "user", "content": prompt}],
                )
                raw = (response.output_text or "").strip()
                options = self._parse_prompt_options(raw, 1)
                if options:
                    return options[0]
            raise RuntimeError(f"OpenAI did not return a usable image prompt (item {ordinal}/{count}).")

        max_workers = max(1, min(count, 4))
        slots: list[str | None] = [None] * count
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_index = {executor.submit(_one_prompt, index + 1): index for index in range(count)}
            for future in concurrent.futures.as_completed(future_to_index):
                slots[future_to_index[future]] = future.result()

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
                input=[
                    {
                        "role": "user",
                        "content": self._build_shepherd_prompt_generation_prompt(examples, ordinal=extra_ordinal, total=count),
                    }
                ],
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
        raise RuntimeError("OpenAI did not return usable image prompts.")

    def _openai_generate_prompts_mercy(self, examples: list[str], count: int) -> list[str]:
        batch_size = self._resolve_prompt_batch_size(count, mode="mercy")
        ordinal_batches = self._build_ordinal_batches(count, batch_size)
        slots: list[list[str] | None] = [None] * len(ordinal_batches)

        def _one_batch(batch_index: int, ordinals: list[int]) -> list[str]:
            prompt = self._build_mercy_prompt_generation_prompt(
                examples,
                len(ordinals),
                ordinal_start=ordinals[0],
                total=count,
            )
            max_attempts = self._prompt_batch_retry_attempts()
            for attempt in range(1, max_attempts + 1):
                response = self.openai_provider.client().responses.create(
                    model=self.settings.openai.model,
                    input=[{"role": "user", "content": prompt}],
                )
                raw = (response.output_text or "").strip()
                options = self._parse_prompt_options(raw, len(ordinals))
                if len(options) >= len(ordinals):
                    return options[: len(ordinals)]
                if attempt < max_attempts:
                    self._warn_incomplete_prompt_batch(
                        kind="image",
                        batch_index=batch_index,
                        total_batches=len(ordinal_batches),
                        expected=len(ordinals),
                        received=len(options),
                        attempt=attempt,
                        max_attempts=max_attempts,
                    )
            raise RuntimeError(
                f"OpenAI did not return enough image prompts for batch {batch_index + 1}/{len(ordinal_batches)}."
            )

        max_workers = self._resolve_prompt_parallel_requests(len(ordinal_batches))
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_index = {
                executor.submit(_one_batch, batch_index, ordinals): batch_index
                for batch_index, ordinals in enumerate(ordinal_batches)
            }
            for future in concurrent.futures.as_completed(future_to_index):
                slots[future_to_index[future]] = future.result()

        prompts = [prompt for batch in slots if batch for prompt in batch]
        if len(prompts) >= count:
            return prompts[:count]
        raise RuntimeError("OpenAI did not return enough image prompts.")

    def _build_shepherd_prompt_generation_prompt(self, examples: list[str], ordinal: int, total: int) -> str:
        lines = [
            f"Generate one image prompt similar to the examples, on the theme of Jesus (item {ordinal}/{total}).",
            "Constraint: Jesus must be sleeping.",
            "Clearly describe that Jesus is asleep so there is no ambiguity.",
            "",
            "Examples:",
            *[f"- {example}" for example in examples],
        ]
        return "\n".join(lines)

    def _build_mercy_prompt_generation_prompt(
        self,
        examples: list[str],
        count: int,
        *,
        ordinal_start: int = 1,
        total: int | None = None,
    ) -> str:
        lines = [
            f"Write EXACTLY {count} NEW image prompts in English.",
        ]
        if total is not None and total > count:
            lines.extend(
                [
                    f"This request covers items {ordinal_start} to {ordinal_start + count - 1} of {total}.",
                    "Make the prompts distinct from the likely outputs for the other item ranges in the same batch.",
                ]
            )
        lines.extend(
            [
            "Match the distribution of length, structure, adjective density, and scene composition from the examples.",
            "Keep the same family of themes and visual ingredients as the examples.",
            "Do not copy any exact sequence of words from the examples.",
            "Each output should be one long, comma-separated cinematic scene prompt.",
            'Return strict JSON: {"options": ["prompt1", "prompt2", "..."]}.',
            "",
            "Examples:",
            *[f"- {example}" for example in examples],
            ]
        )
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

    def _create_batch_dir(self, target_dir: Path) -> tuple[str, Path]:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        batch_id = f"{self.settings.profile.id}-candidates-{stamp}"
        batch_dir = target_dir / batch_id
        batch_dir.mkdir(parents=True, exist_ok=True)
        return batch_id, batch_dir

    def _write_candidate_batch(
        self,
        *,
        batch_id: str,
        batch_dir: Path,
        prompts: list[str],
        source_visual_asset: VisualAsset | None,
    ) -> ReplicateImageBatch:
        image_ext = (self.settings.replicate.image_output_format or "png").lower().lstrip(".")
        candidates: list[ReplicateImageCandidate] = []
        for index, prompt in enumerate(prompts, start=1):
            final_prompt = self._finalize_image_prompt(prompt)
            image_path = batch_dir / f"candidate_{index:02d}.{image_ext}"
            image_path.write_bytes(self.replicate_provider.generate_image_bytes(final_prompt))
            candidates.append(
                ReplicateImageCandidate(
                    candidate_id=f"candidate-{index:02d}",
                    prompt=final_prompt,
                    image_path=image_path,
                    label=f"Candidate {index:02d}",
                )
            )

        batch = ReplicateImageBatch(
            batch_id=batch_id,
            profile_id=self.settings.profile.id,
            batch_dir=batch_dir,
            created_at=datetime.now(timezone.utc).isoformat(),
            candidates=candidates,
            source_visual_asset=source_visual_asset,
        )
        (batch.batch_dir / "batch.json").write_text(json.dumps(batch.to_dict(), indent=2), encoding="utf-8")
        return batch

    def _finalize_image_prompt(self, prompt: str) -> str:
        base = (prompt or "").strip()
        prefix = (self.settings.replicate.image_prompt_prefix or "").strip()
        suffix = (self.settings.replicate.image_prompt_suffix or "").strip()
        parts: list[str] = []
        if prefix and prefix not in base:
            parts.append(prefix)
        if base:
            parts.append(base)
        if suffix and suffix not in base:
            parts.append(suffix)
        return "\n\n".join(part for part in parts if part)

    def _prepare_visual_source_for_batch(
        self,
        *,
        visual_source: Path,
        batch_dir: Path,
    ) -> tuple[VisualAsset, list[dict]]:
        source_path = visual_source.expanduser().resolve()
        if not source_path.exists():
            raise FileNotFoundError(f"Visual source not found: {source_path}")

        suffix = source_path.suffix.lower()
        if suffix in {".png", ".jpg", ".jpeg", ".webp"}:
            kind = "image"
        elif suffix in {".mp4", ".mov", ".m4v", ".mkv", ".avi", ".mpeg", ".mpg"}:
            kind = "video"
        else:
            raise ValueError(f"Unsupported visual file: {source_path.name}")

        copied_path = batch_dir / f"source_visual{suffix}"
        shutil.copy2(source_path, copied_path)
        source_visual_asset = VisualAsset(
            kind=kind,
            path=copied_path,
            original_name=source_path.name,
        )

        if kind == "image":
            parts = [{"type": "input_image", "image_url": img_to_data_url(copied_path)}]
            return source_visual_asset, parts

        preview_path = extract_video_frame(copied_path, batch_dir / "source_visual_preview.jpg")
        if preview_path:
            parts = [
                {
                    "type": "input_text",
                    "text": (
                        f"The source visual is a video clip named {source_path.name}. "
                        "Use the extracted preview frame to infer the intended scene accurately."
                    ),
                },
                {"type": "input_image", "image_url": img_to_data_url(preview_path)},
            ]
            return source_visual_asset, parts

        return source_visual_asset, [
            {
                "type": "input_text",
                "text": (
                    f"The source visual is a video clip named {source_path.name}. "
                    "No preview frame is available, so infer the scene from the clip context and filename only."
                ),
            }
        ]

    def _visual_prompt_user_text(self, ordinal: int, total: int) -> str:
        return self._visual_prompt_batch_user_text([ordinal], total)

    def _visual_prompt_batch_user_text(self, ordinals: list[int], total: int) -> str:
        prompt_settings = self.settings.replicate.visual_prompt_generation
        lines = []
        user_prompt = (prompt_settings.user_prompt or "").strip()
        if user_prompt:
            lines.append(user_prompt)
        variation_prompt = (prompt_settings.variation_prompt or "").strip()
        if variation_prompt:
            for ordinal in ordinals:
                lines.append(variation_prompt.format(ordinal=ordinal, total=total))
        if len(ordinals) > 1:
            lines.append(
                f'Return EXACTLY {len(ordinals)} prompts as strict JSON: {{"prompts": ["prompt1", "prompt2", "..."]}}.'
            )
            lines.append("Keep the prompts in the same order as the candidate numbers above.")
        return "\n\n".join(lines).strip()

    def _extract_visual_prompt(self, raw: str) -> str:
        prompts = self._extract_visual_prompts(raw, 1)
        return prompts[0] if prompts else ""

    def _extract_visual_prompts(self, raw: str, count: int) -> list[str]:
        text = (raw or "").strip()
        if not text:
            return []
        if text.startswith("```"):
            text = text.strip("`").strip()
            if text.lower().startswith("json"):
                text = text[4:].strip()
        try:
            payload = json.loads(text)
            if isinstance(payload, dict):
                if isinstance(payload.get("prompt"), str):
                    cleaned = dedupe_preserve_order([payload["prompt"].strip()])
                    return cleaned[:count]
                prompts = payload.get("prompts")
                if isinstance(prompts, list):
                    cleaned = dedupe_preserve_order(
                        [str(item).strip() for item in prompts if str(item).strip()]
                    )
                    return cleaned[:count]
            if isinstance(payload, list):
                cleaned = dedupe_preserve_order(
                    [str(item).strip() for item in payload if str(item).strip()]
                )
                return cleaned[:count]
        except Exception:
            pass

        lines = [line.strip() for line in text.splitlines() if line.strip()]
        cleaned_lines = [line.strip("-* \t") for line in lines]
        if count <= 1:
            single = " ".join(cleaned_lines).strip()
            return [single] if single else []
        return cleaned_lines[:count]

    def _build_visual_prompt_request(
        self,
        *,
        system_prompt: str,
        visual_prompt_parts: list[dict],
        ordinals: list[int],
        total: int,
    ) -> list[dict]:
        messages: list[dict] = [{"role": "system", "content": system_prompt}]
        if len(ordinals) > 1:
            messages.append(
                {
                    "role": "system",
                    "content": (
                        f"For this request, return EXACTLY {len(ordinals)} prompts as strict JSON with a "
                        '"prompts" array. Each prompt must be a single polished English paragraph.'
                    ),
                }
            )
        messages.append(
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": self._visual_prompt_batch_user_text(ordinals, total)},
                    *visual_prompt_parts,
                ],
            }
        )
        return messages

    def _resolve_prompt_batch_size(self, count: int, *, mode: str) -> int:
        configured = int(self.settings.replicate.prompt_batch_size or 0)
        if configured > 0:
            return max(1, min(count, configured))
        if mode == "mercy":
            return count
        return 1

    def _resolve_prompt_parallel_requests(self, batch_count: int) -> int:
        configured = int(self.settings.replicate.prompt_parallel_requests or 4)
        return max(1, min(batch_count, configured))

    @staticmethod
    def _prompt_batch_retry_attempts() -> int:
        return 4

    @staticmethod
    def _warn_incomplete_prompt_batch(
        *,
        kind: str,
        batch_index: int,
        total_batches: int,
        expected: int,
        received: int,
        attempt: int,
        max_attempts: int,
    ) -> None:
        warnings.warn(
            (
                f"OpenAI returned only {received}/{expected} {kind} prompts for batch "
                f"{batch_index + 1}/{total_batches}. Retrying ({attempt}/{max_attempts - 1})..."
            ),
            RuntimeWarning,
            stacklevel=2,
        )

    @staticmethod
    def _build_ordinal_batches(total: int, batch_size: int) -> list[list[int]]:
        batches: list[list[int]] = []
        current = 1
        while current <= total:
            stop = min(total, current + batch_size - 1)
            batches.append(list(range(current, stop + 1)))
            current = stop + 1
        return batches

    def _maybe_reuse_candidate_batch(
        self,
        target_dir: Path,
        *,
        requested: int,
    ) -> ReplicateImageBatch | None:
        debug_settings = self.settings.replicate.debug
        if not debug_settings.enabled or not debug_settings.reuse_candidate_batch:
            return None

        batch = self._load_debug_candidate_batch(target_dir)
        if batch is None:
            raise RuntimeError("Replicate debug reuse is enabled, but no reusable candidate batch was found.")
        if len(batch.candidates) < requested:
            raise RuntimeError(
                f"Replicate debug batch {batch.batch_id} has only {len(batch.candidates)} candidates, expected at least {requested}."
            )
        return batch

    def _load_debug_candidate_batch(self, target_dir: Path) -> ReplicateImageBatch | None:
        debug_settings = self.settings.replicate.debug
        explicit_batch_id = (debug_settings.candidate_batch_id or "").strip()
        if explicit_batch_id:
            batch_path = target_dir / explicit_batch_id / "batch.json"
            if not batch_path.exists():
                raise FileNotFoundError(f"Replicate debug batch not found: {explicit_batch_id}")
            return self._read_candidate_batch(batch_path)

        strategy = (debug_settings.candidate_batch_strategy or "explicit_or_latest").strip().lower()
        if strategy not in {"explicit_or_latest", "latest"}:
            raise RuntimeError(f"Unsupported replicate debug candidate batch strategy: {debug_settings.candidate_batch_strategy}")

        batch_paths = sorted(
            target_dir.glob(f"{self.settings.profile.id}-candidates-*/batch.json"),
            key=lambda path: path.parent.name,
        )
        if not batch_paths:
            return None
        return self._read_candidate_batch(batch_paths[-1])

    @staticmethod
    def _read_candidate_batch(batch_path: Path) -> ReplicateImageBatch:
        payload = json.loads(batch_path.read_text(encoding="utf-8"))
        return ReplicateImageBatch.from_dict(payload)


ShepherdReplicateService = ReplicateWorkflowService
