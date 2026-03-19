import unittest
from pathlib import Path

from youtube_creator_assistant.core.config import load_settings
from youtube_creator_assistant.providers.replicate import ReplicateProvider


class _FakeRunClient:
    def __init__(self):
        self.calls = []

    def run(self, model, input):
        self.calls.append((model, input))
        return _FakeReadableResponse(b"ok")


class _FakeReadableResponse:
    def __init__(self, payload: bytes):
        self._payload = payload

    def read(self) -> bytes:
        return self._payload


class ReplicateProviderTests(unittest.TestCase):
    def test_seedream_payload_matches_legacy_shepherd_options(self):
        root = Path(__file__).resolve().parents[1]
        settings = load_settings(root / "configs/profiles/shepherd.yaml")
        provider = ReplicateProvider(settings)
        client = _FakeRunClient()
        provider._client = client

        payload = provider.generate_image_bytes("Prompt example")

        self.assertEqual(payload, b"ok")
        self.assertEqual(len(client.calls), 1)
        model, input_payload = client.calls[0]
        self.assertEqual(model, "bytedance/seedream-4")
        self.assertEqual(
            input_payload,
            {
                "size": "2K",
                "width": 2048,
                "height": 2048,
                "prompt": "Prompt example",
                "max_images": 1,
                "image_input": [],
                "aspect_ratio": "16:9",
                "enhance_prompt": False,
                "sequential_image_generation": "disabled",
            },
        )

    def test_seedance_payload_matches_legacy_shepherd_options(self):
        root = Path(__file__).resolve().parents[1]
        settings = load_settings(root / "configs/profiles/shepherd.yaml")
        provider = ReplicateProvider(settings)
        client = _FakeRunClient()
        provider._client = client

        image_path = root / "tests" / "fixtures_seedance_input.png"
        image_path.write_bytes(b"png")
        try:
            payload = provider.generate_video_bytes(image_path)
        finally:
            image_path.unlink(missing_ok=True)

        self.assertEqual(payload, b"ok")
        self.assertEqual(len(client.calls), 1)
        model, input_payload = client.calls[0]
        self.assertEqual(model, "bytedance/seedance-1.5-pro")
        self.assertEqual(input_payload["fps"], 24)
        self.assertEqual(input_payload["prompt"], "no camera movement. campfire. no smoke.")
        self.assertEqual(input_payload["duration"], 12)
        self.assertEqual(input_payload["resolution"], "1080p")
        self.assertEqual(input_payload["aspect_ratio"], "16:9")
        self.assertEqual(input_payload["camera_fixed"], True)
        self.assertEqual(input_payload["generate_audio"], False)
        self.assertTrue(hasattr(input_payload["image"], "read"))
        self.assertTrue(hasattr(input_payload["last_frame_image"], "read"))


if __name__ == "__main__":
    unittest.main()
