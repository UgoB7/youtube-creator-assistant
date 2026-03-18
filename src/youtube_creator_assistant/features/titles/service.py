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
        examples = "\n".join(
            f"- {item}" for item in split_examples(self.settings.openai.devotional_examples_input)
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
                                "You craft devotional YouTube titles.\n"
                                "Look at the image and return exactly 20 titles as JSON only.\n"
                                "Constraints:\n"
                                "- tone: prayer, surrender, peace, comfort, hope\n"
                                "- keep them relevant to the image\n"
                                "- no emojis, no hashtags, no all caps\n"
                                "- use soft punctuation when natural\n"
                                f"Examples:\n{examples}\n\n"
                                'Return only: {"titles": ["t1", "...", "t20"]}'
                            ),
                        },
                        *self._visual_prompt_parts(visual_asset, working_dir),
                    ],
                }
            ],
        )
        payload = self._extract_json(response.output_text)
        raw_titles = payload.get("titles", [])
        titles = [item.strip() for item in raw_titles if isinstance(item, str) and item.strip()]
        titles = dedupe_preserve_order(titles)
        if len(titles) < 5:
            raise RuntimeError("OpenAI returned too few titles.")
        return titles[:20]

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
        tracks_text = "\n".join(f"- {label}" for label in audio_labels[:12])
        response = self.provider.client().responses.create(
            model=self.settings.openai.model,
            input=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": (
                                "You create short YouTube devotional themes.\n"
                                "Using the title, image, and selected audio chapters, return exactly 5 themes.\n"
                                "- 1 to 4 words each\n"
                                "- spiritually focused\n"
                                "- aligned with the chosen title\n"
                                'Return only: {"themes": ["...", "...", "...", "...", "..."]}'
                            ),
                        },
                        {"type": "input_text", "text": f"Title: {selected_title}"},
                        {"type": "input_text", "text": f"Audio:\n{tracks_text}"},
                        *self._visual_prompt_parts(visual_asset, working_dir),
                    ],
                }
            ],
        )
        payload = self._extract_json(response.output_text)
        themes = [item.strip() for item in payload.get("themes", []) if isinstance(item, str) and item.strip()]
        themes = dedupe_preserve_order(themes)
        if len(themes) < 3:
            raise RuntimeError("OpenAI returned too few themes.")
        return themes[:5]

    def _extract_json(self, text: str) -> dict:
        raw = text.strip()
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if not match:
                raise RuntimeError("OpenAI response did not contain JSON.")
            return json.loads(match.group(0))

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
