from __future__ import annotations

from youtube_creator_assistant.core.config import Settings
from youtube_creator_assistant.core.models import VideoProject
from youtube_creator_assistant.core.render_plan import RenderPlan, RenderSegment
from youtube_creator_assistant.core.runtime import RuntimeManager


class RenderPlanBuilder:
    def __init__(self, settings: Settings, runtime: RuntimeManager):
        self.settings = settings
        self.runtime = runtime

    def build_for_project(self, project: VideoProject) -> RenderPlan:
        if not project.audio_tracks:
            raise ValueError("Build the package before sending the project to Resolve.")

        timeline_index = self._timeline_index_for_project(project)
        timeline_name = f"{self.settings.render.timeline_prefix}{timeline_index:02d}"
        fps = self.settings.workflow.fps

        audio_segments: list[RenderSegment] = []
        record_frame = 0
        trim_frames_remaining = max(0, round(self.settings.workflow.trim_first_audio_seconds * fps))

        for track in project.audio_tracks:
            clip_frames = max(1, round(track.duration_seconds * fps))
            start_frame = 0
            if trim_frames_remaining > 0:
                if trim_frames_remaining >= clip_frames:
                    trim_frames_remaining -= clip_frames
                    continue
                start_frame = trim_frames_remaining
                clip_frames -= trim_frames_remaining
                trim_frames_remaining = 0
            end_frame = start_frame + max(0, clip_frames - 1)
            audio_segments.append(
                RenderSegment(
                    media_kind="audio",
                    label=track.label,
                    path=(track.copied_path or track.source_path),
                    start_frame=start_frame,
                    end_frame=end_frame,
                    record_frame=record_frame,
                    track_index=1,
                )
            )
            record_frame += clip_frames

        duration_frames = max(1, record_frame)
        duration_seconds = duration_frames / float(fps)

        visual_segments = [
            RenderSegment(
                media_kind=project.visual_asset.kind,
                label=project.visual_asset.original_name,
                path=project.visual_asset.path,
                start_frame=0,
                end_frame=max(0, duration_frames - 1),
                record_frame=0,
                track_index=1,
            )
        ]

        return RenderPlan(
            project_id=project.project_id,
            profile_id=project.profile_id,
            timeline_index=timeline_index,
            timeline_name=timeline_name,
            fps=fps,
            duration_frames=duration_frames,
            duration_seconds=duration_seconds,
            video_mode=self.settings.render.video_mode,
            image_strategy=self.settings.render.image_strategy,
            media_pool_folder_name=self.settings.render.media_pool_folder_name,
            created_at=project.created_at,
            visual_segments=visual_segments,
            audio_segments=audio_segments,
        )

    def _timeline_index_for_project(self, project: VideoProject) -> int:
        chronological = [
            item
            for item in self.runtime.list_projects()
            if item.profile_id == project.profile_id
        ]
        chronological.sort(key=lambda item: (item.created_at, item.project_id))
        for index, item in enumerate(chronological):
            if item.project_id == project.project_id:
                return index
        raise ValueError(f"Project {project.project_id} is missing from runtime outputs.")
