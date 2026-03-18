import unittest
from pathlib import Path

from PIL import Image

from youtube_creator_assistant.core.config import load_settings
from youtube_creator_assistant.core.models import VideoProject, VisualAsset
from youtube_creator_assistant.features.thumbnails.service import ThumbnailService


class ThumbnailServiceTests(unittest.TestCase):
    def test_thumbnail_service_copies_small_image(self):
        temp_root = Path(__file__).resolve().parents[1] / "runtime" / "test-thumbnail"
        temp_root.mkdir(parents=True, exist_ok=True)
        image_path = temp_root / "sample.png"
        Image.new("RGB", (64, 64), (120, 80, 30)).save(image_path)

        root = Path(__file__).resolve().parents[1]
        settings = load_settings(root / "configs/profiles/vibespro.yaml")
        project_dir = temp_root / "project"
        (project_dir / "artifacts").mkdir(parents=True, exist_ok=True)

        project = VideoProject(
            project_id="test-project",
            profile_id="vibespro",
            project_dir=project_dir,
            visual_asset=VisualAsset(kind="image", path=image_path, original_name=image_path.name),
            created_at="2026-01-01T00:00:00+00:00",
        )

        project = ThumbnailService(settings).build_thumbnail(project)
        self.assertIsNotNone(project.yt_thumbnail_path)
        self.assertTrue(project.yt_thumbnail_path.exists())


if __name__ == "__main__":
    unittest.main()
