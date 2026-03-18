from __future__ import annotations

import json
import re
from typing import List

from youtube_creator_assistant.core.config import Settings
from youtube_creator_assistant.core.models import VideoProject
from youtube_creator_assistant.providers.openai_client import OpenAIProvider


class DescriptionService:
    def __init__(self, settings: Settings, provider: OpenAIProvider | None = None):
        self.settings = settings
        self.provider = provider or OpenAIProvider()

    def build_description(self, project: VideoProject) -> VideoProject:
        refs = [track.label for track in project.audio_tracks[: self.settings.workflow.max_reference_summaries]]
        refs_block = "\n".join(f"- {ref}" for ref in refs)
        themes_block = "\n".join(f"- {theme}" for theme in project.themes)
        response = self.provider.client().responses.create(
            model=self.settings.openai.model,
            input=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": (
                                "Write a YouTube devotional video description as strict JSON.\n"
                                "We need:\n"
                                "- intro: 2 to 4 sentences\n"
                                "- themes_intro: 1 sentence introducing the themes\n"
                                "- reference_notes: one short note for each listed reference\n"
                                "- closing: 1 to 2 sentences\n"
                                "Keep it warm, reverent, and clear.\n"
                                'Return only: {"intro": "...", "themes_intro": "...", "reference_notes": [{"ref": "...", "summary": "..."}], "closing": "..."}'
                            ),
                        },
                        {"type": "input_text", "text": f"Title: {project.selected_title or ''}"},
                        {"type": "input_text", "text": f"Themes:\n{themes_block}"},
                        {"type": "input_text", "text": f"References:\n{refs_block}"},
                    ],
                }
            ],
        )
        payload = self._extract_json(response.output_text)
        intro = str(payload.get("intro", "")).strip()
        themes_intro = str(payload.get("themes_intro", "")).strip()
        closing = str(payload.get("closing", "")).strip()
        notes = payload.get("reference_notes", [])
        note_lines: List[str] = []
        for note in notes[: len(refs)]:
            if not isinstance(note, dict):
                continue
            ref = str(note.get("ref", "")).strip()
            summary = str(note.get("summary", "")).strip()
            if ref and summary:
                note_lines.append(f"- {ref}: {summary}")

        description = "\n\n".join(
            block
            for block in [
                project.selected_title or "",
                intro,
                "Themes\n" + themes_intro + ("\n" + themes_block if themes_block else ""),
                "First references\n" + "\n".join(note_lines),
                closing,
            ]
            if block.strip()
        )
        project.description_text = description
        (project.project_dir / "yt_video_description.txt").write_text(description, encoding="utf-8")
        return project

    def _extract_json(self, text: str) -> dict:
        raw = text.strip()
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if not match:
                raise RuntimeError("OpenAI response did not contain JSON.")
            return json.loads(match.group(0))
