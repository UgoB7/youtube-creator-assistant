from __future__ import annotations

import random
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set, Tuple

from mutagen import File as MutagenFile

from youtube_creator_assistant.core.config import Settings
from youtube_creator_assistant.core.models import AudioTrack, ChapterEntry, VideoProject
from youtube_creator_assistant.core.utils import stable_seed, tc_to_seconds


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
        effective_preferred_refs = (
            list(preferred_refs)
            if self.settings.workflow.use_title_reference_guidance
            else []
        )
        psalms = self.collect_psalms()
        gospels = self.collect_gospels() if self.settings.workflow.include_gospel else []
        pool = psalms + gospels
        if not pool:
            raise RuntimeError("No audio files found in the local library.")

        selection = self._build_selection(
            psalm_items=psalms,
            gospel_items=gospels,
            target_seconds=tc_to_seconds(
                self.settings.workflow.target_duration_tc,
                self.settings.workflow.fps,
            ),
            preferred_refs=effective_preferred_refs,
            selection_seed=self._selection_seed(project, effective_preferred_refs),
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

        unique_duration_seconds = sum(item.duration_seconds for item in selection)
        (project.project_dir / "audio_selection.txt").write_text(
            "\n".join(track.label for track in audio_tracks),
            encoding="utf-8",
        )
        (project.project_dir / "audio_selection_debug.txt").write_text(
            "\n".join(
                [
                    f"Preferred refs enabled: {self.settings.workflow.use_title_reference_guidance}",
                    f"Preferred refs: {', '.join(effective_preferred_refs)}",
                    f"Guided head target: {self.settings.workflow.max_head_items}",
                    f"Preferred refs returned: {len(effective_preferred_refs)}",
                    f"Unique tracks selected: {len(audio_tracks)}",
                    f"Unique duration seconds: {int(unique_duration_seconds)}",
                    f"Repeats allowed: {self.settings.workflow.allow_repeats}",
                    f"Selection seed mode: {self.settings.workflow.selection_seed_mode}",
                    f"Audio extensions: {', '.join(self._audio_extensions())}",
                    f"Selected tracks: {', '.join(track.label for track in audio_tracks)}",
                ]
            ),
            encoding="utf-8",
        )
        (project.project_dir / "chapters.txt").write_text(
            "\n".join(f"{chapter.timestamp} - {chapter.label}" for chapter in chapters),
            encoding="utf-8",
        )
        return project

    def collect_psalms(self) -> List[LibraryItem]:
        items: List[LibraryItem] = []
        for path in self._iter_audio_files(self.settings.paths.psalms_dir, recursive=False):
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
        for path in self._iter_audio_files(self.settings.paths.gospel_dir, recursive=True):
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
        psalm_items: Sequence[LibraryItem],
        gospel_items: Sequence[LibraryItem],
        target_seconds: float,
        preferred_refs: Sequence[str],
        selection_seed: int,
    ) -> List[LibraryItem]:
        rng = random.Random(selection_seed)
        pool_items = list(psalm_items) + list(gospel_items)
        by_psalm: Dict[int, LibraryItem] = {}
        by_gospel: Dict[Tuple[str, int], LibraryItem] = {}
        for item in pool_items:
            if item.psalm_num is not None:
                by_psalm.setdefault(item.psalm_num, item)
            if item.gospel_name and item.gospel_chapter is not None:
                by_gospel.setdefault((item.gospel_name, item.gospel_chapter), item)

        preferred_psalms: List[LibraryItem] = []
        preferred_gospels: List[LibraryItem] = []
        for ref in preferred_refs:
            psalm_num = self._parse_psalm_number_from_text(ref)
            if psalm_num is not None and psalm_num in by_psalm:
                item = by_psalm[psalm_num]
                if item not in preferred_psalms:
                    preferred_psalms.append(item)
                continue
            gospel_name, chapter = self._parse_gospel_ref(ref)
            if gospel_name and chapter is not None:
                item = by_gospel.get((gospel_name, chapter))
                if item and item not in preferred_gospels:
                    preferred_gospels.append(item)

        selection: List[LibraryItem] = []
        total = 0.0
        used_paths: set[Path] = set()
        head_cap = self.settings.workflow.max_head_items or len(preferred_refs)

        rng.shuffle(preferred_psalms)
        rng.shuffle(preferred_gospels)
        preferred_head = self._interleave_lists(preferred_gospels, preferred_psalms)[:head_cap]
        for item in preferred_head:
            if item.path in used_paths:
                continue
            selection.append(item)
            used_paths.add(item.path)
            total += item.duration_seconds
            if total >= target_seconds:
                return selection

        remaining_psalms = [item for item in psalm_items if item.path not in used_paths]
        remaining_gospels = [item for item in gospel_items if item.path not in used_paths]
        rng.shuffle(remaining_psalms)
        rng.shuffle(remaining_gospels)

        while total < target_seconds:
            progressed = False
            balanced_queue = self._build_balanced_queue(remaining_gospels, remaining_psalms, rng)
            for item in balanced_queue:
                if item.path in used_paths:
                    continue
                selection.append(item)
                used_paths.add(item.path)
                total += item.duration_seconds
                progressed = True
                if item.kind == "psalm":
                    remaining_psalms = [candidate for candidate in remaining_psalms if candidate.path != item.path]
                else:
                    remaining_gospels = [candidate for candidate in remaining_gospels if candidate.path != item.path]
                if total >= target_seconds:
                    return selection
            if not progressed:
                if not getattr(self.settings.workflow, "allow_repeats", True):
                    break
                used_paths.clear()
                remaining_psalms = list(psalm_items)
                remaining_gospels = list(gospel_items)
                rng.shuffle(remaining_psalms)
                rng.shuffle(remaining_gospels)
                if not remaining_psalms and not remaining_gospels:
                    break
        return selection

    def _selection_seed(self, project: VideoProject, preferred_refs: Sequence[str]) -> int:
        if self.settings.workflow.selection_seed_mode == "random":
            return random.SystemRandom().randrange(0, 2**63)
        return stable_seed(project.project_id, project.selected_titles, preferred_refs)

    def _audio_extensions(self) -> List[str]:
        normalized: List[str] = []
        for value in self.settings.workflow.audio_extensions:
            suffix = str(value).strip().lower()
            if not suffix:
                continue
            if not suffix.startswith("."):
                suffix = f".{suffix}"
            if suffix not in normalized:
                normalized.append(suffix)
        return normalized or [".mp3"]

    def _iter_audio_files(self, base_dir: Path, recursive: bool) -> List[Path]:
        if not base_dir.exists():
            return []
        allowed_suffixes: Set[str] = set(self._audio_extensions())
        iterator = base_dir.rglob("*") if recursive else base_dir.iterdir()
        files = [
            path
            for path in iterator
            if path.is_file() and path.suffix.lower() in allowed_suffixes
        ]
        return sorted(files)

    def _build_balanced_queue(
        self,
        gospel_items: Sequence[LibraryItem],
        psalm_items: Sequence[LibraryItem],
        rng: random.Random,
    ) -> List[LibraryItem]:
        gospel_queue = list(gospel_items)
        psalm_queue = list(psalm_items)
        if not gospel_queue:
            return psalm_queue
        if not psalm_queue:
            return gospel_queue
        prefer_gospel = rng.random() < 0.5
        if len(psalm_queue) > len(gospel_queue):
            prefer_gospel = False
        if len(gospel_queue) > len(psalm_queue):
            prefer_gospel = True
        if prefer_gospel:
            return self._interleave_lists(gospel_queue, psalm_queue)
        return self._interleave_lists(psalm_queue, gospel_queue)

    def _interleave_lists(
        self,
        primary: Sequence[LibraryItem],
        secondary: Sequence[LibraryItem],
    ) -> List[LibraryItem]:
        output: List[LibraryItem] = []
        p_idx = 0
        s_idx = 0
        while p_idx < len(primary) or s_idx < len(secondary):
            if p_idx < len(primary):
                output.append(primary[p_idx])
                p_idx += 1
            if s_idx < len(secondary):
                output.append(secondary[s_idx])
                s_idx += 1
        return output

    def _duration_seconds(self, path: Path) -> float:
        try:
            audio_file = MutagenFile(path)
            if audio_file is None or audio_file.info is None:
                return 0.0
            return float(audio_file.info.length)
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
