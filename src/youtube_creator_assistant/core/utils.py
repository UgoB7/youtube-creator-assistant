from __future__ import annotations

import base64
import re
import shutil
from pathlib import Path
from typing import Iterable, List


_WS_RE = re.compile(r"\s+")
_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)


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
