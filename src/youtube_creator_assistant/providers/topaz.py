from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from youtube_creator_assistant.core.config import Settings


@dataclass
class TopazVideoUpscaleResult:
    request_id: str
    output_path: Path
    source_path: Path
    model: str
    status_payload: dict[str, Any]


class TopazVideoProvider:
    def __init__(self, settings: Settings, api_key: str | None = None):
        self.settings = settings
        self.api_key = api_key or os.environ.get(settings.topaz.api_key_env)

    def upscale_video(self, source_path: Path, output_path: Path | None = None) -> TopazVideoUpscaleResult:
        if not self.settings.topaz.enabled:
            raise RuntimeError("Topaz video upscale is disabled for this profile.")

        source = Path(source_path).expanduser().resolve()
        if not source.exists() or not source.is_file():
            raise FileNotFoundError(f"Topaz source video not found: {source}")

        if self.settings.topaz.verify_supported_model:
            supported = self.system_status().get("supportedModels") or []
            if supported and self.settings.topaz.model not in supported:
                supported_text = ", ".join(sorted(str(item) for item in supported))
                raise RuntimeError(
                    f"Topaz model '{self.settings.topaz.model}' is not listed by /video/status. "
                    f"Supported models reported by the API: {supported_text}"
                )

        metadata = self._probe_video_metadata(source)
        target = self._resolve_output_path(source, output_path)
        target.parent.mkdir(parents=True, exist_ok=True)

        create_payload = self._create_express_request(source, metadata)
        request_id = str(create_payload.get("requestId") or "").strip()
        upload_urls = create_payload.get("uploadUrls") or []
        if not request_id or not upload_urls:
            raise RuntimeError("Topaz did not return a requestId/uploadUrls pair.")

        self._upload_file(str(upload_urls[0]), source)
        status_payload = self._wait_for_completion(request_id)
        download = status_payload.get("download") or {}
        download_url = str(download.get("url") or "").strip()
        if not download_url:
            raise RuntimeError("Topaz completed without returning a download URL.")

        self._download_file(download_url, target)
        return TopazVideoUpscaleResult(
            request_id=request_id,
            output_path=target,
            source_path=source,
            model=self.settings.topaz.model,
            status_payload=status_payload,
        )

    def system_status(self) -> dict[str, Any]:
        return self._request_json("GET", "/video/status")

    def request_status(self, request_id: str) -> dict[str, Any]:
        clean_request_id = str(request_id).strip()
        if not clean_request_id:
            raise RuntimeError("Topaz request_id is missing.")
        return self._request_json("GET", f"/video/{clean_request_id}/status")

    def _request_json(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        api_key = self._api_key()
        url = f"{self.settings.topaz.api_base_url.rstrip('/')}{path}"
        headers = {"X-API-Key": api_key, "Accept": "application/json"}
        data = None
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=True).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=data, headers=headers, method=method.upper())
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                body = response.read()
        except Exception as exc:
            raise RuntimeError(f"Topaz API request failed for {method.upper()} {url}: {exc}") from exc
        if not body:
            return {}
        try:
            decoded = json.loads(body.decode("utf-8"))
        except Exception as exc:
            raise RuntimeError(f"Topaz API did not return valid JSON for {method.upper()} {url}.") from exc
        if not isinstance(decoded, dict):
            raise RuntimeError(f"Topaz API returned an unexpected payload for {method.upper()} {url}.")
        return decoded

    def _create_express_request(self, source_path: Path, metadata: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "source": {
                "container": metadata["container"],
                "md5Hash": self._md5_for_file(source_path),
            },
            "filters": [
                {
                    "model": self.settings.topaz.model,
                    **dict(self.settings.topaz.filter_params or {}),
                }
            ],
            "output": self._build_output_payload(metadata),
        }
        return self._request_json("POST", "/video/express", payload)

    def _build_output_payload(self, metadata: dict[str, Any]) -> dict[str, Any]:
        upscale_factor = max(1.0, float(self.settings.topaz.upscale_factor or 1.0))
        source_width = int(metadata["width"])
        source_height = int(metadata["height"])
        target_width = self._even(max(2, round(source_width * upscale_factor)))
        target_height = self._even(max(2, round(source_height * upscale_factor)))
        source_fps = float(metadata["fps"])
        output: dict[str, Any] = {
            "resolution": {
                "width": target_width,
                "height": target_height,
            },
            "frameRate": max(1, round(source_fps)) if source_fps > 0 else 24,
            "container": self.settings.topaz.output_container or metadata["container"],
        }
        output.update(dict(self.settings.topaz.output_overrides or {}))
        return output

    def _resolve_output_path(self, source_path: Path, output_path: Path | None) -> Path:
        if output_path is not None:
            return Path(output_path).expanduser().resolve()
        suffix = self.settings.topaz.output_suffix or "_topaz"
        ext = self.settings.topaz.output_container or source_path.suffix.lstrip(".") or "mp4"
        return source_path.with_name(f"{source_path.stem}{suffix}.{ext.lstrip('.')}")

    def _wait_for_completion(self, request_id: str) -> dict[str, Any]:
        deadline = time.monotonic() + max(1.0, float(self.settings.topaz.timeout_seconds or 14400.0))
        last_payload: dict[str, Any] = {}
        while time.monotonic() < deadline:
            payload = self.request_status(request_id)
            last_payload = payload
            status = str(payload.get("status") or "").strip().lower()
            if status == "complete":
                return payload
            if status in {"failed", "canceled"}:
                message = str(payload.get("message") or status or "unknown failure")
                raise RuntimeError(f"Topaz request {request_id} ended with status '{status}': {message}")
            time.sleep(max(1.0, float(self.settings.topaz.poll_interval_seconds or 20.0)))
        last_status = str(last_payload.get("status") or "timeout").strip()
        raise RuntimeError(f"Topaz request {request_id} timed out while waiting for completion. Last status: {last_status}")

    def _upload_file(self, upload_url: str, source_path: Path) -> None:
        curl = shutil.which("curl")
        if not curl:
            raise RuntimeError("curl is required to upload videos to the Topaz express endpoint.")
        command = [
            curl,
            "--fail",
            "--silent",
            "--show-error",
            "-X",
            "PUT",
            "-H",
            "Content-Type: application/octet-stream",
            "--upload-file",
            str(source_path),
            upload_url,
        ]
        proc = subprocess.run(command, check=False, capture_output=True, text=True)
        if proc.returncode != 0:
            tail = (proc.stderr or proc.stdout or "").strip()
            raise RuntimeError(f"Topaz upload failed for {source_path.name}: {tail or 'curl PUT failed.'}")

    def _download_file(self, download_url: str, output_path: Path) -> None:
        temp_path = output_path.with_name(f"{output_path.stem}.tmp{output_path.suffix}")
        try:
            with urllib.request.urlopen(download_url, timeout=300) as response, temp_path.open("wb") as handle:
                shutil.copyfileobj(response, handle)
            if not temp_path.exists() or temp_path.stat().st_size <= 0:
                raise RuntimeError("Topaz download produced an empty file.")
            temp_path.replace(output_path)
        finally:
            temp_path.unlink(missing_ok=True)

    def _probe_video_metadata(self, source_path: Path) -> dict[str, Any]:
        ffprobe = shutil.which("ffprobe")
        if not ffprobe:
            raise RuntimeError("ffprobe is required to inspect the source video for Topaz upscale.")
        command = [
            ffprobe,
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height,avg_frame_rate,r_frame_rate",
            "-show_entries",
            "format=format_name",
            "-of",
            "json",
            str(source_path),
        ]
        proc = subprocess.run(command, check=False, capture_output=True, text=True)
        if proc.returncode != 0:
            tail = (proc.stderr or "").strip() or "Unknown ffprobe error."
            raise RuntimeError(f"ffprobe failed for {source_path.name}: {tail}")
        try:
            payload = json.loads(proc.stdout or "{}")
        except Exception as exc:
            raise RuntimeError(f"ffprobe returned invalid JSON for {source_path.name}.") from exc
        streams = payload.get("streams") or []
        stream = streams[0] if streams else {}
        width = int(stream.get("width") or 0)
        height = int(stream.get("height") or 0)
        fps = self._parse_rate(stream.get("avg_frame_rate")) or self._parse_rate(stream.get("r_frame_rate")) or 24.0
        format_name = str((payload.get("format") or {}).get("format_name") or "").strip()
        container = self._container_from_format(format_name, source_path)
        if width <= 0 or height <= 0:
            raise RuntimeError(f"Could not determine video dimensions for {source_path.name}.")
        return {
            "width": width,
            "height": height,
            "fps": fps,
            "container": container,
        }

    def _md5_for_file(self, source_path: Path) -> str:
        digest = hashlib.md5()
        with source_path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _api_key(self) -> str:
        if not self.api_key:
            self.api_key = os.environ.get(self.settings.topaz.api_key_env)
        if not self.api_key:
            raise RuntimeError(f"{self.settings.topaz.api_key_env} is missing.")
        return self.api_key

    @staticmethod
    def _parse_rate(raw: Any) -> float | None:
        if raw in {None, "", "0/0"}:
            return None
        text = str(raw)
        if "/" in text:
            numerator, denominator = text.split("/", 1)
            try:
                num = float(numerator)
                den = float(denominator)
            except Exception:
                return None
            if den == 0:
                return None
            return num / den
        try:
            return float(text)
        except Exception:
            return None

    @staticmethod
    def _container_from_format(format_name: str, source_path: Path) -> str:
        if format_name:
            first = format_name.split(",", 1)[0].strip().lower()
            if first in {"mov", "mp4", "m4a", "3gp", "3g2", "mj2"}:
                return "mp4"
            if first:
                return first
        suffix = source_path.suffix.lower().lstrip(".")
        return suffix or "mp4"

    @staticmethod
    def _even(value: int) -> int:
        number = int(value)
        return number if number % 2 == 0 else number + 1
