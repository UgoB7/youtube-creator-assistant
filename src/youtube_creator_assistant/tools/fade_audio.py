from __future__ import annotations

import argparse
import subprocess
from pathlib import Path
from typing import Iterable, List, Sequence

from mutagen import File as MutagenFile


DEFAULT_FADE_SECONDS = 5.0
DEFAULT_EXTENSIONS = (".wav", ".mp3")


def normalize_extensions(values: Iterable[str]) -> List[str]:
    normalized: List[str] = []
    for value in values:
        suffix = str(value).strip().lower()
        if not suffix:
            continue
        if not suffix.startswith("."):
            suffix = f".{suffix}"
        if suffix not in normalized:
            normalized.append(suffix)
    return normalized or list(DEFAULT_EXTENSIONS)


def list_audio_files(source_dir: Path, output_dir: Path, extensions: Sequence[str]) -> List[Path]:
    allowed = set(normalize_extensions(extensions))
    files: List[Path] = []
    for path in sorted(source_dir.iterdir()):
        if not path.is_file():
            continue
        if path.parent == output_dir:
            continue
        if path.suffix.lower() not in allowed:
            continue
        files.append(path)
    return files


def get_audio_duration_seconds(path: Path) -> float:
    audio_file = MutagenFile(path)
    if audio_file is None or audio_file.info is None:
        raise RuntimeError(f"Could not read audio metadata for {path}")
    return float(audio_file.info.length)


def compute_fade_durations(duration_seconds: float, requested_fade_seconds: float) -> tuple[float, float, float]:
    if duration_seconds <= 0:
        raise ValueError("Audio duration must be positive.")
    fade_seconds = min(max(requested_fade_seconds, 0.0), duration_seconds / 2.0)
    fade_out_start = max(0.0, duration_seconds - fade_seconds)
    return fade_seconds, fade_seconds, fade_out_start


def encoder_args_for(path: Path) -> List[str]:
    suffix = path.suffix.lower()
    if suffix == ".wav":
        return ["-c:a", "pcm_s16le"]
    if suffix == ".mp3":
        return ["-c:a", "libmp3lame", "-q:a", "2"]
    raise ValueError(f"Unsupported audio format: {path.suffix}")


def build_ffmpeg_command(
    input_path: Path,
    output_path: Path,
    fade_seconds: float,
    overwrite: bool,
) -> List[str]:
    duration_seconds = get_audio_duration_seconds(input_path)
    fade_in_seconds, fade_out_seconds, fade_out_start = compute_fade_durations(
        duration_seconds,
        fade_seconds,
    )
    audio_filter = (
        f"afade=t=in:st=0:d={fade_in_seconds:.3f},"
        f"afade=t=out:st={fade_out_start:.3f}:d={fade_out_seconds:.3f}"
    )
    return [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y" if overwrite else "-n",
        "-i",
        str(input_path),
        "-map_metadata",
        "0",
        "-af",
        audio_filter,
        *encoder_args_for(output_path),
        str(output_path),
    ]


def fade_audio_library(
    source_dir: Path,
    output_dir: Path,
    fade_seconds: float = DEFAULT_FADE_SECONDS,
    extensions: Sequence[str] = DEFAULT_EXTENSIONS,
    overwrite: bool = False,
) -> list[Path]:
    source_dir = source_dir.expanduser().resolve()
    output_dir = output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    rendered_files: list[Path] = []
    for input_path in list_audio_files(source_dir, output_dir, extensions):
        output_path = output_dir / input_path.name
        command = build_ffmpeg_command(
            input_path=input_path,
            output_path=output_path,
            fade_seconds=fade_seconds,
            overwrite=overwrite,
        )
        subprocess.run(command, check=True)
        rendered_files.append(output_path)
    return rendered_files


def _default_source_dir() -> Path:
    repo_root = Path(__file__).resolve().parents[3]
    return repo_root / "assets" / "audio" / "enchanted_melodies"


def parse_args() -> argparse.Namespace:
    default_source_dir = _default_source_dir()
    parser = argparse.ArgumentParser(
        description="Generate faded audio copies for the enchanted_melodies profile.",
    )
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=default_source_dir,
        help=f"Directory containing source audio files. Default: {default_source_dir}",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output directory for faded files. Default: <source-dir>/faded",
    )
    parser.add_argument(
        "--fade-seconds",
        type=float,
        default=DEFAULT_FADE_SECONDS,
        help=f"Fade in/out duration in seconds. Default: {DEFAULT_FADE_SECONDS}",
    )
    parser.add_argument(
        "--extensions",
        nargs="*",
        default=list(DEFAULT_EXTENSIONS),
        help="Audio extensions to process, for example: .wav .mp3",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing faded files.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    source_dir = args.source_dir.expanduser().resolve()
    output_dir = (
        args.output_dir.expanduser().resolve()
        if args.output_dir is not None
        else source_dir / "faded"
    )
    rendered_files = fade_audio_library(
        source_dir=source_dir,
        output_dir=output_dir,
        fade_seconds=float(args.fade_seconds),
        extensions=normalize_extensions(args.extensions),
        overwrite=bool(args.force),
    )
    print(f"Generated {len(rendered_files)} faded audio files in {output_dir}")


if __name__ == "__main__":
    main()
