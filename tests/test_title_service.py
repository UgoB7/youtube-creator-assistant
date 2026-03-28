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


class TitleServiceTests(unittest.TestCase):
    def test_enchanted_title_generation_uses_yaml_examples_visual_input_and_x_dash_y_format(self):
        root = Path(__file__).resolve().parents[1]
        settings = load_settings(root / "configs/profiles/enchanted_melodies.yaml")
        fake_provider = _FakeProvider(
            json.dumps(
                {
                    "titles": [
                        "1. Fantasy Music for Study & Relaxation - The Library Beneath the Aurora",
                        "Fantasy Music for Study & Relaxation – The Moonwell of Silver Pines",
                        "Fantasy Music for Relaxation & Peace: The Guardian at the Sapphire Gate",
                        "Fantasy Music for Focus & Relaxation — The Cartographer of Dawnlit Isles",
                        "Fantasy Music for Study & Relaxation - The Astral Garden of Quiet Lanterns",
                        "Fantasy Music for Relaxation & Peace - The Oracle Watching the Rainfall",
                        "Fantasy Music for Focus & Relaxation — The Hall Where Starlight Rests",
                        "Fantasy Music for Study & Relaxation - The Alchemist's Balcony at First Light",
                        "Fantasy Music for Relaxation & Peace - The Hidden Sanctuary Above the Clouds",
                        "Fantasy Music for Focus & Relaxation - The Keeper of the Ember Archive",
                    ]
                }
            )
        )
        service = TitleAndThemeService(settings, provider=fake_provider)

        with tempfile.TemporaryDirectory() as temp_dir_name:
            temp_dir = Path(temp_dir_name)
            image_path = temp_dir / "visual.png"
            image_path.write_bytes(_PNG_BYTES)

            titles = service.generate_titles(
                VisualAsset(kind="image", path=image_path, original_name="visual.png")
            )

        self.assertEqual(len(titles), 10)
        self.assertTrue(all(title.count(" — ") == 1 for title in titles))
        self.assertIn(
            "Fantasy Music for Study & Relaxation — The Library Beneath the Aurora",
            titles,
        )
        self.assertIn(
            "Fantasy Music for Relaxation & Peace — The Guardian at the Sapphire Gate",
            titles,
        )

        call = fake_provider.client().responses.calls[0]
        content = call["input"][0]["content"]
        prompt_text = next(part["text"] for part in content if part["type"] == "input_text")
        self.assertIn("return exactly 10 titles", prompt_text)
        self.assertIn("Use the exact two-part structure", prompt_text)
        self.assertIn(
            "Fantasy Music for Study & Relaxation — The Mage’s Terrace of Solace",
            prompt_text,
        )
        self.assertTrue(any(part["type"] == "input_image" for part in content))


if __name__ == "__main__":
    unittest.main()
