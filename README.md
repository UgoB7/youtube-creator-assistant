# youtube-creator-assistant

A modular workspace for assisting YouTube content creation across multiple configurable workflows.

This first version focuses on an image-first workflow and is built to scale:

- one shared core pipeline
- profile-specific YAML configs
- reusable features for titles, audio planning, themes, descriptions, and thumbnails
- isolated runtime outputs
- no dependency on the legacy `yt/` workspace at runtime

## Current MVP

For the current image-first workflow, the app can:

- take an input image
- generate title candidates with OpenAI
- select and copy audio tracks from local psalm and gospel libraries
- generate themes
- generate `chapters.txt`
- generate `yt_video_description.txt`
- generate a YouTube thumbnail under 2 MB

## Project layout

```text
youtube-creator-assistant/
  configs/profiles/         # profile YAML files
  assets/audio/             # local audio libraries
  runtime/                  # generated project outputs
  src/youtube_creator_assistant/
    app/                    # CLI and Flask UI
    core/                   # config, models, pipeline, runtime
    features/               # reusable domain features
    profiles/               # profile definitions
    providers/              # external integrations
  tests/
```

## Install

```bash
cd /Users/bellanca/Documents/youtube-creator-assistant
python3 -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
```

## Configure

1. Copy `.env.example` to `.env`
2. Set `OPENAI_API_KEY`
3. Use the default workflow config at `configs/profiles/vibes.yaml`

## CLI

Create a project from an image:

```bash
yca init-project --config configs/profiles/vibes.yaml --visual /path/to/image.png
```

Generate titles:

```bash
yca generate-titles --config configs/profiles/vibes.yaml --project-id <project_id>
```

Build the package after choosing a title:

```bash
yca build-package --config configs/profiles/vibes.yaml --project-id <project_id> --title "Chosen title"
```

One-shot helper:

```bash
yca run --config configs/profiles/vibes.yaml --visual /path/to/image.png
```

## Web UI

```bash
yca-web --config configs/profiles/vibes.yaml
```

The UI supports:

- uploading an image
- generating title candidates
- selecting a title
- building the final package

## Notes

- Large audio libraries are copied locally into `assets/audio/` but ignored by Git.
- Additional workflow configs are already scaffolded for future expansion.
