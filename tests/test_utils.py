import unittest
from pathlib import Path
from unittest.mock import patch

from youtube_creator_assistant.core.utils import probe_video_metadata


class UtilsTests(unittest.TestCase):
    @patch("youtube_creator_assistant.core.utils._probe_video_metadata_with_ffprobe", return_value=(None, None))
    @patch("youtube_creator_assistant.core.utils._probe_video_metadata_with_ffmpeg", return_value=(8.0, 30.0))
    def test_probe_video_metadata_falls_back_to_ffmpeg(self, _mock_ffmpeg, _mock_ffprobe):
        duration, fps = probe_video_metadata(Path("/tmp/example.mp4"))
        self.assertEqual(duration, 8.0)
        self.assertEqual(fps, 30.0)

    @patch("youtube_creator_assistant.core.utils._probe_video_metadata_with_ffprobe", return_value=(12.0, 24.0))
    @patch("youtube_creator_assistant.core.utils._probe_video_metadata_with_ffmpeg", return_value=(11.9, 24.0))
    def test_probe_video_metadata_prefers_ffprobe_when_available(self, _mock_ffmpeg, _mock_ffprobe):
        duration, fps = probe_video_metadata(Path("/tmp/example.mp4"))
        self.assertEqual(duration, 12.0)
        self.assertEqual(fps, 24.0)


if __name__ == "__main__":
    unittest.main()
