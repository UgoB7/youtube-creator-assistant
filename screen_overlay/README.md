# Screen Overlay Renderer

Deterministic Remotion project used to build the reusable screen-replacement overlay video.
What you preview in Remotion Studio is the same composition exported for YCA.

## Setup

```bash
cd screen_overlay
npm install
```

## Local assets

Put your local source assets in:

```text
assets/screen_replace/source
```

Expected names follow the old LoFi convention:

- `video1.mp4` or another supported video extension
- `current_video_16x9.png`
- `channel_avatar.png` or `.jpg`
- `im1` to `im4`
- `yt.png`
- `spotify.png`
- optional `screen_overlay_props.local.json`

The synchronized Remotion public assets live in:

```text
screen_overlay/public/ecran
```

They are regenerated automatically and ignored by Git.

## Render from YCA

```bash
yca render-screen-overlay --config configs/profiles/lofi.yaml
```

Output default:

```text
assets/screen_replace/lofi_overlay.local.mp4
```

The metadata companion file is written next to it as:

```text
assets/screen_replace/lofi_overlay.local.mp4.meta.json
```

## Manual Remotion commands

```bash
cd screen_overlay
npm run studio
```

The YCA render path uses the same composition via the Python overlay builder.
