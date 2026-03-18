from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from youtube_creator_assistant.core.config import Settings
from youtube_creator_assistant.features.replicate.service import ShepherdReplicateService
from youtube_creator_assistant.features.render.builder import RenderPlanBuilder
from youtube_creator_assistant.core.runtime import RuntimeManager
from youtube_creator_assistant.core.utils import dedupe_preserve_order
from youtube_creator_assistant.features.audio.service import AudioPlanService
from youtube_creator_assistant.features.descriptions.service import DescriptionService
from youtube_creator_assistant.features.thumbnails.service import ThumbnailService
from youtube_creator_assistant.features.titles.service import TitleAndThemeService
from youtube_creator_assistant.providers.replicate import ReplicateProvider
from youtube_creator_assistant.providers.resolve import ResolveProvider
from youtube_creator_assistant.profiles.registry import get_profile_definition


class ContentPipeline:
    MAX_SELECTED_TITLES = 3

    def __init__(self, settings: Settings):
        self.settings = settings
        self.runtime = RuntimeManager(settings)
        self.profile_definition = get_profile_definition(settings.profile.id)
        self.title_service = TitleAndThemeService(settings)
        self.audio_service = AudioPlanService(settings)
        self.description_service = DescriptionService(settings)
        self.thumbnail_service = ThumbnailService(settings)
        self.render_plan_builder = RenderPlanBuilder(settings, self.runtime)
        self.replicate_provider = ReplicateProvider(settings)
        self.shepherd_replicate_service = ShepherdReplicateService(
            settings,
            replicate_provider=self.replicate_provider,
        )
        self.resolve_provider = ResolveProvider(settings)

    def create_project(self, visual_source: str | Path):
        return self.runtime.create_project(Path(visual_source))

    def create_project_from_seed_prompts(self):
        if self.settings.profile.id != "shepherd":
            raise ValueError("Seed-based Replicate generation is only enabled for the shepherd profile.")
        if not self.settings.replicate.enabled:
            raise RuntimeError("Replicate is disabled for this profile.")

        generated_dir = self.settings.paths.incoming_dir / "replicate_generated"
        generated_dir.mkdir(parents=True, exist_ok=True)

        generated_prompt, image_path, video_path = self.shepherd_replicate_service.generate_visual_stack(
            generated_dir
        )

        project = self.runtime.create_project_from_assets(
            image_path,
            render_visual_source=video_path,
            source_prompt=generated_prompt,
        )
        (project.project_dir / "replicate_prompt.txt").write_text(generated_prompt, encoding="utf-8")
        self.runtime.save_project(project)
        return project

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

    def send_to_resolve(self, project_id: str):
        project = self.runtime.load_project(project_id)
        plan = self.render_plan_builder.build_for_project(project)
        plan.write_json(project.project_dir / "render_plan.json")
        result = self.resolve_provider.sync_render_plan(plan)
        (project.project_dir / "resolve_sync.json").write_text(
            json.dumps(
                {
                    "timeline_name": result.timeline_name,
                    "imported_media_count": result.imported_media_count,
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
        project.preferred_references = self.title_service.generate_reference_preferences_for_titles(
            project.visual_asset,
            project.selected_titles or [project.selected_title],
            project.project_dir,
        )
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
        return cleaned[: self.MAX_SELECTED_TITLES]
