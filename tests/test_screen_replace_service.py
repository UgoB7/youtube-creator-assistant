import unittest
from pathlib import Path

from youtube_creator_assistant.core.config import load_settings
from youtube_creator_assistant.features.screen_replace.service import ScreenReplaceService


class ScreenReplaceServiceTests(unittest.TestCase):
    def test_quad_norm_roundtrip_uses_editor_order(self):
        root = Path(__file__).resolve().parents[1]
        settings = load_settings(root / "configs/profiles/lofi.yaml")
        service = ScreenReplaceService(settings)

        points = service.parse_quad_norm("0.4300,0.3600;0.7400,0.3700;0.7300,0.6100;0.4200,0.6000")

        self.assertEqual(
            points,
            [(0.43, 0.36), (0.74, 0.37), (0.73, 0.61), (0.42, 0.60)],
        )
        self.assertEqual(
            service.serialize_quad_norm(points),
            "0.4300,0.3600;0.7400,0.3700;0.7300,0.6100;0.4200,0.6000",
        )

    def test_quad_pixels_convert_editor_order_to_ffmpeg_render_order(self):
        root = Path(__file__).resolve().parents[1]
        settings = load_settings(root / "configs/profiles/lofi.yaml")
        service = ScreenReplaceService(settings)

        quad_px = service._quad_pixels_for_output(
            [(0.10, 0.20), (0.70, 0.20), (0.80, 0.90), (0.20, 0.80)],
            width=1000,
            height=1000,
        )

        self.assertEqual(
            quad_px,
            [(100, 200), (700, 200), (200, 800), (800, 900)],
        )

    def test_parse_quad_norm_preserves_explicit_editor_order(self):
        root = Path(__file__).resolve().parents[1]
        settings = load_settings(root / "configs/profiles/lofi.yaml")
        service = ScreenReplaceService(settings)

        points = service.parse_quad_norm("0.4200,0.6000;0.4300,0.3600;0.7400,0.3700;0.7300,0.6100")

        self.assertEqual(
            points,
            [(0.42, 0.60), (0.43, 0.36), (0.74, 0.37), (0.73, 0.61)],
        )


if __name__ == "__main__":
    unittest.main()
