import unittest
from pathlib import Path

from youtube_creator_assistant.core.config import load_settings
from youtube_creator_assistant.profiles.registry import get_profile_definition


class ConfigTests(unittest.TestCase):
    def test_load_vibes_config(self):
        root = Path(__file__).resolve().parents[1]
        settings = load_settings(root / "configs/profiles/vibes.yaml")
        self.assertEqual(settings.profile.id, "vibes")
        self.assertEqual(settings.paths.psalms_dir.name, "psalms")
        self.assertEqual(settings.paths.gospel_dir.name, "gospel")
        self.assertTrue(settings.render.enabled)
        self.assertEqual(settings.render.timeline_prefix, "vibes")
        self.assertEqual(settings.render.append_mode, "sequential_exact")
        self.assertFalse(settings.replicate.enabled)
        self.assertEqual(settings.description.variant, "vibespro_legacy")

    def test_load_shepherd_replicate_config(self):
        root = Path(__file__).resolve().parents[1]
        settings = load_settings(root / "configs/profiles/shepherd.yaml")
        self.assertTrue(settings.replicate.enabled)
        self.assertEqual(settings.replicate.prompt_seed_path.name, "shepherd_prompts.txt")
        self.assertEqual(settings.replicate.image_model, "bytedance/seedream-4")
        self.assertEqual(settings.replicate.video_model, "bytedance/seedance-1.5-pro")
        self.assertEqual(settings.render.append_mode, "sequential_exact")
        self.assertEqual(settings.description.variant, "shepherd_legacy")

    def test_profile_registry_has_placeholders(self):
        self.assertEqual(get_profile_definition("vibes").display_name, "Image Workflow")
        self.assertEqual(get_profile_definition("shepherd").display_name, "Mixed Visual Workflow")
        self.assertEqual(get_profile_definition("mercy").display_name, "Motion-Assisted Workflow")
        self.assertEqual(get_profile_definition("lofi").display_name, "Video Workflow")

    def test_load_mercy_replicate_config(self):
        root = Path(__file__).resolve().parents[1]
        settings = load_settings(root / "configs/profiles/mercy.yaml")
        self.assertTrue(settings.replicate.enabled)
        self.assertEqual(settings.replicate.prompt_style, "mercy_legacy")
        self.assertEqual(settings.replicate.image_model, "black-forest-labs/flux-2-max")
        self.assertEqual(settings.replicate.image_payload_style, "flux")
        self.assertEqual(settings.render.append_mode, "sequential_exact")


if __name__ == "__main__":
    unittest.main()
