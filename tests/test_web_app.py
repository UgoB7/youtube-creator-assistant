import base64
import tempfile
import unittest
from pathlib import Path

from youtube_creator_assistant.app.web import create_app


_PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9WlH0x8AAAAASUVORK5CYII="
)


class _FakeOpenAIResponse:
    def __init__(self, output_text: str):
        self.output_text = output_text


class _FakeOpenAIClient:
    def __init__(self, outputs):
        self._outputs = list(outputs)
        self._index = 0
        self.responses = self

    def create(self, **_kwargs):
        if self._index >= len(self._outputs):
            value = self._outputs[-1]
        else:
            value = self._outputs[self._index]
        self._index += 1
        return _FakeOpenAIResponse(value)


class _FakeOpenAIProvider:
    def __init__(self, outputs):
        self._client = _FakeOpenAIClient(outputs)

    def client(self):
        return self._client


class _FakeReplicateProvider:
    def generate_video_bytes(self, _path):
        return b"fake-video"

    def generate_image_bytes(self, prompt):
        return prompt.encode("utf-8")


class _FakeScreenReplaceService:
    def parse_quad_norm(self, raw):
        return [(0.43, 0.36), (0.74, 0.37), (0.42, 0.60), (0.73, 0.61)]

    def serialize_quad_norm(self, _points):
        return "0.4300,0.3600;0.7400,0.3700;0.4200,0.6000;0.7300,0.6100"

    def render_video(self, *, base_video_path, output_path, quad_norm=None):
        output_path.write_bytes(
            f"screen-replace:{Path(base_video_path).name}:{quad_norm or ''}".encode("utf-8")
        )
        return output_path


class _FakeScreenOverlayBuilderService:
    def __init__(self, output_path: Path):
        self._output_path = output_path

    def output_video_path(self):
        return self._output_path

    def metadata_path(self):
        return Path(f"{self._output_path}.meta.json")


class _FakeTopazProvider:
    def upscale_video(self, source_path, output_path=None):
        target = Path(output_path) if output_path is not None else Path(source_path).with_name(f"{Path(source_path).stem}_astra.mp4")
        target.write_bytes(b"topaz-upscaled")
        return type(
            "_TopazResult",
            (),
            {
                "request_id": "topaz-req-123",
                "output_path": target,
                "source_path": Path(source_path),
                "model": "astra",
                "status_payload": {"status": "complete", "download": {"url": "https://download.example/video.mp4"}},
            },
        )()


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

    def test_uploaded_image_can_create_candidate_batch_from_visual_prompting(self):
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
                app = create_app(root / "configs/profiles/lofi.yaml")
                app.config["TESTING"] = True
                app.pipeline.settings.paths.runtime_root = runtime_root
                app.pipeline.settings.paths.outputs_dir = runtime_root / "outputs"
                app.pipeline.settings.paths.incoming_dir = runtime_root / "incoming"
                app.pipeline.settings.paths.images_dir = runtime_root / "images"
                app.pipeline.settings.paths.logs_dir = runtime_root / "logs"
                app.pipeline.settings.paths.runtime_root.mkdir(parents=True, exist_ok=True)
                app.pipeline.settings.paths.outputs_dir.mkdir(parents=True, exist_ok=True)
                app.pipeline.settings.paths.incoming_dir.mkdir(parents=True, exist_ok=True)
                app.pipeline.settings.paths.images_dir.mkdir(parents=True, exist_ok=True)
                app.pipeline.settings.paths.logs_dir.mkdir(parents=True, exist_ok=True)
                app.pipeline.settings.replicate.debug.enabled = False
                app.pipeline.settings.replicate.debug.reuse_candidate_batch = False
                app.pipeline.settings.replicate.debug.candidate_batch_id = ""
                app.pipeline.openai_provider = _FakeOpenAIProvider(
                    ['{"prompts":["Prompt 1","Prompt 2","Prompt 3","Prompt 4","Prompt 5"]}']
                )
                app.pipeline.replicate_provider = _FakeReplicateProvider()

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
                self.assertIn("/?batch_id=", response.headers["Location"])
            finally:
                if created_env:
                    env_file.unlink(missing_ok=True)

    def test_lofi_project_page_offers_screen_replace_and_route_renders_output(self):
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
                app = create_app(root / "configs/profiles/lofi.yaml")
                app.config["TESTING"] = True
                app.pipeline.settings.paths.runtime_root = runtime_root
                app.pipeline.settings.paths.outputs_dir = runtime_root / "outputs"
                app.pipeline.settings.paths.incoming_dir = runtime_root / "incoming"
                app.pipeline.settings.paths.images_dir = runtime_root / "images"
                app.pipeline.settings.paths.logs_dir = runtime_root / "logs"
                app.pipeline.settings.paths.runtime_root.mkdir(parents=True, exist_ok=True)
                app.pipeline.settings.paths.outputs_dir.mkdir(parents=True, exist_ok=True)
                app.pipeline.settings.paths.incoming_dir.mkdir(parents=True, exist_ok=True)
                app.pipeline.settings.paths.images_dir.mkdir(parents=True, exist_ok=True)
                app.pipeline.settings.paths.logs_dir.mkdir(parents=True, exist_ok=True)
                app.pipeline.settings.screen_replace.overlay_video_path = temp_dir / "overlay.mp4"
                (temp_dir / "overlay.mp4").write_bytes(b"overlay")
                app.pipeline.screen_replace_service = _FakeScreenReplaceService()

                upload_path = temp_dir / "upload.png"
                upload_path.write_bytes(_PNG_BYTES)
                render_path = temp_dir / "render.mp4"
                render_path.write_bytes(b"render")
                project = app.pipeline.runtime.create_project_from_assets(
                    upload_path,
                    render_visual_source=render_path,
                    render_visual_duration_seconds=12.0,
                    render_visual_fps=24.0,
                )

                client = app.test_client()
                page = client.get(f"/?project_id={project.project_id}")

                self.assertEqual(page.status_code, 200)
                self.assertIn(b"Render screen replacement", page.data)

                response = client.post(
                    f"/projects/{project.project_id}/screen-replace",
                    data={"quad_norm": "0.43,0.36;0.74,0.37;0.73,0.61;0.42,0.60"},
                    follow_redirects=False,
                )

                self.assertEqual(response.status_code, 302)
                updated_project = app.pipeline.runtime.load_project(project.project_id)
                self.assertIsNotNone(updated_project.render_visual_asset)
                assert updated_project.render_visual_asset is not None
                self.assertEqual(updated_project.render_visual_asset.path.name, "render_visual_screen_replace.mp4")
                self.assertTrue((updated_project.project_dir / "screen_replace.json").exists())
            finally:
                if created_env:
                    env_file.unlink(missing_ok=True)

    def test_lofi_project_page_can_render_reusable_screen_overlay_video(self):
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
                app = create_app(root / "configs/profiles/lofi.yaml")
                app.config["TESTING"] = True
                app.pipeline.settings.paths.runtime_root = runtime_root
                app.pipeline.settings.paths.outputs_dir = runtime_root / "outputs"
                app.pipeline.settings.paths.incoming_dir = runtime_root / "incoming"
                app.pipeline.settings.paths.images_dir = runtime_root / "images"
                app.pipeline.settings.paths.logs_dir = runtime_root / "logs"
                app.pipeline.settings.paths.runtime_root.mkdir(parents=True, exist_ok=True)
                app.pipeline.settings.paths.outputs_dir.mkdir(parents=True, exist_ok=True)
                app.pipeline.settings.paths.incoming_dir.mkdir(parents=True, exist_ok=True)
                app.pipeline.settings.paths.images_dir.mkdir(parents=True, exist_ok=True)
                app.pipeline.settings.paths.logs_dir.mkdir(parents=True, exist_ok=True)

                overlay_output = temp_dir / "lofi_overlay.local.mp4"
                overlay_service = _FakeScreenOverlayBuilderService(overlay_output)
                app.pipeline.screen_overlay_builder_service = overlay_service

                def _render_overlay(**_kwargs):
                    overlay_output.write_bytes(b"overlay-video")
                    overlay_service.metadata_path().write_text("{}", encoding="utf-8")
                    return overlay_output

                app.pipeline.render_screen_overlay_video = _render_overlay

                upload_path = temp_dir / "upload.png"
                upload_path.write_bytes(_PNG_BYTES)
                render_path = temp_dir / "render.mp4"
                render_path.write_bytes(b"render")
                project = app.pipeline.runtime.create_project_from_assets(
                    upload_path,
                    render_visual_source=render_path,
                    render_visual_duration_seconds=12.0,
                    render_visual_fps=24.0,
                )

                client = app.test_client()
                response = client.post(
                    f"/projects/{project.project_id}/render-screen-overlay",
                    follow_redirects=False,
                )

                self.assertEqual(response.status_code, 302)
                self.assertTrue(overlay_output.exists())
                page = client.get(f"/?project_id={project.project_id}")
                self.assertIn(b"Render reusable overlay video", page.data)
                self.assertIn(b"Reusable overlay preview", page.data)
            finally:
                if created_env:
                    env_file.unlink(missing_ok=True)

    def test_lofi_project_page_offers_topaz_upscale_before_screen_replace(self):
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
                app = create_app(root / "configs/profiles/lofi.yaml")
                app.config["TESTING"] = True
                app.pipeline.settings.paths.runtime_root = runtime_root
                app.pipeline.settings.paths.outputs_dir = runtime_root / "outputs"
                app.pipeline.settings.paths.incoming_dir = runtime_root / "incoming"
                app.pipeline.settings.paths.images_dir = runtime_root / "images"
                app.pipeline.settings.paths.logs_dir = runtime_root / "logs"
                app.pipeline.settings.paths.runtime_root.mkdir(parents=True, exist_ok=True)
                app.pipeline.settings.paths.outputs_dir.mkdir(parents=True, exist_ok=True)
                app.pipeline.settings.paths.incoming_dir.mkdir(parents=True, exist_ok=True)
                app.pipeline.settings.paths.images_dir.mkdir(parents=True, exist_ok=True)
                app.pipeline.settings.paths.logs_dir.mkdir(parents=True, exist_ok=True)
                app.pipeline.topaz_provider = _FakeTopazProvider()

                upload_path = temp_dir / "upload.png"
                upload_path.write_bytes(_PNG_BYTES)
                render_path = temp_dir / "render.mp4"
                render_path.write_bytes(b"render")
                project = app.pipeline.runtime.create_project_from_assets(
                    upload_path,
                    render_visual_source=render_path,
                    render_visual_duration_seconds=12.0,
                    render_visual_fps=24.0,
                )

                client = app.test_client()
                page = client.get(f"/?project_id={project.project_id}")

                self.assertEqual(page.status_code, 200)
                self.assertIn(b"Upscale render with Topaz", page.data)

                response = client.post(
                    f"/projects/{project.project_id}/topaz-upscale",
                    follow_redirects=False,
                )

                self.assertEqual(response.status_code, 302)
                updated_project = app.pipeline.runtime.load_project(project.project_id)
                self.assertIsNotNone(updated_project.render_visual_asset)
                assert updated_project.render_visual_asset is not None
                self.assertEqual(updated_project.render_visual_asset.path.name, "render_visual_astra.mp4")
                self.assertEqual(updated_project.render_visual_asset.path.read_bytes(), b"topaz-upscaled")
                self.assertTrue((updated_project.project_dir / "topaz_upscale.json").exists())
            finally:
                if created_env:
                    env_file.unlink(missing_ok=True)
