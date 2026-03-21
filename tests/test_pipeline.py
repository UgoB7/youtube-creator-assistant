import base64
import tempfile
import unittest
from pathlib import Path

from youtube_creator_assistant.core.config import load_settings
from youtube_creator_assistant.core.pipeline import ContentPipeline


_PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9WlH0x8AAAAASUVORK5CYII="
)


class _FakeReplicateProvider:
    def __init__(self, payload: bytes = b"fake-video"):
        self.payload = payload
        self.video_inputs: list[Path] = []

    def generate_video_bytes(self, image_path: Path) -> bytes:
        self.video_inputs.append(Path(image_path))
        return self.payload


class ContentPipelineTests(unittest.TestCase):
    def test_shepherd_uploaded_image_generates_render_video(self):
        root = Path(__file__).resolve().parents[1]
        settings = load_settings(root / "configs/profiles/shepherd.yaml")

        with tempfile.TemporaryDirectory() as temp_dir_name:
            temp_dir = Path(temp_dir_name)
            settings.paths.runtime_root = temp_dir / "runtime"
            settings.paths.outputs_dir = settings.paths.runtime_root / "outputs"
            settings.paths.incoming_dir = settings.paths.runtime_root / "incoming"
            settings.paths.images_dir = settings.paths.runtime_root / "images"
            settings.paths.logs_dir = settings.paths.runtime_root / "logs"
            settings.paths.psalms_dir = temp_dir / "assets" / "psalms"
            settings.paths.gospel_dir = temp_dir / "assets" / "gospel"
            settings.paths.psalms_dir.mkdir(parents=True, exist_ok=True)
            settings.paths.gospel_dir.mkdir(parents=True, exist_ok=True)

            uploaded_image = temp_dir / "uploaded.png"
            uploaded_image.write_bytes(_PNG_BYTES)

            pipeline = ContentPipeline(settings)
            fake_replicate = _FakeReplicateProvider()
            pipeline.replicate_provider = fake_replicate

            project = pipeline.create_project(uploaded_image)

            self.assertEqual(fake_replicate.video_inputs, [uploaded_image.resolve()])
            self.assertEqual(project.visual_asset.kind, "image")
            self.assertIsNotNone(project.render_visual_asset)
            assert project.render_visual_asset is not None
            self.assertEqual(project.render_visual_asset.kind, "video")
            self.assertTrue(project.render_visual_asset.path.exists())
            self.assertEqual(project.render_visual_asset.duration_seconds, float(settings.replicate.video_duration))
            self.assertEqual(project.render_visual_asset.fps, float(settings.replicate.video_fps))
            self.assertEqual(project.render_visual_asset.path.read_bytes(), b"fake-video")

    def test_mercy_uploaded_image_generates_render_video(self):
        root = Path(__file__).resolve().parents[1]
        settings = load_settings(root / "configs/profiles/mercy.yaml")

        with tempfile.TemporaryDirectory() as temp_dir_name:
            temp_dir = Path(temp_dir_name)
            settings.paths.runtime_root = temp_dir / "runtime"
            settings.paths.outputs_dir = settings.paths.runtime_root / "outputs"
            settings.paths.incoming_dir = settings.paths.runtime_root / "incoming"
            settings.paths.images_dir = settings.paths.runtime_root / "images"
            settings.paths.logs_dir = settings.paths.runtime_root / "logs"
            settings.paths.psalms_dir = temp_dir / "assets" / "psalms"
            settings.paths.gospel_dir = temp_dir / "assets" / "gospel"
            settings.paths.psalms_dir.mkdir(parents=True, exist_ok=True)
            settings.paths.gospel_dir.mkdir(parents=True, exist_ok=True)

            uploaded_image = temp_dir / "uploaded.png"
            uploaded_image.write_bytes(_PNG_BYTES)

            pipeline = ContentPipeline(settings)
            fake_replicate = _FakeReplicateProvider()
            pipeline.replicate_provider = fake_replicate

            project = pipeline.create_project(uploaded_image)

            self.assertEqual(fake_replicate.video_inputs, [uploaded_image.resolve()])
            self.assertEqual(project.visual_asset.kind, "image")
            self.assertIsNotNone(project.render_visual_asset)
            assert project.render_visual_asset is not None
            self.assertEqual(project.render_visual_asset.kind, "video")

    def test_regenerate_project_render_video_rewrites_existing_render_asset(self):
        root = Path(__file__).resolve().parents[1]
        settings = load_settings(root / "configs/profiles/shepherd.yaml")

        with tempfile.TemporaryDirectory() as temp_dir_name:
            temp_dir = Path(temp_dir_name)
            settings.paths.runtime_root = temp_dir / "runtime"
            settings.paths.outputs_dir = settings.paths.runtime_root / "outputs"
            settings.paths.incoming_dir = settings.paths.runtime_root / "incoming"
            settings.paths.images_dir = settings.paths.runtime_root / "images"
            settings.paths.logs_dir = settings.paths.runtime_root / "logs"
            settings.paths.psalms_dir = temp_dir / "assets" / "psalms"
            settings.paths.gospel_dir = temp_dir / "assets" / "gospel"
            settings.paths.psalms_dir.mkdir(parents=True, exist_ok=True)
            settings.paths.gospel_dir.mkdir(parents=True, exist_ok=True)

            uploaded_image = temp_dir / "uploaded.png"
            uploaded_image.write_bytes(_PNG_BYTES)

            pipeline = ContentPipeline(settings)
            first_replicate = _FakeReplicateProvider(payload=b"first-video")
            pipeline.replicate_provider = first_replicate
            project = pipeline.create_project(uploaded_image)

            second_replicate = _FakeReplicateProvider(payload=b"second-video")
            pipeline.replicate_provider = second_replicate
            project.status = "resolve_synced"
            pipeline.runtime.save_project(project)

            regenerated = pipeline.regenerate_project_render_video(project.project_id)

            self.assertEqual(second_replicate.video_inputs, [project.visual_asset.path.resolve()])
            self.assertIsNotNone(regenerated.render_visual_asset)
            assert regenerated.render_visual_asset is not None
            self.assertEqual(regenerated.render_visual_asset.path.read_bytes(), b"second-video")
            self.assertEqual(regenerated.render_visual_asset.duration_seconds, float(settings.replicate.video_duration))
            self.assertEqual(regenerated.render_visual_asset.fps, float(settings.replicate.video_fps))
            self.assertEqual(regenerated.status, "package_built")
            self.assertIsNone(regenerated.resolve_last_synced_at)

    def test_regenerate_project_render_video_is_available_for_non_shepherd_profiles(self):
        root = Path(__file__).resolve().parents[1]
        settings = load_settings(root / "configs/profiles/vibes.yaml")
        settings.replicate.enabled = True
        settings.replicate.video_duration = 12
        settings.replicate.video_fps = 24

        with tempfile.TemporaryDirectory() as temp_dir_name:
            temp_dir = Path(temp_dir_name)
            settings.paths.runtime_root = temp_dir / "runtime"
            settings.paths.outputs_dir = settings.paths.runtime_root / "outputs"
            settings.paths.incoming_dir = settings.paths.runtime_root / "incoming"
            settings.paths.images_dir = settings.paths.runtime_root / "images"
            settings.paths.logs_dir = settings.paths.runtime_root / "logs"
            settings.paths.psalms_dir = temp_dir / "assets" / "psalms"
            settings.paths.gospel_dir = temp_dir / "assets" / "gospel"
            settings.paths.psalms_dir.mkdir(parents=True, exist_ok=True)
            settings.paths.gospel_dir.mkdir(parents=True, exist_ok=True)

            uploaded_image = temp_dir / "uploaded.png"
            uploaded_image.write_bytes(_PNG_BYTES)

            pipeline = ContentPipeline(settings)
            project = pipeline.runtime.create_project(uploaded_image)
            fake_replicate = _FakeReplicateProvider(payload=b"vibes-video")
            pipeline.replicate_provider = fake_replicate

            regenerated = pipeline.regenerate_project_render_video(project.project_id)

            self.assertEqual(fake_replicate.video_inputs, [project.visual_asset.path.resolve()])
            self.assertIsNotNone(regenerated.render_visual_asset)
            assert regenerated.render_visual_asset is not None
            self.assertEqual(regenerated.render_visual_asset.kind, "video")
            self.assertEqual(regenerated.render_visual_asset.path.read_bytes(), b"vibes-video")


if __name__ == "__main__":
    unittest.main()
