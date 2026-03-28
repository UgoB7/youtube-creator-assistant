import base64
import json
import threading
import unittest
from pathlib import Path

from youtube_creator_assistant.core.config import load_settings
from youtube_creator_assistant.features.replicate.service import ShepherdReplicateService


_PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9WlH0x8AAAAASUVORK5CYII="
)


class _FakeResponse:
    def __init__(self, output_text: str):
        self.output_text = output_text


class _FakeOpenAIClient:
    def __init__(self, outputs):
        self._outputs = list(outputs)
        self._index = 0
        self._lock = threading.Lock()
        self.responses = self

    def create(self, **_kwargs):
        with self._lock:
            if self._index >= len(self._outputs):
                value = self._outputs[-1]
            else:
                value = self._outputs[self._index]
            self._index += 1
        return _FakeResponse(value)


class _FakeOpenAIProvider:
    def __init__(self, outputs):
        self._client = _FakeOpenAIClient(outputs)

    def client(self):
        return self._client


class _FakeReplicateProvider:
    def __init__(self):
        self.prompts = []

    def generate_image_bytes(self, prompt: str) -> bytes:
        self.prompts.append(prompt)
        return prompt.encode("utf-8")


class _FailingReplicateProvider:
    def generate_image_bytes(self, _prompt: str) -> bytes:
        raise AssertionError("Replicate should not be called when debug batch reuse is enabled.")


class ShepherdReplicateServiceTests(unittest.TestCase):
    def test_generate_candidate_batch_creates_requested_images(self):
        root = Path(__file__).resolve().parents[1]
        settings = load_settings(root / "configs/profiles/shepherd.yaml")
        settings.replicate.candidate_count = 10

        outputs = [json.dumps([f"Prompt {index}"]) for index in range(1, 11)]
        service = ShepherdReplicateService(
            settings,
            openai_provider=_FakeOpenAIProvider(outputs),
            replicate_provider=_FakeReplicateProvider(),
        )

        temp_root = root / "runtime" / "test-shepherd-candidates"
        temp_root.mkdir(parents=True, exist_ok=True)
        batch = service.generate_candidate_batch(temp_root, count=10)

        self.assertEqual(len(batch.candidates), 10)
        self.assertTrue((batch.batch_dir / "batch.json").exists())
        self.assertEqual(batch.candidates[0].candidate_id, "candidate-01")
        self.assertEqual(batch.candidates[-1].candidate_id, "candidate-10")
        self.assertTrue(all(candidate.image_path.exists() for candidate in batch.candidates))

    def test_mercy_prompt_generation_uses_single_llm_call_for_batch(self):
        root = Path(__file__).resolve().parents[1]
        settings = load_settings(root / "configs/profiles/mercy.yaml")
        settings.replicate.candidate_count = 3

        outputs = ['{"options":["Mercy Prompt 1","Mercy Prompt 2","Mercy Prompt 3"]}']
        provider = _FakeOpenAIProvider(outputs)
        service = ShepherdReplicateService(
            settings,
            openai_provider=provider,
            replicate_provider=_FakeReplicateProvider(),
        )

        temp_root = root / "runtime" / "test-mercy-candidates"
        temp_root.mkdir(parents=True, exist_ok=True)
        batch = service.generate_candidate_batch(temp_root, count=3)

        self.assertEqual(len(batch.candidates), 3)
        self.assertEqual(provider.client()._index, 1)

    def test_generate_candidate_batch_from_visual_uses_visual_prompt_generation(self):
        root = Path(__file__).resolve().parents[1]
        settings = load_settings(root / "configs/profiles/shepherd.yaml")
        settings.replicate.visual_prompt_generation.enabled = True
        settings.replicate.visual_prompt_generation.system_prompt = "Return one prompt only."
        settings.replicate.visual_prompt_generation.user_prompt = "Analyze the image."
        settings.replicate.visual_prompt_generation.variation_prompt = "Candidate {ordinal}/{total}."

        outputs = ["Visual Prompt 1", "Visual Prompt 2"]
        replicate_provider = _FakeReplicateProvider()
        service = ShepherdReplicateService(
            settings,
            openai_provider=_FakeOpenAIProvider(outputs),
            replicate_provider=replicate_provider,
        )

        temp_root = root / "runtime" / "test-visual-candidates"
        temp_root.mkdir(parents=True, exist_ok=True)
        image_path = temp_root / "source.png"
        image_path.write_bytes(_PNG_BYTES)
        batch = service.generate_candidate_batch_from_visual(temp_root, image_path, count=2)

        self.assertEqual(len(batch.candidates), 2)
        self.assertEqual(replicate_provider.prompts, ["Visual Prompt 1", "Visual Prompt 2"])
        self.assertIsNotNone(batch.source_visual_asset)
        assert batch.source_visual_asset is not None
        self.assertEqual(batch.source_visual_asset.kind, "image")
        self.assertTrue(batch.source_visual_asset.path.exists())

    def test_generate_candidate_batch_from_visual_can_split_prompt_requests_into_batches(self):
        root = Path(__file__).resolve().parents[1]
        settings = load_settings(root / "configs/profiles/shepherd.yaml")
        settings.replicate.visual_prompt_generation.enabled = True
        settings.replicate.visual_prompt_generation.system_prompt = "Return prompts."
        settings.replicate.visual_prompt_generation.user_prompt = "Analyze the image."
        settings.replicate.visual_prompt_generation.variation_prompt = "Candidate {ordinal}/{total}."
        settings.replicate.prompt_batch_size = 5
        settings.replicate.prompt_parallel_requests = 4

        outputs = [
            json.dumps({"prompts": [f"Visual Prompt {index}" for index in range(1, 6)]}),
            json.dumps({"prompts": [f"Visual Prompt {index}" for index in range(6, 11)]}),
        ]
        provider = _FakeOpenAIProvider(outputs)
        replicate_provider = _FakeReplicateProvider()
        service = ShepherdReplicateService(
            settings,
            openai_provider=provider,
            replicate_provider=replicate_provider,
        )

        temp_root = root / "runtime" / "test-visual-batched-candidates"
        temp_root.mkdir(parents=True, exist_ok=True)
        image_path = temp_root / "source.png"
        image_path.write_bytes(_PNG_BYTES)
        batch = service.generate_candidate_batch_from_visual(temp_root, image_path, count=10)

        self.assertEqual(len(batch.candidates), 10)
        self.assertCountEqual(replicate_provider.prompts, [f"Visual Prompt {index}" for index in range(1, 11)])
        self.assertEqual(provider.client()._index, 2)

    def test_generated_candidate_prompts_can_append_required_suffix(self):
        root = Path(__file__).resolve().parents[1]
        settings = load_settings(root / "configs/profiles/shepherd.yaml")
        settings.replicate.visual_prompt_generation.enabled = True
        settings.replicate.visual_prompt_generation.system_prompt = "Return one prompt only."
        settings.replicate.visual_prompt_generation.user_prompt = "Analyze the image."
        settings.replicate.visual_prompt_generation.variation_prompt = "Candidate {ordinal}/{total}."
        settings.replicate.image_prompt_prefix = (
            "Additional style requirements:\n"
            "- The lineart should be soft and colored."
        )
        settings.replicate.image_prompt_suffix = (
            "Jesus requirements:\n"
            "- Shoulder-length wavy brown hair, well-defined beard and moustache, calm serene expression.\n"
            "\n"
            "Additional required changes:\n"
            "- Add subtle Christian candles."
        )

        replicate_provider = _FakeReplicateProvider()
        service = ShepherdReplicateService(
            settings,
            openai_provider=_FakeOpenAIProvider(["Visual Prompt Base"]),
            replicate_provider=replicate_provider,
        )

        temp_root = root / "runtime" / "test-visual-suffix-candidates"
        temp_root.mkdir(parents=True, exist_ok=True)
        image_path = temp_root / "source.png"
        image_path.write_bytes(_PNG_BYTES)
        batch = service.generate_candidate_batch_from_visual(temp_root, image_path, count=1)

        self.assertEqual(len(batch.candidates), 1)
        self.assertTrue(batch.candidates[0].prompt.startswith("Additional style requirements:"))
        self.assertIn("Visual Prompt Base", batch.candidates[0].prompt)
        self.assertIn("Jesus requirements:", batch.candidates[0].prompt)
        self.assertIn("Additional required changes:", batch.candidates[0].prompt)
        self.assertEqual(replicate_provider.prompts[0], batch.candidates[0].prompt)

    def test_mercy_prompt_generation_can_split_into_parallel_batches(self):
        root = Path(__file__).resolve().parents[1]
        settings = load_settings(root / "configs/profiles/mercy.yaml")
        settings.replicate.candidate_count = 20
        settings.replicate.prompt_batch_size = 5
        settings.replicate.prompt_parallel_requests = 4

        outputs = [
            json.dumps({"options": [f"Mercy Prompt {index}" for index in range(1, 6)]}),
            json.dumps({"options": [f"Mercy Prompt {index}" for index in range(6, 11)]}),
            json.dumps({"options": [f"Mercy Prompt {index}" for index in range(11, 16)]}),
            json.dumps({"options": [f"Mercy Prompt {index}" for index in range(16, 21)]}),
        ]
        provider = _FakeOpenAIProvider(outputs)
        replicate_provider = _FakeReplicateProvider()
        service = ShepherdReplicateService(
            settings,
            openai_provider=provider,
            replicate_provider=replicate_provider,
        )

        temp_root = root / "runtime" / "test-mercy-batched-candidates"
        temp_root.mkdir(parents=True, exist_ok=True)
        batch = service.generate_candidate_batch(temp_root, count=20)

        self.assertEqual(len(batch.candidates), 20)
        self.assertCountEqual(replicate_provider.prompts, [f"Mercy Prompt {index}" for index in range(1, 21)])
        self.assertEqual(provider.client()._index, 4)

    def test_debug_reuses_explicit_candidate_batch_without_regeneration(self):
        root = Path(__file__).resolve().parents[1]
        settings = load_settings(root / "configs/profiles/shepherd.yaml")
        settings.replicate.candidate_count = 2
        settings.replicate.debug.enabled = True
        settings.replicate.debug.reuse_candidate_batch = True

        temp_root = root / "runtime" / "test-debug-reuse-candidates"
        batch_dir = temp_root / "shepherd-candidates-20990101-000000"
        batch_dir.mkdir(parents=True, exist_ok=True)
        candidate_a = batch_dir / "candidate_01.png"
        candidate_b = batch_dir / "candidate_02.png"
        candidate_a.write_bytes(b"a")
        candidate_b.write_bytes(b"b")
        payload = {
            "batch_id": "shepherd-candidates-20990101-000000",
            "profile_id": "shepherd",
            "batch_dir": str(batch_dir),
            "created_at": "2099-01-01T00:00:00+00:00",
            "candidates": [
                {"candidate_id": "candidate-01", "prompt": "Prompt A", "image_path": str(candidate_a), "label": "Candidate 01"},
                {"candidate_id": "candidate-02", "prompt": "Prompt B", "image_path": str(candidate_b), "label": "Candidate 02"},
            ],
            "source_visual_asset": None,
        }
        (batch_dir / "batch.json").write_text(json.dumps(payload), encoding="utf-8")
        settings.replicate.debug.candidate_batch_id = "shepherd-candidates-20990101-000000"

        service = ShepherdReplicateService(
            settings,
            openai_provider=_FakeOpenAIProvider(["should not be used"]),
            replicate_provider=_FailingReplicateProvider(),
        )

        batch = service.generate_candidate_batch(temp_root, count=2)

        self.assertEqual(batch.batch_id, "shepherd-candidates-20990101-000000")
        self.assertEqual(len(batch.candidates), 2)
        self.assertEqual(batch.candidates[0].prompt, "Prompt A")


if __name__ == "__main__":
    unittest.main()
