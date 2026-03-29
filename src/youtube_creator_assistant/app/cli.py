from __future__ import annotations

import argparse
from pathlib import Path

from youtube_creator_assistant.core.config import load_settings
from youtube_creator_assistant.core.pipeline import ContentPipeline


def main() -> None:
    parser = argparse.ArgumentParser(description="YouTube creator assistant CLI.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init-project", help="Create a project from a visual source.")
    init_parser.add_argument("--config", type=Path, required=True)
    init_parser.add_argument("--visual", type=Path, required=True)

    titles_parser = subparsers.add_parser("generate-titles", help="Generate title candidates.")
    titles_parser.add_argument("--config", type=Path, required=True)
    titles_parser.add_argument("--project-id", required=True)

    build_parser = subparsers.add_parser("build-package", help="Build audio, themes, description, and thumbnail.")
    build_parser.add_argument("--config", type=Path, required=True)
    build_parser.add_argument("--project-id", required=True)
    build_parser.add_argument("--title", action="append", required=True)

    overlay_parser = subparsers.add_parser(
        "render-screen-overlay",
        help="Render the reusable screen overlay video from the local Remotion project.",
    )
    overlay_parser.add_argument("--config", type=Path, required=True)
    overlay_parser.add_argument("--install", action="store_true")
    overlay_parser.add_argument("--debug", action="store_true")

    topaz_parser = subparsers.add_parser(
        "topaz-upscale",
        help="Upscale a local video or a project render using the Topaz Video API.",
    )
    topaz_parser.add_argument("--config", type=Path, required=True)
    topaz_source = topaz_parser.add_mutually_exclusive_group(required=True)
    topaz_source.add_argument("--video", type=Path)
    topaz_source.add_argument("--project-id")
    topaz_parser.add_argument("--output", type=Path)

    run_parser = subparsers.add_parser("run", help="Convenience flow: create project and generate titles.")
    run_parser.add_argument("--config", type=Path, required=True)
    run_parser.add_argument("--visual", type=Path, required=True)
    run_parser.add_argument("--title", action="append")

    args = parser.parse_args()
    settings = load_settings(args.config)
    pipeline = ContentPipeline(settings)

    if args.command == "init-project":
        project = pipeline.create_project(args.visual)
        print(project.project_id)
        print(project.project_dir)
        return

    if args.command == "generate-titles":
        project = pipeline.generate_titles(args.project_id)
        print(project.project_id)
        for idx, title in enumerate(project.title_candidates, start=1):
            print(f"{idx:02d}. {title}")
        return

    if args.command == "build-package":
        project = pipeline.build_package(args.project_id, args.title)
        print(project.project_dir)
        return

    if args.command == "render-screen-overlay":
        output_path = pipeline.render_screen_overlay_video(
            install=bool(args.install),
            debug=bool(args.debug),
        )
        print(output_path)
        print(pipeline.screen_overlay_builder_service.metadata_path())
        return

    if args.command == "topaz-upscale":
        if args.video is not None:
            result = pipeline.upscale_video_with_topaz(args.video, output_path=args.output)
            print(result.output_path)
            print(result.request_id)
            return
        project = pipeline.upscale_project_render_video_with_topaz(args.project_id, output_path=args.output)
        print(project.project_dir)
        if project.render_visual_asset is not None:
            print(project.render_visual_asset.path)
        return

    if args.command == "run":
        project = pipeline.create_project(args.visual)
        project = pipeline.generate_titles(project.project_id)
        print(project.project_id)
        for idx, title in enumerate(project.title_candidates, start=1):
            print(f"{idx:02d}. {title}")
        if args.title:
            project = pipeline.build_package(project.project_id, args.title)
            print(project.project_dir)
        return
