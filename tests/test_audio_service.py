import base64
import tempfile
import unittest
from pathlib import Path

from youtube_creator_assistant.core.config import load_settings
from youtube_creator_assistant.features.audio.service import AudioPlanService


_PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9WlH0x8AAAAASUVORK5CYII="
)


class AudioPlanServiceTests(unittest.TestCase):
    def test_collect_psalms_uses_configured_audio_extensions(self):
        root = Path(__file__).resolve().parents[1]
        settings = load_settings(root / "configs/profiles/enchanted_melodies.yaml")

        with tempfile.TemporaryDirectory() as temp_dir_name:
            temp_dir = Path(temp_dir_name)
            settings.paths.psalms_dir = temp_dir / "audio"
            settings.paths.gospel_dir = temp_dir / "audio"
            settings.paths.psalms_dir.mkdir(parents=True, exist_ok=True)

            wav_path = settings.paths.psalms_dir / "Track - 001.wav"
            mp3_path = settings.paths.psalms_dir / "Track - 002.mp3"
            txt_path = settings.paths.psalms_dir / "ignore.txt"
            wav_path.write_bytes(b"wav")
            mp3_path.write_bytes(b"mp3")
            txt_path.write_text("ignore", encoding="utf-8")

            service = AudioPlanService(settings)
            service._duration_seconds = lambda path: 12.0 if path.suffix.lower() in {".wav", ".mp3"} else 0.0

            items = service.collect_psalms()

            self.assertEqual([item.path.name for item in items], ["Track - 001.wav", "Track - 002.mp3"])
            self.assertEqual([item.label for item in items], ["Track - 001", "Track - 002"])

    def test_build_for_project_can_repeat_tracks_when_needed(self):
        root = Path(__file__).resolve().parents[1]
        settings = load_settings(root / "configs/profiles/enchanted_melodies.yaml")

        with tempfile.TemporaryDirectory() as temp_dir_name:
            temp_dir = Path(temp_dir_name)
            settings.paths.runtime_root = temp_dir / "runtime"
            settings.paths.outputs_dir = settings.paths.runtime_root / "outputs"
            settings.paths.incoming_dir = settings.paths.runtime_root / "incoming"
            settings.paths.images_dir = settings.paths.runtime_root / "images"
            settings.paths.logs_dir = settings.paths.runtime_root / "logs"
            settings.paths.psalms_dir = temp_dir / "audio"
            settings.paths.gospel_dir = temp_dir / "audio"
            settings.paths.psalms_dir.mkdir(parents=True, exist_ok=True)
            settings.workflow.target_duration_tc = "0:00:25:00"
            settings.workflow.selection_seed_mode = "project_stable"

            track_a = settings.paths.psalms_dir / "Track - 001.wav"
            track_b = settings.paths.psalms_dir / "Track - 002.mp3"
            track_a.write_bytes(b"a")
            track_b.write_bytes(b"b")

            visual_path = temp_dir / "visual.png"
            visual_path.write_bytes(_PNG_BYTES)

            service = AudioPlanService(settings)
            service._duration_seconds = lambda path: 10.0
            project = self._create_project(settings, visual_path)

            built_project = service.build_for_project(project, ["Psalm 23"])

            self.assertEqual(len(built_project.audio_tracks), 3)
            self.assertGreater(
                len({track.source_path.name for track in built_project.audio_tracks}),
                1,
            )
            self.assertEqual(
                built_project.project_dir.joinpath("audio_selection_debug.txt").read_text(encoding="utf-8").splitlines()[1],
                "Preferred refs: ",
            )

    def _create_project(self, settings, visual_path: Path):
        from youtube_creator_assistant.core.runtime import RuntimeManager

        runtime = RuntimeManager(settings)
        return runtime.create_project(visual_path)
