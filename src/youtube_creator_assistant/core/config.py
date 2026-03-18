from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

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


@dataclass
class ThumbnailSettings:
    max_bytes: int = 2 * 1024 * 1024
    target_bytes: int = 1_800_000
    suffix: str = "_yt"


@dataclass
class OpenAISettings:
    model: str = "gpt-5.2-2025-12-11"
    title_examples_input: str = ""
    devotional_examples_input: str = ""


@dataclass
class ReplicateSettings:
    enabled: bool = False
    image_model: str = "bytedance/seedream-4"
    image_output_format: str = "png"
    image_size: str = "2K"
    image_aspect_ratio: str = "16:9"
    image_enhance_prompt: bool = False
    image_sequential_generation: str = "disabled"
    video_model: str = "bytedance/seedance-1.5-pro"
    video_fps: int = 24
    video_duration: int = 12
    video_resolution: str = "1080p"
    video_aspect_ratio: str = "16:9"
    video_camera_fixed: bool = True
    video_generate_audio: bool = False
    video_prompt: str = "no camera movement. campfire. no smoke."


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
    clean_media_pool_imports: bool = True
    media_pool_folder_name: str = "YCA Imports"
    import_only_required_media: bool = True
    video_mode: str = "image"
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
        openai=OpenAISettings(**openai_data),
        replicate=ReplicateSettings(**replicate_data),
        web=WebSettings(**web_data),
        render=RenderSettings(**render_data),
    )
