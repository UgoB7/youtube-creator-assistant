import tempfile
import unittest
from pathlib import Path

from youtube_creator_assistant.core.config import load_settings
from youtube_creator_assistant.providers.topaz import TopazVideoProvider


class _FakeTopazProvider(TopazVideoProvider):
    def __init__(self, settings):
        super().__init__(settings, api_key="test-key")
        self.requests: list[tuple[str, str, dict | None]] = []
        self.uploads: list[tuple[str, Path]] = []
        self.downloads: list[tuple[str, Path]] = []
        self.status_calls = 0

    def _probe_video_metadata(self, source_path: Path) -> dict[str, object]:
        return {"width": 1920, "height": 1080, "fps": 23.976, "container": "mp4"}

    def _request_json(self, method: str, path: str, payload: dict | None = None) -> dict:
        self.requests.append((method, path, payload))
        if method == "GET" and path == "/video/status":
            return {"supportedModels": ["astra", "prob-4"]}
        if method == "POST" and path == "/video/express":
            return {"requestId": "req-123", "uploadUrls": ["https://upload.example/video"]}
        if method == "GET" and path == "/video/req-123/status":
            self.status_calls += 1
            if self.status_calls == 1:
                return {"status": "processing", "progress": 42}
            return {
                "status": "complete",
                "progress": 100,
                "download": {"url": "https://download.example/enhanced.mp4"},
            }
        raise AssertionError(f"Unexpected Topaz call: {method} {path}")

    def _upload_file(self, upload_url: str, source_path: Path) -> None:
        self.uploads.append((upload_url, Path(source_path)))

    def _download_file(self, download_url: str, output_path: Path) -> None:
        self.downloads.append((download_url, Path(output_path)))
        output_path.write_bytes(b"enhanced-video")


class TopazProviderTests(unittest.TestCase):
    def test_upscale_video_uses_express_flow_and_downloads_output(self):
        root = Path(__file__).resolve().parents[1]
        settings = load_settings(root / "configs/profiles/lofi.yaml")
        settings.topaz.poll_interval_seconds = 0.0

        with tempfile.TemporaryDirectory() as temp_dir_name:
            temp_dir = Path(temp_dir_name)
            source = temp_dir / "input.mp4"
            source.write_bytes(b"video-data")

            provider = _FakeTopazProvider(settings)
            result = provider.upscale_video(source)

            self.assertEqual(result.request_id, "req-123")
            self.assertTrue(result.output_path.exists())
            self.assertEqual(result.output_path.read_bytes(), b"enhanced-video")
            self.assertEqual(result.output_path.name, "input_astra.mp4")
            self.assertEqual(provider.uploads, [("https://upload.example/video", source.resolve())])
            self.assertEqual(provider.downloads, [("https://download.example/enhanced.mp4", result.output_path)])

            create_request = next(payload for method, path, payload in provider.requests if method == "POST" and path == "/video/express")
            assert create_request is not None
            self.assertEqual(create_request["filters"][0]["model"], "astra")
            self.assertEqual(create_request["output"]["resolution"]["width"], 3840)
            self.assertEqual(create_request["output"]["resolution"]["height"], 2160)
            self.assertEqual(create_request["output"]["frameRate"], 24)
            self.assertEqual(create_request["output"]["container"], "mp4")
            self.assertEqual(len(create_request["source"]["md5Hash"]), 32)

    def test_upscale_video_rejects_model_not_reported_by_status(self):
        root = Path(__file__).resolve().parents[1]
        settings = load_settings(root / "configs/profiles/lofi.yaml")
        settings.topaz.poll_interval_seconds = 0.0
        settings.topaz.model = "missing-model"

        with tempfile.TemporaryDirectory() as temp_dir_name:
            temp_dir = Path(temp_dir_name)
            source = temp_dir / "input.mp4"
            source.write_bytes(b"video-data")

            provider = _FakeTopazProvider(settings)
            with self.assertRaises(RuntimeError) as ctx:
                provider.upscale_video(source)

            self.assertIn("missing-model", str(ctx.exception))
            self.assertIn("supported models", str(ctx.exception).lower())


if __name__ == "__main__":
    unittest.main()
