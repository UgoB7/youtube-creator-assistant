import unittest
from pathlib import Path

from youtube_creator_assistant.core.config import load_settings
from youtube_creator_assistant.core.models import AudioTrack, ChapterEntry, VideoProject, VisualAsset
from youtube_creator_assistant.features.descriptions.service import DescriptionService


class _FakeResponse:
    def __init__(self, output_text: str):
        self.output_text = output_text


class _FakeOpenAIClient:
    def __init__(self, outputs):
        self._outputs = list(outputs)
        self._index = 0
        self.calls = []
        self.responses = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self._index >= len(self._outputs):
            payload = self._outputs[-1]
        else:
            payload = self._outputs[self._index]
        self._index += 1
        return _FakeResponse(payload)


class _FakeOpenAIProvider:
    def __init__(self, outputs):
        self._client = _FakeOpenAIClient(outputs)

    def client(self):
        return self._client


class DescriptionServiceTests(unittest.TestCase):
    def _make_project(self, root: Path, profile_id: str) -> VideoProject:
        project_dir = root / "runtime" / "test-description-service" / profile_id
        project_dir.mkdir(parents=True, exist_ok=True)
        image_path = project_dir / "visual.png"
        image_path.write_bytes(b"fakepng")
        return VideoProject(
            project_id=f"{profile_id}-project",
            profile_id=profile_id,
            project_dir=project_dir,
            visual_asset=VisualAsset(kind="image", path=image_path, original_name="visual.png"),
            created_at="2026-03-20T00:00:00+00:00",
            selected_title="Jesus Brings Peace",
            themes=["Peace", "Trust", "Rest"],
            audio_tracks=[
                AudioTrack(
                    kind="psalm",
                    label="Psalm 23",
                    source_path=image_path,
                    copied_path=image_path,
                    duration_seconds=120.0,
                )
            ],
            chapters=[ChapterEntry(timestamp="0:00:00", label="Psalm 23")],
        )

    def test_shepherd_description_matches_legacy_shape_and_multi_call_flow(self):
        root = Path(__file__).resolve().parents[1]
        settings = load_settings(root / "configs/profiles/shepherd.yaml")
        provider = _FakeOpenAIProvider(
            [
                '{"intro_line":"Welcome, child of God, into a quiet place of peace and trust with Christ."}',
                '{"theme_line":"For this video, our central themes are: i) Peace; ii) Trust; iii) Rest.","importance_line_1":"Why these themes matter in Christian faith: Peace and Trust teach believers to rest in Christ.","importance_line_2":"How sacred Scripture carries these themes: Scripture presents Peace and Trust as living realities in prayer."}',
                '{"audio_explanations":[{"audio":"Psalm 23","explanation":"Guides the listener into calm trust before God. Its words support steady prayer and emotional rest. The chapter fits the selected themes with clarity. It connects naturally with a long devotional listening flow."}]}',
            ]
        )
        service = DescriptionService(settings, provider=provider)
        project = self._make_project(root, "shepherd")

        text = service.build_description(project)

        self.assertIn("Welcome, child of God,", text)
        self.assertIn("Scripture Journey Notes", text)
        self.assertIn("All chapter timestamps are listed below in full:", text)
        self.assertIn("[Scripture Spotlight: PSALM 23 | 0:00:00]", text)
        self.assertIn("0:00:00 - Psalm 23", text)
        self.assertEqual(len(provider.client().calls), 3)
        first_prompt = provider.client().calls[0]["input"][0]["content"][0]["text"]
        self.assertIn("Must start exactly with 'Welcome, child of God,'", first_prompt)

    def test_vibes_variant_uses_vibespro_legacy_wording(self):
        root = Path(__file__).resolve().parents[1]
        settings = load_settings(root / "configs/profiles/vibes.yaml")
        provider = _FakeOpenAIProvider(
            [
                '{"intro_line":"Today we rest before Christ and receive His peace."}',
                '{"theme_line":"The themes of today\'s video are: i) Peace; ii) Trust; iii) Rest.","importance_line_1":"In Christianity, these themes of Peace, Trust, Rest call believers to rely on Christ.","importance_line_2":"In sacred Scripture, these themes of Peace, Trust, Rest appear through psalms of refuge and Gospel calls to rest."}',
                '{"audio_explanations":[{"audio":"Psalm 23","explanation":"Supports a gentle devotional movement around peace and trust. Its pacing invites sustained prayer. The language fits the title well. It also strengthens continuity across the long listening session."}]}',
            ]
        )
        service = DescriptionService(settings, provider=provider)
        project = self._make_project(root, "vibes")

        text = service.build_description(project)

        self.assertIn("How Scripture guides today's meditation", text)
        self.assertIn("The themes of today's video are:", text)
        self.assertIn("All chapter timestamps are listed below in full:", text)
        audio_prompt = provider.client().calls[2]["input"][0]["content"][0]["text"]
        self.assertIn("Provide explanation text only (the chapter/psalm heading is formatted separately by the system).", audio_prompt)

    def test_mercy_variant_uses_mercy_legacy_heading_and_period(self):
        root = Path(__file__).resolve().parents[1]
        settings = load_settings(root / "configs/profiles/mercy.yaml")
        provider = _FakeOpenAIProvider(
            [
                '{"intro_line":"Welcome into a gentle place of mercy and rest in Christ."}',
                '{"theme_line":"For this video, our central themes are: i) Peace; ii) Trust; iii) Rest.","importance_line_1":"Why these themes matter in Christian faith: Peace and Trust shape Christian endurance.","importance_line_2":"How sacred Scripture carries these themes: Scripture carries Peace and Trust through psalms and Gospel passages."}',
                '{"audio_explanations":[{"audio":"Psalm 23","explanation":"Creates a calm spiritual opening for the full reflection. Its movement supports patient prayer. The passage sits naturally with the title. It also gives continuity to the listening arc."}]}',
            ]
        )
        service = DescriptionService(settings, provider=provider)
        project = self._make_project(root, "mercy")

        text = service.build_description(project)

        self.assertIn("Scripture Journey Notes", text)
        self.assertIn("All chapter timestamps are listed below in full.", text)
        intro_prompt = provider.client().calls[0]["input"][0]["content"][0]["text"]
        self.assertIn("Must start with 'Welcome'.", intro_prompt)


if __name__ == "__main__":
    unittest.main()
