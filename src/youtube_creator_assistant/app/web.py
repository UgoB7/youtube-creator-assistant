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
    .gallery { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; }
    .candidate { border: 1px solid #e5e7eb; border-radius: 14px; padding: 12px; background: #fcfcfd; }
    .candidate img { width: 100%; aspect-ratio: 16 / 9; object-fit: cover; border-radius: 12px; }
    .candidate-title { margin: 10px 0 0; font-size: 15px; line-height: 1.35; }
    .candidate-batch-card .candidate-prompt { display: none; }
    .candidate-batch-card.show-prompts .candidate-prompt { display: block; }
    .candidate-prompt { margin: 10px 0 0; font-size: 12px; line-height: 1.45; white-space: pre-wrap; word-break: break-word; }
    .candidate-tools { display: flex; align-items: center; gap: 10px; margin: 12px 0 8px; }
    .toggle-check { margin: 0; width: 16px; height: 16px; }
    .toggle-label { display: inline-flex; align-items: center; gap: 8px; color: #6b7280; font-size: 13px; cursor: pointer; user-select: none; }
    .muted { color: #6b7280; font-size: 14px; }
    .flash { color: #991b1b; margin-bottom: 12px; }
    img { max-width: 100%; border-radius: 14px; }
    video { width: 100%; border-radius: 14px; background: #111827; }
    button { border: none; border-radius: 10px; padding: 10px 14px; cursor: pointer; background: #111827; color: white; }
    button.secondary { background: #d97706; }
    input[type=file] { margin-bottom: 12px; }
    ul { padding-left: 18px; }
    code { background: #f3f4f6; padding: 2px 6px; border-radius: 6px; }
    .project-link { display: block; margin-bottom: 8px; }
    .screen-stage { position: relative; margin: 12px 0; aspect-ratio: 16 / 9; border-radius: 16px; overflow: hidden; background: #111827; border: 1px solid #d1d5db; }
    .screen-stage video { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: contain; border-radius: 0; pointer-events: none; }
    .screen-stage svg { position: absolute; inset: 0; width: 100%; height: 100%; pointer-events: none; z-index: 2; }
    .screen-quad-line { fill: rgba(107, 114, 128, 0.22); stroke: rgba(255, 255, 255, 0.56); stroke-width: 1; vector-effect: non-scaling-stroke; }
    .screen-handle { position: absolute; width: 28px; height: 28px; border: none; background: transparent; color: transparent; font-size: 0; transform: translate(-50%, -50%); cursor: grab; user-select: none; touch-action: none; z-index: 3; }
    .screen-handle::after { content: attr(data-handle-label); position: absolute; left: 12px; top: -2px; color: rgba(255,255,255,0.96); font-size: 11px; font-weight: 700; line-height: 1; text-shadow: 0 1px 2px rgba(0,0,0,0.85); pointer-events: none; }
    .screen-handle:active { cursor: grabbing; }
    @media (max-width: 860px) { .grid { grid-template-columns: 1fr; } }
  </style>
</head>
<body>
  <div class="shell">
    <div class="card">
      <h1>{{ settings.profile.display_name }} MVP</h1>
      <p class="muted">
        Upload a visual.
        {% if settings.replicate.enabled and settings.replicate.visual_prompt_generation.enabled %}
          This profile will turn the uploaded visual into LLM-generated image prompts, render candidate images, then let you choose one before generating the video and the final project.
        {% elif settings.replicate.enabled and settings.replicate.allow_candidate_generation %}
          Or leave the file empty to generate a batch of candidate images from the local prompt seeds, select one, then create the video and the project from that chosen image.
        {% elif settings.replicate.enabled %}
          If you upload an image, this profile will also generate a render video from it.
        {% endif %}
      </p>
      {% with messages = get_flashed_messages() %}
        {% if messages %}
          <div class="flash">{{ messages[0] }}</div>
        {% endif %}
      {% endwith %}
      <form method="post" action="{{ url_for('create_project_route') }}" enctype="multipart/form-data">
        <input type="file" name="visual" accept="{{ accept_attr }}">
        {% if settings.replicate.enabled and settings.replicate.visual_prompt_generation.enabled %}
          <p class="muted">If you upload a visual, this profile will generate {{ settings.replicate.candidate_count }} prompt-based image candidates from it first.</p>
        {% endif %}
        {% if settings.replicate.enabled and settings.replicate.allow_candidate_generation %}
          <p class="muted">If you leave the file empty, this profile will generate {{ settings.replicate.candidate_count }} candidate images first, then you can pick one.</p>
        {% endif %}
        <button type="submit">Create project</button>
      </form>
    </div>

    {% if candidate_batch %}
      <div class="card candidate-batch-card">
        <h2>{{ settings.profile.display_name }} Candidates</h2>
        <p class="muted">Batch {{ candidate_batch.batch_id }}. Choose one image to create the video and the project.</p>
        {% if candidate_batch.source_visual_asset %}
          <p class="muted">Source visual used for prompt generation:</p>
          {% if candidate_batch.source_visual_asset.kind == "image" %}
            <img src="{{ url_for('candidate_batch_file', batch_id=candidate_batch.batch_id, filename=candidate_batch.source_visual_asset.path.name) }}" alt="candidate source visual">
          {% elif candidate_batch.source_visual_asset.kind == "video" %}
            <video controls loop autoplay muted playsinline preload="metadata">
              <source src="{{ url_for('candidate_batch_file', batch_id=candidate_batch.batch_id, filename=candidate_batch.source_visual_asset.path.name) }}">
            </video>
          {% endif %}
        {% endif %}
        <div class="candidate-tools">
          <label class="toggle-label">
            <input id="show-candidate-prompts" class="toggle-check" type="checkbox">
            Show prompts
          </label>
        </div>
        <div class="gallery">
          {% for candidate in candidate_batch.candidates %}
            <form class="candidate" method="post" action="{{ url_for('select_candidate_route', batch_id=candidate_batch.batch_id) }}">
              <img src="{{ url_for('candidate_batch_file', batch_id=candidate_batch.batch_id, filename=candidate.image_path.name) }}" alt="{{ candidate.candidate_id }}">
              <p class="candidate-title"><strong>{{ candidate.label or candidate.candidate_id }}</strong></p>
              <p class="candidate-prompt muted">{{ candidate.prompt }}</p>
              <input type="hidden" name="candidate_id" value="{{ candidate.candidate_id }}">
              <button type="submit">Use this image</button>
            </form>
          {% endfor %}
        </div>
      </div>
    {% endif %}

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
        {% elif project.visual_asset.kind == "video" %}
          <p class="muted">Visual preview (loop)</p>
          <video controls loop autoplay muted playsinline preload="metadata">
            <source src="{{ url_for('project_file', project_id=project.project_id, relpath='input/' + project.visual_asset.path.name) }}">
          </video>
        {% endif %}
        {% if project.render_visual_asset and project.render_visual_asset.kind == "video" %}
          <p class="muted" style="margin-top: 12px;">Render visual preview (loop)</p>
          <video controls loop autoplay muted playsinline preload="metadata">
            <source src="{{ url_for('project_file', project_id=project.project_id, relpath='input/' + project.render_visual_asset.path.name) }}">
          </video>
        {% endif %}
        {% if settings.replicate.enabled and project.visual_asset.kind == "image" %}
          <form method="post" action="{{ url_for('regenerate_render_video_route', project_id=project.project_id) }}" style="margin-top: 12px;">
            <button class="secondary" type="submit">Regenerate video</button>
          </form>
        {% endif %}
        {% if settings.screen_replace.overlay_builder.enabled %}
          <form method="post" action="{{ url_for('render_screen_overlay_route', project_id=project.project_id) }}" style="margin-top: 12px;">
            <p class="muted">Reusable site-preview overlay video for screen replacement. Generate it once, then reuse it across renders.</p>
            <button class="secondary" type="submit">Render reusable overlay video</button>
          </form>
          {% if screen_overlay_video_exists %}
            <p class="muted" style="margin-top: 12px;">Reusable overlay preview</p>
            <video controls loop autoplay muted playsinline preload="metadata">
              <source src="{{ url_for('screen_overlay_file') }}">
            </video>
          {% endif %}
        {% endif %}
        {% if settings.topaz.enabled and project.render_visual_asset and project.render_visual_asset.kind == "video" %}
          <form method="post" action="{{ url_for('topaz_upscale_route', project_id=project.project_id) }}" style="margin-top: 12px;">
            <p class="muted">Optional: upscale the current render with Topaz before doing screen replacement.</p>
            <button class="secondary" type="submit">Upscale render with Topaz</button>
          </form>
        {% endif %}
        {% if settings.screen_replace.enabled and project.render_visual_asset and project.render_visual_asset.kind == "video" %}
          <form method="post" action="{{ url_for('render_screen_replace_route', project_id=project.project_id) }}" style="margin-top: 12px;">
            <p class="muted">Optional: render a monitor/screen replacement pass onto the current video.</p>
            <div class="screen-stage" id="screenStage" data-default-quad="{{ settings.screen_replace.quad_norm }}">
              <video id="screenStageVideo" autoplay muted loop playsinline preload="metadata">
                <source src="{{ url_for('project_file', project_id=project.project_id, relpath='input/' + project.render_visual_asset.path.name) }}">
              </video>
              <svg viewBox="0 0 1920 1080" preserveAspectRatio="none">
                <polygon id="screenQuadPolygon" class="screen-quad-line" points=""></polygon>
              </svg>
              <button type="button" class="screen-handle" data-handle-index="0" data-handle-label="1">1</button>
              <button type="button" class="screen-handle" data-handle-index="1" data-handle-label="2">2</button>
              <button type="button" class="screen-handle" data-handle-index="2" data-handle-label="3">3</button>
              <button type="button" class="screen-handle" data-handle-index="3" data-handle-label="4">4</button>
            </div>
            <p class="muted">Editor order: 1 top-left, 2 top-right, 3 bottom-right, 4 bottom-left. The backend keeps the old LoFi render mapping automatically.</p>
            <label class="muted" for="quad-norm-{{ project.project_id }}">Screen quad</label>
            <input id="screenQuadNormInput" type="text" name="quad_norm" value="{{ screen_replace_quad_norm }}" style="width: 100%; margin: 8px 0 12px; padding: 10px; border: 1px solid #d1d5db; border-radius: 10px;">
            <button class="secondary" type="submit">Render screen replacement</button>
          </form>
        {% endif %}

        <form method="post" action="{{ url_for('generate_titles_route', project_id=project.project_id) }}" style="margin-top: 12px;">
          <button class="secondary" type="submit">Generate titles</button>
        </form>

        {% if project.title_candidates %}
          <form method="post" action="{{ url_for('build_package_route', project_id=project.project_id) }}" style="margin-top: 16px;">
            <h3>
              {% if settings.workflow.max_selected_titles == 1 %}
                Choose the best title
              {% else %}
                Choose up to {{ settings.workflow.max_selected_titles }} titles
              {% endif %}
            </h3>
            {% for title in project.title_candidates %}
              <div>
                <label>
                  <input
                    type="{% if settings.workflow.max_selected_titles == 1 %}radio{% else %}checkbox{% endif %}"
                    name="titles"
                    value="{{ title }}"
                    {% if project.selected_titles and title in project.selected_titles %}checked{% elif not project.selected_titles and loop.index <= settings.workflow.max_selected_titles %}checked{% endif %}
                  >
                  {{ title }}
                </label>
              </div>
            {% endfor %}
            <button type="submit" style="margin-top: 12px;">Build package</button>
          </form>
        {% endif %}
      </div>
    {% endif %}

    {% if project and project.status in ["package_built", "resolve_synced"] %}
      <div class="card">
        <h2>Outputs</h2>
        <p><strong>Primary title</strong>: {{ project.selected_title }}</p>
        {% if project.resolve_timeline_name %}
          <p><strong>Resolve timeline</strong>: {{ project.resolve_timeline_name }}</p>
        {% endif %}
        {% if project.resolve_last_synced_at %}
          <p class="muted">Last Resolve sync: {{ project.resolve_last_synced_at }}</p>
        {% endif %}
        {% if project.resolve_last_error %}
          <p class="flash">{{ project.resolve_last_error }}</p>
        {% endif %}
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
          {% if project.source_prompt %}
            <li><a href="{{ url_for('project_file', project_id=project.project_id, relpath='replicate_prompt.txt') }}">replicate_prompt.txt</a></li>
          {% endif %}
          <li><a href="{{ url_for('project_file', project_id=project.project_id, relpath='chapters.txt') }}">chapters.txt</a></li>
          <li><a href="{{ url_for('project_file', project_id=project.project_id, relpath='yt_video_description.txt') }}">yt_video_description.txt</a></li>
          <li><a href="{{ url_for('project_file', project_id=project.project_id, relpath='themes.txt') }}">themes.txt</a></li>
          <li><a href="{{ url_for('project_file', project_id=project.project_id, relpath='audio_selection.txt') }}">audio_selection.txt</a></li>
          <li><a href="{{ url_for('project_file', project_id=project.project_id, relpath='audio_selection_debug.txt') }}">audio_selection_debug.txt</a></li>
          <li><a href="{{ url_for('project_file', project_id=project.project_id, relpath='selected_titles.txt') }}">selected_titles.txt</a></li>
          <li><a href="{{ url_for('project_file', project_id=project.project_id, relpath='render_plan.json') }}">render_plan.json</a></li>
          {% if screen_overlay_video_exists %}
            <li><a href="{{ url_for('screen_overlay_file') }}">screen_overlay_video</a></li>
          {% endif %}
          {% if screen_overlay_metadata_exists %}
            <li><a href="{{ url_for('screen_overlay_metadata_file') }}">screen_overlay_video.meta.json</a></li>
          {% endif %}
          {% if project.render_visual_asset and project.render_visual_asset.path.name == settings.screen_replace.output_filename %}
            <li><a href="{{ url_for('project_file', project_id=project.project_id, relpath='screen_replace.json') }}">screen_replace.json</a></li>
          {% endif %}
          {% if project.resolve_last_synced_at %}
            <li><a href="{{ url_for('project_file', project_id=project.project_id, relpath='resolve_sync.json') }}">resolve_sync.json</a></li>
          {% endif %}
          {% if project.yt_thumbnail_path %}
            <li><a href="{{ url_for('project_file', project_id=project.project_id, relpath='artifacts/' + project.yt_thumbnail_path.name) }}">thumbnail</a></li>
          {% endif %}
        </ul>
        {% if settings.thumbnail.candidate_generation_enabled and project.selected_title %}
          <form method="post" action="{{ url_for('generate_thumbnail_candidates_route', project_id=project.project_id) }}" style="margin-top: 12px;">
            <button class="secondary" type="submit">Generate thumbnail candidates</button>
          </form>
        {% endif %}
        {% if selected_thumbnail_candidates %}
          <p><strong>Selected thumbnail concepts</strong></p>
          <ul>
            {% for item in selected_thumbnail_candidates %}
              <li>{{ item.label }}</li>
            {% endfor %}
          </ul>
        {% endif %}
        {% if thumbnail_candidates %}
          <div style="margin-top: 18px;">
            <p><strong>Thumbnail candidates</strong></p>
            <p class="muted">LLM concepts plus Replicate renders based on the current image and selected title.</p>
            <form method="post" action="{{ url_for('select_thumbnail_candidates_route', project_id=project.project_id) }}">
              <div class="gallery">
                {% for item in thumbnail_candidates %}
                  <div class="candidate">
                    <img src="{{ url_for('project_file', project_id=project.project_id, relpath='artifacts/thumbnail_candidates/' + item.image_filename) }}" alt="{{ item.label }}">
                    <p><strong>{{ item.label }}</strong></p>
                    <p class="muted">{{ item.summary }}</p>
                    <label>
                      <input type="checkbox" name="thumbnail_candidates" value="{{ item.candidate_id }}" {% if selected_thumbnail_candidates and item.candidate_id in selected_thumbnail_candidate_ids %}checked{% elif not selected_thumbnail_candidates and loop.index == 1 %}checked{% endif %}>
                      Use for thumbnail
                    </label>
                  </div>
                {% endfor %}
              </div>
              <button type="submit" style="margin-top: 12px;">Save selected thumbnails</button>
            </form>
          </div>
        {% endif %}
        <form method="post" action="{{ url_for('send_to_resolve_route', project_id=project.project_id) }}">
          <button class="secondary" type="submit">Send to Resolve</button>
        </form>
      </div>
    {% endif %}
  </div>
  <script>
    (() => {
      const toggle = document.getElementById("show-candidate-prompts");
      const card = document.querySelector(".candidate-batch-card");
      if (!toggle || !card) return;
      const sync = () => card.classList.toggle("show-prompts", toggle.checked);
      toggle.addEventListener("change", sync);
      sync();
    })();
    (() => {
      const screenStage = document.getElementById("screenStage");
      const screenQuadPolygon = document.getElementById("screenQuadPolygon");
      const screenQuadNormInput = document.getElementById("screenQuadNormInput");
      const screenHandles = Array.from(document.querySelectorAll(".screen-handle"));
      if (!screenStage || !screenQuadPolygon || !screenQuadNormInput || screenHandles.length !== 4) return;

      const clamp01 = (value) => Math.max(0, Math.min(1, value));
      const parseQuadText = (text) => {
        const chunks = String(text || "").split(";").map((item) => item.trim()).filter(Boolean);
        if (chunks.length !== 4) return [];
        const points = [];
        chunks.forEach((chunk) => {
          const pair = chunk.split(",").map((item) => item.trim());
          if (pair.length !== 2) return;
          const x = Number.parseFloat(pair[0]);
          const y = Number.parseFloat(pair[1]);
          if (!Number.isFinite(x) || !Number.isFinite(y)) return;
          points.push({ x: clamp01(x), y: clamp01(y) });
        });
        return points.length === 4 ? points : [];
      };
      const parseQuad = (raw, fallbackRaw) => {
        const first = parseQuadText(raw);
        if (first.length === 4) return first;
        const second = parseQuadText(fallbackRaw);
        if (second.length === 4) return second;
        return [
          { x: 0.36, y: 0.30 },
          { x: 0.64, y: 0.30 },
          { x: 0.64, y: 0.70 },
          { x: 0.36, y: 0.70 },
        ];
      };
      const quadToString = (points) => {
        return points.map((point) => `${point.x.toFixed(4)},${point.y.toFixed(4)}`).join(";");
      };

      let screenQuadPoints = parseQuad(screenQuadNormInput.value, screenStage.dataset.defaultQuad || "");
      let draggingHandleIndex = null;

      const syncScreenQuadUI = () => {
        if (!Array.isArray(screenQuadPoints) || screenQuadPoints.length !== 4) return;
        screenQuadNormInput.value = quadToString(screenQuadPoints);
        const polygonPoints = screenQuadPoints
          .map((point) => `${(point.x * 1920).toFixed(1)},${(point.y * 1080).toFixed(1)}`)
          .join(" ");
        screenQuadPolygon.setAttribute("points", polygonPoints);
        screenHandles.forEach((handle, index) => {
          const point = screenQuadPoints[index];
          if (!point) return;
          handle.style.left = `${(point.x * 100).toFixed(2)}%`;
          handle.style.top = `${(point.y * 100).toFixed(2)}%`;
        });
      };

      const setHandlePositionFromEvent = (event) => {
        if (draggingHandleIndex === null) return;
        const rect = screenStage.getBoundingClientRect();
        if (!rect.width || !rect.height) return;
        const x = clamp01((event.clientX - rect.left) / rect.width);
        const y = clamp01((event.clientY - rect.top) / rect.height);
        const points = [...screenQuadPoints];
        points[draggingHandleIndex] = { x, y };
        screenQuadPoints = points;
        syncScreenQuadUI();
      };

      screenHandles.forEach((handle) => {
        handle.addEventListener("pointerdown", (event) => {
          const idx = Number.parseInt(handle.dataset.handleIndex || "", 10);
          if (!Number.isInteger(idx)) return;
          event.preventDefault();
          draggingHandleIndex = idx;
          handle.setPointerCapture?.(event.pointerId);
        });
      });
      window.addEventListener("pointermove", (event) => {
        if (draggingHandleIndex === null) return;
        setHandlePositionFromEvent(event);
      });
      window.addEventListener("pointerup", () => {
        draggingHandleIndex = null;
      });
      window.addEventListener("pointercancel", () => {
        draggingHandleIndex = null;
      });
      screenQuadNormInput.addEventListener("change", () => {
        screenQuadPoints = parseQuad(screenQuadNormInput.value, screenStage.dataset.defaultQuad || "");
        syncScreenQuadUI();
      });
      window.addEventListener("resize", syncScreenQuadUI);
      syncScreenQuadUI();
    })();
  </script>
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
    app.pipeline = pipeline
    app.secret_key = "youtube-creator-assistant-dev"
    accept_attr = {
        "image": ".png,.jpg,.jpeg,.webp",
        "video": ".mp4,.mov,.m4v,.mkv,.avi,.mpeg,.mpg",
        "image_or_video": ".png,.jpg,.jpeg,.webp,.mp4,.mov,.m4v,.mkv,.avi,.mpeg,.mpg",
    }.get(settings.profile.visual_input_mode, ".png,.jpg,.jpeg,.webp")

    def _get_project(project_id: str | None):
        if not project_id:
            return None
        try:
            return pipeline.runtime.load_project(project_id)
        except FileNotFoundError:
            return None

    def _get_batch(batch_id: str | None):
        if not batch_id:
            return None
        try:
            return pipeline.load_candidate_batch(batch_id)
        except FileNotFoundError:
            return None

    def _get_thumbnail_candidates(project):
        if project is None:
            return []
        try:
            return pipeline.thumbnail_service.load_thumbnail_candidates(project)
        except Exception:
            return []

    def _get_selected_thumbnail_candidates(project):
        if project is None:
            return []
        try:
            return pipeline.thumbnail_service.load_selected_thumbnail_candidates(project)
        except Exception:
            return []

    @app.get("/")
    def index():
        current_id = request.args.get("project_id", "")
        batch_id = request.args.get("batch_id", "")
        project = _get_project(current_id)
        thumbnail_candidates = _get_thumbnail_candidates(project)
        selected_thumbnail_candidates = _get_selected_thumbnail_candidates(project)
        screen_replace_quad_norm = pipeline.get_screen_replace_quad_norm(current_id) if project is not None else settings.screen_replace.quad_norm
        screen_overlay_video_exists = False
        screen_overlay_metadata_exists = False
        if settings.screen_replace.overlay_builder.enabled:
            try:
                screen_overlay_video_exists = pipeline.screen_overlay_builder_service.output_video_path().exists()
                screen_overlay_metadata_exists = pipeline.screen_overlay_builder_service.metadata_path().exists()
            except Exception:
                screen_overlay_video_exists = False
                screen_overlay_metadata_exists = False
        return render_template_string(
            PAGE,
            settings=settings,
            projects=pipeline.runtime.list_projects(),
            project=project,
            candidate_batch=_get_batch(batch_id),
            thumbnail_candidates=thumbnail_candidates,
            selected_thumbnail_candidates=selected_thumbnail_candidates,
            selected_thumbnail_candidate_ids={str(item.get("candidate_id")) for item in selected_thumbnail_candidates},
            screen_replace_quad_norm=screen_replace_quad_norm,
            screen_overlay_video_exists=screen_overlay_video_exists,
            screen_overlay_metadata_exists=screen_overlay_metadata_exists,
            accept_attr=accept_attr,
        )

    @app.get("/projects/<project_id>")
    def project_detail(project_id: str):
        return redirect(url_for("index", project_id=project_id))

    @app.post("/projects")
    def create_project_route():
        uploaded = request.files.get("visual")
        if uploaded and uploaded.filename:
            incoming_dir = settings.paths.incoming_dir
            incoming_dir.mkdir(parents=True, exist_ok=True)
            filename = secure_filename(uploaded.filename) or "upload.png"
            temp_path = incoming_dir / filename
            uploaded.save(temp_path)
            if pipeline.should_generate_candidate_batch_from_uploaded_visual(temp_path):
                batch = pipeline.create_candidate_batch_from_visual(temp_path)
                flash(
                    f"Generated {len(batch.candidates)} {settings.profile.id} image candidates from the uploaded visual. Choose one to continue."
                )
                return redirect(url_for("index", batch_id=batch.batch_id))
            project = pipeline.create_project(temp_path)
        elif settings.replicate.enabled and settings.replicate.allow_candidate_generation:
            batch = pipeline.create_candidate_batch()
            flash(f"Generated {len(batch.candidates)} {settings.profile.id} image candidates. Choose one to continue.")
            return redirect(url_for("index", batch_id=batch.batch_id))
        else:
            flash(
                "Please upload a visual file."
                if settings.replicate.enabled
                else "Please upload a visual file, or use a profile with Replicate enabled."
            )
            return redirect(url_for("index"))
        return redirect(url_for("index", project_id=project.project_id))

    @app.post("/candidate-batches/<batch_id>/select")
    def select_candidate_route(batch_id: str):
        candidate_id = (request.form.get("candidate_id") or "").strip()
        if not candidate_id:
            flash("Please choose a candidate image.")
            return redirect(url_for("index", batch_id=batch_id))
        project = pipeline.create_project_from_candidate(batch_id, candidate_id)
        flash(f"Candidate selected. The {settings.profile.id} project has been created.")
        return redirect(url_for("index", project_id=project.project_id))

    @app.post("/projects/<project_id>/titles")
    def generate_titles_route(project_id: str):
        pipeline.generate_titles(project_id)
        return redirect(url_for("index", project_id=project_id))

    @app.post("/projects/<project_id>/regenerate-video")
    def regenerate_render_video_route(project_id: str):
        try:
            project = pipeline.regenerate_project_render_video(project_id)
            flash("Render video regenerated.")
            return redirect(url_for("index", project_id=project.project_id))
        except Exception as exc:
            flash(str(exc))
            return redirect(url_for("index", project_id=project_id))

    @app.post("/projects/<project_id>/screen-replace")
    def render_screen_replace_route(project_id: str):
        try:
            quad_norm = (request.form.get("quad_norm") or "").strip()
            project = pipeline.render_screen_replacement(project_id, quad_norm=quad_norm or None)
            flash("Screen replacement render completed.")
            return redirect(url_for("index", project_id=project.project_id))
        except Exception as exc:
            flash(str(exc))
            return redirect(url_for("index", project_id=project_id))

    @app.post("/projects/<project_id>/topaz-upscale")
    def topaz_upscale_route(project_id: str):
        try:
            project = pipeline.upscale_project_render_video_with_topaz(project_id)
            flash("Topaz upscale completed.")
            return redirect(url_for("index", project_id=project.project_id))
        except Exception as exc:
            flash(str(exc))
            return redirect(url_for("index", project_id=project_id))

    @app.post("/projects/<project_id>/render-screen-overlay")
    def render_screen_overlay_route(project_id: str):
        try:
            pipeline.render_screen_overlay_video()
            flash("Reusable screen overlay video rendered.")
        except Exception as exc:
            flash(str(exc))
        return redirect(url_for("index", project_id=project_id))

    @app.post("/projects/<project_id>/build")
    def build_package_route(project_id: str):
        titles = [title.strip() for title in request.form.getlist("titles") if title.strip()]
        max_selected_titles = max(1, int(settings.workflow.max_selected_titles or ContentPipeline.MAX_SELECTED_TITLES))
        if not titles:
            flash("Please choose at least one title.")
            return redirect(url_for("index", project_id=project_id))
        if len(titles) > max_selected_titles:
            flash(f"Please choose at most {max_selected_titles} titles.")
            return redirect(url_for("index", project_id=project_id))
        pipeline.build_package(project_id, titles)
        return redirect(url_for("index", project_id=project_id))

    @app.post("/projects/<project_id>/thumbnail-candidates")
    def generate_thumbnail_candidates_route(project_id: str):
        try:
            pipeline.generate_thumbnail_candidates(project_id)
            flash("Thumbnail candidates generated.")
        except Exception as exc:
            flash(str(exc))
        return redirect(url_for("index", project_id=project_id))

    @app.post("/projects/<project_id>/thumbnail-select")
    def select_thumbnail_candidates_route(project_id: str):
        candidate_ids = [
            item.strip()
            for item in request.form.getlist("thumbnail_candidates")
            if isinstance(item, str) and item.strip()
        ]
        if not candidate_ids:
            flash("Please choose at least one thumbnail candidate.")
            return redirect(url_for("index", project_id=project_id))
        try:
            pipeline.select_thumbnail_candidates(project_id, candidate_ids)
            flash("Thumbnail selection saved.")
        except Exception as exc:
            flash(str(exc))
        return redirect(url_for("index", project_id=project_id))

    @app.post("/projects/<project_id>/send-to-resolve")
    def send_to_resolve_route(project_id: str):
        try:
            project, result = pipeline.send_to_resolve(project_id)
            flash(result.message)
            return redirect(url_for("index", project_id=project.project_id))
        except Exception as exc:
            project = _get_project(project_id)
            if project is not None:
                project.resolve_last_error = str(exc)
                pipeline.runtime.save_project(project)
            flash(str(exc))
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

    @app.get("/candidate-batches/<batch_id>/files/<path:filename>")
    def candidate_batch_file(batch_id: str, filename: str):
        batch = _get_batch(batch_id)
        if batch is None:
            abort(404)
        target = (batch.batch_dir / filename).resolve()
        if batch.batch_dir.resolve() not in target.parents and target != batch.batch_dir.resolve():
            abort(404)
        if not target.exists() or not target.is_file():
            abort(404)
        return send_from_directory(target.parent, target.name)

    @app.get("/screen-overlay/file")
    def screen_overlay_file():
        try:
            target = pipeline.screen_overlay_builder_service.output_video_path()
        except Exception:
            abort(404)
        if not target.exists() or not target.is_file():
            abort(404)
        return send_from_directory(target.parent, target.name)

    @app.get("/screen-overlay/meta")
    def screen_overlay_metadata_file():
        try:
            target = pipeline.screen_overlay_builder_service.metadata_path()
        except Exception:
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
