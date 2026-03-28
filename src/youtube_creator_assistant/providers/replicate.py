from __future__ import annotations

import os
import re
import time
import urllib.request
from pathlib import Path
from typing import Optional

from youtube_creator_assistant.core.config import Settings


class ReplicateProvider:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._client = None

    def generate_image_bytes(self, prompt: str) -> bytes:
        style = (self.settings.replicate.image_payload_style or "seedream").strip().lower()
        if style == "flux":
            payload = {
                "prompt": prompt,
                "resolution": self.settings.replicate.image_size,
                "aspect_ratio": self.settings.replicate.image_aspect_ratio,
                "input_images": [],
                "output_format": self.settings.replicate.image_output_format,
                "output_quality": int(self.settings.replicate.image_output_quality),
                "safety_tolerance": int(self.settings.replicate.image_safety_tolerance),
            }
        else:
            payload = {
                "width": int(self.settings.replicate.image_width),
                "height": int(self.settings.replicate.image_height),
                "prompt": prompt,
                "max_images": int(self.settings.replicate.image_max_images),
                "image_input": [],
                "size": self.settings.replicate.image_size,
                "aspect_ratio": self.settings.replicate.image_aspect_ratio,
                "enhance_prompt": self.settings.replicate.image_enhance_prompt,
                "sequential_image_generation": self.settings.replicate.image_sequential_generation,
            }
        output = self._run_with_retry(self.settings.replicate.image_model, payload)
        return self._output_bytes(output)

    def generate_video_bytes(self, image_path: Path) -> bytes:
        with image_path.open("rb") as first, image_path.open("rb") as last:
            payload = {
                "fps": int(self.settings.replicate.video_fps or 24),
                "image": first,
                "prompt": self.settings.replicate.video_prompt,
                "duration": self.settings.replicate.video_duration,
                "resolution": self.settings.replicate.video_resolution,
                "aspect_ratio": self.settings.replicate.video_aspect_ratio,
                "camera_fixed": self.settings.replicate.video_camera_fixed,
                "generate_audio": self.settings.replicate.video_generate_audio,
                "last_frame_image": last,
            }
            output = self._run_with_retry(self.settings.replicate.video_model, payload)
        return self._output_bytes(output)

    def generate_thumbnail_candidate_bytes(self, prompt: str, image_path: Path) -> bytes:
        with image_path.open("rb") as image_file:
            payload = {
                "prompt": prompt,
                "resolution": self.settings.thumbnail.candidate_resolution,
                "image_input": [image_file],
                "aspect_ratio": self.settings.thumbnail.candidate_aspect_ratio,
                "output_format": self.settings.thumbnail.candidate_output_format,
                "safety_filter_level": self.settings.thumbnail.candidate_safety_filter_level,
                "allow_fallback_model": self.settings.thumbnail.candidate_allow_fallback_model,
            }
            output = self._run_with_retry(self.settings.thumbnail.candidate_model, payload)
        return self._output_bytes(output)

    def client(self):
        if self._client is None:
            try:
                import replicate
            except Exception as exc:
                raise RuntimeError("Install `replicate` to enable the shepherd Replicate workflow.") from exc
            raw_token = os.environ.get("REPLICATE_API_TOKEN") or ""
            api_token = raw_token.strip().strip('"').strip("'")
            if not api_token or api_token == "...":
                raise RuntimeError("REPLICATE_API_TOKEN is missing or invalid.")
            self._client = replicate.Client(api_token=api_token)
        return self._client

    def _run_with_retry(self, model: str, payload: dict):
        last_exc: Optional[Exception] = None
        for attempt in range(4):
            try:
                return self.client().run(model, input=payload)
            except Exception as exc:
                last_exc = exc
                if not self._is_throttle_error(exc) or attempt >= 3:
                    raise
                time.sleep(self._retry_delay(exc, attempt))
        if last_exc:
            raise last_exc
        raise RuntimeError("Replicate failed without an explicit exception.")

    def _retry_delay(self, exc: Exception, attempt: int) -> float:
        text = str(exc)
        match = re.search(r"resets in ~(\d+)s", text, re.IGNORECASE)
        if match:
            try:
                return min(float(match.group(1)) + 0.5, 12.0)
            except Exception:
                pass
        return min(2.0 * (2 ** attempt), 12.0)

    def _is_throttle_error(self, exc: Exception) -> bool:
        text = str(exc).lower()
        return "status: 429" in text or "throttl" in text or "rate limit" in text

    def _output_bytes(self, output: object) -> bytes:
        if hasattr(output, "read"):
            try:
                return output.read()
            except Exception:
                pass
        if isinstance(output, list) and output:
            return self._output_bytes(output[0])
        urls = self._extract_urls(output)
        if urls:
            with urllib.request.urlopen(urls[0]) as resp:
                return resp.read()
        raise RuntimeError("Replicate did not return a usable file output.")

    def _extract_urls(self, output: object) -> list[str]:
        if hasattr(output, "url"):
            url = getattr(output, "url", None)
            if isinstance(url, str) and url:
                return [url]
        if isinstance(output, str):
            return [output]
        if isinstance(output, list):
            urls = []
            for item in output:
                if hasattr(item, "url"):
                    url = getattr(item, "url", None)
                    if isinstance(url, str) and url:
                        urls.append(url)
                elif isinstance(item, str):
                    urls.append(item)
            return urls
        return []
