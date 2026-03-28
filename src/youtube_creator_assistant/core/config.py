from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


def _expand_path(value: str | Path, base_dir: Path) -> Path:
    raw = Path(value).expanduser()
    if raw.is_absolute():
        return raw
    return (base_dir / raw).resolve()


@dataclass
class ProfileSettings:
    id: str
    display_name: str
    visual_input_mode: str


@dataclass
class PathSettings:
    runtime_root: Path
    outputs_dir: Path
    incoming_dir: Path
    images_dir: Path
    logs_dir: Path
    psalms_dir: Path
    gospel_dir: Path


@dataclass
class WorkflowSettings:
    fps: int = 30
    target_duration_tc: str = "3:33:32:20"
    trim_first_audio_seconds: float = 3.2
    include_gospel: bool = True
    max_head_items: Optional[int] = 3
    max_reference_summaries: int = 5
    preferred_reference_count: int = 16
    allow_repeats: bool = True
    use_title_reference_guidance: bool = True
    selection_seed_mode: str = "project_stable"
    max_selected_titles: int = 3
    audio_extensions: List[str] = field(default_factory=lambda: [".mp3"])


@dataclass
class ThumbnailSettings:
    max_bytes: int = 2 * 1024 * 1024
    target_bytes: int = 1_800_000
    suffix: str = "_yt"
    candidate_generation_enabled: bool = False
    idea_count: int = 4
    idea_prompt: str = ""
    candidate_model: str = "google/nano-banana-pro"
    candidate_resolution: str = "2K"
    candidate_aspect_ratio: str = "16:9"
    candidate_output_format: str = "jpg"
    candidate_safety_filter_level: str = "block_only_high"
    candidate_allow_fallback_model: bool = False


@dataclass
class TitleGenerationSettings:
    count: int = 20
    min_count: int = 5
    examples_input: str = ""
    use_visual_input: bool = True
    require_separator: bool = False
    separator: str = " — "
    prompt_addendum: str = ""
    rules: List[str] = field(
        default_factory=lambda: [
            "tone: prayer, surrender, peace, comfort, hope",
            "keep them relevant to the image",
            "no emojis, no hashtags, no all caps",
            "use soft punctuation when natural",
        ]
    )

    @classmethod
    def from_dict(
        cls,
        data: Optional[Dict[str, Any]],
        *,
        title_examples_input: str = "",
        devotional_examples_input: str = "",
    ) -> "TitleGenerationSettings":
        payload = data or {}
        raw_rules = payload.get("rules")
        if isinstance(raw_rules, list):
            rules = [str(item).strip() for item in raw_rules if str(item).strip()]
        else:
            rules = cls().rules
        examples_input = str(
            payload.get("examples_input")
            or title_examples_input
            or devotional_examples_input
            or ""
        )
        return cls(
            count=int(payload.get("count", 20)),
            min_count=int(payload.get("min_count", 5)),
            examples_input=examples_input,
            use_visual_input=bool(payload.get("use_visual_input", True)),
            require_separator=bool(payload.get("require_separator", False)),
            separator=str(payload.get("separator", " — ")),
            prompt_addendum=str(payload.get("prompt_addendum", "")),
            rules=rules,
        )


@dataclass
class ThemeGenerationSettings:
    count: int = 5
    min_count: int = 3
    use_visual_input: bool = True
    include_audio_context: bool = True
    prompt_addendum: str = ""
    rules: List[str] = field(
        default_factory=lambda: [
            "1 to 4 words each",
            "spiritually focused",
            "aligned with the chosen title",
        ]
    )

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "ThemeGenerationSettings":
        payload = data or {}
        raw_rules = payload.get("rules")
        if isinstance(raw_rules, list):
            rules = [str(item).strip() for item in raw_rules if str(item).strip()]
        else:
            rules = cls().rules
        return cls(
            count=int(payload.get("count", 5)),
            min_count=int(payload.get("min_count", 3)),
            use_visual_input=bool(payload.get("use_visual_input", True)),
            include_audio_context=bool(payload.get("include_audio_context", True)),
            prompt_addendum=str(payload.get("prompt_addendum", "")),
            rules=rules,
        )


@dataclass
class OpenAISettings:
    model: str = "gpt-5.2-2025-12-11"
    title_examples_input: str = ""
    devotional_examples_input: str = ""
    title_generation: TitleGenerationSettings = field(default_factory=TitleGenerationSettings)
    theme_generation: ThemeGenerationSettings = field(default_factory=ThemeGenerationSettings)

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "OpenAISettings":
        payload = data or {}
        title_examples_input = str(payload.get("title_examples_input", ""))
        devotional_examples_input = str(payload.get("devotional_examples_input", ""))
        return cls(
            model=str(payload.get("model", "gpt-5.2-2025-12-11")),
            title_examples_input=title_examples_input,
            devotional_examples_input=devotional_examples_input,
            title_generation=TitleGenerationSettings.from_dict(
                payload.get("title_generation"),
                title_examples_input=title_examples_input,
                devotional_examples_input=devotional_examples_input,
            ),
            theme_generation=ThemeGenerationSettings.from_dict(payload.get("theme_generation")),
        )


@dataclass
class DescriptionSettings:
    variant: str = "shepherd_legacy"
    audio_explanation_count: int = 5
    dynamic_intro_prompt: str = ""
    dynamic_intro_include_audio_context: bool = True


@dataclass
class VisualPromptGenerationSettings:
    enabled: bool = False
    system_prompt: str = ""
    user_prompt: str = "Analyze this image and return only the final single-paragraph generation prompt."
    variation_prompt: str = (
        "Generate one distinct prompt variation for candidate {ordinal} of {total}. "
        "Keep the core scene constraints intact while varying tasteful secondary details."
    )

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "VisualPromptGenerationSettings":
        payload = data or {}
        return cls(
            enabled=bool(payload.get("enabled", False)),
            system_prompt=str(payload.get("system_prompt", "")),
            user_prompt=str(
                payload.get(
                    "user_prompt",
                    "Analyze this image and return only the final single-paragraph generation prompt.",
                )
            ),
            variation_prompt=str(
                payload.get(
                    "variation_prompt",
                    (
                        "Generate one distinct prompt variation for candidate {ordinal} of {total}. "
                        "Keep the core scene constraints intact while varying tasteful secondary details."
                    ),
                )
            ),
        )


@dataclass
class ReplicateDebugSettings:
    enabled: bool = False
    reuse_candidate_batch: bool = False
    candidate_batch_id: str = ""
    candidate_batch_strategy: str = "explicit_or_latest"
    reuse_render_video: bool = False
    render_video_path: Optional[Path] = None

    @classmethod
    def from_dict(
        cls,
        data: Optional[Dict[str, Any]],
        *,
        base_dir: Path,
    ) -> "ReplicateDebugSettings":
        payload = data or {}
        render_video_path = payload.get("render_video_path")
        return cls(
            enabled=bool(payload.get("enabled", False)),
            reuse_candidate_batch=bool(payload.get("reuse_candidate_batch", False)),
            candidate_batch_id=str(payload.get("candidate_batch_id", "")),
            candidate_batch_strategy=str(payload.get("candidate_batch_strategy", "explicit_or_latest")),
            reuse_render_video=bool(payload.get("reuse_render_video", False)),
            render_video_path=_expand_path(render_video_path, base_dir) if render_video_path else None,
        )


@dataclass
class ReplicateSettings:
    enabled: bool = False
    allow_candidate_generation: bool = True
    candidate_count: int = 10
    prompt_style: str = "shepherd_legacy"
    prompt_batch_size: int = 0
    prompt_parallel_requests: int = 4
    image_prompt_prefix: str = ""
    image_prompt_suffix: str = ""
    prompt_seed_path: Path = field(default_factory=lambda: Path("./assets/prompts/shepherd_prompts.txt"))
    image_model: str = "bytedance/seedream-4"
    image_payload_style: str = "seedream"
    image_output_format: str = "png"
    image_size: str = "2K"
    image_width: int = 2048
    image_height: int = 2048
    image_max_images: int = 1
    image_aspect_ratio: str = "16:9"
    image_enhance_prompt: bool = False
    image_sequential_generation: str = "disabled"
    image_output_quality: int = 100
    image_safety_tolerance: int = 5
    video_model: str = "bytedance/seedance-1.5-pro"
    video_fps: int = 24
    video_duration: int = 12
    video_resolution: str = "1080p"
    video_aspect_ratio: str = "16:9"
    video_camera_fixed: bool = True
    video_generate_audio: bool = False
    video_prompt: str = "no camera movement. campfire. no smoke."
    visual_prompt_generation: VisualPromptGenerationSettings = field(
        default_factory=VisualPromptGenerationSettings
    )
    debug: ReplicateDebugSettings = field(default_factory=ReplicateDebugSettings)

    @classmethod
    def from_dict(
        cls,
        data: Optional[Dict[str, Any]],
        *,
        base_dir: Path,
    ) -> "ReplicateSettings":
        payload = dict(data or {})
        if "prompt_seed_path" in payload:
            payload["prompt_seed_path"] = _expand_path(payload["prompt_seed_path"], base_dir)
        visual_prompt_generation = VisualPromptGenerationSettings.from_dict(
            payload.pop("visual_prompt_generation", None)
        )
        debug = ReplicateDebugSettings.from_dict(payload.pop("debug", None), base_dir=base_dir)
        return cls(
            **payload,
            visual_prompt_generation=visual_prompt_generation,
            debug=debug,
        )


@dataclass
class WebSettings:
    host: str = "127.0.0.1"
    port: int = 5000
    debug: bool = True


@dataclass
class RenderSettings:
    enabled: bool = False
    backend: str = "resolve"
    timeline_prefix: str = "timeline"
    timeline_mode: str = "existing_only"
    append_mode: str = "sequential_exact"
    clean_media_pool_imports: bool = True
    media_pool_folder_name: str = "YCA Imports"
    import_only_required_media: bool = True
    video_mode: str = "image"
    audio_strategy: str = "cut_to_duration"
    video_strategy: str = "loop_to_duration"
    video_timing_source: str = "metadata_first"
    image_strategy: str = "fixed_full_duration"
    do_render: bool = False
    render_dir: Path = field(default_factory=lambda: Path("./runtime/renders"))
    width: int = 1920
    height: int = 1080


@dataclass
class Settings:
    config_path: Path
    profile: ProfileSettings
    paths: PathSettings
    workflow: WorkflowSettings = field(default_factory=WorkflowSettings)
    thumbnail: ThumbnailSettings = field(default_factory=ThumbnailSettings)
    openai: OpenAISettings = field(default_factory=OpenAISettings)
    description: DescriptionSettings = field(default_factory=DescriptionSettings)
    replicate: ReplicateSettings = field(default_factory=ReplicateSettings)
    web: WebSettings = field(default_factory=WebSettings)
    render: RenderSettings = field(default_factory=RenderSettings)


def load_settings(config_path: str | Path) -> Settings:
    path = Path(config_path).expanduser().resolve()
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    base_dir = path.parent

    profile_data: Dict[str, Any] = data.get("profile", {})
    paths_data: Dict[str, Any] = data.get("paths", {})
    workflow_data: Dict[str, Any] = data.get("workflow", {})
    thumbnail_data: Dict[str, Any] = data.get("thumbnail", {})
    openai_data: Dict[str, Any] = data.get("openai", {})
    description_data: Dict[str, Any] = data.get("description", {})
    replicate_data: Dict[str, Any] = data.get("replicate", {})
    web_data: Dict[str, Any] = data.get("web", {})
    render_data: Dict[str, Any] = data.get("render", {})
    if "render_dir" in render_data:
        render_data = {
            **render_data,
            "render_dir": _expand_path(render_data["render_dir"], base_dir),
        }

    return Settings(
        config_path=path,
        profile=ProfileSettings(
            id=str(profile_data["id"]),
            display_name=str(profile_data.get("display_name", profile_data["id"])),
            visual_input_mode=str(profile_data.get("visual_input_mode", "image")),
        ),
        paths=PathSettings(
            runtime_root=_expand_path(paths_data["runtime_root"], base_dir),
            outputs_dir=_expand_path(paths_data["outputs_dir"], base_dir),
            incoming_dir=_expand_path(paths_data["incoming_dir"], base_dir),
            images_dir=_expand_path(paths_data["images_dir"], base_dir),
            logs_dir=_expand_path(paths_data["logs_dir"], base_dir),
            psalms_dir=_expand_path(paths_data["psalms_dir"], base_dir),
            gospel_dir=_expand_path(paths_data["gospel_dir"], base_dir),
        ),
        workflow=WorkflowSettings(**workflow_data),
        thumbnail=ThumbnailSettings(**thumbnail_data),
        openai=OpenAISettings.from_dict(openai_data),
        description=DescriptionSettings(**description_data),
        replicate=ReplicateSettings.from_dict(replicate_data, base_dir=base_dir),
        web=WebSettings(**web_data),
        render=RenderSettings(**render_data),
    )
