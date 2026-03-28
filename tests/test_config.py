import unittest
from pathlib import Path

from youtube_creator_assistant.core.config import load_settings
from youtube_creator_assistant.profiles.registry import get_profile_definition


class ConfigTests(unittest.TestCase):
    def test_load_vibes_config(self):
        root = Path(__file__).resolve().parents[1]
        settings = load_settings(root / "configs/profiles/vibes.yaml")
        self.assertEqual(settings.profile.id, "vibes")
        self.assertEqual(settings.profile.visual_input_mode, "image_or_video")
        self.assertEqual(settings.paths.psalms_dir.name, "psalms")
        self.assertEqual(settings.paths.gospel_dir.name, "gospel")
        self.assertTrue(settings.render.enabled)
        self.assertEqual(settings.render.timeline_prefix, "vibes")
        self.assertEqual(settings.render.append_mode, "sequential_exact")
        self.assertTrue(settings.replicate.enabled)
        self.assertFalse(settings.replicate.allow_candidate_generation)
        self.assertEqual(settings.replicate.image_model, "black-forest-labs/flux-2-max")
        self.assertEqual(settings.replicate.video_model, "bytedance/seedance-1.5-pro")
        self.assertEqual(settings.description.variant, "vibespro_legacy")

    def test_load_shepherd_replicate_config(self):
        root = Path(__file__).resolve().parents[1]
        settings = load_settings(root / "configs/profiles/shepherd.yaml")
        self.assertTrue(settings.replicate.enabled)
        self.assertEqual(settings.replicate.prompt_seed_path.name, "shepherd_prompts.txt")
        self.assertEqual(settings.replicate.image_model, "bytedance/seedream-4")
        self.assertEqual(settings.replicate.video_model, "bytedance/seedance-1.5-pro")
        self.assertEqual(settings.render.append_mode, "sequential_exact")
        self.assertEqual(settings.description.variant, "shepherd_legacy")

    def test_profile_registry_has_placeholders(self):
        self.assertEqual(get_profile_definition("vibes").display_name, "Image Workflow")
        self.assertEqual(get_profile_definition("shepherd").display_name, "Mixed Visual Workflow")
        self.assertEqual(get_profile_definition("mercy").display_name, "Motion-Assisted Workflow")
        self.assertEqual(get_profile_definition("lofi").display_name, "Video Workflow")
        self.assertEqual(get_profile_definition("enchanted_melodies").display_name, "Enchanted Melodies")

    def test_load_mercy_replicate_config(self):
        root = Path(__file__).resolve().parents[1]
        settings = load_settings(root / "configs/profiles/mercy.yaml")
        self.assertTrue(settings.replicate.enabled)
        self.assertEqual(settings.replicate.prompt_style, "mercy_legacy")
        self.assertEqual(settings.replicate.image_model, "black-forest-labs/flux-2-max")
        self.assertEqual(settings.replicate.image_payload_style, "flux")
        self.assertEqual(settings.render.append_mode, "sequential_exact")

    def test_load_lofi_visual_prompt_generation_config(self):
        root = Path(__file__).resolve().parents[1]
        settings = load_settings(root / "configs/profiles/lofi.yaml")
        self.assertEqual(settings.profile.id, "lofi")
        self.assertEqual(settings.profile.visual_input_mode, "image_or_video")
        self.assertTrue(settings.replicate.enabled)
        self.assertTrue(settings.replicate.allow_candidate_generation)
        self.assertTrue(settings.replicate.visual_prompt_generation.enabled)
        self.assertIn("LoFi Jesus", settings.replicate.visual_prompt_generation.system_prompt)
        self.assertNotIn("Additional style requirements:", settings.replicate.visual_prompt_generation.system_prompt)
        self.assertEqual(settings.replicate.prompt_seed_path.name, "prompts.txt")
        self.assertEqual(settings.replicate.prompt_batch_size, 5)
        self.assertEqual(settings.replicate.prompt_parallel_requests, 4)
        self.assertIn("Additional style requirements:", settings.replicate.image_prompt_prefix)
        self.assertEqual(settings.replicate.image_prompt_suffix, "")
        self.assertEqual(settings.replicate.video_prompt, "Camera locked.")
        self.assertFalse(settings.replicate.debug.enabled)
        self.assertFalse(settings.replicate.debug.reuse_candidate_batch)
        self.assertEqual(settings.replicate.debug.candidate_batch_id, "lofi-candidates-20260328-061400")
        self.assertTrue(settings.replicate.debug.reuse_render_video)
        self.assertEqual(settings.replicate.debug.render_video_path.name, "candidate-04_render.mp4")

    def test_load_enchanted_melodies_config(self):
        root = Path(__file__).resolve().parents[1]
        settings = load_settings(root / "configs/profiles/enchanted_melodies.yaml")
        self.assertEqual(settings.profile.id, "enchanted_melodies")
        self.assertFalse(settings.workflow.include_gospel)
        self.assertFalse(settings.workflow.use_title_reference_guidance)
        self.assertEqual(settings.workflow.selection_seed_mode, "random")
        self.assertEqual(settings.workflow.max_selected_titles, 1)
        self.assertEqual(settings.workflow.audio_extensions, [".wav", ".mp3"])
        self.assertEqual(settings.paths.psalms_dir.name, "faded")
        self.assertEqual(settings.description.variant, "enchanted_melodies_template")
        self.assertIn("Return STRICT JSON only", settings.description.dynamic_intro_prompt)
        self.assertFalse(settings.description.dynamic_intro_include_audio_context)
        self.assertEqual(settings.openai.title_generation.count, 10)
        self.assertEqual(settings.openai.title_generation.min_count, 10)
        self.assertTrue(settings.openai.title_generation.require_separator)
        self.assertEqual(settings.openai.title_generation.separator, " — ")
        self.assertFalse(settings.openai.theme_generation.include_audio_context)
        self.assertEqual(settings.openai.theme_generation.count, 5)
        self.assertTrue(settings.thumbnail.candidate_generation_enabled)
        self.assertEqual(settings.thumbnail.idea_count, 4)
        self.assertEqual(settings.thumbnail.candidate_model, "google/nano-banana-pro")
        self.assertIn(
            "Fantasy Music for Study & Relaxation — The Mage’s Terrace of Solace",
            settings.openai.title_generation.examples_input,
        )


if __name__ == "__main__":
    unittest.main()
