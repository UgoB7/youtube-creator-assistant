from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterable, List

from youtube_creator_assistant.core.config import Settings
from youtube_creator_assistant.core.models import VisualAsset
from youtube_creator_assistant.core.utils import (
    dedupe_preserve_order,
    extract_video_frame,
    img_to_data_url,
    split_examples,
)
from youtube_creator_assistant.providers.openai_client import OpenAIProvider


class TitleAndThemeService:
    def __init__(self, settings: Settings, provider: OpenAIProvider | None = None):
        self.settings = settings
        self.provider = provider or OpenAIProvider()

    def generate_titles(self, visual_asset: VisualAsset, working_dir: Path | None = None) -> List[str]:
        title_settings = self.settings.openai.title_generation
        examples = "\n".join(f"- {item}" for item in split_examples(title_settings.examples_input))
        rules = self._format_rule_block(title_settings.rules)
        response = self.provider.client().responses.create(
            model=self.settings.openai.model,
            input=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": (
                                "You craft YouTube video titles.\n"
                                f"Look at the current project visual and return exactly {title_settings.count} titles as JSON only.\n"
                                "Every title must stay relevant to the visual.\n"
                                f"{self._separator_prompt_block()}"
                                f"{self._prompt_addendum_block(title_settings.prompt_addendum)}"
                                f"{rules}"
                                f"{self._examples_block(examples)}\n"
                                f'Return only: {{"titles": ["t1", "...", "t{title_settings.count}"]}}'
                            ),
                        },
                        *self._visual_prompt_parts_for_title_generation(visual_asset, working_dir),
                    ],
                }
            ],
        )
        payload = self._extract_json(response.output_text)
        raw_titles = payload.get("titles", [])
        titles = [item.strip() for item in raw_titles if isinstance(item, str) and item.strip()]
        titles = self._normalize_title_candidates(titles)
        titles = dedupe_preserve_order(titles)
        if len(titles) < title_settings.min_count:
            raise RuntimeError("OpenAI returned too few titles.")
        return titles[: title_settings.count]

    def generate_reference_preferences(self, visual_asset: VisualAsset, selected_title: str, working_dir: Path | None = None) -> List[str]:
        return self.generate_reference_preferences_for_titles(visual_asset, [selected_title], working_dir)

    def generate_reference_preferences_for_titles(
        self,
        visual_asset: VisualAsset,
        selected_titles: Iterable[str],
        working_dir: Path | None = None,
    ) -> List[str]:
        cleaned_titles = [title.strip() for title in selected_titles if isinstance(title, str) and title.strip()]
        if not cleaned_titles:
            return []
        titles_block = "\n".join(f"- {title}" for title in cleaned_titles[:3])
        target_count = max(
            int(getattr(self.settings.workflow, "preferred_reference_count", 16) or 16),
            int(getattr(self.settings.workflow, "max_head_items", 0) or 0),
        )
        response = self.provider.client().responses.create(
            model=self.settings.openai.model,
            input=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": (
                                "You are selecting Bible audio references for a YouTube devotional video.\n"
                                "Use the image and the selected titles to create a diverse, ranked list of references.\n"
                                "Rules:\n"
                                "- Return a JSON object only.\n"
                                "- Use strings like 'John 14' or 'Psalm 23'.\n"
                                "- Prefer diversity and rotation; do not overuse the same common chapters.\n"
                                "- Mix gospels and psalms when relevant.\n"
                                f"- Return exactly {target_count} references.\n"
                                '- Return only: {"preferred_refs": ["John 14", "Psalm 23"]}'
                            ),
                        },
                        {"type": "input_text", "text": f"Selected titles:\n{titles_block}"},
                        *self._visual_prompt_parts(visual_asset, working_dir),
                    ],
                }
            ],
        )
        payload = self._extract_json(response.output_text)
        refs = payload.get("preferred_refs", [])
        cleaned = [item.strip() for item in refs if isinstance(item, str) and item.strip()]
        return dedupe_preserve_order(cleaned)[:target_count]

    def generate_themes(
        self,
        visual_asset: VisualAsset,
        selected_title: str,
        audio_labels: List[str],
        working_dir: Path | None = None,
    ) -> List[str]:
        theme_settings = self.settings.openai.theme_generation
        tracks_text = "\n".join(f"- {label}" for label in audio_labels[:12])
        rules = self._format_rule_block(theme_settings.rules)
        content = [
            {
                "type": "input_text",
                "text": (
                    "You create short YouTube video themes.\n"
                    f"Using the title, image, and any provided context, return exactly {theme_settings.count} themes.\n"
                    f"{self._prompt_addendum_block(theme_settings.prompt_addendum)}"
                    f"{rules}"
                    f'Return only: {{"themes": ["...", "...", "...", "...", "..."]}}'
                ),
            },
            {"type": "input_text", "text": f"Title: {selected_title}"},
        ]
        if theme_settings.include_audio_context and tracks_text.strip():
            content.append({"type": "input_text", "text": f"Audio:\n{tracks_text}"})
        if theme_settings.use_visual_input:
            content.extend(self._visual_prompt_parts(visual_asset, working_dir))
        response = self.provider.client().responses.create(
            model=self.settings.openai.model,
            input=[
                {
                    "role": "user",
                    "content": content,
                }
            ],
        )
        payload = self._extract_json(response.output_text)
        themes = [item.strip() for item in payload.get("themes", []) if isinstance(item, str) and item.strip()]
        themes = dedupe_preserve_order(themes)
        if len(themes) < theme_settings.min_count:
            raise RuntimeError("OpenAI returned too few themes.")
        return themes[: theme_settings.count]

    def _extract_json(self, text: str) -> dict:
        raw = text.strip()
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if not match:
                raise RuntimeError("OpenAI response did not contain JSON.")
            return json.loads(match.group(0))

    def _normalize_title_candidates(self, titles: List[str]) -> List[str]:
        if not self.settings.openai.title_generation.require_separator:
            return [self._strip_title_leading_marker(title) for title in titles]
        normalized: List[str] = []
        for title in titles:
            candidate = self._normalize_structured_title(title)
            if candidate:
                normalized.append(candidate)
        return normalized

    def _normalize_structured_title(self, title: str) -> str | None:
        separator = self.settings.openai.title_generation.separator
        cleaned = self._strip_title_leading_marker(title)
        if separator in cleaned:
            parts = [part.strip() for part in cleaned.split(separator)]
            if len(parts) == 2 and all(parts):
                return f"{parts[0]}{separator}{parts[1]}"
            return None

        for alt_separator in (" — ", " – ", " - ", ":", " —", "— ", " –", "– ", " -", "- "):
            if alt_separator not in cleaned:
                continue
            parts = [part.strip() for part in cleaned.split(alt_separator)]
            if len(parts) == 2 and all(parts):
                return f"{parts[0]}{separator}{parts[1]}"
        return None

    @staticmethod
    def _strip_title_leading_marker(title: str) -> str:
        return re.sub(r"^\s*(?:[-*]|\d+[.)])\s*", "", title).strip()

    @staticmethod
    def _format_rule_block(rules: List[str]) -> str:
        if not rules:
            return ""
        formatted = "\n".join(f"- {rule}" for rule in rules)
        return f"Constraints:\n{formatted}\n"

    @staticmethod
    def _prompt_addendum_block(prompt_addendum: str) -> str:
        prompt = prompt_addendum.strip()
        if not prompt:
            return ""
        return f"{prompt}\n"

    @staticmethod
    def _examples_block(examples: str) -> str:
        if not examples.strip():
            return ""
        return f"Examples:\n{examples}\n"

    def _separator_prompt_block(self) -> str:
        title_settings = self.settings.openai.title_generation
        if not title_settings.require_separator:
            return ""
        separator = title_settings.separator
        return (
            f"Use the exact two-part structure `X{separator}Y`.\n"
            f"Use exactly one `{separator}` separator in each title.\n"
            "Let the first part mirror the broad packaging style suggested by the examples when relevant.\n"
            "Let the second part be specifically adapted to the current visual.\n"
        )

    def _visual_prompt_parts_for_title_generation(self, visual_asset: VisualAsset, working_dir: Path | None) -> List[dict]:
        if not self.settings.openai.title_generation.use_visual_input:
            return []
        return self._visual_prompt_parts(visual_asset, working_dir)

    def _visual_prompt_parts(self, visual_asset: VisualAsset, working_dir: Path | None) -> List[dict]:
        if visual_asset.kind == "image":
            return [{"type": "input_image", "image_url": img_to_data_url(visual_asset.path)}]

        preview_path = None
        if working_dir is not None:
            preview_path = extract_video_frame(
                visual_asset.path,
                working_dir / "artifacts" / "visual_preview.jpg",
            )
        if preview_path:
            return [
                {
                    "type": "input_text",
                    "text": f"The visual source is a video clip named {visual_asset.original_name}. Use the extracted preview frame and infer a calm devotional atmosphere from it.",
                },
                {"type": "input_image", "image_url": img_to_data_url(preview_path)},
            ]
        return [
            {
                "type": "input_text",
                "text": (
                    f"The visual source is a video clip named {visual_asset.original_name}. "
                    "No preview frame is available, so infer a calm devotional atmosphere from the clip context and filename only."
                ),
            }
        ]
