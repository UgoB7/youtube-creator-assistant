from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class VisualAsset:
    kind: str
    path: Path
    original_name: str
    duration_seconds: Optional[float] = None
    fps: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "path": str(self.path),
            "original_name": self.original_name,
            "duration_seconds": self.duration_seconds,
            "fps": self.fps,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VisualAsset":
        return cls(
            kind=str(data["kind"]),
            path=Path(str(data["path"])),
            original_name=str(data["original_name"]),
            duration_seconds=float(data["duration_seconds"]) if data.get("duration_seconds") is not None else None,
            fps=float(data["fps"]) if data.get("fps") is not None else None,
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
class ReplicateImageCandidate:
    candidate_id: str
    prompt: str
    image_path: Path

    def to_dict(self) -> Dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "prompt": self.prompt,
            "image_path": str(self.image_path),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ReplicateImageCandidate":
        return cls(
            candidate_id=str(data["candidate_id"]),
            prompt=str(data["prompt"]),
            image_path=Path(str(data["image_path"])),
        )


@dataclass
class ReplicateImageBatch:
    batch_id: str
    profile_id: str
    batch_dir: Path
    created_at: str
    candidates: List[ReplicateImageCandidate] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "batch_id": self.batch_id,
            "profile_id": self.profile_id,
            "batch_dir": str(self.batch_dir),
            "created_at": self.created_at,
            "candidates": [candidate.to_dict() for candidate in self.candidates],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ReplicateImageBatch":
        return cls(
            batch_id=str(data["batch_id"]),
            profile_id=str(data["profile_id"]),
            batch_dir=Path(str(data["batch_dir"])),
            created_at=str(data["created_at"]),
            candidates=[ReplicateImageCandidate.from_dict(item) for item in data.get("candidates", [])],
        )


@dataclass
class VideoProject:
    project_id: str
    profile_id: str
    project_dir: Path
    visual_asset: VisualAsset
    created_at: str
    status: str = "created"
    title_candidates: List[str] = field(default_factory=list)
    selected_titles: List[str] = field(default_factory=list)
    selected_title: Optional[str] = None
    preferred_references: List[str] = field(default_factory=list)
    themes: List[str] = field(default_factory=list)
    audio_tracks: List[AudioTrack] = field(default_factory=list)
    chapters: List[ChapterEntry] = field(default_factory=list)
    description_text: Optional[str] = None
    yt_thumbnail_path: Optional[Path] = None
    render_visual_asset: Optional[VisualAsset] = None
    source_prompt: Optional[str] = None
    resolve_timeline_name: Optional[str] = None
    resolve_last_synced_at: Optional[str] = None
    resolve_last_error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["project_dir"] = str(self.project_dir)
        payload["visual_asset"] = self.visual_asset.to_dict()
        payload["render_visual_asset"] = self.render_visual_asset.to_dict() if self.render_visual_asset else None
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
            selected_titles=list(data.get("selected_titles", [])),
            selected_title=data.get("selected_title"),
            preferred_references=list(data.get("preferred_references", [])),
            themes=list(data.get("themes", [])),
            audio_tracks=[AudioTrack.from_dict(item) for item in data.get("audio_tracks", [])],
            chapters=[ChapterEntry(**item) for item in data.get("chapters", [])],
            description_text=data.get("description_text"),
            yt_thumbnail_path=Path(str(data["yt_thumbnail_path"])) if data.get("yt_thumbnail_path") else None,
            render_visual_asset=VisualAsset.from_dict(data["render_visual_asset"]) if data.get("render_visual_asset") else None,
            source_prompt=data.get("source_prompt"),
            resolve_timeline_name=data.get("resolve_timeline_name"),
            resolve_last_synced_at=data.get("resolve_last_synced_at"),
            resolve_last_error=data.get("resolve_last_error"),
        )
