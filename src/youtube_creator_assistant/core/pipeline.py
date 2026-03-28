from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from youtube_creator_assistant.core.config import Settings
from youtube_creator_assistant.core.models import ReplicateImageBatch
from youtube_creator_assistant.features.replicate.service import ReplicateWorkflowService
from youtube_creator_assistant.features.render.builder import RenderPlanBuilder
from youtube_creator_assistant.core.runtime import RuntimeManager
from youtube_creator_assistant.core.utils import dedupe_preserve_order
from youtube_creator_assistant.features.audio.service import AudioPlanService
from youtube_creator_assistant.features.descriptions.service import DescriptionService
from youtube_creator_assistant.features.thumbnails.service import ThumbnailService
from youtube_creator_assistant.features.titles.service import TitleAndThemeService
from youtube_creator_assistant.providers.openai_client import OpenAIProvider
from youtube_creator_assistant.providers.replicate import ReplicateProvider
from youtube_creator_assistant.providers.resolve import ResolveProvider
from youtube_creator_assistant.profiles.registry import get_profile_definition


class ContentPipeline:
    MAX_SELECTED_TITLES = 3

    def __init__(self, settings: Settings):
        self.settings = settings
        self.runtime = RuntimeManager(settings)
        self.profile_definition = get_profile_definition(settings.profile.id)
        self.openai_provider = OpenAIProvider()
        self.title_service = TitleAndThemeService(settings, provider=self.openai_provider)
        self.audio_service = AudioPlanService(settings)
        self.replicate_provider = ReplicateProvider(settings)
        self.description_service = DescriptionService(settings, provider=self.openai_provider)
        self.thumbnail_service = ThumbnailService(
            settings,
            openai_provider=self.openai_provider,
            replicate_provider=self.replicate_provider,
        )
        self.render_plan_builder = RenderPlanBuilder(settings, self.runtime)
        self.replicate_workflow_service = ReplicateWorkflowService(
            settings,
            replicate_provider=self.replicate_provider,
        )
        self.resolve_provider = ResolveProvider(settings)

    def create_project(self, visual_source: str | Path):
        source_path = Path(visual_source).expanduser().resolve()
        if self._should_generate_render_video(source_path):
            video_path = self._generate_render_video(source_path)
            return self.runtime.create_project_from_assets(
                source_path,
                render_visual_source=video_path,
                render_visual_duration_seconds=float(self.settings.replicate.video_duration),
                render_visual_fps=float(self.settings.replicate.video_fps),
            )
        return self.runtime.create_project(source_path)

    def regenerate_project_render_video(self, project_id: str):
        project = self.runtime.load_project(project_id)
        if not self.settings.replicate.enabled:
            raise RuntimeError("Replicate is disabled for this profile.")
        if project.visual_asset.kind != "image":
            raise ValueError("Render video regeneration requires an image-based project.")

        source_path = project.visual_asset.path.expanduser().resolve()
        video_bytes = self.replicate_provider.generate_video_bytes(source_path)
        input_dir = project.project_dir / "input"
        input_dir.mkdir(parents=True, exist_ok=True)
        render_path = (
            project.render_visual_asset.path
            if project.render_visual_asset is not None
            else input_dir / "render_visual.mp4"
        )
        render_path.write_bytes(video_bytes)

        project.render_visual_asset = project.render_visual_asset or project.visual_asset.__class__(
            kind="video",
            path=render_path,
            original_name=render_path.name,
        )
        project.render_visual_asset.kind = "video"
        project.render_visual_asset.path = render_path
        project.render_visual_asset.original_name = render_path.name
        project.render_visual_asset.duration_seconds = float(self.settings.replicate.video_duration)
        project.render_visual_asset.fps = float(self.settings.replicate.video_fps)
        project.resolve_last_synced_at = None
        project.resolve_last_error = None
        if project.status == "resolve_synced":
            project.status = "package_built"
        self.runtime.save_project(project)
        return project

    def _should_generate_render_video(self, source_path: Path) -> bool:
        return (
            self.settings.replicate.enabled
            and self.runtime._detect_visual_kind(source_path) == "image"
        )

    def _generate_render_video(self, source_path: Path) -> Path:
        generated_dir = self.settings.paths.incoming_dir / "replicate_generated"
        generated_dir.mkdir(parents=True, exist_ok=True)
        video_path = generated_dir / f"{source_path.stem}_render.mp4"
        video_path.write_bytes(self.replicate_provider.generate_video_bytes(source_path))
        return video_path

    def create_candidate_batch(self, count: int | None = None) -> ReplicateImageBatch:
        if not self.settings.replicate.enabled:
            raise RuntimeError("Replicate is disabled for this profile.")
        generated_dir = self.settings.paths.incoming_dir / "replicate_generated"
        generated_dir.mkdir(parents=True, exist_ok=True)
        return self.replicate_workflow_service.generate_candidate_batch(generated_dir, count=count)

    def load_candidate_batch(self, batch_id: str) -> ReplicateImageBatch:
        batch_path = self.settings.paths.incoming_dir / "replicate_generated" / batch_id / "batch.json"
        if not batch_path.exists():
            raise FileNotFoundError(f"Replicate candidate batch not found: {batch_id}")
        payload = json.loads(batch_path.read_text(encoding="utf-8"))
        return ReplicateImageBatch.from_dict(payload)

    def create_project_from_candidate(self, batch_id: str, candidate_id: str):
        batch = self.load_candidate_batch(batch_id)
        candidate = next((item for item in batch.candidates if item.candidate_id == candidate_id), None)
        if candidate is None:
            raise ValueError(f"Candidate {candidate_id} was not found in batch {batch_id}.")

        video_path = batch.batch_dir / f"{candidate.candidate_id}_render.mp4"
        video_path.write_bytes(self.replicate_provider.generate_video_bytes(candidate.image_path))

        project = self.runtime.create_project_from_assets(
            candidate.image_path,
            render_visual_source=video_path,
            source_prompt=candidate.prompt,
            render_visual_duration_seconds=float(self.settings.replicate.video_duration),
            render_visual_fps=float(self.settings.replicate.video_fps),
        )
        (project.project_dir / "replicate_prompt.txt").write_text(candidate.prompt, encoding="utf-8")
        self.runtime.save_project(project)
        return project

    def create_project_from_seed_prompts(self):
        if not self.settings.replicate.enabled:
            raise RuntimeError("Replicate is disabled for this profile.")

        generated_dir = self.settings.paths.incoming_dir / "replicate_generated"
        generated_dir.mkdir(parents=True, exist_ok=True)

        generated_prompt, image_path, video_path = self.replicate_workflow_service.generate_visual_stack(
            generated_dir
        )

        project = self.runtime.create_project_from_assets(
            image_path,
            render_visual_source=video_path,
            source_prompt=generated_prompt,
            render_visual_duration_seconds=float(self.settings.replicate.video_duration),
            render_visual_fps=float(self.settings.replicate.video_fps),
        )
        (project.project_dir / "replicate_prompt.txt").write_text(generated_prompt, encoding="utf-8")
        self.runtime.save_project(project)
        return project

    def create_shepherd_candidate_batch(self, count: int | None = None) -> ReplicateImageBatch:
        return self.create_candidate_batch(count=count)

    def load_shepherd_candidate_batch(self, batch_id: str) -> ReplicateImageBatch:
        return self.load_candidate_batch(batch_id)

    def create_project_from_shepherd_candidate(self, batch_id: str, candidate_id: str):
        return self.create_project_from_candidate(batch_id, candidate_id)

    def generate_titles(self, project_id: str):
        project = self.runtime.load_project(project_id)
        project.title_candidates = self.title_service.generate_titles(project.visual_asset, project.project_dir)
        project.status = "titles_generated"
        (project.project_dir / "titles.json").write_text(
            json.dumps(project.title_candidates, indent=2),
            encoding="utf-8",
        )
        self.runtime.save_project(project)
        return project

    def build_render_plan(self, project_id: str):
        project = self.runtime.load_project(project_id)
        plan = self.render_plan_builder.build_for_project(project)
        plan.write_json(project.project_dir / "render_plan.json")
        return plan

    def generate_thumbnail_candidates(self, project_id: str):
        project = self.runtime.load_project(project_id)
        candidates = self.thumbnail_service.generate_thumbnail_candidates(project)
        self.runtime.save_project(project)
        return project, candidates

    def select_thumbnail_candidates(self, project_id: str, candidate_ids: str | Iterable[str]):
        project = self.runtime.load_project(project_id)
        if isinstance(candidate_ids, str):
            cleaned_ids = [candidate_ids]
        else:
            cleaned_ids = list(candidate_ids)
        project = self.thumbnail_service.select_thumbnail_candidates(project, cleaned_ids)
        self.runtime.save_project(project)
        return project

    def send_to_resolve(self, project_id: str):
        project = self.runtime.load_project(project_id)
        draft_plan = self.render_plan_builder.build_for_project(project)
        timeline_fps = self.resolve_provider.get_timeline_fps(draft_plan.timeline_name)
        plan = self.render_plan_builder.build_for_project(project, fps_override=timeline_fps)
        plan.write_json(project.project_dir / "render_plan.json")
        result = self.resolve_provider.sync_render_plan(plan)
        (project.project_dir / "resolve_sync.json").write_text(
            json.dumps(
                {
                    "timeline_name": result.timeline_name,
                    "imported_media_count": result.imported_media_count,
                    "timeline_fps": result.timeline_fps,
                    "timeline_duration_frames": result.timeline_duration_frames,
                    "timeline_duration_seconds": result.timeline_duration_seconds,
                    "message": result.message,
                    "synced_at": datetime.now(timezone.utc).isoformat(),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        project.resolve_timeline_name = result.timeline_name
        project.resolve_last_synced_at = datetime.now(timezone.utc).isoformat()
        project.resolve_last_error = None
        project.status = "resolve_synced"
        self.runtime.save_project(project)
        return project, result

    def build_package(self, project_id: str, selected_titles: str | Iterable[str]):
        project = self.runtime.load_project(project_id)
        cleaned_titles = self._normalize_selected_titles(selected_titles)
        if not cleaned_titles:
            raise ValueError("At least one title must be selected.")
        project.selected_titles = cleaned_titles
        project.selected_title = cleaned_titles[0]
        if self.settings.workflow.use_title_reference_guidance:
            project.preferred_references = self.title_service.generate_reference_preferences_for_titles(
                project.visual_asset,
                project.selected_titles or [project.selected_title],
                project.project_dir,
            )
        else:
            project.preferred_references = []
        (project.project_dir / "preferred_references.txt").write_text(
            "\n".join(project.preferred_references),
            encoding="utf-8",
        )
        self.audio_service.build_for_project(project, project.preferred_references)
        project.themes = self.title_service.generate_themes(
            project.visual_asset,
            project.selected_title,
            [track.label for track in project.audio_tracks],
            project.project_dir,
        )
        (project.project_dir / "themes.txt").write_text(
            "\n".join(project.themes),
            encoding="utf-8",
        )
        self.description_service.build_description(project)
        self.thumbnail_service.build_thumbnail(project)
        plan = self.render_plan_builder.build_for_project(project)
        plan.write_json(project.project_dir / "render_plan.json")
        if project.selected_title:
            (project.project_dir / "selected_title.txt").write_text(
                project.selected_title,
                encoding="utf-8",
            )
        if project.selected_titles:
            (project.project_dir / "selected_titles.txt").write_text(
                "\n".join(project.selected_titles),
                encoding="utf-8",
            )
        if project.yt_thumbnail_path:
            (project.project_dir / "yt_thumbnail_path.txt").write_text(
                str(project.yt_thumbnail_path),
                encoding="utf-8",
            )
        project.resolve_timeline_name = plan.timeline_name
        project.resolve_last_synced_at = None
        project.resolve_last_error = None
        project.status = "package_built"
        self.runtime.save_project(project)
        return project

    def _normalize_selected_titles(self, selected_titles: str | Iterable[str]) -> list[str]:
        if isinstance(selected_titles, str):
            raw_titles = [selected_titles]
        else:
            raw_titles = list(selected_titles)
        cleaned = [title.strip() for title in raw_titles if isinstance(title, str) and title.strip()]
        cleaned = dedupe_preserve_order(cleaned)
        max_selected_titles = max(
            1,
            int(getattr(self.settings.workflow, "max_selected_titles", self.MAX_SELECTED_TITLES) or self.MAX_SELECTED_TITLES),
        )
        return cleaned[:max_selected_titles]
