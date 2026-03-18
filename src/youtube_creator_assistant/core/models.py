from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class VisualAsset:
    kind: str
    path: Path
    original_name: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "path": str(self.path),
            "original_name": self.original_name,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VisualAsset":
        return cls(
            kind=str(data["kind"]),
            path=Path(str(data["path"])),
            original_name=str(data["original_name"]),
        )


@dataclass
class AudioTrack:
    kind: str
    label: str
    source_path: Path
    copied_path: Optional[Path]
    duration_seconds: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "label": self.label,
            "source_path": str(self.source_path),
            "copied_path": str(self.copied_path) if self.copied_path else None,
            "duration_seconds": self.duration_seconds,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AudioTrack":
        copied_path = data.get("copied_path")
        return cls(
            kind=str(data["kind"]),
            label=str(data["label"]),
            source_path=Path(str(data["source_path"])),
            copied_path=Path(str(copied_path)) if copied_path else None,
            duration_seconds=float(data["duration_seconds"]),
        )


@dataclass
class ChapterEntry:
    timestamp: str
    label: str


@dataclass
class VideoProject:
    project_id: str
    profile_id: str
    project_dir: Path
    visual_asset: VisualAsset
    created_at: str
    status: str = "created"
    title_candidates: List[str] = field(default_factory=list)
    selected_title: Optional[str] = None
    preferred_references: List[str] = field(default_factory=list)
    themes: List[str] = field(default_factory=list)
    audio_tracks: List[AudioTrack] = field(default_factory=list)
    chapters: List[ChapterEntry] = field(default_factory=list)
    description_text: Optional[str] = None
    yt_thumbnail_path: Optional[Path] = None

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["project_dir"] = str(self.project_dir)
        payload["visual_asset"] = self.visual_asset.to_dict()
        payload["audio_tracks"] = [track.to_dict() for track in self.audio_tracks]
        payload["chapters"] = [asdict(chapter) for chapter in self.chapters]
        payload["yt_thumbnail_path"] = str(self.yt_thumbnail_path) if self.yt_thumbnail_path else None
        return payload

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VideoProject":
        return cls(
            project_id=str(data["project_id"]),
            profile_id=str(data["profile_id"]),
            project_dir=Path(str(data["project_dir"])),
            visual_asset=VisualAsset.from_dict(data["visual_asset"]),
            created_at=str(data["created_at"]),
            status=str(data.get("status", "created")),
            title_candidates=list(data.get("title_candidates", [])),
            selected_title=data.get("selected_title"),
            preferred_references=list(data.get("preferred_references", [])),
            themes=list(data.get("themes", [])),
            audio_tracks=[AudioTrack.from_dict(item) for item in data.get("audio_tracks", [])],
            chapters=[ChapterEntry(**item) for item in data.get("chapters", [])],
            description_text=data.get("description_text"),
            yt_thumbnail_path=Path(str(data["yt_thumbnail_path"])) if data.get("yt_thumbnail_path") else None,
        )
