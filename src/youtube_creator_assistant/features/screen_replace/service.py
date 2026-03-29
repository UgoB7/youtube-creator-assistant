from __future__ import annotations

import math
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Sequence

from youtube_creator_assistant.core.config import Settings

try:
    from PIL import Image, ImageDraw
except Exception:  # pragma: no cover - optional dependency
    Image = None
    ImageDraw = None


class ScreenReplaceService:
    def __init__(self, settings: Settings):
        self.settings = settings

    def render_video(
        self,
        *,
        base_video_path: Path,
        output_path: Path,
        quad_norm: str | None = None,
    ) -> Path:
        if not self.settings.screen_replace.enabled:
            raise RuntimeError("Screen replacement is disabled for this profile.")
        overlay_video_path = self._overlay_video_path()
        if not overlay_video_path.exists():
            raise FileNotFoundError(f"Screen replacement overlay video not found: {overlay_video_path}")
        if not base_video_path.exists():
            raise FileNotFoundError(f"Base render video not found: {base_video_path}")

        output_w = max(320, int(self.settings.screen_replace.target_width or 3840))
        output_h = max(180, int(self.settings.screen_replace.target_height or 2160))
        output_fps = max(1, int(self.settings.screen_replace.target_fps or 30))
        quad_points = self.parse_quad_norm(quad_norm or self.settings.screen_replace.quad_norm)
        quad_px = self._quad_pixels_for_output(quad_points, output_w, output_h)

        with tempfile.TemporaryDirectory(prefix="yca-screen-replace-") as temp_dir_name:
            temp_dir = Path(temp_dir_name)
            mask_path = self._write_polygon_mask_image(
                quad_px=quad_px,
                width=output_w,
                height=output_h,
                temp_dir=temp_dir,
            )
            (x0, y0), (x1, y1), (x2, y2), (x3, y3) = quad_px
            perspective_expr = (
                f"x0={x0}:y0={y0}:"
                f"x1={x1}:y1={y1}:"
                f"x2={x2}:y2={y2}:"
                f"x3={x3}:y3={y3}:"
                "sense=destination"
            )
            filter_complex = (
                f"[0:v]scale={output_w}:{output_h}:force_original_aspect_ratio=decrease,"
                f"pad={output_w}:{output_h}:(ow-iw)/2:(oh-ih)/2,setsar=1[base];"
                f"[1:v]scale={output_w}:{output_h}:force_original_aspect_ratio=increase,"
                f"crop={output_w}:{output_h},setsar=1[site];"
                f"[site]perspective={perspective_expr}[site_warp];"
                f"[2:v]scale={output_w}:{output_h},format=gray[alpha_mask];"
                "[site_warp]format=rgba[site_rgba_src];"
                "[site_rgba_src][alpha_mask]alphamerge[site_rgba];"
                "[base][site_rgba]overlay=0:0:shortest=1:format=auto[outv]"
            )
            output_path.parent.mkdir(parents=True, exist_ok=True)
            command = [
                "ffmpeg",
                "-y",
                "-i",
                str(base_video_path),
                "-stream_loop",
                "-1",
                "-i",
                str(overlay_video_path),
                "-loop",
                "1",
                "-i",
                str(mask_path),
                "-filter_complex",
                filter_complex,
                "-map",
                "[outv]",
                "-map",
                "0:a?",
                "-r",
                str(output_fps),
                "-c:v",
                "libx264",
                "-preset",
                "medium",
                "-crf",
                "18",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-b:a",
                "160k",
                "-movflags",
                "+faststart",
                "-shortest",
                str(output_path),
            ]
            proc = subprocess.run(command, check=False, capture_output=True, text=True)
            if proc.returncode != 0 or not output_path.exists() or output_path.stat().st_size <= 0:
                tail = (proc.stderr or "").strip().splitlines()
                tail_text = "\n".join(tail[-14:]) if tail else "Unknown ffmpeg error."
                raise RuntimeError(f"Screen replacement render failed.\n{tail_text}")
        return output_path

    def _overlay_video_path(self) -> Path:
        overlay_video_path = self.settings.screen_replace.overlay_video_path
        if overlay_video_path is None:
            raise RuntimeError("screen_replace.overlay_video_path is not configured.")
        return overlay_video_path.expanduser().resolve()

    @staticmethod
    def parse_quad_norm(raw: str) -> list[tuple[float, float]]:
        parts = [chunk.strip() for chunk in (raw or "").split(";") if chunk.strip()]
        points: list[tuple[float, float]] = []
        for part in parts[:4]:
            coords = [value.strip() for value in part.split(",")]
            if len(coords) != 2:
                continue
            try:
                x = float(coords[0])
                y = float(coords[1])
            except Exception:
                continue
            points.append((max(0.0, min(1.0, x)), max(0.0, min(1.0, y))))
        if len(points) != 4:
            return ScreenReplaceService._default_editor_quad()
        return points

    @staticmethod
    def serialize_quad_norm(points: Sequence[tuple[float, float]]) -> str:
        quad = ScreenReplaceService._normalize_editor_quad(points)
        return ";".join(f"{x:.4f},{y:.4f}" for x, y in quad)

    @staticmethod
    def _ordered_quad_tl_tr_bl_br(points: Sequence[tuple[float, float]]) -> list[tuple[float, float]]:
        if len(points) != 4:
            raise RuntimeError("Need exactly 4 corner points.")
        sorted_by_y = sorted(points, key=lambda point: (point[1], point[0]))
        top = sorted(sorted_by_y[:2], key=lambda point: point[0])
        bottom = sorted(sorted_by_y[2:], key=lambda point: point[0])
        return [top[0], top[1], bottom[0], bottom[1]]

    @staticmethod
    def _ordered_quad_tl_tr_br_bl(points: Sequence[tuple[float, float]]) -> list[tuple[float, float]]:
        canonical = ScreenReplaceService._ordered_quad_tl_tr_bl_br(points)
        return [canonical[0], canonical[1], canonical[3], canonical[2]]

    @staticmethod
    def _default_editor_quad() -> list[tuple[float, float]]:
        return [
            (0.36, 0.30),
            (0.64, 0.30),
            (0.64, 0.70),
            (0.36, 0.70),
        ]

    @staticmethod
    def _normalize_editor_quad(points: Sequence[tuple[float, float]]) -> list[tuple[float, float]]:
        if len(points) != 4:
            return ScreenReplaceService._default_editor_quad()
        normalized: list[tuple[float, float]] = []
        for x, y in points:
            normalized.append((max(0.0, min(1.0, float(x))), max(0.0, min(1.0, float(y)))))
        return normalized

    @staticmethod
    def _editor_quad_to_render_quad(points: Sequence[tuple[float, float]]) -> list[tuple[float, float]]:
        editor = ScreenReplaceService._normalize_editor_quad(points)
        return [editor[0], editor[1], editor[3], editor[2]]

    @staticmethod
    def _quad_pixels_for_output(points: Sequence[tuple[float, float]], width: int, height: int) -> list[tuple[int, int]]:
        quad = ScreenReplaceService._editor_quad_to_render_quad(points)
        output: list[tuple[int, int]] = []
        for x, y in quad:
            px = int(round(max(0.0, min(1.0, x)) * width))
            py = int(round(max(0.0, min(1.0, y)) * height))
            output.append((max(0, min(width, px)), max(0, min(height, py))))
        return output

    @staticmethod
    def _write_polygon_mask_image(
        *,
        quad_px: Sequence[tuple[int, int]],
        width: int,
        height: int,
        temp_dir: Path,
    ) -> Path:
        if len(quad_px) != 4:
            raise RuntimeError("Invalid quad for mask generation.")
        tl, tr, bl, br = quad_px
        polygon = [tl, tr, br, bl]

        if Image is not None and ImageDraw is not None:
            mask = Image.new("L", (width, height), 0)
            draw = ImageDraw.Draw(mask)
            draw.polygon(polygon, fill=255)
            path = temp_dir / f"screen_mask_{uuid.uuid4().hex[:8]}.png"
            mask.save(path, format="PNG")
            return path

        pixels = bytearray(width * height)
        edges = list(zip(polygon, polygon[1:] + polygon[:1]))
        for y in range(height):
            scan_y = y + 0.5
            intersections: list[float] = []
            for (x1, y1), (x2, y2) in edges:
                if y1 == y2:
                    continue
                if not ((y1 <= scan_y < y2) or (y2 <= scan_y < y1)):
                    continue
                t = (scan_y - y1) / (y2 - y1)
                x = x1 + t * (x2 - x1)
                intersections.append(x)
            if len(intersections) < 2:
                continue
            intersections.sort()
            for idx in range(0, len(intersections) - 1, 2):
                x_start = max(0, int(math.floor(intersections[idx])))
                x_end = min(width - 1, int(math.ceil(intersections[idx + 1])))
                if x_end < x_start:
                    continue
                row_start = y * width
                pixels[row_start + x_start : row_start + x_end + 1] = b"\xff" * (x_end - x_start + 1)

        path = temp_dir / f"screen_mask_{uuid.uuid4().hex[:8]}.pgm"
        with path.open("wb") as handle:
            handle.write(f"P5\n{width} {height}\n255\n".encode("ascii"))
            handle.write(pixels)
        return path
