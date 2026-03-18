from __future__ import annotations

import argparse
import os
import threading
import webbrowser
from pathlib import Path

from flask import Flask, abort, flash, redirect, render_template_string, request, send_from_directory, url_for
from werkzeug.utils import secure_filename

from youtube_creator_assistant.core.config import load_settings
from youtube_creator_assistant.core.pipeline import ContentPipeline


PAGE = """<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>{{ settings.profile.display_name }} - youtube-creator-assistant</title>
  <style>
    body { font-family: system-ui, sans-serif; margin: 24px; background: #faf7f2; color: #1f2937; }
    .shell { max-width: 1120px; margin: 0 auto; }
    .card { background: white; border: 1px solid #e5e7eb; border-radius: 18px; padding: 18px; margin-bottom: 18px; box-shadow: 0 12px 30px rgba(15, 23, 42, 0.06); }
    .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; }
    .muted { color: #6b7280; font-size: 14px; }
    .flash { color: #991b1b; margin-bottom: 12px; }
    img { max-width: 100%; border-radius: 14px; }
    button { border: none; border-radius: 10px; padding: 10px 14px; cursor: pointer; background: #111827; color: white; }
    button.secondary { background: #d97706; }
    input[type=file] { margin-bottom: 12px; }
    ul { padding-left: 18px; }
    code { background: #f3f4f6; padding: 2px 6px; border-radius: 6px; }
    .project-link { display: block; margin-bottom: 8px; }
    @media (max-width: 860px) { .grid { grid-template-columns: 1fr; } }
  </style>
</head>
<body>
  <div class="shell">
    <div class="card">
      <h1>{{ settings.profile.display_name }} MVP</h1>
      <p class="muted">Upload an image, generate title candidates, choose up to 3 titles, then build the package.</p>
      {% with messages = get_flashed_messages() %}
        {% if messages %}
          <div class="flash">{{ messages[0] }}</div>
        {% endif %}
      {% endwith %}
      <form method="post" action="{{ url_for('create_project_route') }}" enctype="multipart/form-data">
        <input type="file" name="visual" accept=".png,.jpg,.jpeg,.webp" required>
        <button type="submit">Create project</button>
      </form>
    </div>

    <div class="grid">
      <div class="card">
        <h2>Projects</h2>
        {% if projects %}
          {% for item in projects %}
            <a class="project-link" href="{{ url_for('project_detail', project_id=item.project_id) }}">
              <strong>{{ item.project_id }}</strong> - {{ item.status }}
            </a>
          {% endfor %}
        {% else %}
          <p class="muted">No projects yet.</p>
        {% endif %}
      </div>

      {% if project %}
        <div class="card">
          <h2>Current project</h2>
          <p><strong>{{ project.project_id }}</strong></p>
          <p class="muted">Status: {{ project.status }}</p>
          {% if project.visual_asset.kind == "image" %}
            <img src="{{ url_for('project_file', project_id=project.project_id, relpath='input/' + project.visual_asset.path.name) }}" alt="visual">
          {% endif %}

          <form method="post" action="{{ url_for('generate_titles_route', project_id=project.project_id) }}" style="margin-top: 12px;">
            <button class="secondary" type="submit">Generate titles</button>
          </form>

          {% if project.title_candidates %}
            <form method="post" action="{{ url_for('build_package_route', project_id=project.project_id) }}" style="margin-top: 16px;">
              <h3>Choose up to 3 titles</h3>
              {% for title in project.title_candidates %}
                <div>
                  <label>
                    <input type="checkbox" name="titles" value="{{ title }}" {% if project.selected_titles and title in project.selected_titles %}checked{% elif not project.selected_titles and loop.index <= 3 %}checked{% endif %}>
                    {{ title }}
                  </label>
                </div>
              {% endfor %}
              <button type="submit" style="margin-top: 12px;">Build package</button>
            </form>
          {% endif %}
        </div>
      {% endif %}
    </div>

    {% if project and project.status == "package_built" %}
      <div class="card">
        <h2>Outputs</h2>
        <p><strong>Primary title</strong>: {{ project.selected_title }}</p>
        {% if project.selected_titles %}
          <p><strong>Selected titles</strong></p>
          <ul>
            {% for title in project.selected_titles %}
              <li>{{ title }}</li>
            {% endfor %}
          </ul>
        {% endif %}
        <p><strong>Themes</strong></p>
        <ul>
          {% for theme in project.themes %}
            <li>{{ theme }}</li>
          {% endfor %}
        </ul>
        <p><strong>Files</strong></p>
        <ul>
          <li><a href="{{ url_for('project_file', project_id=project.project_id, relpath='chapters.txt') }}">chapters.txt</a></li>
          <li><a href="{{ url_for('project_file', project_id=project.project_id, relpath='yt_video_description.txt') }}">yt_video_description.txt</a></li>
          <li><a href="{{ url_for('project_file', project_id=project.project_id, relpath='themes.txt') }}">themes.txt</a></li>
          <li><a href="{{ url_for('project_file', project_id=project.project_id, relpath='audio_selection.txt') }}">audio_selection.txt</a></li>
          <li><a href="{{ url_for('project_file', project_id=project.project_id, relpath='selected_titles.txt') }}">selected_titles.txt</a></li>
          {% if project.yt_thumbnail_path %}
            <li><a href="{{ url_for('project_file', project_id=project.project_id, relpath='artifacts/' + project.yt_thumbnail_path.name) }}">thumbnail</a></li>
          {% endif %}
        </ul>
      </div>
    {% endif %}
  </div>
</body>
</html>"""


def _load_env_from(path: Path) -> bool:
    if not path.exists():
        return False

    loaded_any = False
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        os.environ[key] = value
        loaded_any = True
    return loaded_any


def _load_env_files(config_path: Path) -> None:
    candidates = [
        Path.cwd() / ".env",
        config_path.resolve().parents[2] / ".env",
    ]
    seen: set[Path] = set()
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except Exception:
            resolved = candidate
        if resolved in seen:
            continue
        seen.add(resolved)
        _load_env_from(resolved)


def create_app(config_path: Path) -> Flask:
    _load_env_files(config_path)
    settings = load_settings(config_path)
    pipeline = ContentPipeline(settings)
    app = Flask(__name__)
    app.secret_key = "youtube-creator-assistant-dev"

    def _get_project(project_id: str | None):
        if not project_id:
            return None
        try:
            return pipeline.runtime.load_project(project_id)
        except FileNotFoundError:
            return None

    @app.get("/")
    def index():
        current_id = request.args.get("project_id", "")
        project = _get_project(current_id)
        return render_template_string(
            PAGE,
            settings=settings,
            projects=pipeline.runtime.list_projects(),
            project=project,
        )

    @app.get("/projects/<project_id>")
    def project_detail(project_id: str):
        return redirect(url_for("index", project_id=project_id))

    @app.post("/projects")
    def create_project_route():
        uploaded = request.files.get("visual")
        if not uploaded or not uploaded.filename:
            flash("Please choose an image file.")
            return redirect(url_for("index"))
        incoming_dir = settings.paths.incoming_dir
        incoming_dir.mkdir(parents=True, exist_ok=True)
        filename = secure_filename(uploaded.filename) or "upload.png"
        temp_path = incoming_dir / filename
        uploaded.save(temp_path)
        project = pipeline.create_project(temp_path)
        return redirect(url_for("index", project_id=project.project_id))

    @app.post("/projects/<project_id>/titles")
    def generate_titles_route(project_id: str):
        pipeline.generate_titles(project_id)
        return redirect(url_for("index", project_id=project_id))

    @app.post("/projects/<project_id>/build")
    def build_package_route(project_id: str):
        titles = [title.strip() for title in request.form.getlist("titles") if title.strip()]
        if not titles:
            flash("Please choose at least one title.")
            return redirect(url_for("index", project_id=project_id))
        if len(titles) > ContentPipeline.MAX_SELECTED_TITLES:
            flash(f"Please choose at most {ContentPipeline.MAX_SELECTED_TITLES} titles.")
            return redirect(url_for("index", project_id=project_id))
        pipeline.build_package(project_id, titles)
        return redirect(url_for("index", project_id=project_id))

    @app.get("/projects/<project_id>/files/<path:relpath>")
    def project_file(project_id: str, relpath: str):
        project_dir = settings.paths.outputs_dir / project_id
        target = (project_dir / relpath).resolve()
        if project_dir.resolve() not in target.parents and target != project_dir.resolve():
            abort(404)
        if not target.exists() or not target.is_file():
            abort(404)
        return send_from_directory(target.parent, target.name)

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the youtube-creator-assistant web UI.")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    _load_env_files(args.config)
    app = create_app(args.config)
    settings = load_settings(args.config)
    url = f"http://{settings.web.host}:{settings.web.port}/"
    if not args.no_browser and ((not settings.web.debug) or os.environ.get("WERKZEUG_RUN_MAIN") == "true"):
        threading.Timer(1.0, webbrowser.open, args=(url,)).start()
    app.run(host=settings.web.host, port=settings.web.port, debug=settings.web.debug)
