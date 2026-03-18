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
    build_parser.add_argument("--title", required=True)

    run_parser = subparsers.add_parser("run", help="Convenience flow: create project and generate titles.")
    run_parser.add_argument("--config", type=Path, required=True)
    run_parser.add_argument("--visual", type=Path, required=True)
    run_parser.add_argument("--title", default="")

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

    if args.command == "run":
        project = pipeline.create_project(args.visual)
        project = pipeline.generate_titles(project.project_id)
        print(project.project_id)
        for idx, title in enumerate(project.title_candidates, start=1):
            print(f"{idx:02d}. {title}")
        if args.title.strip():
            project = pipeline.build_package(project.project_id, args.title)
            print(project.project_dir)
        return
