from __future__ import annotations

import json
from pathlib import Path

from youtube_creator_assistant.core.config import Settings
from youtube_creator_assistant.core.runtime import RuntimeManager
from youtube_creator_assistant.features.audio.service import AudioPlanService
from youtube_creator_assistant.features.descriptions.service import DescriptionService
from youtube_creator_assistant.features.thumbnails.service import ThumbnailService
from youtube_creator_assistant.features.titles.service import TitleAndThemeService
from youtube_creator_assistant.profiles.registry import get_profile_definition


class ContentPipeline:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.runtime = RuntimeManager(settings)
        self.profile_definition = get_profile_definition(settings.profile.id)
        self.title_service = TitleAndThemeService(settings)
        self.audio_service = AudioPlanService(settings)
        self.description_service = DescriptionService(settings)
        self.thumbnail_service = ThumbnailService(settings)

    def create_project(self, visual_source: str | Path):
        return self.runtime.create_project(Path(visual_source))

    def generate_titles(self, project_id: str):
        project = self.runtime.load_project(project_id)
        project.title_candidates = self.title_service.generate_titles(project.visual_asset.path)
        project.status = "titles_generated"
        (project.project_dir / "titles.json").write_text(
            json.dumps(project.title_candidates, indent=2),
            encoding="utf-8",
        )
        self.runtime.save_project(project)
        return project

    def build_package(self, project_id: str, selected_title: str):
        project = self.runtime.load_project(project_id)
        project.selected_title = selected_title.strip()
        project.preferred_references = self.title_service.generate_reference_preferences(
            project.visual_asset.path,
            project.selected_title,
        )
        self.audio_service.build_for_project(project, project.preferred_references)
        project.themes = self.title_service.generate_themes(
            project.visual_asset.path,
            project.selected_title,
            [track.label for track in project.audio_tracks],
        )
        (project.project_dir / "themes.txt").write_text(
            "\n".join(project.themes),
            encoding="utf-8",
        )
        self.description_service.build_description(project)
        self.thumbnail_service.build_thumbnail(project)
        if project.selected_title:
            (project.project_dir / "selected_title.txt").write_text(
                project.selected_title,
                encoding="utf-8",
            )
        if project.yt_thumbnail_path:
            (project.project_dir / "yt_thumbnail_path.txt").write_text(
                str(project.yt_thumbnail_path),
                encoding="utf-8",
            )
        project.status = "package_built"
        self.runtime.save_project(project)
        return project
