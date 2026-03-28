from __future__ import annotations

import io
import json
import shutil
from pathlib import Path
from typing import Optional

from PIL import Image, ImageOps

from youtube_creator_assistant.core.config import Settings
from youtube_creator_assistant.core.models import VideoProject
from youtube_creator_assistant.core.utils import extract_video_frame
from youtube_creator_assistant.providers.openai_client import OpenAIProvider
from youtube_creator_assistant.providers.replicate import ReplicateProvider


class ThumbnailService:
    def __init__(
        self,
        settings: Settings,
        openai_provider: OpenAIProvider | None = None,
        replicate_provider: ReplicateProvider | None = None,
    ):
        self.settings = settings
        self.openai_provider = openai_provider or OpenAIProvider()
        self.replicate_provider = replicate_provider or ReplicateProvider(settings)

    def build_thumbnail(self, project: VideoProject) -> VideoProject:
        image_path = self._resolve_thumbnail_source(project)
        if image_path is None:
            return project

        project.yt_thumbnail_path = self._finalize_thumbnail_path(project, image_path)
        return project

    def generate_thumbnail_candidates(self, project: VideoProject) -> list[dict]:
        source_image = self._resolve_thumbnail_source(project)
        if source_image is None:
            return []
        if not project.selected_title:
            raise ValueError("A selected title is required before generating thumbnail candidates.")

        ideas = self._generate_thumbnail_ideas(project, source_image)
        if not ideas:
            raise RuntimeError("OpenAI did not return thumbnail ideas.")

        artifacts_dir = project.project_dir / "artifacts"
        candidate_dir = artifacts_dir / "thumbnail_candidates"
        if candidate_dir.exists():
            shutil.rmtree(candidate_dir)
        candidate_dir.mkdir(parents=True, exist_ok=True)

        candidates: list[dict] = []
        for idx, idea in enumerate(ideas, start=1):
            candidate_id = str(idea.get("candidate_id") or f"thumb{idx:02d}")
            prompt = str(idea.get("image_prompt") or "").strip()
            if not prompt:
                continue
            image_bytes = self.replicate_provider.generate_thumbnail_candidate_bytes(prompt, source_image)
            ext = (self.settings.thumbnail.candidate_output_format or "jpg").strip().lower()
            image_path = candidate_dir / f"{candidate_id}.{ext}"
            image_path.write_bytes(image_bytes)
            candidates.append(
                {
                    "candidate_id": candidate_id,
                    "label": str(idea.get("label") or candidate_id),
                    "summary": str(idea.get("summary") or "").strip(),
                    "image_prompt": prompt,
                    "image_filename": image_path.name,
                }
            )

        metadata_path = self._thumbnail_candidates_metadata_path(project)
        metadata_path.write_text(json.dumps(candidates, indent=2), encoding="utf-8")
        return candidates

    def load_thumbnail_candidates(self, project: VideoProject) -> list[dict]:
        path = self._thumbnail_candidates_metadata_path(project)
        if not path.exists():
            return []
        return list(json.loads(path.read_text(encoding="utf-8")))

    def select_thumbnail_candidates(self, project: VideoProject, candidate_ids: list[str]) -> VideoProject:
        selected_ids = [item.strip() for item in candidate_ids if isinstance(item, str) and item.strip()]
        if not selected_ids:
            raise ValueError("At least one thumbnail candidate must be selected.")

        candidates = self.load_thumbnail_candidates(project)
        selected = [item for item in candidates if str(item.get("candidate_id")) in selected_ids]
        if not selected:
            raise ValueError("Selected thumbnail candidates were not found.")

        candidate_dir = project.project_dir / "artifacts" / "thumbnail_candidates"
        first_filename = str(selected[0]["image_filename"])
        first_path = candidate_dir / first_filename
        if not first_path.exists():
            raise FileNotFoundError(f"Thumbnail candidate file is missing: {first_filename}")

        project.yt_thumbnail_path = self._finalize_thumbnail_path(project, first_path)
        selection_path = project.project_dir / "thumbnail_selected.json"
        selection_path.write_text(json.dumps(selected, indent=2), encoding="utf-8")
        return project

    def load_selected_thumbnail_candidates(self, project: VideoProject) -> list[dict]:
        path = project.project_dir / "thumbnail_selected.json"
        if not path.exists():
            return []
        return list(json.loads(path.read_text(encoding="utf-8")))

    def _generate_thumbnail_ideas(self, project: VideoProject, source_image: Path) -> list[dict]:
        prompt = (self.settings.thumbnail.idea_prompt or "").strip()
        if not prompt:
            return []
        response = self.openai_provider.client().responses.create(
            model=self.settings.openai.model,
            input=[
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": prompt},
                        {"type": "input_text", "text": f"VIDEO TITLE: {project.selected_title or ''}"},
                        {"type": "input_text", "text": f"PROFILE: {self.settings.profile.display_name}"},
                        {"type": "input_text", "text": f"IDEA COUNT: {int(self.settings.thumbnail.idea_count)}"},
                        {"type": "input_image", "image_url": self._img_to_data_url(source_image)},
                    ],
                }
            ],
        )
        payload = self._extract_json(response.output_text)
        ideas = payload.get("concepts", [])
        cleaned: list[dict] = []
        for idx, item in enumerate(ideas, start=1):
            if not isinstance(item, dict):
                continue
            cleaned.append(
                {
                    "candidate_id": str(item.get("candidate_id") or f"thumb{idx:02d}"),
                    "label": str(item.get("label") or f"Concept {idx}"),
                    "summary": str(item.get("summary") or "").strip(),
                    "image_prompt": str(item.get("image_prompt") or "").strip(),
                }
            )
        return cleaned[: int(self.settings.thumbnail.idea_count)]

    def _finalize_thumbnail_path(self, project: VideoProject, image_path: Path) -> Path:

        target_dir = project.project_dir / "artifacts"
        target_dir.mkdir(parents=True, exist_ok=True)

        orig_bytes = image_path.stat().st_size
        max_bytes = self.settings.thumbnail.max_bytes
        target_bytes = min(max_bytes, self.settings.thumbnail.target_bytes)

        if orig_bytes <= max_bytes:
            dest = target_dir / image_path.name
            if image_path.resolve() != dest.resolve():
                shutil.copy2(image_path, dest)
            return dest

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
        except Exception:
            dest = target_dir / image_path.name
            if image_path.resolve() != dest.resolve():
                shutil.copy2(image_path, dest)
            return dest
        return output_path

    def _resolve_thumbnail_source(self, project: VideoProject) -> Optional[Path]:
        if project.visual_asset.kind == "image":
            return project.visual_asset.path
        preview_path = project.project_dir / "artifacts" / "thumbnail_preview.jpg"
        return extract_video_frame(project.visual_asset.path, preview_path)

    def _thumbnail_candidates_metadata_path(self, project: VideoProject) -> Path:
        return project.project_dir / "thumbnail_candidates.json"

    @staticmethod
    def _extract_json(raw: str) -> dict:
        text = raw.strip()
        if not text.startswith("{"):
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1 and end > start:
                text = text[start : end + 1]
        return json.loads(text)

    @staticmethod
    def _img_to_data_url(path: Path) -> str:
        suffix = path.suffix.lower()
        if suffix == ".png":
            mime = "image/png"
        elif suffix == ".webp":
            mime = "image/webp"
        else:
            mime = "image/jpeg"
        import base64

        encoded = base64.b64encode(path.read_bytes()).decode("utf-8")
        return f"data:{mime};base64,{encoded}"

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
