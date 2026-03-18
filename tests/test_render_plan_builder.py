import json
import unittest
from pathlib import Path

from youtube_creator_assistant.core.config import load_settings
from youtube_creator_assistant.core.models import AudioTrack, VideoProject, VisualAsset
from youtube_creator_assistant.core.runtime import RuntimeManager
from youtube_creator_assistant.features.render.builder import RenderPlanBuilder


class RenderPlanBuilderTests(unittest.TestCase):
    def test_builds_vibes_timeline_name_from_chronological_order(self):
        root = Path(__file__).resolve().parents[1]
        settings = load_settings(root / "configs/profiles/vibes.yaml")

        temp_root = root / "runtime" / "test-render-plan"
        outputs_dir = temp_root / "outputs"
        incoming_dir = temp_root / "incoming"
        images_dir = temp_root / "images"
        logs_dir = temp_root / "logs"
        outputs_dir.mkdir(parents=True, exist_ok=True)
        incoming_dir.mkdir(parents=True, exist_ok=True)
        images_dir.mkdir(parents=True, exist_ok=True)
        logs_dir.mkdir(parents=True, exist_ok=True)

        settings.paths.runtime_root = temp_root
        settings.paths.outputs_dir = outputs_dir
        settings.paths.incoming_dir = incoming_dir
        settings.paths.images_dir = images_dir
        settings.paths.logs_dir = logs_dir

        image_path = temp_root / "visual.png"
        image_path.write_bytes(b"fake")
        audio_path = temp_root / "track.mp3"
        audio_path.write_bytes(b"fake")

        project_old = VideoProject(
            project_id="older",
            profile_id="vibes",
            project_dir=outputs_dir / "older",
            visual_asset=VisualAsset(kind="image", path=image_path, original_name="visual.png"),
            created_at="2026-01-01T00:00:00+00:00",
            audio_tracks=[
                AudioTrack(
                    kind="psalm",
                    label="Psalm 1",
                    source_path=audio_path,
                    copied_path=audio_path,
                    duration_seconds=60.0,
                )
            ],
        )
        project_new = VideoProject(
            project_id="newer",
            profile_id="vibes",
            project_dir=outputs_dir / "newer",
            visual_asset=VisualAsset(kind="image", path=image_path, original_name="visual.png"),
            created_at="2026-01-02T00:00:00+00:00",
            audio_tracks=[
                AudioTrack(
                    kind="psalm",
                    label="Psalm 2",
                    source_path=audio_path,
                    copied_path=audio_path,
                    duration_seconds=90.0,
                )
            ],
        )

        for project in (project_old, project_new):
            project.project_dir.mkdir(parents=True, exist_ok=True)
            (project.project_dir / "project.json").write_text(
                json.dumps(project.to_dict(), indent=2),
                encoding="utf-8",
            )

        runtime = RuntimeManager(settings)
        plan = RenderPlanBuilder(settings, runtime).build_for_project(project_new)

        self.assertEqual(plan.timeline_index, 1)
        self.assertEqual(plan.timeline_name, "vibes01")


if __name__ == "__main__":
    unittest.main()
