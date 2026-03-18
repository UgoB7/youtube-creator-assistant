from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional

from youtube_creator_assistant.core.config import Settings
from youtube_creator_assistant.core.render_plan import RenderPlan, RenderSegment


@dataclass
class ResolveSyncResult:
    timeline_name: str
    imported_media_count: int
    timeline_fps: float
    timeline_duration_frames: int
    timeline_duration_seconds: float
    message: str


class ResolveProvider:
    def __init__(self, settings: Settings):
        self.settings = settings

    def sync_render_plan(self, plan: RenderPlan) -> ResolveSyncResult:
        if not self.settings.render.enabled:
            raise RuntimeError("Resolve integration is disabled in the profile config.")
        if self.settings.render.backend != "resolve":
            raise RuntimeError(f"Unsupported render backend: {self.settings.render.backend}")

        resolve = self._resolve_app()
        manager = resolve.GetProjectManager()
        if not manager:
            raise RuntimeError("Resolve ProjectManager is unavailable.")
        project = manager.GetCurrentProject()
        if not project:
            raise RuntimeError("No active Resolve project is open.")

        media_pool = project.GetMediaPool()
        if not media_pool:
            raise RuntimeError("Resolve Media Pool is unavailable.")

        timeline = self._find_timeline(project, plan.timeline_name)
        if not timeline:
            raise RuntimeError(
                f"Timeline {plan.timeline_name} was not found in the current Resolve project. "
                "Create it manually, then retry Send to Resolve."
            )
        timeline_fps = self._read_timeline_fps(project, timeline)
        if abs(float(plan.fps) - timeline_fps) > 0.01:
            raise RuntimeError(
                f"Render plan fps ({plan.fps:.3f}) does not match Resolve timeline fps ({timeline_fps:.3f}) "
                f"for {plan.timeline_name}. Rebuild the plan and retry Send to Resolve."
            )

        try:
            resolve.OpenPage("edit")
        except Exception:
            pass

        imports_folder = self._ensure_import_folder(media_pool, plan.media_pool_folder_name)
        if self.settings.render.clean_media_pool_imports:
            self._clear_import_folder(media_pool, imports_folder)

        media_paths = self._collect_required_paths(plan)
        imported_items = self._import_required_media(media_pool, imports_folder, media_paths)

        try:
            project.SetCurrentTimeline(timeline)
        except Exception:
            pass

        self._ensure_track_count(timeline, "video", self._max_track_index(plan.visual_segments))
        self._ensure_track_count(timeline, "audio", self._max_track_index(plan.audio_segments))
        self._unlock_tracks(timeline)
        self._clear_timeline_items(timeline)

        path_to_item = self._path_to_item_map(imports_folder)
        self._append_segments(media_pool, plan.visual_segments, path_to_item)
        self._append_segments(media_pool, plan.audio_segments, path_to_item)

        try:
            manager.SaveProject()
        except Exception:
            pass

        timeline_duration_frames = self._timeline_duration_frames(timeline)

        return ResolveSyncResult(
            timeline_name=plan.timeline_name,
            imported_media_count=len(imported_items),
            timeline_fps=timeline_fps,
            timeline_duration_frames=timeline_duration_frames,
            timeline_duration_seconds=timeline_duration_frames / timeline_fps,
            message=f"Timeline {plan.timeline_name} updated successfully.",
        )

    def get_timeline_fps(self, timeline_name: str) -> float:
        resolve = self._resolve_app()
        manager = resolve.GetProjectManager()
        if not manager:
            raise RuntimeError("Resolve ProjectManager is unavailable.")
        project = manager.GetCurrentProject()
        if not project:
            raise RuntimeError("No active Resolve project is open.")
        timeline = self._find_timeline(project, timeline_name)
        if not timeline:
            raise RuntimeError(
                f"Timeline {timeline_name} was not found in the current Resolve project. "
                "Create it manually, then retry Send to Resolve."
            )
        return self._read_timeline_fps(project, timeline)

    def _resolve_app(self):
        self._ensure_resolve_modules()
        try:
            import DaVinciResolveScript as bmd
        except Exception as exc:
            raise RuntimeError(
                "DaVinciResolveScript could not be imported. Open DaVinci Resolve and make sure the scripting modules are available."
            ) from exc
        resolve = bmd.scriptapp("Resolve")
        if not resolve:
            raise RuntimeError("Resolve scripting API is not accessible.")
        return resolve

    def _ensure_resolve_modules(self) -> None:
        module_dirs = [
            Path("/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules"),
            Path("/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/Frameworks/Fusion.framework/Versions/Current/Resources/Modules"),
        ]
        for module_dir in module_dirs:
            text = str(module_dir)
            if module_dir.exists() and text not in sys.path:
                sys.path.append(text)

    def _find_timeline(self, project, timeline_name: str):
        try:
            count = int(project.GetTimelineCount() or 0)
        except Exception:
            count = 0
        for index in range(1, count + 1):
            timeline = project.GetTimelineByIndex(index)
            if not timeline:
                continue
            try:
                name = timeline.GetName() or ""
            except Exception:
                name = ""
            if name == timeline_name:
                return timeline
        return None

    def _read_timeline_fps(self, project, timeline) -> float:
        for owner in (timeline, project):
            if not owner:
                continue
            try:
                raw = owner.GetSetting("timelineFrameRate")
            except Exception:
                raw = None
            fps = self._parse_fps_value(raw)
            if fps is not None:
                return fps
        return float(self.settings.workflow.fps)

    def _parse_fps_value(self, raw) -> float | None:
        if raw is None:
            return None
        text = str(raw).strip()
        if not text:
            return None
        text = text.replace("DF", "").strip()
        try:
            return float(text)
        except ValueError:
            return None

    def _timeline_duration_frames(self, timeline) -> int:
        try:
            start = int(timeline.GetStartFrame() or 0)
            end = int(timeline.GetEndFrame() or 0)
        except Exception:
            return 0
        return max(0, end - start + 1)

    def _ensure_import_folder(self, media_pool, folder_name: str):
        root = media_pool.GetRootFolder()
        if not root:
            raise RuntimeError("Resolve Media Pool root folder is unavailable.")
        for subfolder in root.GetSubFolderList() or []:
            try:
                if subfolder.GetName() == folder_name:
                    return subfolder
            except Exception:
                continue
        created = media_pool.AddSubFolder(root, folder_name)
        if not created:
            raise RuntimeError(f"Could not create Media Pool folder {folder_name}.")
        return created

    def _clear_import_folder(self, media_pool, folder) -> None:
        current_folder = media_pool.GetCurrentFolder()
        try:
            media_pool.SetCurrentFolder(folder)
        except Exception:
            pass
        self._clear_folder_recursive(media_pool, folder)
        if current_folder:
            try:
                media_pool.SetCurrentFolder(current_folder)
            except Exception:
                pass

    def _clear_folder_recursive(self, media_pool, folder) -> None:
        for subfolder in list(folder.GetSubFolderList() or []):
            self._clear_folder_recursive(media_pool, subfolder)
            try:
                media_pool.DeleteFolders([subfolder])
            except Exception:
                pass

        clips = list(folder.GetClipList() or [])
        if clips:
            try:
                media_pool.DeleteClips(clips)
            except Exception:
                for clip in clips:
                    try:
                        media_pool.DeleteClips([clip])
                    except Exception:
                        pass

    def _collect_required_paths(self, plan: RenderPlan) -> List[Path]:
        required = {segment.path.expanduser().resolve() for segment in (plan.visual_segments + plan.audio_segments)}
        return sorted(required)

    def _import_required_media(self, media_pool, imports_folder, media_paths: Iterable[Path]) -> list:
        current_folder = media_pool.GetCurrentFolder()
        try:
            media_pool.SetCurrentFolder(imports_folder)
        except Exception:
            pass
        imported = []
        if media_paths:
            imported = list(media_pool.ImportMedia([str(path) for path in media_paths]) or [])
        if current_folder:
            try:
                media_pool.SetCurrentFolder(current_folder)
            except Exception:
                pass
        return imported

    def _path_to_item_map(self, folder) -> dict[Path, object]:
        mapping: dict[Path, object] = {}
        for clip in self._iter_clips_recursive(folder):
            try:
                file_path = (clip.GetClipProperty("File Path") or "").strip()
            except Exception:
                file_path = ""
            if not file_path:
                continue
            try:
                resolved = Path(file_path).expanduser().resolve()
            except Exception:
                continue
            mapping[resolved] = clip
        return mapping

    def _find_media_item_by_path(self, folder, target_path: Path, timeout_s: float = 10.0):
        target_resolved = target_path.expanduser().resolve()
        start = time.time()
        while True:
            mapping = self._path_to_item_map(folder)
            item = mapping.get(target_resolved)
            if item is not None:
                return item
            if (time.time() - start) >= timeout_s:
                return None
            time.sleep(0.2)

    def _iter_clips_recursive(self, folder):
        for clip in folder.GetClipList() or []:
            yield clip
        for subfolder in folder.GetSubFolderList() or []:
            yield from self._iter_clips_recursive(subfolder)

    def _max_track_index(self, segments: Iterable[RenderSegment]) -> int:
        max_index = 0
        for segment in segments:
            max_index = max(max_index, segment.track_index)
        return max_index

    def _ensure_track_count(self, timeline, track_type: str, required: int) -> None:
        if required <= 0:
            return
        try:
            existing = int(timeline.GetTrackCount(track_type) or 0)
        except Exception:
            existing = 0
        while existing < required:
            if track_type == "audio":
                ok = timeline.AddTrack("audio", "stereo")
            else:
                ok = timeline.AddTrack(track_type)
            if not ok:
                raise RuntimeError(f"Could not add required {track_type} track to timeline.")
            existing += 1

    def _unlock_tracks(self, timeline) -> None:
        for track_type in ("video", "audio", "subtitle"):
            try:
                count = int(timeline.GetTrackCount(track_type) or 0)
            except Exception:
                count = 0
            for index in range(1, count + 1):
                try:
                    timeline.SetTrackLock(track_type, index, False)
                except Exception:
                    pass

    def _clear_timeline_items(self, timeline) -> None:
        all_items = []
        for track_type in ("video", "audio", "subtitle"):
            try:
                count = int(timeline.GetTrackCount(track_type) or 0)
            except Exception:
                count = 0
            for index in range(1, count + 1):
                try:
                    all_items.extend(timeline.GetItemListInTrack(track_type, index) or [])
                except Exception:
                    continue
        if not all_items:
            return
        delete_fn = getattr(timeline, "DeleteClips", None)
        if callable(delete_fn):
            try:
                ok = delete_fn(all_items, False)
            except Exception:
                ok = False
            if ok:
                return
        for item in all_items:
            try:
                item.SetClipEnabled(False)
            except Exception:
                pass

    def _append_segments(self, media_pool, segments: List[RenderSegment], path_to_item: dict[Path, object]) -> None:
        if not segments:
            return
        ordered_segments = sorted(
            segments,
            key=lambda segment: (segment.track_index, segment.record_frame, segment.start_frame, segment.end_frame),
        )
        for segment in ordered_segments:
            resolved_path = segment.path.expanduser().resolve()
            media_item = path_to_item.get(resolved_path)
            if not media_item:
                media_item = self._find_media_item_by_path(
                    media_pool.GetRootFolder(),
                    resolved_path,
                )
            if not media_item:
                raise RuntimeError(f"Imported media item is missing in Resolve for {segment.path}.")
            media_type = 2 if segment.media_kind == "audio" else 1
            instruction = {
                "mediaPoolItem": media_item,
                "startFrame": segment.start_frame,
                "endFrame": segment.end_frame,
                "recordFrame": segment.record_frame,
                "trackIndex": segment.track_index,
                "mediaType": media_type,
            }
            ok = media_pool.AppendToTimeline([instruction])
            if not ok:
                raise RuntimeError(
                    f"Resolve failed while appending {segment.media_kind} segment at recordFrame {segment.record_frame}."
                )
