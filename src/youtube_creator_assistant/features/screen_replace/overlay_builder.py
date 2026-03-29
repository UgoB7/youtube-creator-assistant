from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from youtube_creator_assistant.core.config import Settings, load_settings


DEBUG_DURATION_SECONDS = 8.0
DEBUG_FPS = 24
DEBUG_WIDTH = 1280
DEBUG_HEIGHT = 720


def _resolve_output_path(raw_output: str, default_filename: str) -> Path:
    candidate = Path(raw_output).expanduser()
    if candidate.exists() and candidate.is_dir():
        return candidate / default_filename
    if raw_output.endswith(("/", "\\")):
        return candidate / default_filename
    return candidate


def _find_asset_file(base_dir: Path, stem: str, exts: list[str]) -> str:
    for ext in exts:
        candidate = base_dir / f"{stem}{ext}"
        if candidate.exists() and candidate.is_file():
            return candidate.name
    return ""


def _copy_asset_file(src: Path, dst: Path) -> None:
    if dst.exists() or dst.is_symlink():
        if dst.is_dir() and not dst.is_symlink():
            shutil.rmtree(dst)
        else:
            dst.unlink(missing_ok=True)
    shutil.copy2(src, dst)


def _find_executable(name: str) -> str | None:
    return shutil.which(name)


def _preferred_node_bin_dir() -> Path | None:
    candidates = [
        Path("/opt/homebrew/opt/node@22/bin"),
        Path("/usr/local/opt/node@22/bin"),
    ]
    for candidate in candidates:
        node_path = candidate / "node"
        npm_path = candidate / "npm"
        if node_path.exists() and npm_path.exists():
            return candidate
    return None


def _subprocess_env_with_node() -> dict[str, str]:
    env = dict(os.environ)
    preferred = _preferred_node_bin_dir()
    if preferred is None:
        return env
    current_path = env.get("PATH", "")
    env["PATH"] = f"{preferred}{os.pathsep}{current_path}" if current_path else str(preferred)
    return env


def _preferred_node_command() -> str:
    preferred = _preferred_node_bin_dir()
    if preferred is not None:
        return str(preferred / "node")
    return "node"


def _preferred_npm_command() -> str:
    preferred = _preferred_node_bin_dir()
    if preferred is not None:
        return str(preferred / "npm")
    return "npm"


def _default_browser_executable() -> Path | None:
    candidates = [
        Path("/Applications/Chromium.app/Contents/MacOS/Chromium"),
        Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
        Path("/Applications/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing"),
        Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
    ]
    return next((candidate for candidate in candidates if candidate.exists() and candidate.is_file()), None)


def _run_checked(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=False, text=True, capture_output=True, env=_subprocess_env_with_node())


def _merge_dict(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = dict(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge_dict(out[key], value)  # type: ignore[arg-type]
        else:
            out[key] = value
    return out


class ScreenOverlayBuilderService:
    def __init__(self, settings: Settings):
        self.settings = settings

    def is_enabled(self) -> bool:
        return bool(self.settings.screen_replace.overlay_builder.enabled)

    def output_video_path(self) -> Path:
        builder = self.settings.screen_replace.overlay_builder
        output_path = builder.output_video_path or self.settings.screen_replace.overlay_video_path
        if output_path is None:
            raise RuntimeError("screen_replace.overlay_builder.output_video_path is not configured.")
        return output_path.expanduser().resolve()

    def metadata_path(self) -> Path:
        return Path(f"{self.output_video_path()}.meta.json")

    def source_assets_dir(self) -> Path:
        source_dir = self.settings.screen_replace.overlay_builder.source_assets_dir
        if source_dir is None:
            raise RuntimeError("screen_replace.overlay_builder.source_assets_dir is not configured.")
        return source_dir.expanduser().resolve()

    def remotion_project_dir(self) -> Path:
        project_dir = self.settings.screen_replace.overlay_builder.project_dir
        if project_dir is None:
            raise RuntimeError("screen_replace.overlay_builder.project_dir is not configured.")
        return project_dir.expanduser().resolve()

    def public_assets_dir(self) -> Path:
        return self.remotion_project_dir() / "public" / "ecran"

    def browser_executable_path(self) -> Path | None:
        configured = self.settings.screen_replace.overlay_builder.browser_executable_path
        if configured is not None:
            resolved = configured.expanduser().resolve()
            return resolved if resolved.exists() and resolved.is_file() else None
        return _default_browser_executable()

    def render_overlay_video(
        self,
        *,
        install: bool = False,
        debug: bool = False,
        output_path: Path | None = None,
        duration_seconds: float | None = None,
        fps: int | None = None,
        width: int | None = None,
        height: int | None = None,
    ) -> Path:
        if not self.is_enabled():
            raise RuntimeError("Screen overlay builder is disabled for this profile.")

        builder = self.settings.screen_replace.overlay_builder
        project_dir = self.remotion_project_dir()
        source_assets_dir = self.source_assets_dir()
        if not source_assets_dir.exists() or not source_assets_dir.is_dir():
            raise FileNotFoundError(f"Screen overlay source assets dir not found: {source_assets_dir}")

        if debug:
            duration_value = (
                float(duration_seconds)
                if duration_seconds is not None
                else (_main_video_duration_seconds(source_assets_dir) or DEBUG_DURATION_SECONDS)
            )
            fps_value = int(fps if fps is not None else DEBUG_FPS)
            width_value = int(width if width is not None else DEBUG_WIDTH)
            height_value = int(height if height is not None else DEBUG_HEIGHT)
        else:
            duration_value = float(
                duration_seconds
                if duration_seconds is not None
                else (
                    builder.duration_seconds
                    if builder.duration_seconds is not None
                    else float(self.settings.replicate.video_duration or 12)
                )
            )
            fps_value = int(
                fps
                if fps is not None
                else (builder.fps if builder.fps is not None else int(self.settings.screen_replace.target_fps or 30))
            )
            width_value = int(
                width
                if width is not None
                else (
                    builder.width if builder.width is not None else int(self.settings.screen_replace.target_width or 3840)
                )
            )
            height_value = int(
                height
                if height is not None
                else (
                    builder.height if builder.height is not None else int(self.settings.screen_replace.target_height or 2160)
                )
            )

        resolved_output = Path(output_path).expanduser().resolve() if output_path else self.output_video_path()
        if debug:
            resolved_output = resolved_output.with_name(
                f"{resolved_output.stem}_debug{resolved_output.suffix or '.mp4'}"
            )
        resolved_output.parent.mkdir(parents=True, exist_ok=True)

        self._ensure_remotion_deps(project_dir, install=install)
        asset_map = self._sync_assets_to_public(source_assets_dir)
        props = self._build_props(
            asset_map=asset_map,
            source_assets_dir=source_assets_dir,
            width=width_value,
            height=height_value,
            fps=fps_value,
            duration_seconds=duration_value,
        )
        tmp_output = resolved_output.with_name(f"{resolved_output.stem}.tmp.render{resolved_output.suffix}")
        try:
            self._render_remotion(project_dir, tmp_output, props)
            shutil.move(str(tmp_output), str(resolved_output))
        finally:
            tmp_output.unlink(missing_ok=True)

        self._write_metadata(
            output_path=resolved_output,
            project_dir=project_dir,
            source_assets_dir=source_assets_dir,
            props=props,
            debug=debug,
        )
        return resolved_output

    def _build_props(
        self,
        *,
        asset_map: dict[str, Any],
        source_assets_dir: Path,
        width: int,
        height: int,
        fps: int,
        duration_seconds: float,
    ) -> dict[str, Any]:
        props: dict[str, Any] = {
            "width": int(max(1280, width)),
            "height": int(max(720, height)),
            "fps": int(max(1, fps)),
            "durationSeconds": float(max(1.0, duration_seconds)),
            "assets": {
                "mainVideo": asset_map["main_video"],
                "mainStill": asset_map["main_still"],
                "avatar": asset_map["avatar"],
                "reco": asset_map["reco"],
                "ytLogo": asset_map["yt_logo"],
                "spotifyLogo": asset_map["spotify_logo"],
            },
            "text": {
                "title": "LoFi Jesus Prayer Mix",
                "channel": "LoFi Jesus",
                "subscribers": "124K subscribers",
                "cta": "Subscribe to LoFi Jesus",
                "views": "1.2M views • live",
                "meta": "Live prayer stream",
                "comments": [
                    "Peace over your home tonight.",
                    "This keeps my prayer time focused.",
                    "Praying for everyone listening.",
                    "Grace and calm in this room.",
                ],
                "recommendedTitles": [
                    "Night Prayer LoFi",
                    "Scripture Sleep Mix",
                    "Morning Worship Beats",
                    "Crosslight Focus",
                ],
                "recommendedMeta": [
                    "LoFi Jesus • 842K views • 8h",
                    "LoFi Jesus • 1.3M views • 2d",
                    "LoFi Jesus • 599K views • 1w",
                    "LoFi Jesus • 411K views • 3w",
                ],
            },
        }
        custom_props = self._load_custom_props(source_assets_dir)
        if custom_props:
            props = _merge_dict(props, custom_props)
        props["width"] = int(max(1280, int(props.get("width", width) or width)))
        props["height"] = int(max(720, int(props.get("height", height) or height)))
        props["fps"] = int(max(1, int(props.get("fps", fps) or fps)))
        props["durationSeconds"] = float(max(1.0, float(props.get("durationSeconds", duration_seconds) or duration_seconds)))
        return props

    def _custom_props_path(self, source_assets_dir: Path) -> Path:
        filename = self.settings.screen_replace.overlay_builder.props_filename or "screen_overlay_props.local.json"
        return source_assets_dir / filename

    def _load_custom_props(self, source_assets_dir: Path) -> dict[str, Any]:
        path = self._custom_props_path(source_assets_dir)
        if not path.exists() or not path.is_file():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise RuntimeError(f"Invalid JSON in {path}: {exc}") from exc
        if not isinstance(payload, dict):
            raise RuntimeError(f"{path} must contain a JSON object at root.")
        return payload

    def _sync_assets_to_public(self, source_assets_dir: Path) -> dict[str, Any]:
        public_dir = self.public_assets_dir()
        public_dir.mkdir(parents=True, exist_ok=True)
        for existing in public_dir.iterdir():
            if existing.name == ".gitkeep":
                continue
            if existing.is_dir() and not existing.is_symlink():
                shutil.rmtree(existing)
            else:
                existing.unlink(missing_ok=True)

        main_video = _find_asset_file(source_assets_dir, "video1", [".mp4", ".mov", ".webm", ".m4v"])
        main_still = _find_asset_file(source_assets_dir, "current_video_16x9", [".png", ".jpg", ".jpeg", ".webp"])
        avatar = _find_asset_file(source_assets_dir, "channel_avatar", [".png", ".jpg", ".jpeg", ".webp"])
        yt_logo = _find_asset_file(source_assets_dir, "yt", [".png", ".jpg", ".jpeg", ".webp"])
        spotify_logo = _find_asset_file(source_assets_dir, "spotify", [".png", ".jpg", ".jpeg", ".webp"])

        reco_names: list[str] = []
        for idx in range(1, 5):
            name = _find_asset_file(source_assets_dir, f"im{idx}", [".png", ".jpg", ".jpeg", ".webp"])
            if name:
                reco_names.append(name)

        if main_video:
            self._normalize_video_for_remotion(source_assets_dir / main_video, public_dir / "video1.mp4")
            main_video = "video1.mp4"

        needed = [name for name in [main_still, avatar, yt_logo, spotify_logo, *reco_names] if name]
        for name in needed:
            _copy_asset_file(source_assets_dir / name, public_dir / name)

        return {
            "main_video": f"ecran/{main_video}" if main_video else "",
            "main_still": f"ecran/{main_still}" if main_still else "",
            "avatar": f"ecran/{avatar}" if avatar else "",
            "yt_logo": f"ecran/{yt_logo}" if yt_logo else "",
            "spotify_logo": f"ecran/{spotify_logo}" if spotify_logo else "",
            "reco": [f"ecran/{name}" for name in reco_names],
        }

    def _ensure_remotion_deps(self, project_dir: Path, *, install: bool) -> None:
        pkg = project_dir / "package.json"
        if not pkg.exists():
            raise RuntimeError(f"Missing screen overlay project: {pkg}")

        node_modules = project_dir / "node_modules"
        local_bin = node_modules / ".bin" / "remotion"
        local_cli_pkg = node_modules / "@remotion" / "cli" / "package.json"
        has_local_cli = local_bin.exists() or local_cli_pkg.exists()
        if node_modules.exists() and has_local_cli:
            return
        if not install:
            npm_command = _preferred_npm_command()
            raise RuntimeError(
                "Screen overlay dependencies are missing. Run:\n"
                f"cd {project_dir} && {npm_command} install"
            )

        proc = subprocess.run(
            [_preferred_npm_command(), "install"],
            cwd=project_dir,
            check=False,
            text=True,
            env=_subprocess_env_with_node(),
        )
        has_local_cli = local_bin.exists() or local_cli_pkg.exists()
        if proc.returncode != 0 or not node_modules.exists() or not has_local_cli:
            raise RuntimeError(f"npm install failed in {project_dir}")

    def _render_remotion(self, project_dir: Path, output_path: Path, props: dict[str, Any]) -> None:
        builder = self.settings.screen_replace.overlay_builder
        json_props = json.dumps(props, ensure_ascii=True, separators=(",", ":"))
        render_args = [
            "render",
            builder.entry_file or "src/index.jsx",
            builder.composition_id or "Overlay4K",
            str(output_path),
            f"--props={json_props}",
            "--codec=h264",
            "--crf=14",
            "--pixel-format=yuv420p",
        ]
        browser_executable = self.browser_executable_path()
        if browser_executable is not None:
            render_args.append(f"--browser-executable={browser_executable}")

        local_bin = project_dir / "node_modules" / ".bin" / "remotion"
        if local_bin.exists():
            command = [str(local_bin), *render_args]
        else:
            local_cli_pkg = project_dir / "node_modules" / "@remotion" / "cli"
            local_cli_entrypoints = [
                local_cli_pkg / "dist" / "index.js",
                local_cli_pkg / "dist" / "cjs" / "index.js",
                local_cli_pkg / "dist" / "remotion.js",
            ]
            local_cli_entry = next((p for p in local_cli_entrypoints if p.exists() and p.is_file()), None)
            if local_cli_entry is not None:
                command = [_preferred_node_command(), str(local_cli_entry), *render_args]
            else:
                command = ["npx", "--yes", "remotion", *render_args]

        proc = subprocess.run(command, cwd=project_dir, check=False, text=True, env=_subprocess_env_with_node())
        if proc.returncode != 0:
            raise RuntimeError("Screen overlay Remotion render failed.")
        if not output_path.exists() or output_path.stat().st_size <= 0:
            raise RuntimeError("Screen overlay Remotion produced no output video.")

    def _write_metadata(
        self,
        *,
        output_path: Path,
        project_dir: Path,
        source_assets_dir: Path,
        props: dict[str, Any],
        debug: bool,
    ) -> None:
        metadata = {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "output_path": str(output_path),
            "renderer": "remotion",
            "project_dir": str(project_dir),
            "public_assets_dir": str(self.public_assets_dir()),
            "source_assets_dir": str(source_assets_dir),
            "entry_file": self.settings.screen_replace.overlay_builder.entry_file,
            "composition_id": self.settings.screen_replace.overlay_builder.composition_id,
            "custom_props_file": str(self._custom_props_path(source_assets_dir)),
            "debug_mode": bool(debug),
            "props": props,
            "duration_seconds": _video_duration_seconds(output_path),
        }
        self.metadata_path().write_text(json.dumps(metadata, ensure_ascii=True, indent=2), encoding="utf-8")

    def _should_normalize_video(self, src: Path) -> bool:
        ffprobe = _find_executable("ffprobe")
        if not ffprobe:
            return True
        proc = _run_checked(
            [
                ffprobe,
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=codec_name,pix_fmt,width,height",
                "-of",
                "json",
                str(src),
            ]
        )
        if proc.returncode != 0:
            return True
        try:
            payload = json.loads(proc.stdout or "{}")
            streams = payload.get("streams") or []
            first = streams[0] if streams else {}
            codec_name = str(first.get("codec_name") or "").lower()
            pix_fmt = str(first.get("pix_fmt") or "").lower()
            width = int(first.get("width") or 0)
            height = int(first.get("height") or 0)
        except Exception:
            return True
        even_size = width > 0 and height > 0 and width % 2 == 0 and height % 2 == 0
        return not (codec_name == "h264" and pix_fmt.startswith("yuv420p") and even_size)

    def _normalize_video_for_remotion(self, src: Path, dst: Path) -> None:
        ffmpeg = _find_executable("ffmpeg")
        if not ffmpeg or not self._should_normalize_video(src):
            _copy_asset_file(src, dst)
            return
        tmp_dst = dst.with_suffix(".tmp.mp4")
        tmp_dst.unlink(missing_ok=True)
        proc = _run_checked(
            [
                ffmpeg,
                "-y",
                "-i",
                str(src),
                "-an",
                "-vf",
                "scale=trunc(iw/2)*2:trunc(ih/2)*2,format=yuv420p",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-preset",
                "slow",
                "-crf",
                "15",
                "-movflags",
                "+faststart",
                str(tmp_dst),
            ]
        )
        if proc.returncode != 0 or not tmp_dst.exists():
            _copy_asset_file(src, dst)
            tmp_dst.unlink(missing_ok=True)
            return
        dst.unlink(missing_ok=True)
        shutil.move(str(tmp_dst), str(dst))


def _video_duration_seconds(video_path: Path) -> float:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(video_path),
    ]
    proc = subprocess.run(command, check=False, capture_output=True, text=True)
    if proc.returncode != 0:
        return 0.0
    try:
        return max(0.0, float((proc.stdout or "").strip()))
    except Exception:
        return 0.0


def _main_video_duration_seconds(screen_assets_dir: Path) -> float:
    main_video_name = _find_asset_file(screen_assets_dir, "video1", [".mp4", ".mov", ".webm", ".m4v"])
    if not main_video_name:
        return 0.0
    candidate = screen_assets_dir / main_video_name
    if not candidate.exists() or not candidate.is_file():
        return 0.0
    return _video_duration_seconds(candidate)


def main() -> None:
    parser = argparse.ArgumentParser(description="Render a reusable screen overlay video from the Remotion project.")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--install", action="store_true", help="Run npm install in the screen overlay project if needed.")
    parser.add_argument("--debug", action="store_true", help="Use a faster low-resolution preset.")
    parser.add_argument("--output", type=str, default=None, help="Optional output path override.")
    parser.add_argument("--duration", type=float, default=None)
    parser.add_argument("--fps", type=int, default=None)
    parser.add_argument("--width", type=int, default=None)
    parser.add_argument("--height", type=int, default=None)
    args = parser.parse_args()

    settings = load_settings(args.config)
    service = ScreenOverlayBuilderService(settings)
    raw_output = args.output
    output_path = None
    if raw_output:
        default_name = service.output_video_path().name
        output_path = _resolve_output_path(raw_output, default_name)
    path = service.render_overlay_video(
        install=bool(args.install),
        debug=bool(args.debug),
        output_path=output_path,
        duration_seconds=args.duration,
        fps=args.fps,
        width=args.width,
        height=args.height,
    )
    print(path)
    print(service.metadata_path())


if __name__ == "__main__":
    main()
