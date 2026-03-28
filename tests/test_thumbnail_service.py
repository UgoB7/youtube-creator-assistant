import unittest
from pathlib import Path
import json

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
        settings = load_settings(root / "configs/profiles/vibes.yaml")
        project_dir = temp_root / "project"
        (project_dir / "artifacts").mkdir(parents=True, exist_ok=True)

        project = VideoProject(
            project_id="test-project",
            profile_id="vibes",
            project_dir=project_dir,
            visual_asset=VisualAsset(kind="image", path=image_path, original_name=image_path.name),
            created_at="2026-01-01T00:00:00+00:00",
        )

        project = ThumbnailService(settings).build_thumbnail(project)
        self.assertIsNotNone(project.yt_thumbnail_path)
        self.assertTrue(project.yt_thumbnail_path.exists())

    def test_enchanted_thumbnail_candidates_are_generated_and_selectable(self):
        class _FakeOpenAIProvider:
            def __init__(self):
                self._client = self
                self.responses = self
                self.calls = []

            def client(self):
                return self

            def create(self, **kwargs):
                self.calls.append(kwargs)
                return type(
                    "_Resp",
                    (),
                    {
                        "output_text": json.dumps(
                            {
                                "concepts": [
                                    {
                                        "candidate_id": "thumb01",
                                        "label": "Parchemin",
                                        "summary": "A curled parchment in the upper-left corner.",
                                        "image_prompt": "Preserve the original scene and integrate the full title inside a curled parchment in the upper-left corner.",
                                    },
                                    {
                                        "candidate_id": "thumb02",
                                        "label": "Banniere",
                                        "summary": "A cloth banner in the foreground grass.",
                                        "image_prompt": "Preserve the original scene and integrate the full title on a cloth banner resting in the foreground grass.",
                                    },
                                    {
                                        "candidate_id": "thumb03",
                                        "label": "Pierre",
                                        "summary": "A carved stone title in the left foreground rocks.",
                                        "image_prompt": "Preserve the original scene and integrate the full title carved into the left foreground rocks.",
                                    },
                                    {
                                        "candidate_id": "thumb04",
                                        "label": "Enluminure",
                                        "summary": "A manuscript-style title in the sky corner.",
                                        "image_prompt": "Preserve the original scene and integrate the full title as a manuscript-style header in the upper-right sky.",
                                    },
                                ]
                            }
                        )
                    },
                )()

        class _FakeReplicateProvider:
            def __init__(self):
                self.calls = []

            def generate_thumbnail_candidate_bytes(self, prompt, image_path):
                self.calls.append((prompt, image_path))
                output_path = Path(__file__).resolve().parents[1] / "runtime" / "test-thumbnail" / "fake-thumb.jpg"
                output_path.parent.mkdir(parents=True, exist_ok=True)
                Image.new("RGB", (320, 180), (90, 60, 20)).save(output_path, format="JPEG")
                return output_path.read_bytes()

        temp_root = Path(__file__).resolve().parents[1] / "runtime" / "test-thumbnail-ideas"
        temp_root.mkdir(parents=True, exist_ok=True)
        image_path = temp_root / "sample.png"
        Image.new("RGB", (640, 360), (120, 80, 30)).save(image_path)

        root = Path(__file__).resolve().parents[1]
        settings = load_settings(root / "configs/profiles/enchanted_melodies.yaml")
        project_dir = temp_root / "project"
        (project_dir / "artifacts").mkdir(parents=True, exist_ok=True)

        project = VideoProject(
            project_id="enchanted-thumbnail-project",
            profile_id="enchanted_melodies",
            project_dir=project_dir,
            visual_asset=VisualAsset(kind="image", path=image_path, original_name=image_path.name),
            created_at="2026-01-01T00:00:00+00:00",
            selected_title="Fantasy Music for Focus & Calm — The Knight’s Quiet Road to the Sunlit Citadel",
        )

        service = ThumbnailService(
            settings,
            openai_provider=_FakeOpenAIProvider(),
            replicate_provider=_FakeReplicateProvider(),
        )

        candidates = service.generate_thumbnail_candidates(project)
        self.assertEqual(len(candidates), 4)
        self.assertTrue((project_dir / "thumbnail_candidates.json").exists())
        self.assertTrue((project_dir / "artifacts" / "thumbnail_candidates" / "thumb01.jpg").exists())

        project = service.select_thumbnail_candidates(project, ["thumb01", "thumb03"])
        self.assertIsNotNone(project.yt_thumbnail_path)
        self.assertTrue(project.yt_thumbnail_path.exists())
        self.assertTrue((project_dir / "thumbnail_selected.json").exists())


if __name__ == "__main__":
    unittest.main()
