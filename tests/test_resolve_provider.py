import unittest
from pathlib import Path

from youtube_creator_assistant.core.config import load_settings
from youtube_creator_assistant.core.render_plan import RenderPlan
from youtube_creator_assistant.core.render_plan import RenderSegment
from youtube_creator_assistant.providers.resolve import ResolveProvider


class _FakeClip:
    def __init__(self, path: Path):
        self._path = path

    def GetClipProperty(self, name: str):
        if name == "File Path":
            return str(self._path)
        return ""


class _FakeFolder:
    def __init__(self, clips=None, subfolders=None):
        self._clips = list(clips or [])
        self._subfolders = list(subfolders or [])

    def GetClipList(self):
        return list(self._clips)

    def GetSubFolderList(self):
        return list(self._subfolders)


class _FakeMediaPool:
    def __init__(self, root_folder):
        self._root_folder = root_folder
        self.append_calls = []

    def GetRootFolder(self):
        return self._root_folder

    def AppendToTimeline(self, instructions):
        self.append_calls.append(instructions)
        return True


class _FakeTimeline:
    def __init__(self, start_frame: int, end_frame: int):
        self._start_frame = start_frame
        self._end_frame = end_frame

    def GetStartFrame(self):
        return self._start_frame

    def GetEndFrame(self):
        return self._end_frame


class ResolveProviderTests(unittest.TestCase):
    def test_appends_segments_one_by_one_in_record_order(self):
        root = Path(__file__).resolve().parents[1]
        settings = load_settings(root / "configs/profiles/vibes.yaml")
        provider = ResolveProvider(settings)

        video_path = root / "runtime" / "test-resolve-provider" / "clip.mp4"
        video_path.parent.mkdir(parents=True, exist_ok=True)
        video_path.write_bytes(b"fake")
        clip = _FakeClip(video_path)
        media_pool = _FakeMediaPool(_FakeFolder(clips=[clip]))

        segments = [
            RenderSegment(
                media_kind="video",
                label="loop-2",
                path=video_path,
                start_frame=0,
                end_frame=99,
                record_frame=100,
                track_index=1,
            ),
            RenderSegment(
                media_kind="video",
                label="loop-1",
                path=video_path,
                start_frame=0,
                end_frame=99,
                record_frame=0,
                track_index=1,
            ),
        ]

        provider._append_segments(media_pool, segments, {video_path.resolve(): clip})

        self.assertEqual(len(media_pool.append_calls), 2)
        self.assertEqual(media_pool.append_calls[0][0]["recordFrame"], 0)
        self.assertEqual(media_pool.append_calls[1][0]["recordFrame"], 100)
        self.assertEqual(media_pool.append_calls[0][0]["mediaType"], 1)

    def test_validates_exact_timeline_duration(self):
        root = Path(__file__).resolve().parents[1]
        settings = load_settings(root / "configs/profiles/vibes.yaml")
        provider = ResolveProvider(settings)
        plan = RenderPlan(
            project_id="project",
            profile_id="vibes",
            timeline_index=0,
            timeline_name="vibes00",
            fps=30.0,
            duration_frames=300,
            duration_seconds=10.0,
            video_mode="image",
            image_strategy="fixed_full_duration",
            media_pool_folder_name="YCA Imports",
            created_at="2026-01-01T00:00:00+00:00",
            visual_segments=[],
            audio_segments=[],
        )

        provider._validate_timeline_duration(_FakeTimeline(0, 299), plan)

        with self.assertRaises(RuntimeError):
            provider._validate_timeline_duration(_FakeTimeline(0, 450), plan)


if __name__ == "__main__":
    unittest.main()
