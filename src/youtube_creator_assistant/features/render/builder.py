from __future__ import annotations

from youtube_creator_assistant.core.config import Settings
from youtube_creator_assistant.core.models import VideoProject
from youtube_creator_assistant.core.render_plan import RenderPlan, RenderSegment
from youtube_creator_assistant.core.runtime import RuntimeManager
from youtube_creator_assistant.core.utils import probe_video_metadata, tc_to_seconds


class RenderPlanBuilder:
    def __init__(self, settings: Settings, runtime: RuntimeManager):
        self.settings = settings
        self.runtime = runtime

    def build_for_project(self, project: VideoProject, fps_override: float | None = None) -> RenderPlan:
        if not project.audio_tracks:
            raise ValueError("Build the package before sending the project to Resolve.")

        timeline_index = self._timeline_index_for_project(project)
        timeline_name = f"{self.settings.render.timeline_prefix}{timeline_index:02d}"
        fps = float(fps_override or self.settings.workflow.fps)
        target_duration_frames = max(
            1,
            round(tc_to_seconds(self.settings.workflow.target_duration_tc, int(round(fps))) * fps),
        )

        audio_segments: list[RenderSegment] = []
        record_frame = 0
        remaining_frames = target_duration_frames
        trim_frames_remaining = max(0, round(self.settings.workflow.trim_first_audio_seconds * fps))

        for track in project.audio_tracks:
            if remaining_frames <= 0:
                break
            clip_frames = max(1, round(track.duration_seconds * fps))
            start_frame = 0
            if trim_frames_remaining > 0:
                if trim_frames_remaining >= clip_frames:
                    trim_frames_remaining -= clip_frames
                    continue
                start_frame = trim_frames_remaining
                clip_frames -= trim_frames_remaining
                trim_frames_remaining = 0
            put_frames = min(clip_frames, remaining_frames)
            end_frame = start_frame + max(0, put_frames - 1)
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
            record_frame += put_frames
            remaining_frames -= put_frames

        duration_frames = target_duration_frames
        duration_seconds = duration_frames / float(fps)

        render_asset = project.render_visual_asset or project.visual_asset
        if render_asset.kind == "video":
            visual_segments = self._build_video_segments(project, render_asset, duration_frames, fps)
        else:
            visual_segments = [
                RenderSegment(
                    media_kind=render_asset.kind,
                    label=render_asset.original_name,
                    path=render_asset.path,
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

    def _build_video_segments(self, project: VideoProject, visual_asset, duration_frames: int, fps: float) -> list[RenderSegment]:
        source_seconds, source_fps = self._video_source_timing(project, visual_asset, duration_frames, fps)
        # Resolve expects startFrame/endFrame in source clip frames, not timeline frames.
        # So we loop by timeline duration, but always trim the clip using source-frame math.
        clip_timeline_frames = max(1, round(source_seconds * fps))
        clip_source_frames = max(1, round(source_seconds * source_fps))
        remaining = duration_frames
        record_frame = 0
        segments: list[RenderSegment] = []

        while remaining > clip_timeline_frames:
            segments.append(
                RenderSegment(
                    media_kind="video",
                    label=visual_asset.original_name,
                    path=visual_asset.path,
                    start_frame=0,
                    end_frame=max(0, clip_source_frames - 1),
                    record_frame=record_frame,
                    track_index=1,
                )
            )
            record_frame += clip_timeline_frames
            remaining -= clip_timeline_frames

        if remaining > 0:
            remaining_seconds = remaining / float(fps)
            partial_source_frames = max(1, min(clip_source_frames, round(remaining_seconds * source_fps)))
            segments.append(
                RenderSegment(
                    media_kind="video",
                    label=visual_asset.original_name,
                    path=visual_asset.path,
                    start_frame=0,
                    end_frame=max(0, partial_source_frames - 1),
                    record_frame=record_frame,
                    track_index=1,
                )
            )
        return segments

    def _video_source_timing(
        self,
        project: VideoProject,
        visual_asset,
        duration_frames: int,
        timeline_fps: float,
    ) -> tuple[float, float]:
        stored_seconds = getattr(visual_asset, "duration_seconds", None)
        stored_fps = getattr(visual_asset, "fps", None)
        probed_seconds, probed_fps = probe_video_metadata(visual_asset.path)
        source_seconds = probed_seconds if probed_seconds is not None else stored_seconds
        source_fps = probed_fps if probed_fps is not None else stored_fps
        if (
            (source_seconds is None or source_fps is None)
            and project.render_visual_asset is not None
            and visual_asset.path == project.render_visual_asset.path
            and self.settings.replicate.enabled
        ):
            source_seconds = source_seconds if source_seconds is not None else float(self.settings.replicate.video_duration)
            source_fps = source_fps if source_fps is not None else float(self.settings.replicate.video_fps)
        source_seconds = source_seconds or (duration_frames / float(timeline_fps))
        source_fps = source_fps or float(timeline_fps)
        return float(source_seconds), float(source_fps)
