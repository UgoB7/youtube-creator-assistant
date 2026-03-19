import json
import unittest
from pathlib import Path

from youtube_creator_assistant.core.config import load_settings
from youtube_creator_assistant.features.replicate.service import ShepherdReplicateService


class _FakeResponse:
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


if __name__ == "__main__":
    unittest.main()
