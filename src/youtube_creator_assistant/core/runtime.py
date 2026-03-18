from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from .config import Settings
from .models import VideoProject, VisualAsset
from .utils import ensure_dir, slugify


IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".mkv", ".avi", ".mpeg", ".mpg"}


class RuntimeManager:
    def __init__(self, settings: Settings):
        self.settings = settings
        ensure_dir(self.settings.paths.runtime_root)
        ensure_dir(self.settings.paths.outputs_dir)
        ensure_dir(self.settings.paths.incoming_dir)
        ensure_dir(self.settings.paths.images_dir)
        ensure_dir(self.settings.paths.logs_dir)

    def create_project(self, visual_source: Path) -> VideoProject:
        return self.create_project_from_assets(visual_source)

    def create_project_from_assets(
        self,
        primary_visual_source: Path,
        render_visual_source: Path | None = None,
        source_prompt: str | None = None,
    ) -> VideoProject:
        visual_source = primary_visual_source.expanduser().resolve()
        if not visual_source.exists():
            raise FileNotFoundError(f"Visual source not found: {visual_source}")

        visual_kind = self._detect_visual_kind(visual_source)
        self._validate_visual_kind(visual_kind)

        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        project_id = f"{stamp}-{slugify(visual_source.stem)}"
        project_dir = self.settings.paths.outputs_dir / project_id
        input_dir = ensure_dir(project_dir / "input")
        tracks_dir = ensure_dir(project_dir / "tracks")
        ensure_dir(project_dir / "artifacts")
        if tracks_dir.exists():
            pass

        copied_visual = input_dir / f"visual{visual_source.suffix.lower()}"
        shutil.copy2(visual_source, copied_visual)

        copied_render_visual = None
        render_kind = None
        if render_visual_source is not None:
            render_visual_source = render_visual_source.expanduser().resolve()
            if not render_visual_source.exists():
                raise FileNotFoundError(f"Render visual source not found: {render_visual_source}")
            render_kind = self._detect_visual_kind(render_visual_source)
            copied_render_visual = input_dir / f"render_visual{render_visual_source.suffix.lower()}"
            shutil.copy2(render_visual_source, copied_render_visual)

        project = VideoProject(
            project_id=project_id,
            profile_id=self.settings.profile.id,
            project_dir=project_dir,
            visual_asset=VisualAsset(
                kind=visual_kind,
                path=copied_visual,
                original_name=visual_source.name,
            ),
            created_at=datetime.now(timezone.utc).isoformat(),
            render_visual_asset=(
                VisualAsset(
                    kind=render_kind,
                    path=copied_render_visual,
                    original_name=render_visual_source.name,
                )
                if copied_render_visual is not None and render_visual_source is not None and render_kind is not None
                else None
            ),
            source_prompt=(source_prompt.strip() if source_prompt else None),
        )
        self.save_project(project)
        return project

    def save_project(self, project: VideoProject) -> None:
        metadata_path = project.project_dir / "project.json"
        metadata_path.write_text(json.dumps(project.to_dict(), indent=2), encoding="utf-8")

    def load_project(self, project_id: str) -> VideoProject:
        metadata_path = self.settings.paths.outputs_dir / project_id / "project.json"
        if not metadata_path.exists():
            raise FileNotFoundError(f"Project not found: {project_id}")
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
        return VideoProject.from_dict(payload)

    def list_projects(self) -> List[VideoProject]:
        projects: List[VideoProject] = []
        if not self.settings.paths.outputs_dir.exists():
            return projects
        for path in sorted(self.settings.paths.outputs_dir.iterdir()):
            if not path.is_dir():
                continue
            metadata_path = path / "project.json"
            if not metadata_path.exists():
                continue
            payload = json.loads(metadata_path.read_text(encoding="utf-8"))
            projects.append(VideoProject.from_dict(payload))
        projects.sort(key=lambda project: project.created_at, reverse=True)
        return projects

    def _detect_visual_kind(self, path: Path) -> str:
        suffix = path.suffix.lower()
        if suffix in IMAGE_EXTS:
            return "image"
        if suffix in VIDEO_EXTS:
            return "video"
        raise ValueError(f"Unsupported visual file: {path.name}")

    def _validate_visual_kind(self, visual_kind: str) -> None:
        mode = self.settings.profile.visual_input_mode
        allowed = {
            "image": {"image"},
            "video": {"video"},
            "image_or_video": {"image", "video"},
        }.get(mode, {"image"})
        if visual_kind not in allowed:
            raise ValueError(
                f"Profile {self.settings.profile.id} expects {mode}, got {visual_kind}."
            )
