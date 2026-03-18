import unittest
from pathlib import Path

from youtube_creator_assistant.core.config import load_settings
from youtube_creator_assistant.profiles.registry import get_profile_definition


class ConfigTests(unittest.TestCase):
    def test_load_vibespro_config(self):
        root = Path(__file__).resolve().parents[1]
        settings = load_settings(root / "configs/profiles/vibespro.yaml")
        self.assertEqual(settings.profile.id, "vibespro")
        self.assertEqual(settings.paths.psalms_dir.name, "psalms")
        self.assertEqual(settings.paths.gospel_dir.name, "gospel")

    def test_profile_registry_has_placeholders(self):
        self.assertEqual(get_profile_definition("vibespro").display_name, "VibesPro")
        self.assertEqual(get_profile_definition("shepherd").display_name, "Shepherd")
        self.assertEqual(get_profile_definition("mercy").display_name, "Mercy")
        self.assertEqual(get_profile_definition("lofi").display_name, "Lofi")


if __name__ == "__main__":
    unittest.main()
