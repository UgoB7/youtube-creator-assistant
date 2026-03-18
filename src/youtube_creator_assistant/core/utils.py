from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Iterable, List


_WS_RE = re.compile(r"\s+")
_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)
_FFMPEG_DURATION_RE = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")
_FFMPEG_FPS_RE = re.compile(r"(\d+(?:\.\d+)?)\s*fps\b", re.IGNORECASE)


def split_examples(raw: str) -> List[str]:
    return [item.strip() for item in raw.split("/") if item.strip()]


def normalize_text(value: str) -> str:
    text = value.strip().casefold()
    text = _PUNCT_RE.sub("", text)
    text = _WS_RE.sub(" ", text)
    return text


def slugify(value: str) -> str:
    text = normalize_text(value)
    text = text.replace(" ", "-")
    return text[:80] or "project"


def tc_to_seconds(tc: str, fps: int) -> float:
    hours, minutes, seconds, frames = [int(part) for part in tc.split(":")]
    return (hours * 3600) + (minutes * 60) + seconds + (frames / float(fps))


def img_to_data_url(path: Path) -> str:
    mime = "image/jpeg" if path.suffix.lower() in {".jpg", ".jpeg"} else "image/png"
    b64 = base64.b64encode(path.read_bytes()).decode("utf-8")
    return f"data:{mime};base64,{b64}"


def ensure_clean_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def dedupe_preserve_order(items: Iterable[str]) -> List[str]:
    seen = set()
    output: List[str] = []
    for item in items:
        norm = normalize_text(item)
        if not norm or norm in seen:
            continue
        seen.add(norm)
        output.append(item.strip())
    return output


def stable_seed(*parts: object) -> int:
    hasher = hashlib.sha256()
    for part in parts:
        hasher.update(str(part).encode("utf-8"))
        hasher.update(b"::")
    return int.from_bytes(hasher.digest()[:8], "big", signed=False)


def _parse_ffprobe_rate(value: str | None) -> float | None:
    if not value or value in {"0/0", "N/A"}:
        return None
    try:
        if "/" in value:
            numerator, denominator = value.split("/", 1)
            denominator_value = float(denominator)
            if denominator_value == 0:
                return None
            return float(numerator) / denominator_value
        return float(value)
    except Exception:
        return None


def _find_media_binary(name: str) -> str | None:
    env_names = {
        "ffprobe": ["YCA_FFPROBE_BIN", "FFPROBE_BIN"],
        "ffmpeg": ["YCA_FFMPEG_BIN", "FFMPEG_BIN"],
    }.get(name, [])
    for env_name in env_names:
        raw = os.environ.get(env_name)
        if raw:
            candidate = str(Path(raw).expanduser())
            if Path(candidate).exists():
                return candidate
    return shutil.which(name)


def _probe_video_metadata_with_ffprobe(path: Path) -> tuple[float | None, float | None]:
    ffprobe = _find_media_binary("ffprobe")
    if not ffprobe:
        return None, None
    try:
        output = subprocess.check_output(
            [
                ffprobe,
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=avg_frame_rate,r_frame_rate,duration:format=duration",
                "-of",
                "json",
                str(path),
            ],
            stderr=subprocess.STDOUT,
        )
        payload = json.loads(output.decode("utf-8"))
        streams = payload.get("streams") or []
        stream = streams[0] if streams else {}
        duration_raw = stream.get("duration")
        if duration_raw in {None, "N/A"}:
            duration_raw = (payload.get("format") or {}).get("duration")
        duration_seconds = float(duration_raw) if duration_raw not in {None, "N/A"} else None
        fps = _parse_ffprobe_rate(stream.get("avg_frame_rate")) or _parse_ffprobe_rate(stream.get("r_frame_rate"))
        return duration_seconds, fps
    except Exception:
        return None, None


def _probe_video_metadata_with_ffmpeg(path: Path) -> tuple[float | None, float | None]:
    ffmpeg = _find_media_binary("ffmpeg")
    if not ffmpeg:
        return None, None
    try:
        result = subprocess.run(
            [
                ffmpeg,
                "-hide_banner",
                "-i",
                str(path),
            ],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        text = (result.stderr or "") + "\n" + (result.stdout or "")
        duration_match = _FFMPEG_DURATION_RE.search(text)
        fps_match = _FFMPEG_FPS_RE.search(text)
        duration_seconds = None
        fps = None
        if duration_match:
            hours = int(duration_match.group(1))
            minutes = int(duration_match.group(2))
            seconds = float(duration_match.group(3))
            duration_seconds = (hours * 3600) + (minutes * 60) + seconds
        if fps_match:
            fps = float(fps_match.group(1))
        return duration_seconds, fps
    except Exception:
        return None, None


def probe_video_metadata(path: Path) -> tuple[float | None, float | None]:
    ffprobe_duration, ffprobe_fps = _probe_video_metadata_with_ffprobe(path)
    ffmpeg_duration, ffmpeg_fps = _probe_video_metadata_with_ffmpeg(path)
    duration_seconds = ffprobe_duration if ffprobe_duration is not None else ffmpeg_duration
    fps = ffprobe_fps if ffprobe_fps is not None else ffmpeg_fps
    return duration_seconds, fps


def probe_video_duration_seconds(path: Path) -> float | None:
    duration_seconds, _fps = probe_video_metadata(path)
    return duration_seconds


def extract_video_frame(video_path: Path, output_path: Path, timestamp_seconds: float = 0.0) -> Path | None:
    ffmpeg = _find_media_binary("ffmpeg")
    if not ffmpeg:
        return None
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            [
                ffmpeg,
                "-y",
                "-ss",
                f"{timestamp_seconds:.3f}",
                "-i",
                str(video_path),
                "-frames:v",
                "1",
                str(output_path),
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if output_path.exists() and output_path.stat().st_size > 0:
            return output_path
    except Exception:
        return None
    return None
