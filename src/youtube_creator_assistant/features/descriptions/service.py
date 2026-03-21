from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Sequence

from youtube_creator_assistant.core.config import Settings
from youtube_creator_assistant.core.models import VideoProject, VisualAsset
from youtube_creator_assistant.core.utils import extract_video_frame, img_to_data_url
from youtube_creator_assistant.providers.openai_client import OpenAIProvider


@dataclass(frozen=True)
class DescriptionPreset:
    variant: str
    section_heading: str
    chapters_heading: str
    intro_prompt: str
    intro_required_prefix: str
    theme_prompt: str
    theme_required_prefix: str
    importance_required_prefix_1: str
    importance_required_prefix_2: str
    fallback_intro_with_title: str
    fallback_intro_without_title: str
    fallback_theme_prefix: str
    fallback_importance_line_1_with_themes: str
    fallback_importance_line_1_without_themes: str
    fallback_importance_line_2_with_themes: str
    fallback_importance_line_2_without_themes: str
    audio_prompt: str
    audio_fallback_explanation: str


PRESETS: dict[str, DescriptionPreset] = {
    "shepherd_legacy": DescriptionPreset(
        variant="shepherd_legacy",
        section_heading="Scripture Journey Notes",
        chapters_heading="All chapter timestamps are listed below in full:",
        intro_prompt=(
            "You write one intro line for a Christian YouTube description.\n"
            "Write in ENGLISH only.\n"
            'Return STRICT JSON only: {"intro_line":"..."}\n\n'
            "Rules:\n"
            "• Exactly one sentence.\n"
            "• Must start exactly with 'Welcome, child of God,'.\n"
            "• Warm, reverent, calming devotional tone.\n"
            "• Keep concise (about 16 to 30 words).\n"
            "• Reflect the title and validated themes.\n"
            "• No hashtags, no CTA, no extra keys, no prose outside JSON.\n"
        ),
        intro_required_prefix="Welcome, child of God,",
        theme_prompt=(
            "You write the theme context block for a Christian YouTube description.\n"
            "Write in ENGLISH only.\n"
            "Return STRICT JSON only in this format:\n"
            '{"theme_line":"...","importance_line_1":"...","importance_line_2":"..."}\n\n'
            "Rules:\n"
            "• theme_line must start exactly with: 'For this video, our central themes are: '.\n"
            "• theme_line must list the themes with roman numerals: i), ii), iii)...\n"
            "• importance_line_1 must start exactly with: 'Why these themes matter in Christian faith: '.\n"
            "• importance_line_2 must start exactly with: 'How sacred Scripture carries these themes: '.\n"
            "• Both importance lines must be specific and concrete, not generic filler.\n"
            "• Mention at least one validated theme name directly in the importance lines.\n"
            "• Reflect only the provided validated themes.\n"
            "• Warm, reverent, calming tone.\n"
            "• No hashtags, no CTA, no bullets, no extra keys, no prose outside JSON.\n"
        ),
        theme_required_prefix="For this video, our central themes are: ",
        importance_required_prefix_1="Why these themes matter in Christian faith: ",
        importance_required_prefix_2="How sacred Scripture carries these themes: ",
        fallback_intro_with_title=(
            'Welcome, child of God, to a quiet Christian reflection through "{title}", '
            "where we receive Christ's mercy, steadiness, and peace."
        ),
        fallback_intro_without_title=(
            "Welcome, child of God, to a quiet Christian reflection where we receive Christ's mercy, "
            "steadiness, and peace."
        ),
        fallback_theme_prefix="For this video, our central themes are: ",
        fallback_importance_line_1_with_themes=(
            "Why these themes matter in Christian faith: {themes} call believers to trust Christ under pressure, "
            "practice surrender in prayer, and remain rooted in faithful obedience."
        ),
        fallback_importance_line_1_without_themes=(
            "Why these themes matter in Christian faith: they call believers to trust Christ under pressure, "
            "practice surrender in prayer, and remain rooted in faithful obedience."
        ),
        fallback_importance_line_2_with_themes=(
            "How sacred Scripture carries these themes: across psalms and Gospel passages, {themes} are shown as "
            "living realities that reshape fear into trust and weariness into hope."
        ),
        fallback_importance_line_2_without_themes=(
            "How sacred Scripture carries these themes: across psalms and Gospel passages, God forms His people "
            "to move from fear into trust and from weariness into hope."
        ),
        audio_prompt=(
            "You are a devotional audio curator.\n"
            "Write in ENGLISH only.\n"
            "For each of the first 5 audio tracks, explain why it was selected for this video.\n"
            "Provide explanation text only (the chapter/timestamp heading is formatted separately by the system).\n\n"
            "Return STRICT JSON only in this format:\n"
            '{"audio_explanations":[{"audio":"<exact audio line>","explanation":"4 to 6 sentences"}]}\n'
            "Rules:\n"
            "• Explanation must be 4 to 6 natural sentences.\n"
            "• No bullet points in the explanation text.\n"
            "• Do NOT start the explanation by repeating the chapter/psalm reference.\n"
            "• Do NOT start with generic openers like 'This track was chosen because' or 'This passage was chosen because'.\n"
            "• Avoid repeated sentence openings; do not start multiple consecutive sentences with 'It'.\n"
            "• Preserve the exact input audio line in the 'audio' field.\n"
            "• Output items count must match provided focused tracks.\n"
            "• No extra keys, no prose outside JSON.\n"
        ),
        audio_fallback_explanation=(
            "Centers the listening flow around a clear spiritual movement that fits the selected themes. "
            "Its emotional pacing supports prayerful attention and helps the audience settle without rushing. "
            "The passage language also connects naturally with the surrounding chapter order. "
            "This passage strengthens continuity across the full long-form reflection and supports a coherent devotional arc."
        ),
    ),
    "mercy_legacy": DescriptionPreset(
        variant="mercy_legacy",
        section_heading="Scripture Journey Notes",
        chapters_heading="All chapter timestamps are listed below in full.",
        intro_prompt=(
            "You write one intro line for a Christian YouTube description.\n"
            "Write in ENGLISH only.\n"
            'Return STRICT JSON only: {"intro_line":"..."}\n\n'
            "Rules:\n"
            "• Exactly one sentence.\n"
            "• Must start with 'Welcome'.\n"
            "• Warm, reverent, calming devotional tone.\n"
            "• Keep concise (about 16 to 30 words).\n"
            "• Reflect the title and validated themes.\n"
            "• No hashtags, no CTA, no extra keys, no prose outside JSON.\n"
        ),
        intro_required_prefix="Welcome",
        theme_prompt=(
            "You write the theme context block for a Christian YouTube description.\n"
            "Write in ENGLISH only.\n"
            "Return STRICT JSON only in this format:\n"
            '{"theme_line":"...","importance_line_1":"...","importance_line_2":"..."}\n\n'
            "Rules:\n"
            "• theme_line must start exactly with: 'For this video, our central themes are: '.\n"
            "• theme_line must list the themes with roman numerals: i), ii), iii)...\n"
            "• importance_line_1 must start exactly with: 'Why these themes matter in Christian faith: '.\n"
            "• importance_line_2 must start exactly with: 'How sacred Scripture carries these themes: '.\n"
            "• Both importance lines must be specific and concrete, not generic filler.\n"
            "• Mention at least one validated theme name directly in the importance lines.\n"
            "• Reflect only the provided validated themes.\n"
            "• Warm, reverent, calming tone.\n"
            "• No hashtags, no CTA, no bullets, no extra keys, no prose outside JSON.\n"
        ),
        theme_required_prefix="For this video, our central themes are: ",
        importance_required_prefix_1="Why these themes matter in Christian faith: ",
        importance_required_prefix_2="How sacred Scripture carries these themes: ",
        fallback_intro_with_title=(
            'Welcome, beloved soul, to a quiet Christian reflection through "{title}", '
            "where we receive Christ's mercy, steadiness, and peace."
        ),
        fallback_intro_without_title=(
            "Welcome, beloved soul, to a quiet Christian reflection where we receive Christ's mercy, steadiness, and peace."
        ),
        fallback_theme_prefix="For this video, our central themes are: ",
        fallback_importance_line_1_with_themes=(
            "Why these themes matter in Christian faith: {themes} call believers to trust Christ under pressure, "
            "practice surrender in prayer, and remain rooted in faithful obedience."
        ),
        fallback_importance_line_1_without_themes=(
            "Why these themes matter in Christian faith: they call believers to trust Christ under pressure, "
            "practice surrender in prayer, and remain rooted in faithful obedience."
        ),
        fallback_importance_line_2_with_themes=(
            "How sacred Scripture carries these themes: across psalms and Gospel passages, {themes} are shown as "
            "living realities that reshape fear into trust and weariness into hope."
        ),
        fallback_importance_line_2_without_themes=(
            "How sacred Scripture carries these themes: across psalms and Gospel passages, God forms His people "
            "to move from fear into trust and from weariness into hope."
        ),
        audio_prompt=(
            "You are a devotional audio curator.\n"
            "Write in ENGLISH only.\n"
            "For each of the first 5 audio tracks, explain why it was selected for this video.\n"
            "Provide explanation text only (the chapter/timestamp heading is formatted separately by the system).\n\n"
            "Return STRICT JSON only in this format:\n"
            '{"audio_explanations":[{"audio":"<exact audio line>","explanation":"4 to 6 sentences"}]}\n'
            "Rules:\n"
            "• Explanation must be 4 to 6 natural sentences.\n"
            "• No bullet points in the explanation text.\n"
            "• Do NOT start the explanation by repeating the chapter/psalm reference.\n"
            "• Do NOT start with generic openers like 'This track was chosen because' or 'This passage was chosen because'.\n"
            "• Avoid repeated sentence openings; do not start multiple consecutive sentences with 'It'.\n"
            "• Preserve the exact input audio line in the 'audio' field.\n"
            "• Output items count must match provided focused tracks.\n"
            "• No extra keys, no prose outside JSON.\n"
        ),
        audio_fallback_explanation=(
            "Centers the listening flow around a clear spiritual movement that fits the selected themes. "
            "Its emotional pacing supports prayerful attention and helps the audience settle without rushing. "
            "The passage language also connects naturally with the surrounding chapter order. "
            "This passage strengthens continuity across the full long-form reflection and supports a coherent devotional arc."
        ),
    ),
    "vibespro_legacy": DescriptionPreset(
        variant="vibespro_legacy",
        section_heading="How Scripture guides today's meditation",
        chapters_heading="All chapter timestamps are listed below in full:",
        intro_prompt=(
            "You write one intro line for a Christian YouTube description.\n"
            "Write in ENGLISH only.\n"
            'Return STRICT JSON only: {"intro_line":"..."}\n\n'
            "Rules:\n"
            "• Exactly one sentence.\n"
            "• Must start with 'Today we'.\n"
            "• Warm, reverent, calming devotional tone.\n"
            "• Keep concise (about 16 to 30 words).\n"
            "• Reflect the title and validated themes.\n"
            "• No hashtags, no CTA, no extra keys, no prose outside JSON.\n"
        ),
        intro_required_prefix="Today we",
        theme_prompt=(
            "You write the theme context block for a Christian YouTube description.\n"
            "Write in ENGLISH only.\n"
            'Return STRICT JSON only in this format:\n{"theme_line":"...","importance_line_1":"...","importance_line_2":"..."}\n\n'
            "Rules:\n"
            "• theme_line must start exactly with: 'The themes of today's video are: '\n"
            "• theme_line must list the themes with roman numerals: i), ii), iii)...\n"
            "• importance_line_1: one sentence explaining why these themes matter in Christianity.\n"
            "• importance_line_2: one sentence linking these themes to sacred Scripture.\n"
            "• Both importance lines must be specific and concrete, not generic filler.\n"
            "• Mention at least one validated theme name directly in the importance lines.\n"
            "• Reflect only the provided validated themes.\n"
            "• Warm, reverent, calming tone.\n"
            "• No hashtags, no CTA, no bullets, no extra keys, no prose outside JSON.\n"
        ),
        theme_required_prefix="The themes of today's video are: ",
        importance_required_prefix_1="",
        importance_required_prefix_2="",
        fallback_intro_with_title=(
            'Today we enter a quiet Christian meditation through "{title}", bringing our burdens to Christ and '
            "asking for renewed peace and faith."
        ),
        fallback_intro_without_title=(
            "Today we enter a quiet Christian meditation, bringing our burdens to Christ and asking for renewed peace and faith."
        ),
        fallback_theme_prefix="The themes of today's video are: ",
        fallback_importance_line_1_with_themes=(
            "In Christianity, these themes of {themes} call believers to trust Christ in weakness, persevere in prayer, and walk in faithful obedience."
        ),
        fallback_importance_line_1_without_themes=(
            "In Christianity, these themes call believers to trust Christ in weakness, persevere in prayer, and walk in faithful obedience."
        ),
        fallback_importance_line_2_with_themes=(
            "In sacred Scripture, these themes of {themes} appear through psalms of refuge and Gospel calls to rest, training believers to trust God with a steadier heart."
        ),
        fallback_importance_line_2_without_themes=(
            "Across sacred Scripture, God forms His people through psalms of refuge and Gospel calls to rest, teaching hearts to trust His presence under pressure."
        ),
        audio_prompt=(
            "You are a devotional audio curator.\n"
            "Write in ENGLISH only.\n"
            "For each of the first 5 audio tracks, explain why it was selected for this video.\n"
            "Provide explanation text only (the chapter/psalm heading is formatted separately by the system).\n\n"
            "Return STRICT JSON only in this format:\n"
            '{"audio_explanations":[{"audio":"<exact audio line>","explanation":"4 to 6 sentences"}]}\n'
            "Rules:\n"
            "• Explanation must be 4 to 6 natural sentences.\n"
            "• No bullet points in the explanation text.\n"
            "• Do NOT start the explanation by repeating the chapter/psalm reference.\n"
            "• Do NOT start with generic openers like 'This track was chosen because' or 'This passage was chosen because'.\n"
            "• Avoid repeated sentence openings; do not start multiple consecutive sentences with 'It'.\n"
            "• Preserve the exact input audio line in the 'audio' field.\n"
            "• Output items count must match provided focused tracks.\n"
            "• No extra keys, no prose outside JSON.\n"
        ),
        audio_fallback_explanation=(
            "This passage supports the spiritual direction of the title and reinforces the selected themes with a coherent devotional mood. "
            "Its pacing helps listeners settle into prayer and reflection, while its emotional movement fits the surrounding chapters. "
            "It also strengthens continuity across the full long-form listening session."
        ),
    ),
}


class DescriptionService:
    def __init__(self, settings: Settings, provider: OpenAIProvider | None = None):
        self.settings = settings
        self.provider = provider or OpenAIProvider()

    def build_description(self, project: VideoProject) -> str:
        preset = self._preset()
        chapters = [self._normalize_english_scripture_names(f"{entry.timestamp} - {entry.label}") for entry in project.chapters]
        audio_count = max(0, int(self.settings.description.audio_explanation_count or 0))
        audio_labels = [track.label for track in project.audio_tracks[:audio_count]]
        timestamps = [entry.timestamp for entry in project.chapters[:audio_count]]

        intro_line = self._build_intro_line(
            preset=preset,
            visual_asset=project.visual_asset,
            working_dir=project.project_dir,
            chosen_title=project.selected_title or "",
            validated_themes=project.themes,
        )
        theme_line, importance_line_1, importance_line_2 = self._build_theme_context_lines(
            preset=preset,
            visual_asset=project.visual_asset,
            working_dir=project.project_dir,
            chosen_title=project.selected_title or "",
            validated_themes=project.themes,
        )
        audio_explanations = self._build_audio_explanations(
            preset=preset,
            visual_asset=project.visual_asset,
            working_dir=project.project_dir,
            chosen_title=project.selected_title or "",
            validated_themes=project.themes,
            audio_tracks=audio_labels,
            timestamps=timestamps,
        )

        lines: List[str] = [
            intro_line,
            "",
            theme_line,
            importance_line_1,
            importance_line_2,
            "",
            preset.section_heading,
        ]
        if audio_explanations:
            lines.append("")
            for idx, block in enumerate(audio_explanations):
                if idx > 0:
                    lines.append("")
                lines.append(block)

        lines.extend(["", preset.chapters_heading])
        if chapters:
            lines.extend(chapters)
        else:
            lines.append("0:00:00 - Intro")

        text = "\n".join(lines).strip()
        (project.project_dir / "yt_video_description.txt").write_text(text, encoding="utf-8")
        project.description_text = text
        return text

    def _build_intro_line(
        self,
        preset: DescriptionPreset,
        visual_asset: VisualAsset,
        working_dir: Path,
        chosen_title: str,
        validated_themes: Sequence[str],
    ) -> str:
        themes_text = "\n".join(f"- {theme}" for theme in self._clean_lines(validated_themes))
        fallback = self._fallback_intro_line(preset, chosen_title)
        try:
            response = self.provider.client().responses.create(
                model=self.settings.openai.model,
                input=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": preset.intro_prompt},
                            {"type": "input_text", "text": f"VIDEO TITLE: {chosen_title}"},
                            {"type": "input_text", "text": f"VALIDATED THEMES:\n{themes_text}"},
                            *self._visual_prompt_parts(visual_asset, working_dir),
                        ],
                    }
                ],
            )
            payload = self._extract_json(response.output_text.strip())
            intro_line = self._normalize_single_line(str(payload.get("intro_line", "")))
            if not intro_line:
                return fallback
            if not intro_line.startswith(preset.intro_required_prefix):
                if preset.variant == "vibespro_legacy" and preset.intro_required_prefix == "Today we":
                    return f"Today we {intro_line[0].lower() + intro_line[1:]}" if intro_line else fallback
                if preset.variant == "mercy_legacy" and preset.intro_required_prefix == "Welcome":
                    return f"Welcome, {intro_line[0].lower() + intro_line[1:]}" if intro_line else fallback
                return fallback
            return intro_line
        except Exception:
            return fallback

    def _build_theme_context_lines(
        self,
        preset: DescriptionPreset,
        visual_asset: VisualAsset,
        working_dir: Path,
        chosen_title: str,
        validated_themes: Sequence[str],
    ) -> tuple[str, str, str]:
        themes_text = "\n".join(f"- {theme}" for theme in self._clean_lines(validated_themes))
        fallback_theme_line = self._fallback_theme_line(preset, validated_themes)
        fallback_importance_1 = self._fallback_importance_line_1(preset, validated_themes)
        fallback_importance_2 = self._fallback_importance_line_2(preset, validated_themes)
        try:
            response = self.provider.client().responses.create(
                model=self.settings.openai.model,
                input=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": preset.theme_prompt},
                            {"type": "input_text", "text": f"VIDEO TITLE: {chosen_title}"},
                            {"type": "input_text", "text": f"VALIDATED THEMES:\n{themes_text}"},
                            *self._visual_prompt_parts(visual_asset, working_dir),
                        ],
                    }
                ],
            )
            payload = self._extract_json(response.output_text.strip())
            theme_line = self._normalize_theme_line(
                preset,
                self._normalize_single_line(str(payload.get("theme_line", ""))),
                validated_themes,
            )
            importance_line_1 = self._normalize_single_line(str(payload.get("importance_line_1", "")))
            importance_line_2 = self._normalize_single_line(str(payload.get("importance_line_2", "")))

            if preset.importance_required_prefix_1:
                if not importance_line_1.startswith(preset.importance_required_prefix_1):
                    importance_line_1 = fallback_importance_1
            elif not importance_line_1:
                importance_line_1 = fallback_importance_1

            if preset.importance_required_prefix_2:
                if not importance_line_2.startswith(preset.importance_required_prefix_2):
                    importance_line_2 = fallback_importance_2
            elif not importance_line_2:
                importance_line_2 = fallback_importance_2

            if not importance_line_1:
                importance_line_1 = fallback_importance_1
            if not importance_line_2:
                importance_line_2 = fallback_importance_2
            return theme_line, importance_line_1, importance_line_2
        except Exception:
            return fallback_theme_line, fallback_importance_1, fallback_importance_2

    def _build_audio_explanations(
        self,
        preset: DescriptionPreset,
        visual_asset: VisualAsset,
        working_dir: Path,
        chosen_title: str,
        validated_themes: Sequence[str],
        audio_tracks: Sequence[str],
        timestamps: Sequence[str],
    ) -> List[str]:
        focused_tracks = [track.strip() for track in audio_tracks if isinstance(track, str) and track.strip()]
        if not focused_tracks:
            return []
        focused_timestamps = [
            timestamp.strip() for timestamp in timestamps if isinstance(timestamp, str) and timestamp.strip()
        ][: len(focused_tracks)]
        themes_text = "\n".join(f"- {theme}" for theme in self._clean_lines(validated_themes))
        tracks_text = "\n".join(f"{idx + 1}. {track}" for idx, track in enumerate(focused_tracks))
        explanations_by_audio: dict[str, str] = {}
        try:
            response = self.provider.client().responses.create(
                model=self.settings.openai.model,
                input=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": preset.audio_prompt},
                            {"type": "input_text", "text": f"VIDEO TITLE: {chosen_title}"},
                            {"type": "input_text", "text": f"VALIDATED THEMES:\n{themes_text}"},
                            {"type": "input_text", "text": f"AUDIO TRACKS (first 5, ordered):\n{tracks_text}"},
                            *self._visual_prompt_parts(visual_asset, working_dir),
                        ],
                    }
                ],
            )
            payload = self._extract_json(response.output_text.strip())
            for item in payload.get("audio_explanations", []):
                if not isinstance(item, dict):
                    continue
                audio = item.get("audio")
                explanation = item.get("explanation")
                if isinstance(audio, str) and audio.strip() and isinstance(explanation, str) and explanation.strip():
                    explanations_by_audio[audio.strip()] = explanation.strip()
        except Exception:
            explanations_by_audio = {}

        output: List[str] = []
        for idx, track in enumerate(focused_tracks, start=1):
            ref_label = self._audio_reference_label(track)
            timestamp = focused_timestamps[idx - 1] if idx - 1 < len(focused_timestamps) else "N/A"
            spotlight = self._spotlight_reference_with_timestamp(ref_label, timestamp)
            explanation = explanations_by_audio.get(track) or preset.audio_fallback_explanation
            explanation = self._normalize_english_scripture_names(explanation)
            explanation = self._drop_redundant_reference_prefix(explanation, ref_label)
            explanation = self._drop_repetitive_openers(explanation)
            explanation = self._reduce_it_sentence_repetition(explanation)
            explanation = self._normalize_explanation_start(explanation)
            output.append(f"{spotlight}\n{explanation}")
        return output

    def _preset(self) -> DescriptionPreset:
        variant = self.settings.description.variant
        if variant not in PRESETS:
            raise ValueError(f"Unknown description variant: {variant}")
        return PRESETS[variant]

    def _fallback_intro_line(self, preset: DescriptionPreset, chosen_title: str) -> str:
        title = self._normalize_single_line(chosen_title)
        if title:
            return preset.fallback_intro_with_title.format(title=title)
        return preset.fallback_intro_without_title

    def _fallback_theme_line(self, preset: DescriptionPreset, validated_themes: Sequence[str]) -> str:
        themes = self._clean_lines(validated_themes)
        if not themes:
            themes = ["Peace", "Trust in God"]
        roman = ("i", "ii", "iii", "iv", "v")
        labeled = []
        for idx, theme in enumerate(themes):
            label = roman[idx] if idx < len(roman) else str(idx + 1)
            labeled.append(f"{label}) {theme}")
        return f"{preset.fallback_theme_prefix}{'; '.join(labeled)}."

    def _normalize_theme_line(
        self,
        preset: DescriptionPreset,
        theme_line: str,
        validated_themes: Sequence[str],
    ) -> str:
        line = self._normalize_single_line(theme_line)
        if not line:
            return self._fallback_theme_line(preset, validated_themes)
        if not line.startswith(preset.theme_required_prefix):
            line = f"{preset.theme_required_prefix}{line}"
        if "i)" not in line.lower():
            return self._fallback_theme_line(preset, validated_themes)
        if not line.endswith("."):
            line = f"{line}."
        return line

    def _fallback_importance_line_1(self, preset: DescriptionPreset, validated_themes: Sequence[str]) -> str:
        themes = ", ".join(self._clean_lines(validated_themes)[:3])
        if themes:
            return preset.fallback_importance_line_1_with_themes.format(themes=themes)
        return preset.fallback_importance_line_1_without_themes

    def _fallback_importance_line_2(self, preset: DescriptionPreset, validated_themes: Sequence[str]) -> str:
        themes = ", ".join(self._clean_lines(validated_themes)[:3])
        if themes:
            return preset.fallback_importance_line_2_with_themes.format(themes=themes)
        return preset.fallback_importance_line_2_without_themes

    def _visual_prompt_parts(self, visual_asset: VisualAsset, working_dir: Path) -> List[dict]:
        if visual_asset.kind == "image":
            return [{"type": "input_image", "image_url": img_to_data_url(visual_asset.path)}]
        preview_path = extract_video_frame(
            visual_asset.path,
            working_dir / "artifacts" / "description_visual_preview.jpg",
        )
        if preview_path is not None:
            return [{"type": "input_image", "image_url": img_to_data_url(preview_path)}]
        return [
            {
                "type": "input_text",
                "text": (
                    f"The visual source is a video clip named {visual_asset.original_name}. "
                    "No preview frame is available, so infer the devotional atmosphere from the clip context only."
                ),
            }
        ]

    @staticmethod
    def _audio_reference_label(audio_line: str) -> str:
        raw = (audio_line or "").strip()
        if not raw:
            return "Unknown reference"
        if "|" in raw:
            raw = raw.split("|", 1)[0].strip() or raw
        return DescriptionService._normalize_english_scripture_names(raw)

    @staticmethod
    def _spotlight_reference_with_timestamp(label: str, timestamp: str) -> str:
        clean_label = (label or "").strip().upper() or "UNKNOWN REFERENCE"
        clean_timestamp = (timestamp or "").strip() or "N/A"
        return f"[Scripture Spotlight: {clean_label} | {clean_timestamp}]"

    @staticmethod
    def _drop_redundant_reference_prefix(explanation: str, ref_label: str) -> str:
        text = (explanation or "").strip()
        ref = (ref_label or "").strip()
        if not text or not ref:
            return text
        ref_pat = re.escape(ref)
        patterns = [
            rf"^\s*\[\s*scripture\s+spotlight\s*:\s*{ref_pat}[^\]]*\]\s*[:\-–—]\s*",
            rf"^\s*===\s*{ref_pat}\s*===\s*[:\-–—]\s*",
            rf"^\s*{ref_pat}\s*[:\-–—]\s*",
            rf"^\s*{ref_pat}\s+",
        ]
        for pattern in patterns:
            text = re.sub(pattern, "", text, flags=re.IGNORECASE)
        return text.strip()

    @staticmethod
    def _drop_repetitive_openers(explanation: str) -> str:
        text = (explanation or "").strip()
        if not text:
            return text
        patterns = [
            r"^\s*this\s+track\s+was\s+chosen\s+because\s+(?:it\s+)?",
            r"^\s*this\s+track\s+was\s+selected\s+because\s+(?:it\s+)?",
            r"^\s*this\s+passage\s+was\s+chosen\s+because\s+(?:it\s+)?",
            r"^\s*this\s+passage\s+was\s+selected\s+because\s+(?:it\s+)?",
        ]
        for pattern in patterns:
            text = re.sub(pattern, "", text, flags=re.IGNORECASE)
        return text.strip()

    @staticmethod
    def _reduce_it_sentence_repetition(explanation: str) -> str:
        text = (explanation or "").strip()
        if not text:
            return text
        sentences = re.split(r"(?<=[.!?])\s+", text)
        output: List[str] = []
        consecutive_it = 0
        for sentence in sentences:
            item = sentence.strip()
            if not item:
                continue
            if re.match(r"^it\b", item, flags=re.IGNORECASE):
                consecutive_it += 1
                if consecutive_it >= 1:
                    item = re.sub(r"^it\b", "This passage", item, count=1, flags=re.IGNORECASE)
            else:
                consecutive_it = 0
            output.append(item)
        return " ".join(output).strip()

    @staticmethod
    def _normalize_explanation_start(explanation: str) -> str:
        text = (explanation or "").strip()
        if not text:
            return text
        first_char = text[0]
        if first_char.isalpha():
            return first_char.upper() + text[1:]
        return text

    @staticmethod
    def _clean_lines(items: Sequence[str]) -> List[str]:
        return [line.strip() for line in items if isinstance(line, str) and line.strip()]

    @staticmethod
    def _normalize_single_line(text: str) -> str:
        return re.sub(r"\s+", " ", (text or "").strip())

    @staticmethod
    def _normalize_english_scripture_names(text: str) -> str:
        value = text or ""
        pattern = re.compile(r"\bMarc\b", flags=re.IGNORECASE)
        return pattern.sub(lambda match: DescriptionService._match_case("Mark", match.group(0)), value)

    @staticmethod
    def _match_case(replacement: str, original: str) -> str:
        if original.isupper():
            return replacement.upper()
        if original.islower():
            return replacement.lower()
        if original[:1].isupper() and original[1:].islower():
            return replacement.capitalize()
        return replacement

    @staticmethod
    def _extract_json(raw: str) -> dict:
        text = raw.strip()
        if not text.startswith("{"):
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1 and end > start:
                text = text[start : end + 1]
        return json.loads(text)
