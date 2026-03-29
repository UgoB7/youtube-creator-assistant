import base64
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from youtube_creator_assistant.core.config import load_settings
from youtube_creator_assistant.core.models import AudioTrack, ChapterEntry
from youtube_creator_assistant.core.pipeline import ContentPipeline
from youtube_creator_assistant.providers.topaz import TopazVideoUpscaleResult


_PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9WlH0x8AAAAASUVORK5CYII="
)


class _FakeReplicateProvider:
    def __init__(self, payload: bytes = b"fake-video"):
        self.payload = payload
        self.video_inputs: list[Path] = []

    def generate_video_bytes(self, image_path: Path) -> bytes:
        self.video_inputs.append(Path(image_path))
        return self.payload


class _FailingReplicateProvider:
    def generate_video_bytes(self, _image_path: Path) -> bytes:
        raise AssertionError("Replicate video generation should not be called when debug render reuse is enabled.")


class _FakeScreenReplaceService:
    def __init__(self):
        self.calls: list[dict[str, object]] = []

    def parse_quad_norm(self, raw: str):
        cleaned = str(raw or "").strip()
        self.calls.append({"kind": "parse", "raw": cleaned})
        return [(0.43, 0.36), (0.74, 0.37), (0.42, 0.60), (0.73, 0.61)]

    def serialize_quad_norm(self, points):
        self.calls.append({"kind": "serialize", "points": list(points)})
        return "0.4300,0.3600;0.7400,0.3700;0.4200,0.6000;0.7300,0.6100"

    def render_video(self, *, base_video_path: Path, output_path: Path, quad_norm: str | None = None) -> Path:
        self.calls.append(
            {
                "kind": "render",
                "base_video_path": Path(base_video_path),
                "output_path": Path(output_path),
                "quad_norm": quad_norm,
            }
        )
        output_path.write_bytes(f"screen-replace:{Path(base_video_path).name}".encode("utf-8"))
        return output_path


class _FakeTopazProvider:
    def __init__(self, payload: bytes = b"topaz-video"):
        self.payload = payload
        self.calls: list[tuple[Path, Path | None]] = []

    def upscale_video(self, source_path: Path, output_path: Path | None = None) -> TopazVideoUpscaleResult:
        chosen_output = output_path or source_path.with_name(f"{source_path.stem}_astra.mp4")
        chosen_output.write_bytes(self.payload)
        self.calls.append((Path(source_path), Path(chosen_output)))
        return TopazVideoUpscaleResult(
            request_id="topaz-req-123",
            output_path=Path(chosen_output),
            source_path=Path(source_path),
            model="astra",
            status_payload={"status": "complete", "download": {"url": "https://download.example/video.mp4"}},
        )


class ContentPipelineTests(unittest.TestCase):
    def test_enchanted_selected_titles_are_limited_by_yaml(self):
        root = Path(__file__).resolve().parents[1]
        settings = load_settings(root / "configs/profiles/enchanted_melodies.yaml")
        pipeline = ContentPipeline(settings)

        selected = pipeline._normalize_selected_titles(
            ["First title", "Second title", "Third title"]
        )

        self.assertEqual(selected, ["First title"])

    def test_build_package_skips_reference_generation_when_disabled_in_config(self):
        root = Path(__file__).resolve().parents[1]
        settings = load_settings(root / "configs/profiles/enchanted_melodies.yaml")

        with tempfile.TemporaryDirectory() as temp_dir_name:
            temp_dir = Path(temp_dir_name)
            settings.paths.runtime_root = temp_dir / "runtime"
            settings.paths.outputs_dir = settings.paths.runtime_root / "outputs"
            settings.paths.incoming_dir = settings.paths.runtime_root / "incoming"
            settings.paths.images_dir = settings.paths.runtime_root / "images"
            settings.paths.logs_dir = settings.paths.runtime_root / "logs"
            settings.paths.psalms_dir = temp_dir / "assets" / "audio"
            settings.paths.gospel_dir = temp_dir / "assets" / "audio"
            settings.paths.psalms_dir.mkdir(parents=True, exist_ok=True)
            settings.paths.gospel_dir.mkdir(parents=True, exist_ok=True)

            uploaded_image = temp_dir / "uploaded.png"
            uploaded_image.write_bytes(_PNG_BYTES)

            pipeline = ContentPipeline(settings)
            project = pipeline.runtime.create_project(uploaded_image)

            pipeline.title_service.generate_reference_preferences_for_titles = lambda *_args, **_kwargs: (_ for _ in ()).throw(
                AssertionError("reference guidance should be disabled")
            )
            pipeline.title_service.generate_themes = lambda *_args, **_kwargs: ["Dreamy calm"]

            def fake_build_audio(project_arg, preferred_refs):
                project_arg.audio_tracks = [
                    AudioTrack(
                        kind="psalm",
                        label="Track - 001",
                        source_path=settings.paths.psalms_dir / "Track - 001.wav",
                        copied_path=None,
                        duration_seconds=10.0,
                    )
                ]
                project_arg.chapters = [ChapterEntry(timestamp="0:00:00", label="Track - 001")]
                self.assertEqual(preferred_refs, [])
                return project_arg

            pipeline.audio_service.build_for_project = fake_build_audio
            pipeline.description_service.build_description = lambda project_arg: project_arg
            pipeline.thumbnail_service.build_thumbnail = lambda project_arg: project_arg
            pipeline.render_plan_builder.build_for_project = lambda _project: SimpleNamespace(
                timeline_name="enchanted-test",
                write_json=lambda path: path.write_text("{}", encoding="utf-8"),
            )

            built_project = pipeline.build_package(project.project_id, "Quiet enchanted rest")

            self.assertEqual(built_project.preferred_references, [])
            self.assertEqual(
                (built_project.project_dir / "preferred_references.txt").read_text(encoding="utf-8"),
                "",
            )

    def test_shepherd_uploaded_image_generates_render_video(self):
        root = Path(__file__).resolve().parents[1]
        settings = load_settings(root / "configs/profiles/shepherd.yaml")

        with tempfile.TemporaryDirectory() as temp_dir_name:
            temp_dir = Path(temp_dir_name)
            settings.paths.runtime_root = temp_dir / "runtime"
            settings.paths.outputs_dir = settings.paths.runtime_root / "outputs"
            settings.paths.incoming_dir = settings.paths.runtime_root / "incoming"
            settings.paths.images_dir = settings.paths.runtime_root / "images"
            settings.paths.logs_dir = settings.paths.runtime_root / "logs"
            settings.paths.psalms_dir = temp_dir / "assets" / "psalms"
            settings.paths.gospel_dir = temp_dir / "assets" / "gospel"
            settings.paths.psalms_dir.mkdir(parents=True, exist_ok=True)
            settings.paths.gospel_dir.mkdir(parents=True, exist_ok=True)

            uploaded_image = temp_dir / "uploaded.png"
            uploaded_image.write_bytes(_PNG_BYTES)

            pipeline = ContentPipeline(settings)
            fake_replicate = _FakeReplicateProvider()
            pipeline.replicate_provider = fake_replicate

            project = pipeline.create_project(uploaded_image)

            self.assertEqual(fake_replicate.video_inputs, [uploaded_image.resolve()])
            self.assertEqual(project.visual_asset.kind, "image")
            self.assertIsNotNone(project.render_visual_asset)
            assert project.render_visual_asset is not None
            self.assertEqual(project.render_visual_asset.kind, "video")
            self.assertTrue(project.render_visual_asset.path.exists())
            self.assertEqual(project.render_visual_asset.duration_seconds, float(settings.replicate.video_duration))
            self.assertEqual(project.render_visual_asset.fps, float(settings.replicate.video_fps))
            self.assertEqual(project.render_visual_asset.path.read_bytes(), b"fake-video")

    def test_mercy_uploaded_image_generates_render_video(self):
        root = Path(__file__).resolve().parents[1]
        settings = load_settings(root / "configs/profiles/mercy.yaml")

        with tempfile.TemporaryDirectory() as temp_dir_name:
            temp_dir = Path(temp_dir_name)
            settings.paths.runtime_root = temp_dir / "runtime"
            settings.paths.outputs_dir = settings.paths.runtime_root / "outputs"
            settings.paths.incoming_dir = settings.paths.runtime_root / "incoming"
            settings.paths.images_dir = settings.paths.runtime_root / "images"
            settings.paths.logs_dir = settings.paths.runtime_root / "logs"
            settings.paths.psalms_dir = temp_dir / "assets" / "psalms"
            settings.paths.gospel_dir = temp_dir / "assets" / "gospel"
            settings.paths.psalms_dir.mkdir(parents=True, exist_ok=True)
            settings.paths.gospel_dir.mkdir(parents=True, exist_ok=True)

            uploaded_image = temp_dir / "uploaded.png"
            uploaded_image.write_bytes(_PNG_BYTES)

            pipeline = ContentPipeline(settings)
            fake_replicate = _FakeReplicateProvider()
            pipeline.replicate_provider = fake_replicate

            project = pipeline.create_project(uploaded_image)

            self.assertEqual(fake_replicate.video_inputs, [uploaded_image.resolve()])
            self.assertEqual(project.visual_asset.kind, "image")
            self.assertIsNotNone(project.render_visual_asset)
            assert project.render_visual_asset is not None
            self.assertEqual(project.render_visual_asset.kind, "video")

    def test_regenerate_project_render_video_rewrites_existing_render_asset(self):
        root = Path(__file__).resolve().parents[1]
        settings = load_settings(root / "configs/profiles/shepherd.yaml")

        with tempfile.TemporaryDirectory() as temp_dir_name:
            temp_dir = Path(temp_dir_name)
            settings.paths.runtime_root = temp_dir / "runtime"
            settings.paths.outputs_dir = settings.paths.runtime_root / "outputs"
            settings.paths.incoming_dir = settings.paths.runtime_root / "incoming"
            settings.paths.images_dir = settings.paths.runtime_root / "images"
            settings.paths.logs_dir = settings.paths.runtime_root / "logs"
            settings.paths.psalms_dir = temp_dir / "assets" / "psalms"
            settings.paths.gospel_dir = temp_dir / "assets" / "gospel"
            settings.paths.psalms_dir.mkdir(parents=True, exist_ok=True)
            settings.paths.gospel_dir.mkdir(parents=True, exist_ok=True)

            uploaded_image = temp_dir / "uploaded.png"
            uploaded_image.write_bytes(_PNG_BYTES)

            pipeline = ContentPipeline(settings)
            first_replicate = _FakeReplicateProvider(payload=b"first-video")
            pipeline.replicate_provider = first_replicate
            project = pipeline.create_project(uploaded_image)

            second_replicate = _FakeReplicateProvider(payload=b"second-video")
            pipeline.replicate_provider = second_replicate
            project.status = "resolve_synced"
            pipeline.runtime.save_project(project)

            regenerated = pipeline.regenerate_project_render_video(project.project_id)

            self.assertEqual(second_replicate.video_inputs, [project.visual_asset.path.resolve()])
            self.assertIsNotNone(regenerated.render_visual_asset)
            assert regenerated.render_visual_asset is not None
            self.assertEqual(regenerated.render_visual_asset.path.read_bytes(), b"second-video")
            self.assertEqual(regenerated.render_visual_asset.duration_seconds, float(settings.replicate.video_duration))
            self.assertEqual(regenerated.render_visual_asset.fps, float(settings.replicate.video_fps))
            self.assertEqual(regenerated.status, "package_built")
            self.assertIsNone(regenerated.resolve_last_synced_at)

    def test_regenerate_project_render_video_is_available_for_non_shepherd_profiles(self):
        root = Path(__file__).resolve().parents[1]
        settings = load_settings(root / "configs/profiles/vibes.yaml")
        settings.replicate.enabled = True
        settings.replicate.video_duration = 12
        settings.replicate.video_fps = 24

        with tempfile.TemporaryDirectory() as temp_dir_name:
            temp_dir = Path(temp_dir_name)
            settings.paths.runtime_root = temp_dir / "runtime"
            settings.paths.outputs_dir = settings.paths.runtime_root / "outputs"
            settings.paths.incoming_dir = settings.paths.runtime_root / "incoming"
            settings.paths.images_dir = settings.paths.runtime_root / "images"
            settings.paths.logs_dir = settings.paths.runtime_root / "logs"
            settings.paths.psalms_dir = temp_dir / "assets" / "psalms"
            settings.paths.gospel_dir = temp_dir / "assets" / "gospel"
            settings.paths.psalms_dir.mkdir(parents=True, exist_ok=True)
            settings.paths.gospel_dir.mkdir(parents=True, exist_ok=True)

            uploaded_image = temp_dir / "uploaded.png"
            uploaded_image.write_bytes(_PNG_BYTES)

            pipeline = ContentPipeline(settings)
            project = pipeline.runtime.create_project(uploaded_image)
            fake_replicate = _FakeReplicateProvider(payload=b"vibes-video")
            pipeline.replicate_provider = fake_replicate

            regenerated = pipeline.regenerate_project_render_video(project.project_id)

            self.assertEqual(fake_replicate.video_inputs, [project.visual_asset.path.resolve()])
            self.assertIsNotNone(regenerated.render_visual_asset)
            assert regenerated.render_visual_asset is not None
            self.assertEqual(regenerated.render_visual_asset.kind, "video")
            self.assertEqual(regenerated.render_visual_asset.path.read_bytes(), b"vibes-video")

    def test_create_project_reuses_debug_render_video_without_calling_replicate(self):
        root = Path(__file__).resolve().parents[1]
        settings = load_settings(root / "configs/profiles/shepherd.yaml")
        settings.replicate.debug.enabled = True
        settings.replicate.debug.reuse_render_video = True

        with tempfile.TemporaryDirectory() as temp_dir_name:
            temp_dir = Path(temp_dir_name)
            settings.paths.runtime_root = temp_dir / "runtime"
            settings.paths.outputs_dir = settings.paths.runtime_root / "outputs"
            settings.paths.incoming_dir = settings.paths.runtime_root / "incoming"
            settings.paths.images_dir = settings.paths.runtime_root / "images"
            settings.paths.logs_dir = settings.paths.runtime_root / "logs"
            settings.paths.psalms_dir = temp_dir / "assets" / "psalms"
            settings.paths.gospel_dir = temp_dir / "assets" / "gospel"
            settings.paths.psalms_dir.mkdir(parents=True, exist_ok=True)
            settings.paths.gospel_dir.mkdir(parents=True, exist_ok=True)

            uploaded_image = temp_dir / "uploaded.png"
            uploaded_image.write_bytes(_PNG_BYTES)
            debug_video = temp_dir / "debug_render.mp4"
            debug_video.write_bytes(b"debug-video")
            settings.replicate.debug.render_video_path = debug_video

            pipeline = ContentPipeline(settings)
            pipeline.replicate_provider = _FailingReplicateProvider()

            project = pipeline.create_project(uploaded_image)

            self.assertIsNotNone(project.render_visual_asset)
            assert project.render_visual_asset is not None
            self.assertEqual(project.render_visual_asset.path.read_bytes(), b"debug-video")

    def test_create_project_from_candidate_reuses_debug_render_video_without_calling_replicate(self):
        root = Path(__file__).resolve().parents[1]
        settings = load_settings(root / "configs/profiles/shepherd.yaml")
        settings.replicate.debug.enabled = True
        settings.replicate.debug.reuse_render_video = True

        with tempfile.TemporaryDirectory() as temp_dir_name:
            temp_dir = Path(temp_dir_name)
            settings.paths.runtime_root = temp_dir / "runtime"
            settings.paths.outputs_dir = settings.paths.runtime_root / "outputs"
            settings.paths.incoming_dir = settings.paths.runtime_root / "incoming"
            settings.paths.images_dir = settings.paths.runtime_root / "images"
            settings.paths.logs_dir = settings.paths.runtime_root / "logs"
            settings.paths.psalms_dir = temp_dir / "assets" / "psalms"
            settings.paths.gospel_dir = temp_dir / "assets" / "gospel"
            settings.paths.psalms_dir.mkdir(parents=True, exist_ok=True)
            settings.paths.gospel_dir.mkdir(parents=True, exist_ok=True)

            batch_dir = settings.paths.incoming_dir / "replicate_generated" / "shepherd-candidates-20990101-000000"
            batch_dir.mkdir(parents=True, exist_ok=True)
            candidate_image = batch_dir / "candidate_01.png"
            candidate_image.write_bytes(_PNG_BYTES)
            (batch_dir / "batch.json").write_text(
                (
                    "{\n"
                    '  "batch_id": "shepherd-candidates-20990101-000000",\n'
                    '  "profile_id": "shepherd",\n'
                    f'  "batch_dir": "{batch_dir}",\n'
                    '  "created_at": "2099-01-01T00:00:00+00:00",\n'
                    '  "candidates": [\n'
                    "    {\n"
                    '      "candidate_id": "candidate-01",\n'
                    '      "prompt": "Prompt A",\n'
                    f'      "image_path": "{candidate_image}",\n'
                    '      "label": "Candidate 01"\n'
                    "    }\n"
                    "  ],\n"
                    '  "source_visual_asset": null\n'
                    "}\n"
                ),
                encoding="utf-8",
            )
            debug_video = temp_dir / "candidate_debug_render.mp4"
            debug_video.write_bytes(b"debug-candidate-video")
            settings.replicate.debug.render_video_path = debug_video

            pipeline = ContentPipeline(settings)
            pipeline.replicate_provider = _FailingReplicateProvider()

            project = pipeline.create_project_from_candidate(
                "shepherd-candidates-20990101-000000",
                "candidate-01",
            )

            self.assertIsNotNone(project.render_visual_asset)
            assert project.render_visual_asset is not None
            self.assertEqual(project.render_visual_asset.path.read_bytes(), b"debug-candidate-video")

    def test_create_project_from_candidate_allows_debug_video_path_to_match_destination(self):
        root = Path(__file__).resolve().parents[1]
        settings = load_settings(root / "configs/profiles/shepherd.yaml")
        settings.replicate.debug.enabled = True
        settings.replicate.debug.reuse_render_video = True

        with tempfile.TemporaryDirectory() as temp_dir_name:
            temp_dir = Path(temp_dir_name)
            settings.paths.runtime_root = temp_dir / "runtime"
            settings.paths.outputs_dir = settings.paths.runtime_root / "outputs"
            settings.paths.incoming_dir = settings.paths.runtime_root / "incoming"
            settings.paths.images_dir = settings.paths.runtime_root / "images"
            settings.paths.logs_dir = settings.paths.runtime_root / "logs"
            settings.paths.psalms_dir = temp_dir / "assets" / "psalms"
            settings.paths.gospel_dir = temp_dir / "assets" / "gospel"
            settings.paths.psalms_dir.mkdir(parents=True, exist_ok=True)
            settings.paths.gospel_dir.mkdir(parents=True, exist_ok=True)

            batch_dir = settings.paths.incoming_dir / "replicate_generated" / "shepherd-candidates-20990101-000000"
            batch_dir.mkdir(parents=True, exist_ok=True)
            candidate_image = batch_dir / "candidate_01.png"
            candidate_image.write_bytes(_PNG_BYTES)
            debug_video = batch_dir / "candidate-01_render.mp4"
            debug_video.write_bytes(b"same-file-debug-video")
            (batch_dir / "batch.json").write_text(
                (
                    "{\n"
                    '  "batch_id": "shepherd-candidates-20990101-000000",\n'
                    '  "profile_id": "shepherd",\n'
                    f'  "batch_dir": "{batch_dir}",\n'
                    '  "created_at": "2099-01-01T00:00:00+00:00",\n'
                    '  "candidates": [\n'
                    "    {\n"
                    '      "candidate_id": "candidate-01",\n'
                    '      "prompt": "Prompt A",\n'
                    f'      "image_path": "{candidate_image}",\n'
                    '      "label": "Candidate 01"\n'
                    "    }\n"
                    "  ],\n"
                    '  "source_visual_asset": null\n'
                    "}\n"
                ),
                encoding="utf-8",
            )
            settings.replicate.debug.render_video_path = debug_video

            pipeline = ContentPipeline(settings)
            pipeline.replicate_provider = _FailingReplicateProvider()

            project = pipeline.create_project_from_candidate(
                "shepherd-candidates-20990101-000000",
                "candidate-01",
            )

            self.assertIsNotNone(project.render_visual_asset)
            assert project.render_visual_asset is not None
            self.assertEqual(project.render_visual_asset.path.read_bytes(), b"same-file-debug-video")

    def test_render_screen_replacement_updates_project_and_reuses_original_render_video_on_repeat(self):
        root = Path(__file__).resolve().parents[1]
        settings = load_settings(root / "configs/profiles/shepherd.yaml")
        settings.screen_replace.enabled = True
        settings.screen_replace.overlay_video_path = root / "assets" / "screen_replace" / "test_overlay.mp4"
        settings.screen_replace.output_filename = "render_visual_screen_replace.mp4"
        settings.screen_replace.target_fps = 30

        with tempfile.TemporaryDirectory() as temp_dir_name:
            temp_dir = Path(temp_dir_name)
            settings.paths.runtime_root = temp_dir / "runtime"
            settings.paths.outputs_dir = settings.paths.runtime_root / "outputs"
            settings.paths.incoming_dir = settings.paths.runtime_root / "incoming"
            settings.paths.images_dir = settings.paths.runtime_root / "images"
            settings.paths.logs_dir = settings.paths.runtime_root / "logs"
            settings.paths.psalms_dir = temp_dir / "assets" / "psalms"
            settings.paths.gospel_dir = temp_dir / "assets" / "gospel"
            settings.paths.psalms_dir.mkdir(parents=True, exist_ok=True)
            settings.paths.gospel_dir.mkdir(parents=True, exist_ok=True)

            uploaded_image = temp_dir / "uploaded.png"
            uploaded_image.write_bytes(_PNG_BYTES)
            render_video = temp_dir / "render_source.mp4"
            render_video.write_bytes(b"original-render-video")

            pipeline = ContentPipeline(settings)
            fake_screen_replace = _FakeScreenReplaceService()
            pipeline.screen_replace_service = fake_screen_replace

            project = pipeline.runtime.create_project_from_assets(
                uploaded_image,
                render_visual_source=render_video,
                render_visual_duration_seconds=12.0,
                render_visual_fps=24.0,
            )

            rendered = pipeline.render_screen_replacement(project.project_id)

            self.assertIsNotNone(rendered.render_visual_asset)
            assert rendered.render_visual_asset is not None
            self.assertEqual(rendered.render_visual_asset.path.name, "render_visual_screen_replace.mp4")
            self.assertEqual(rendered.render_visual_asset.fps, 30.0)
            self.assertEqual(
                rendered.render_visual_asset.path.read_bytes(),
                b"screen-replace:render_visual.mp4",
            )
            self.assertTrue((rendered.project_dir / "screen_replace.json").exists())
            self.assertEqual(
                (rendered.project_dir / "screen_replace_quad_norm.txt").read_text(encoding="utf-8"),
                "0.4300,0.3600;0.7400,0.3700;0.4200,0.6000;0.7300,0.6100",
            )

            rerendered = pipeline.render_screen_replacement(project.project_id, quad_norm="0.1,0.2;0.8,0.2;0.1,0.9;0.8,0.9")

            self.assertIsNotNone(rerendered.render_visual_asset)
            assert rerendered.render_visual_asset is not None
            render_calls = [call for call in fake_screen_replace.calls if call.get("kind") == "render"]
            self.assertEqual(len(render_calls), 2)
            self.assertEqual(Path(render_calls[0]["base_video_path"]).name, "render_visual.mp4")
            self.assertEqual(Path(render_calls[1]["base_video_path"]).name, "render_visual.mp4")

    def test_topaz_upscale_project_render_video_updates_project_render_asset(self):
        root = Path(__file__).resolve().parents[1]
        settings = load_settings(root / "configs/profiles/lofi.yaml")

        with tempfile.TemporaryDirectory() as temp_dir_name:
            temp_dir = Path(temp_dir_name)
            settings.paths.runtime_root = temp_dir / "runtime"
            settings.paths.outputs_dir = settings.paths.runtime_root / "outputs"
            settings.paths.incoming_dir = settings.paths.runtime_root / "incoming"
            settings.paths.images_dir = settings.paths.runtime_root / "images"
            settings.paths.logs_dir = settings.paths.runtime_root / "logs"
            settings.paths.psalms_dir = temp_dir / "assets" / "psalms"
            settings.paths.gospel_dir = temp_dir / "assets" / "gospel"
            settings.paths.psalms_dir.mkdir(parents=True, exist_ok=True)
            settings.paths.gospel_dir.mkdir(parents=True, exist_ok=True)

            uploaded_video = temp_dir / "uploaded.mp4"
            uploaded_video.write_bytes(b"source-video")
            render_video = temp_dir / "render_visual.mp4"
            render_video.write_bytes(b"render-video")

            pipeline = ContentPipeline(settings)
            fake_topaz = _FakeTopazProvider(payload=b"upscaled-video")
            pipeline.topaz_provider = fake_topaz

            project = pipeline.runtime.create_project_from_assets(
                uploaded_video,
                render_visual_source=render_video,
                primary_visual_duration_seconds=12.0,
                primary_visual_fps=24.0,
                render_visual_duration_seconds=12.0,
                render_visual_fps=24.0,
            )

            upscaled = pipeline.upscale_project_render_video_with_topaz(project.project_id)

            self.assertEqual(fake_topaz.calls[0][0].name, "render_visual.mp4")
            self.assertIsNotNone(upscaled.render_visual_asset)
            assert upscaled.render_visual_asset is not None
            self.assertEqual(upscaled.render_visual_asset.path.name, "render_visual_astra.mp4")
            self.assertEqual(upscaled.render_visual_asset.path.read_bytes(), b"upscaled-video")
            self.assertTrue((upscaled.project_dir / "topaz_upscale.json").exists())


if __name__ == "__main__":
    unittest.main()
