import json
import unittest
from pathlib import Path
from unittest.mock import patch

from youtube_creator_assistant.core.config import load_settings
from youtube_creator_assistant.core.models import AudioTrack, VideoProject, VisualAsset
from youtube_creator_assistant.core.runtime import RuntimeManager
from youtube_creator_assistant.features.render.builder import RenderPlanBuilder


class RenderPlanBuilderTests(unittest.TestCase):
    def test_builds_vibes_timeline_name_from_chronological_order(self):
        root = Path(__file__).resolve().parents[1]
        settings = load_settings(root / "configs/profiles/vibes.yaml")

        temp_root = root / "runtime" / "test-render-plan"
        outputs_dir = temp_root / "outputs"
        incoming_dir = temp_root / "incoming"
        images_dir = temp_root / "images"
        logs_dir = temp_root / "logs"
        outputs_dir.mkdir(parents=True, exist_ok=True)
        incoming_dir.mkdir(parents=True, exist_ok=True)
        images_dir.mkdir(parents=True, exist_ok=True)
        logs_dir.mkdir(parents=True, exist_ok=True)

        settings.paths.runtime_root = temp_root
        settings.paths.outputs_dir = outputs_dir
        settings.paths.incoming_dir = incoming_dir
        settings.paths.images_dir = images_dir
        settings.paths.logs_dir = logs_dir

        image_path = temp_root / "visual.png"
        image_path.write_bytes(b"fake")
        audio_path = temp_root / "track.mp3"
        audio_path.write_bytes(b"fake")

        project_old = VideoProject(
            project_id="older",
            profile_id="vibes",
            project_dir=outputs_dir / "older",
            visual_asset=VisualAsset(kind="image", path=image_path, original_name="visual.png"),
            created_at="2026-01-01T00:00:00+00:00",
            audio_tracks=[
                AudioTrack(
                    kind="psalm",
                    label="Psalm 1",
                    source_path=audio_path,
                    copied_path=audio_path,
                    duration_seconds=60.0,
                )
            ],
        )
        project_new = VideoProject(
            project_id="newer",
            profile_id="vibes",
            project_dir=outputs_dir / "newer",
            visual_asset=VisualAsset(kind="image", path=image_path, original_name="visual.png"),
            created_at="2026-01-02T00:00:00+00:00",
            audio_tracks=[
                AudioTrack(
                    kind="psalm",
                    label="Psalm 2",
                    source_path=audio_path,
                    copied_path=audio_path,
                    duration_seconds=90.0,
                )
            ],
        )

        for project in (project_old, project_new):
            project.project_dir.mkdir(parents=True, exist_ok=True)
            (project.project_dir / "project.json").write_text(
                json.dumps(project.to_dict(), indent=2),
                encoding="utf-8",
            )

        runtime = RuntimeManager(settings)
        plan = RenderPlanBuilder(settings, runtime).build_for_project(project_new)

        self.assertEqual(plan.timeline_index, 1)
        self.assertEqual(plan.timeline_name, "vibes01")

    def test_cuts_audio_and_visual_to_exact_target_duration(self):
        root = Path(__file__).resolve().parents[1]
        settings = load_settings(root / "configs/profiles/vibes.yaml")

        temp_root = root / "runtime" / "test-render-plan-target-duration"
        outputs_dir = temp_root / "outputs"
        incoming_dir = temp_root / "incoming"
        images_dir = temp_root / "images"
        logs_dir = temp_root / "logs"
        outputs_dir.mkdir(parents=True, exist_ok=True)
        incoming_dir.mkdir(parents=True, exist_ok=True)
        images_dir.mkdir(parents=True, exist_ok=True)
        logs_dir.mkdir(parents=True, exist_ok=True)

        settings.paths.runtime_root = temp_root
        settings.paths.outputs_dir = outputs_dir
        settings.paths.incoming_dir = incoming_dir
        settings.paths.images_dir = images_dir
        settings.paths.logs_dir = logs_dir
        settings.workflow.fps = 30
        settings.workflow.target_duration_tc = "0:00:25:00"
        settings.workflow.target_duration_tc = "0:00:10:00"
        settings.workflow.trim_first_audio_seconds = 0.0

        image_path = temp_root / "visual.png"
        image_path.write_bytes(b"fake")
        audio_path = temp_root / "track.mp3"
        audio_path.write_bytes(b"fake")

        project = VideoProject(
            project_id="exact-target-project",
            profile_id="vibes",
            project_dir=outputs_dir / "exact-target-project",
            visual_asset=VisualAsset(kind="image", path=image_path, original_name="visual.png"),
            created_at="2026-01-01T00:00:00+00:00",
            audio_tracks=[
                AudioTrack(
                    kind="psalm",
                    label="Psalm 1",
                    source_path=audio_path,
                    copied_path=audio_path,
                    duration_seconds=20.0,
                )
            ],
        )

        project.project_dir.mkdir(parents=True, exist_ok=True)
        (project.project_dir / "project.json").write_text(
            json.dumps(project.to_dict(), indent=2),
            encoding="utf-8",
        )

        runtime = RuntimeManager(settings)
        plan = RenderPlanBuilder(settings, runtime).build_for_project(project)

        self.assertEqual(plan.duration_frames, 300)
        self.assertEqual(plan.audio_segments[-1].record_frame, 0)
        self.assertEqual(plan.audio_segments[-1].end_frame, 299)
        self.assertEqual(plan.visual_segments[-1].end_frame, 0)
        self.assertEqual(plan.visual_segments[-1].timeline_duration_frames, 300)

    @patch("youtube_creator_assistant.features.render.builder.probe_video_metadata", return_value=(10.0, 24.0))
    def test_loops_video_visual_for_shepherd(self, _mock_probe):
        root = Path(__file__).resolve().parents[1]
        settings = load_settings(root / "configs/profiles/shepherd.yaml")

        temp_root = root / "runtime" / "test-render-plan-shepherd"
        outputs_dir = temp_root / "outputs"
        incoming_dir = temp_root / "incoming"
        images_dir = temp_root / "images"
        logs_dir = temp_root / "logs"
        outputs_dir.mkdir(parents=True, exist_ok=True)
        incoming_dir.mkdir(parents=True, exist_ok=True)
        images_dir.mkdir(parents=True, exist_ok=True)
        logs_dir.mkdir(parents=True, exist_ok=True)

        settings.paths.runtime_root = temp_root
        settings.paths.outputs_dir = outputs_dir
        settings.paths.incoming_dir = incoming_dir
        settings.paths.images_dir = images_dir
        settings.paths.logs_dir = logs_dir
        settings.workflow.fps = 30
        settings.workflow.target_duration_tc = "0:00:26:19"

        video_path = temp_root / "visual.mp4"
        video_path.write_bytes(b"fake")
        image_path = temp_root / "image.png"
        image_path.write_bytes(b"fake-image")
        audio_path = temp_root / "track.mp3"
        audio_path.write_bytes(b"fake")

        project = VideoProject(
            project_id="shepherd-project",
            profile_id="shepherd",
            project_dir=outputs_dir / "shepherd-project",
            visual_asset=VisualAsset(kind="image", path=image_path, original_name="image.png"),
            render_visual_asset=VisualAsset(kind="video", path=video_path, original_name="visual.mp4"),
            created_at="2026-01-01T00:00:00+00:00",
            audio_tracks=[
                AudioTrack(
                    kind="psalm",
                    label="Psalm 2",
                    source_path=audio_path,
                    copied_path=audio_path,
                    duration_seconds=25.0,
                )
            ],
        )

        project.project_dir.mkdir(parents=True, exist_ok=True)
        (project.project_dir / "project.json").write_text(
            json.dumps(project.to_dict(), indent=2),
            encoding="utf-8",
        )

        runtime = RuntimeManager(settings)
        plan = RenderPlanBuilder(settings, runtime).build_for_project(project)

        self.assertEqual(plan.timeline_name, "shepherd00")
        self.assertGreater(len(plan.visual_segments), 1)
        self.assertTrue(all(segment.media_kind == "video" for segment in plan.visual_segments))

    @patch("youtube_creator_assistant.features.render.builder.probe_video_metadata", return_value=(12.0, 24.0))
    def test_uses_timeline_fps_override_for_segment_math(self, _mock_probe):
        root = Path(__file__).resolve().parents[1]
        settings = load_settings(root / "configs/profiles/shepherd.yaml")

        temp_root = root / "runtime" / "test-render-plan-fps-override"
        outputs_dir = temp_root / "outputs"
        incoming_dir = temp_root / "incoming"
        images_dir = temp_root / "images"
        logs_dir = temp_root / "logs"
        outputs_dir.mkdir(parents=True, exist_ok=True)
        incoming_dir.mkdir(parents=True, exist_ok=True)
        images_dir.mkdir(parents=True, exist_ok=True)
        logs_dir.mkdir(parents=True, exist_ok=True)

        settings.paths.runtime_root = temp_root
        settings.paths.outputs_dir = outputs_dir
        settings.paths.incoming_dir = incoming_dir
        settings.paths.images_dir = images_dir
        settings.paths.logs_dir = logs_dir
        settings.workflow.target_duration_tc = "0:00:30:00"
        settings.workflow.fps = 30

        video_path = temp_root / "visual.mp4"
        video_path.write_bytes(b"fake")
        image_path = temp_root / "image.png"
        image_path.write_bytes(b"fake-image")
        audio_path = temp_root / "track.mp3"
        audio_path.write_bytes(b"fake")

        project = VideoProject(
            project_id="fps-override-project",
            profile_id="shepherd",
            project_dir=outputs_dir / "fps-override-project",
            visual_asset=VisualAsset(kind="image", path=image_path, original_name="image.png"),
            render_visual_asset=VisualAsset(kind="video", path=video_path, original_name="visual.mp4"),
            created_at="2026-01-01T00:00:00+00:00",
            audio_tracks=[
                AudioTrack(
                    kind="psalm",
                    label="Psalm 2",
                    source_path=audio_path,
                    copied_path=audio_path,
                    duration_seconds=30.0,
                )
            ],
        )

        project.project_dir.mkdir(parents=True, exist_ok=True)
        (project.project_dir / "project.json").write_text(
            json.dumps(project.to_dict(), indent=2),
            encoding="utf-8",
        )

        runtime = RuntimeManager(settings)
        plan = RenderPlanBuilder(settings, runtime).build_for_project(project, fps_override=24.0)

        self.assertEqual(plan.fps, 24.0)
        self.assertEqual(plan.duration_frames, 720)
        self.assertEqual(plan.visual_segments[0].end_frame, 287)
        self.assertEqual(plan.visual_segments[1].record_frame, 288)

    @patch("youtube_creator_assistant.features.render.builder.probe_video_metadata", return_value=(12.041667, 24.0))
    def test_prefers_stored_video_timing_when_configured(self, _mock_probe):
        root = Path(__file__).resolve().parents[1]
        settings = load_settings(root / "configs/profiles/shepherd.yaml")
        settings.render.video_timing_source = "metadata_first"

        temp_root = root / "runtime" / "test-render-plan-metadata-first"
        outputs_dir = temp_root / "outputs"
        incoming_dir = temp_root / "incoming"
        images_dir = temp_root / "images"
        logs_dir = temp_root / "logs"
        outputs_dir.mkdir(parents=True, exist_ok=True)
        incoming_dir.mkdir(parents=True, exist_ok=True)
        images_dir.mkdir(parents=True, exist_ok=True)
        logs_dir.mkdir(parents=True, exist_ok=True)

        settings.paths.runtime_root = temp_root
        settings.paths.outputs_dir = outputs_dir
        settings.paths.incoming_dir = incoming_dir
        settings.paths.images_dir = images_dir
        settings.paths.logs_dir = logs_dir
        settings.workflow.target_duration_tc = "0:00:24:00"
        settings.workflow.fps = 24

        video_path = temp_root / "visual.mp4"
        video_path.write_bytes(b"fake")
        image_path = temp_root / "image.png"
        image_path.write_bytes(b"fake-image")
        audio_path = temp_root / "track.mp3"
        audio_path.write_bytes(b"fake")

        project = VideoProject(
            project_id="metadata-first-project",
            profile_id="shepherd",
            project_dir=outputs_dir / "metadata-first-project",
            visual_asset=VisualAsset(kind="image", path=image_path, original_name="image.png"),
            render_visual_asset=VisualAsset(
                kind="video",
                path=video_path,
                original_name="visual.mp4",
                duration_seconds=12.0,
                fps=24.0,
            ),
            created_at="2026-01-01T00:00:00+00:00",
            audio_tracks=[
                AudioTrack(
                    kind="psalm",
                    label="Psalm 2",
                    source_path=audio_path,
                    copied_path=audio_path,
                    duration_seconds=24.0,
                )
            ],
        )

        project.project_dir.mkdir(parents=True, exist_ok=True)
        (project.project_dir / "project.json").write_text(
            json.dumps(project.to_dict(), indent=2),
            encoding="utf-8",
        )

        runtime = RuntimeManager(settings)
        plan = RenderPlanBuilder(settings, runtime).build_for_project(project)

        self.assertEqual(plan.visual_segments[0].timeline_duration_frames, 288)
        self.assertEqual(plan.visual_segments[1].record_frame, 288)

    @patch("youtube_creator_assistant.features.render.builder.probe_video_metadata", return_value=(12.0, 24.0))
    def test_matches_legacy_shepherd_timeline_frame_looping(self, _mock_probe):
        root = Path(__file__).resolve().parents[1]
        settings = load_settings(root / "configs/profiles/shepherd.yaml")

        temp_root = root / "runtime" / "test-render-plan-legacy-looping"
        outputs_dir = temp_root / "outputs"
        incoming_dir = temp_root / "incoming"
        images_dir = temp_root / "images"
        logs_dir = temp_root / "logs"
        outputs_dir.mkdir(parents=True, exist_ok=True)
        incoming_dir.mkdir(parents=True, exist_ok=True)
        images_dir.mkdir(parents=True, exist_ok=True)
        logs_dir.mkdir(parents=True, exist_ok=True)

        settings.paths.runtime_root = temp_root
        settings.paths.outputs_dir = outputs_dir
        settings.paths.incoming_dir = incoming_dir
        settings.paths.images_dir = images_dir
        settings.paths.logs_dir = logs_dir
        settings.workflow.target_duration_tc = "0:00:30:00"
        settings.workflow.fps = 30

        video_path = temp_root / "visual.mp4"
        video_path.write_bytes(b"fake")
        image_path = temp_root / "image.png"
        image_path.write_bytes(b"fake-image")
        audio_path = temp_root / "track.mp3"
        audio_path.write_bytes(b"fake")

        project = VideoProject(
            project_id="legacy-looping-project",
            profile_id="shepherd",
            project_dir=outputs_dir / "legacy-looping-project",
            visual_asset=VisualAsset(kind="image", path=image_path, original_name="image.png"),
            render_visual_asset=VisualAsset(
                kind="video",
                path=video_path,
                original_name="visual.mp4",
                duration_seconds=12.0,
                fps=24.0,
            ),
            created_at="2026-01-01T00:00:00+00:00",
            audio_tracks=[
                AudioTrack(
                    kind="psalm",
                    label="Psalm 2",
                    source_path=audio_path,
                    copied_path=audio_path,
                    duration_seconds=30.0,
                )
            ],
        )

        project.project_dir.mkdir(parents=True, exist_ok=True)
        (project.project_dir / "project.json").write_text(
            json.dumps(project.to_dict(), indent=2),
            encoding="utf-8",
        )

        runtime = RuntimeManager(settings)
        plan = RenderPlanBuilder(settings, runtime).build_for_project(project)

        self.assertEqual(plan.visual_segments[0].end_frame, 359)
        self.assertEqual(plan.visual_segments[0].record_frame, 0)
        self.assertEqual(plan.visual_segments[1].record_frame, 360)

    @patch("youtube_creator_assistant.features.render.builder.probe_video_metadata", return_value=(12.0, 24.0))
    def test_uses_source_frames_for_video_trim_when_timeline_fps_differs(self, _mock_probe):
        root = Path(__file__).resolve().parents[1]
        settings = load_settings(root / "configs/profiles/shepherd.yaml")

        temp_root = root / "runtime" / "test-render-plan-source-fps"
        outputs_dir = temp_root / "outputs"
        incoming_dir = temp_root / "incoming"
        images_dir = temp_root / "images"
        logs_dir = temp_root / "logs"
        outputs_dir.mkdir(parents=True, exist_ok=True)
        incoming_dir.mkdir(parents=True, exist_ok=True)
        images_dir.mkdir(parents=True, exist_ok=True)
        logs_dir.mkdir(parents=True, exist_ok=True)

        settings.paths.runtime_root = temp_root
        settings.paths.outputs_dir = outputs_dir
        settings.paths.incoming_dir = incoming_dir
        settings.paths.images_dir = images_dir
        settings.paths.logs_dir = logs_dir

        video_path = temp_root / "visual.mp4"
        video_path.write_bytes(b"fake")
        image_path = temp_root / "image.png"
        image_path.write_bytes(b"fake-image")
        audio_path = temp_root / "track.mp3"
        audio_path.write_bytes(b"fake")

        project = VideoProject(
            project_id="source-fps-project",
            profile_id="shepherd",
            project_dir=outputs_dir / "source-fps-project",
            visual_asset=VisualAsset(kind="image", path=image_path, original_name="image.png"),
            render_visual_asset=VisualAsset(kind="video", path=video_path, original_name="visual.mp4"),
            created_at="2026-01-01T00:00:00+00:00",
            audio_tracks=[
                AudioTrack(
                    kind="psalm",
                    label="Psalm 2",
                    source_path=audio_path,
                    copied_path=audio_path,
                    duration_seconds=30.0,
                )
            ],
        )

        project.project_dir.mkdir(parents=True, exist_ok=True)
        (project.project_dir / "project.json").write_text(
            json.dumps(project.to_dict(), indent=2),
            encoding="utf-8",
        )

        runtime = RuntimeManager(settings)
        plan = RenderPlanBuilder(settings, runtime).build_for_project(project, fps_override=30.0)

        self.assertEqual(plan.visual_segments[0].end_frame, 359)
        self.assertEqual(plan.visual_segments[1].record_frame, 360)

    @patch("youtube_creator_assistant.features.render.builder.probe_video_metadata", return_value=(None, None))
    def test_falls_back_to_replicate_video_metadata_when_ffprobe_is_missing(self, _mock_probe):
        root = Path(__file__).resolve().parents[1]
        settings = load_settings(root / "configs/profiles/shepherd.yaml")

        temp_root = root / "runtime" / "test-render-plan-replicate-fallback"
        outputs_dir = temp_root / "outputs"
        incoming_dir = temp_root / "incoming"
        images_dir = temp_root / "images"
        logs_dir = temp_root / "logs"
        outputs_dir.mkdir(parents=True, exist_ok=True)
        incoming_dir.mkdir(parents=True, exist_ok=True)
        images_dir.mkdir(parents=True, exist_ok=True)
        logs_dir.mkdir(parents=True, exist_ok=True)

        settings.paths.runtime_root = temp_root
        settings.paths.outputs_dir = outputs_dir
        settings.paths.incoming_dir = incoming_dir
        settings.paths.images_dir = images_dir
        settings.paths.logs_dir = logs_dir
        settings.replicate.enabled = True
        settings.replicate.video_duration = 12
        settings.replicate.video_fps = 24
        settings.workflow.target_duration_tc = "0:00:25:00"

        video_path = temp_root / "render_visual.mp4"
        video_path.write_bytes(b"fake")
        image_path = temp_root / "image.png"
        image_path.write_bytes(b"fake-image")
        audio_path = temp_root / "track.mp3"
        audio_path.write_bytes(b"fake")

        project = VideoProject(
            project_id="replicate-fallback-project",
            profile_id="shepherd",
            project_dir=outputs_dir / "replicate-fallback-project",
            visual_asset=VisualAsset(kind="image", path=image_path, original_name="image.png"),
            render_visual_asset=VisualAsset(kind="video", path=video_path, original_name="render_visual.mp4"),
            created_at="2026-01-01T00:00:00+00:00",
            audio_tracks=[
                AudioTrack(
                    kind="psalm",
                    label="Psalm 2",
                    source_path=audio_path,
                    copied_path=audio_path,
                    duration_seconds=25.0,
                )
            ],
        )

        project.project_dir.mkdir(parents=True, exist_ok=True)
        (project.project_dir / "project.json").write_text(
            json.dumps(project.to_dict(), indent=2),
            encoding="utf-8",
        )

        runtime = RuntimeManager(settings)
        plan = RenderPlanBuilder(settings, runtime).build_for_project(project, fps_override=24.0)

        self.assertGreater(len(plan.visual_segments), 1)
        self.assertEqual(plan.visual_segments[0].end_frame, 287)
        self.assertEqual(plan.visual_segments[1].record_frame, 288)


if __name__ == "__main__":
    unittest.main()
