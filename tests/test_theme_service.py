import base64
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from youtube_creator_assistant.core.config import load_settings
from youtube_creator_assistant.core.models import VisualAsset
from youtube_creator_assistant.features.titles.service import TitleAndThemeService


_PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9WlH0x8AAAAASUVORK5CYII="
)


class _FakeResponses:
    def __init__(self, output_text: str):
        self.output_text = output_text
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(output_text=self.output_text)


class _FakeClient:
    def __init__(self, output_text: str):
        self.responses = _FakeResponses(output_text)


class _FakeProvider:
    def __init__(self, output_text: str):
        self._client = _FakeClient(output_text)

    def client(self):
        return self._client


class ThemeServiceTests(unittest.TestCase):
    def test_enchanted_theme_generation_uses_title_and_image_without_audio_context(self):
        root = Path(__file__).resolve().parents[1]
        settings = load_settings(root / "configs/profiles/enchanted_melodies.yaml")
        fake_provider = _FakeProvider(
            json.dumps(
                {
                    "themes": [
                        "Quiet Pilgrim Grace",
                        "Sunlit Citadel Hope",
                        "Golden Ascent",
                        "Armored Stillness",
                        "Radiant Focus",
                    ]
                }
            )
        )
        service = TitleAndThemeService(settings, provider=fake_provider)

        with tempfile.TemporaryDirectory() as temp_dir_name:
            temp_dir = Path(temp_dir_name)
            image_path = temp_dir / "visual.png"
            image_path.write_bytes(_PNG_BYTES)

            themes = service.generate_themes(
                VisualAsset(kind="image", path=image_path, original_name="visual.png"),
                "Fantasy Music for Focus & Calm — The Knight’s Quiet Road to the Sunlit Citadel",
                ["Track A", "Track B"],
            )

        self.assertEqual(len(themes), 5)
        self.assertIn("Radiant Focus", themes)

        call = fake_provider.client().responses.calls[0]
        content = call["input"][0]["content"]
        prompt_text = next(part["text"] for part in content if part["type"] == "input_text")
        self.assertIn("return exactly 5 themes", prompt_text)
        self.assertFalse(any(part.get("text", "").startswith("Audio:\n") for part in content if part["type"] == "input_text"))


if __name__ == "__main__":
    unittest.main()
