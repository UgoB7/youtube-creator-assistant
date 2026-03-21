import unittest
from pathlib import Path
from unittest.mock import patch

from youtube_creator_assistant.core.config import load_settings
from youtube_creator_assistant.core.render_plan import RenderPlan
from youtube_creator_assistant.core.render_plan import RenderSegment
from youtube_creator_assistant.providers.resolve import _AppendedSegment
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
    def __init__(self, root_folder, duration_offset: int = 0):
        self._root_folder = root_folder
        self.append_calls = []
        self.duration_offset = duration_offset

    def GetRootFolder(self):
        return self._root_folder

    def AppendToTimeline(self, instructions):
        self.append_calls.append(instructions)
        items = []
        for instruction in instructions:
            payload = dict(instruction)
            payload["_duration_offset"] = self.duration_offset
            items.append(_FakeTimelineItem(payload))
        return items


class _FakeTimeline:
    def __init__(self, start_frame: int, end_frame: int):
        self._start_frame = start_frame
        self._end_frame = end_frame

    def GetStartFrame(self):
        return self._start_frame

    def GetEndFrame(self):
        return self._end_frame


class _FakeTimelineItem:
    def __init__(self, instruction):
        self._instruction = instruction

    def GetTrackTypeAndIndex(self):
        track_type = self._instruction.get("_track_type", "video")
        return [track_type, self._instruction.get("trackIndex", 1)]

    def GetStart(self, _subframe_precision):
        return self._instruction["recordFrame"]

    def GetDuration(self, _subframe_precision):
        return self._instruction["endFrame"] - self._instruction["startFrame"] + 1 + self._instruction.get("_duration_offset", 0)


class _FakeDeleteTimeline:
    def __init__(self):
        self.deleted = []

    def DeleteClips(self, items, _ripple_delete=False):
        self.deleted.extend(items)
        return True


class ResolveProviderTests(unittest.TestCase):
    def test_appends_segments_sequentially_in_actual_record_order(self):
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

        appended = provider._append_segments(
            media_pool,
            segments,
            {video_path.resolve(): clip},
            append_mode="sequential_exact",
        )

        self.assertEqual(len(media_pool.append_calls), 2)
        self.assertEqual(media_pool.append_calls[0][0]["recordFrame"], 0)
        self.assertEqual(media_pool.append_calls[1][0]["recordFrame"], 100)
        self.assertEqual(len(appended), 2)

    def test_sequential_exact_mode_uses_actual_resolve_duration_for_next_clip(self):
        root = Path(__file__).resolve().parents[1]
        settings = load_settings(root / "configs/profiles/vibes.yaml")
        provider = ResolveProvider(settings)

        video_path = root / "runtime" / "test-resolve-provider" / "clip-actual.mp4"
        video_path.parent.mkdir(parents=True, exist_ok=True)
        video_path.write_bytes(b"fake")
        clip = _FakeClip(video_path)
        media_pool = _FakeMediaPool(_FakeFolder(clips=[clip]), duration_offset=1)

        segments = [
            RenderSegment(
                media_kind="video",
                label="loop-1",
                path=video_path,
                start_frame=0,
                end_frame=99,
                record_frame=0,
                track_index=1,
                timeline_duration_frames=100,
            ),
            RenderSegment(
                media_kind="video",
                label="loop-2",
                path=video_path,
                start_frame=0,
                end_frame=99,
                record_frame=100,
                track_index=1,
                timeline_duration_frames=100,
            ),
        ]

        provider._append_segments(
            media_pool,
            segments,
            {video_path.resolve(): clip},
            append_mode="sequential_exact",
            target_duration_frames=300,
        )

        self.assertEqual(media_pool.append_calls[0][0]["recordFrame"], 0)
        self.assertEqual(media_pool.append_calls[1][0]["recordFrame"], 101)

    def test_trims_last_appended_segment_to_exact_target(self):
        root = Path(__file__).resolve().parents[1]
        settings = load_settings(root / "configs/profiles/vibes.yaml")
        provider = ResolveProvider(settings)

        video_path = root / "runtime" / "test-resolve-provider" / "clip-trim.mp4"
        video_path.parent.mkdir(parents=True, exist_ok=True)
        video_path.write_bytes(b"fake")
        clip = _FakeClip(video_path)
        media_pool = _FakeMediaPool(_FakeFolder(clips=[clip]))
        timeline = _FakeDeleteTimeline()

        appended = [
            _AppendedSegment(
                segment=RenderSegment(
                    media_kind="video",
                    label="loop-1",
                    path=video_path,
                    start_frame=0,
                    end_frame=99,
                    record_frame=0,
                    track_index=1,
                    timeline_duration_frames=100,
                ),
                media_item=clip,
                timeline_item=_FakeTimelineItem({"recordFrame": 0, "startFrame": 0, "endFrame": 99}),
            ),
            _AppendedSegment(
                segment=RenderSegment(
                    media_kind="video",
                    label="loop-2",
                    path=video_path,
                    start_frame=0,
                    end_frame=99,
                    record_frame=100,
                    track_index=1,
                    timeline_duration_frames=100,
                ),
                media_item=clip,
                timeline_item=_FakeTimelineItem({"recordFrame": 100, "startFrame": 0, "endFrame": 109}),
            ),
        ]

        provider._trim_appended_segments_to_target(timeline, media_pool, appended, 200)

        self.assertEqual(len(timeline.deleted), 1)
        self.assertEqual(media_pool.append_calls[-1][0]["recordFrame"], 100)
        self.assertEqual(media_pool.append_calls[-1][0]["endFrame"], 99)

    @patch("youtube_creator_assistant.providers.resolve.make_still_video")
    def test_prepares_image_segments_as_resolve_stills_when_configured(self, mock_make_still_video):
        root = Path(__file__).resolve().parents[1]
        settings = load_settings(root / "configs/profiles/vibes.yaml")
        provider = ResolveProvider(settings)
        image_path = root / "runtime" / "test-resolve-provider" / "still.png"
        image_path.parent.mkdir(parents=True, exist_ok=True)
        image_path.write_bytes(b"fake")
        plan = RenderPlan(
            project_id="project",
            profile_id="vibes",
            timeline_index=0,
            timeline_name="vibes00",
            fps=30.0,
            duration_frames=300,
            duration_seconds=10.0,
            video_mode="image",
            image_strategy="resolve_still_duration",
            media_pool_folder_name="YCA Imports",
            created_at="2026-01-01T00:00:00+00:00",
            visual_segments=[
                RenderSegment(
                    media_kind="image",
                    label="still",
                    path=image_path,
                    start_frame=0,
                    end_frame=0,
                    record_frame=0,
                    track_index=1,
                    timeline_duration_frames=300,
                )
            ],
            audio_segments=[],
        )

        prepared = provider._prepare_visual_segments(plan)

        self.assertEqual(len(prepared), 1)
        self.assertEqual(prepared[0].media_kind, "image")
        self.assertEqual(prepared[0].end_frame, 299)
        self.assertEqual(prepared[0].path, image_path)
        mock_make_still_video.assert_not_called()

    @patch("youtube_creator_assistant.providers.resolve.make_still_video")
    def test_prepares_image_segments_as_exact_duration_video_clips_for_mp4_strategy(self, mock_make_still_video):
        root = Path(__file__).resolve().parents[1]
        settings = load_settings(root / "configs/profiles/vibes.yaml")
        settings.render.image_strategy = "fixed_full_duration"
        provider = ResolveProvider(settings)
        image_path = root / "runtime" / "test-resolve-provider" / "still-fixed.png"
        image_path.parent.mkdir(parents=True, exist_ok=True)
        image_path.write_bytes(b"fake")

        def _fake_make_still_video(image_path, output_path, seconds, fps, width, height):
            output_path.write_bytes(b"clip")
            return output_path

        mock_make_still_video.side_effect = _fake_make_still_video
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
            visual_segments=[
                RenderSegment(
                    media_kind="image",
                    label="still",
                    path=image_path,
                    start_frame=0,
                    end_frame=0,
                    record_frame=0,
                    track_index=1,
                    timeline_duration_frames=300,
                )
            ],
            audio_segments=[],
        )

        prepared = provider._prepare_visual_segments(plan)

        self.assertEqual(len(prepared), 1)
        self.assertEqual(prepared[0].media_kind, "video")
        self.assertEqual(prepared[0].end_frame, 299)
        self.assertTrue(prepared[0].path.exists())

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

    def test_validates_visual_contiguity(self):
        root = Path(__file__).resolve().parents[1]
        settings = load_settings(root / "configs/profiles/vibes.yaml")
        provider = ResolveProvider(settings)

        contiguous_items = [
            _FakeTimelineItem({"recordFrame": 0, "startFrame": 0, "endFrame": 359, "trackIndex": 1}),
            _FakeTimelineItem({"recordFrame": 360, "startFrame": 0, "endFrame": 359, "trackIndex": 1}),
        ]
        provider._validate_visual_contiguity(contiguous_items)

        gapped_items = [
            _FakeTimelineItem({"recordFrame": 0, "startFrame": 0, "endFrame": 359, "trackIndex": 1}),
            _FakeTimelineItem({"recordFrame": 361, "startFrame": 0, "endFrame": 359, "trackIndex": 1}),
        ]
        with self.assertRaises(RuntimeError):
            provider._validate_visual_contiguity(gapped_items)


if __name__ == "__main__":
    unittest.main()
