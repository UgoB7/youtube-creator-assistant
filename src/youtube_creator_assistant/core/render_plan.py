from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List


@dataclass
class RenderSegment:
    media_kind: str
    label: str
    path: Path
    start_frame: int
    end_frame: int
    record_frame: int
    track_index: int = 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "media_kind": self.media_kind,
            "label": self.label,
            "path": str(self.path),
            "start_frame": self.start_frame,
            "end_frame": self.end_frame,
            "record_frame": self.record_frame,
            "track_index": self.track_index,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RenderSegment":
        return cls(
            media_kind=str(data["media_kind"]),
            label=str(data["label"]),
            path=Path(str(data["path"])),
            start_frame=int(data["start_frame"]),
            end_frame=int(data["end_frame"]),
            record_frame=int(data["record_frame"]),
            track_index=int(data.get("track_index", 1)),
        )


@dataclass
class RenderPlan:
    project_id: str
    profile_id: str
    timeline_index: int
    timeline_name: str
    fps: int
    duration_frames: int
    duration_seconds: float
    video_mode: str
    image_strategy: str
    media_pool_folder_name: str
    created_at: str
    visual_segments: List[RenderSegment] = field(default_factory=list)
    audio_segments: List[RenderSegment] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_id": self.project_id,
            "profile_id": self.profile_id,
            "timeline_index": self.timeline_index,
            "timeline_name": self.timeline_name,
            "fps": self.fps,
            "duration_frames": self.duration_frames,
            "duration_seconds": self.duration_seconds,
            "video_mode": self.video_mode,
            "image_strategy": self.image_strategy,
            "media_pool_folder_name": self.media_pool_folder_name,
            "created_at": self.created_at,
            "visual_segments": [segment.to_dict() for segment in self.visual_segments],
            "audio_segments": [segment.to_dict() for segment in self.audio_segments],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RenderPlan":
        return cls(
            project_id=str(data["project_id"]),
            profile_id=str(data["profile_id"]),
            timeline_index=int(data["timeline_index"]),
            timeline_name=str(data["timeline_name"]),
            fps=int(data["fps"]),
            duration_frames=int(data["duration_frames"]),
            duration_seconds=float(data["duration_seconds"]),
            video_mode=str(data["video_mode"]),
            image_strategy=str(data["image_strategy"]),
            media_pool_folder_name=str(data["media_pool_folder_name"]),
            created_at=str(data["created_at"]),
            visual_segments=[RenderSegment.from_dict(item) for item in data.get("visual_segments", [])],
            audio_segments=[RenderSegment.from_dict(item) for item in data.get("audio_segments", [])],
        )

    def write_json(self, path: Path) -> Path:
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        return path
