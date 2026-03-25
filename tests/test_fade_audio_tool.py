import tempfile
import unittest
from pathlib import Path

from youtube_creator_assistant.tools.fade_audio import (
    build_ffmpeg_command,
    compute_fade_durations,
    list_audio_files,
    normalize_extensions,
)


class FadeAudioToolTests(unittest.TestCase):
    def test_normalize_extensions_adds_dots_and_dedupes(self):
        self.assertEqual(
            normalize_extensions(["wav", ".mp3", ".WAV", ""]),
            [".wav", ".mp3"],
        )

    def test_compute_fade_durations_caps_for_short_audio(self):
        fade_in, fade_out, fade_out_start = compute_fade_durations(8.0, 5.0)
        self.assertEqual((fade_in, fade_out, fade_out_start), (4.0, 4.0, 4.0))

    def test_compute_fade_durations_keeps_requested_length_for_long_audio(self):
        fade_in, fade_out, fade_out_start = compute_fade_durations(42.0, 5.0)
        self.assertEqual((fade_in, fade_out, fade_out_start), (5.0, 5.0, 37.0))

    def test_list_audio_files_filters_by_extension(self):
        with tempfile.TemporaryDirectory() as temp_dir_name:
            temp_dir = Path(temp_dir_name)
            source_dir = temp_dir / "audio"
            output_dir = source_dir / "faded"
            source_dir.mkdir(parents=True, exist_ok=True)
            output_dir.mkdir(parents=True, exist_ok=True)
            (source_dir / "a.wav").write_bytes(b"a")
            (source_dir / "b.mp3").write_bytes(b"b")
            (source_dir / "note.txt").write_text("x", encoding="utf-8")

            files = list_audio_files(source_dir, output_dir, [".wav", ".mp3"])

            self.assertEqual([item.name for item in files], ["a.wav", "b.mp3"])

    def test_build_ffmpeg_command_preserves_extension_codec(self):
        with tempfile.TemporaryDirectory() as temp_dir_name:
            temp_dir = Path(temp_dir_name)
            input_path = temp_dir / "track.wav"
            output_path = temp_dir / "out.wav"
            input_path.write_bytes(b"a")

            import youtube_creator_assistant.tools.fade_audio as fade_audio

            original = fade_audio.get_audio_duration_seconds
            fade_audio.get_audio_duration_seconds = lambda _path: 12.0
            try:
                command = build_ffmpeg_command(input_path, output_path, 5.0, overwrite=True)
            finally:
                fade_audio.get_audio_duration_seconds = original

            self.assertIn("-af", command)
            self.assertIn("pcm_s16le", command)


if __name__ == "__main__":
    unittest.main()
