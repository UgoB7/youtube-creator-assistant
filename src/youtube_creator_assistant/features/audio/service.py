from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from mutagen.mp3 import MP3

from youtube_creator_assistant.core.config import Settings
from youtube_creator_assistant.core.models import AudioTrack, ChapterEntry, VideoProject
from youtube_creator_assistant.core.utils import tc_to_seconds


PSALM_RE = re.compile(r"(?i)psalm[\s_\-]*0*([0-9]+)")
GOSPEL_RE = re.compile(r"(?i)\b(luke|luc|matt(?:hew|hieu)?|john|jean|marc|mark)\b[\s_\-]*0*([0-9]+)")


@dataclass
class LibraryItem:
    kind: str
    label: str
    path: Path
    duration_seconds: float
    psalm_num: Optional[int] = None
    gospel_name: Optional[str] = None
    gospel_chapter: Optional[int] = None


class AudioPlanService:
    def __init__(self, settings: Settings):
        self.settings = settings

    def build_for_project(self, project: VideoProject, preferred_refs: Sequence[str]) -> VideoProject:
        pool = self.collect_psalms()
        if self.settings.workflow.include_gospel:
            pool.extend(self.collect_gospels())
        if not pool:
            raise RuntimeError("No audio files found in the local library.")

        selection = self._build_selection(
            pool_items=pool,
            target_seconds=tc_to_seconds(
                self.settings.workflow.target_duration_tc,
                self.settings.workflow.fps,
            ),
            preferred_refs=preferred_refs,
        )

        tracks_dir = project.project_dir / "tracks"
        if tracks_dir.exists():
            shutil.rmtree(tracks_dir)
        tracks_dir.mkdir(parents=True, exist_ok=True)

        audio_tracks: List[AudioTrack] = []
        chapters: List[ChapterEntry] = []
        elapsed = 0.0

        for idx, item in enumerate(selection, start=1):
            dest = tracks_dir / f"{idx:02d}_{item.path.name}"
            shutil.copy2(item.path, dest)
            audio_tracks.append(
                AudioTrack(
                    kind=item.kind,
                    label=item.label,
                    source_path=item.path,
                    copied_path=dest,
                    duration_seconds=item.duration_seconds,
                )
            )
            chapters.append(
                ChapterEntry(
                    timestamp=self._format_ts(elapsed),
                    label=item.label,
                )
            )
            if idx == 1:
                elapsed += max(
                    0.0,
                    item.duration_seconds - self.settings.workflow.trim_first_audio_seconds,
                )
            else:
                elapsed += item.duration_seconds

        project.audio_tracks = audio_tracks
        project.chapters = chapters

        (project.project_dir / "audio_selection.txt").write_text(
            "\n".join(track.label for track in audio_tracks),
            encoding="utf-8",
        )
        (project.project_dir / "chapters.txt").write_text(
            "\n".join(f"{chapter.timestamp} - {chapter.label}" for chapter in chapters),
            encoding="utf-8",
        )
        return project

    def collect_psalms(self) -> List[LibraryItem]:
        items: List[LibraryItem] = []
        for path in sorted(self.settings.paths.psalms_dir.glob("*.mp3")):
            psalm_num = self._parse_psalm_number(path)
            items.append(
                LibraryItem(
                    kind="psalm",
                    label=f"Psalm {psalm_num}" if psalm_num is not None else path.stem,
                    path=path,
                    duration_seconds=self._duration_seconds(path),
                    psalm_num=psalm_num,
                )
            )
        return [item for item in items if item.duration_seconds > 0]

    def collect_gospels(self) -> List[LibraryItem]:
        items: List[LibraryItem] = []
        for path in sorted(self.settings.paths.gospel_dir.glob("*/*.mp3")):
            gospel_name, chapter = self._parse_gospel_ref(path.stem)
            if not gospel_name or chapter is None:
                gospel_name = self._normalize_gospel_name(path.parent.name)
                _, chapter = self._parse_gospel_ref(f"{path.parent.name} {path.stem}")
            if not gospel_name or chapter is None:
                continue
            items.append(
                LibraryItem(
                    kind="gospel",
                    label=f"{self._display_gospel_name(gospel_name)} {chapter}",
                    path=path,
                    duration_seconds=self._duration_seconds(path),
                    gospel_name=gospel_name,
                    gospel_chapter=chapter,
                )
            )
        return [item for item in items if item.duration_seconds > 0]

    def _build_selection(
        self,
        pool_items: Sequence[LibraryItem],
        target_seconds: float,
        preferred_refs: Sequence[str],
    ) -> List[LibraryItem]:
        by_psalm: Dict[int, LibraryItem] = {}
        by_gospel: Dict[Tuple[str, int], LibraryItem] = {}
        for item in pool_items:
            if item.psalm_num is not None:
                by_psalm.setdefault(item.psalm_num, item)
            if item.gospel_name and item.gospel_chapter is not None:
                by_gospel.setdefault((item.gospel_name, item.gospel_chapter), item)

        preferred_items: List[LibraryItem] = []
        for ref in preferred_refs[: self.settings.workflow.max_head_items or len(preferred_refs)]:
            psalm_num = self._parse_psalm_number_from_text(ref)
            if psalm_num is not None and psalm_num in by_psalm:
                item = by_psalm[psalm_num]
                if item not in preferred_items:
                    preferred_items.append(item)
                continue
            gospel_name, chapter = self._parse_gospel_ref(ref)
            if gospel_name and chapter is not None:
                item = by_gospel.get((gospel_name, chapter))
                if item and item not in preferred_items:
                    preferred_items.append(item)

        selection: List[LibraryItem] = []
        total = 0.0
        used_paths = set()

        ordered_pool = list(preferred_items) + [item for item in pool_items if item.path not in {p.path for p in preferred_items}]
        while total < target_seconds:
            added_any = False
            for item in ordered_pool:
                if item.path in used_paths:
                    continue
                selection.append(item)
                used_paths.add(item.path)
                total += item.duration_seconds
                added_any = True
                if total >= target_seconds:
                    break
            if total >= target_seconds:
                break
            if not added_any:
                used_paths.clear()
        return selection

    def _duration_seconds(self, path: Path) -> float:
        try:
            return float(MP3(path).info.length)
        except Exception:
            return 0.0

    def _parse_psalm_number(self, path: Path) -> Optional[int]:
        match = PSALM_RE.search(path.stem)
        if not match:
            return None
        return int(match.group(1))

    def _parse_psalm_number_from_text(self, text: str) -> Optional[int]:
        match = re.search(r"(?i)psalm[\s_\-]*0*([0-9]+)", text)
        if not match:
            return None
        return int(match.group(1))

    def _parse_gospel_ref(self, text: str) -> Tuple[Optional[str], Optional[int]]:
        match = GOSPEL_RE.search(text)
        if not match:
            return None, None
        return self._normalize_gospel_name(match.group(1)), int(match.group(2))

    def _normalize_gospel_name(self, value: str) -> str:
        normalized = value.strip().lower()
        if normalized in {"marc", "mark"}:
            return "mark"
        if normalized in {"luc", "luke"}:
            return "luke"
        if normalized in {"matt", "matthew", "matthieu"}:
            return "matthew"
        if normalized in {"jean", "john"}:
            return "john"
        return normalized

    def _display_gospel_name(self, value: str) -> str:
        return {
            "mark": "Mark",
            "luke": "Luke",
            "matthew": "Matthew",
            "john": "John",
        }.get(value, value.title())

    def _format_ts(self, seconds_float: float) -> str:
        total_seconds = max(0, int(seconds_float))
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        return f"{hours}:{minutes:02d}:{seconds:02d}"
