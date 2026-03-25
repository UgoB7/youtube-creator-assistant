import base64
import tempfile
import unittest
from pathlib import Path

from youtube_creator_assistant.app.web import create_app


_PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9WlH0x8AAAAASUVORK5CYII="
)


class WebAppTests(unittest.TestCase):
    def test_vibes_requires_upload_when_candidate_generation_disabled(self):
        root = Path(__file__).resolve().parents[1]

        with tempfile.TemporaryDirectory() as temp_dir_name:
            temp_dir = Path(temp_dir_name)
            runtime_root = temp_dir / "runtime"
            env_file = root / ".env"
            created_env = False
            if not env_file.exists():
                env_file.write_text("OPENAI_API_KEY=test-key\n", encoding="utf-8")
                created_env = True
            try:
                config_path = temp_dir / "vibes-test.yaml"
                config_path.write_text(
                    (root / "configs/profiles/vibes.yaml").read_text(encoding="utf-8").replace(
                        "../../runtime/vibes", str(runtime_root)
                    ),
                    encoding="utf-8",
                )

                app = create_app(config_path)
                app.config["TESTING"] = True

                client = app.test_client()
                response = client.post("/projects", data={}, follow_redirects=True)

                self.assertEqual(response.status_code, 200)
                self.assertIn(b"Please upload a visual file", response.data)
                generated_root = runtime_root / "incoming" / "replicate_generated"
                self.assertFalse(generated_root.exists())
            finally:
                if created_env:
                    env_file.unlink(missing_ok=True)

    def test_vibes_uploaded_image_creates_project(self):
        root = Path(__file__).resolve().parents[1]

        with tempfile.TemporaryDirectory() as temp_dir_name:
            temp_dir = Path(temp_dir_name)
            runtime_root = temp_dir / "runtime"
            env_file = root / ".env"
            created_env = False
            if not env_file.exists():
                env_file.write_text("OPENAI_API_KEY=test-key\n", encoding="utf-8")
                created_env = True
            try:
                config_path = temp_dir / "vibes-test.yaml"
                config_path.write_text(
                    (root / "configs/profiles/vibes.yaml").read_text(encoding="utf-8").replace(
                        "../../runtime/vibes", str(runtime_root)
                    ),
                    encoding="utf-8",
                )

                app = create_app(config_path)
                app.config["TESTING"] = True
                app.pipeline.replicate_provider = type(
                    "_FakeReplicateProvider",
                    (),
                    {"generate_video_bytes": lambda _self, _path: b"fake-video"},
                )()

                upload_path = temp_dir / "upload.png"
                upload_path.write_bytes(_PNG_BYTES)

                client = app.test_client()
                with upload_path.open("rb") as handle:
                    response = client.post(
                        "/projects",
                        data={"visual": (handle, "upload.png")},
                        content_type="multipart/form-data",
                        follow_redirects=False,
                    )

                self.assertEqual(response.status_code, 302)
                self.assertIn("/?project_id=", response.headers["Location"])
            finally:
                if created_env:
                    env_file.unlink(missing_ok=True)
