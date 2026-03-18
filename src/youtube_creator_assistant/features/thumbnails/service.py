from __future__ import annotations

import io
import shutil
from pathlib import Path
from typing import Optional

from PIL import Image, ImageOps

from youtube_creator_assistant.core.config import Settings
from youtube_creator_assistant.core.models import VideoProject


class ThumbnailService:
    def __init__(self, settings: Settings):
        self.settings = settings

    def build_thumbnail(self, project: VideoProject) -> VideoProject:
        if project.visual_asset.kind != "image":
            return project

        image_path = project.visual_asset.path
        target_dir = project.project_dir / "artifacts"
        target_dir.mkdir(parents=True, exist_ok=True)

        orig_bytes = image_path.stat().st_size
        max_bytes = self.settings.thumbnail.max_bytes
        target_bytes = min(max_bytes, self.settings.thumbnail.target_bytes)

        if orig_bytes <= max_bytes:
            dest = target_dir / image_path.name
            shutil.copy2(image_path, dest)
            project.yt_thumbnail_path = dest
            return project

        suffix = self.settings.thumbnail.suffix or "_yt"
        output_path = target_dir / f"{image_path.stem}{suffix}.jpg"

        try:
            image = self._ensure_rgb_no_alpha(Image.open(image_path))
            lo, hi = 40, 95
            best_data: Optional[bytes] = None
            while lo <= hi:
                quality = (lo + hi) // 2
                data = self._save_jpeg(image, quality)
                if len(data) <= target_bytes:
                    best_data = data
                    lo = quality + 1
                else:
                    hi = quality - 1
            if best_data is None:
                best_data = self._save_jpeg(image, 35)
            output_path.write_bytes(best_data)
            project.yt_thumbnail_path = output_path
        except Exception:
            dest = target_dir / image_path.name
            shutil.copy2(image_path, dest)
            project.yt_thumbnail_path = dest
        return project

    @staticmethod
    def _save_jpeg(image: Image.Image, quality: int) -> bytes:
        buffer = io.BytesIO()
        image.save(
            buffer,
            format="JPEG",
            quality=quality,
            optimize=True,
            progressive=True,
        )
        return buffer.getvalue()

    @staticmethod
    def _ensure_rgb_no_alpha(image: Image.Image) -> Image.Image:
        image = ImageOps.exif_transpose(image)
        if image.mode in {"RGBA", "LA"}:
            background = Image.new("RGB", image.size, (255, 255, 255))
            background.paste(image, mask=image.split()[-1])
            return background
        return image.convert("RGB")
