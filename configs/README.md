# Config Strategy

This repository separates profile configuration into two layers:

1. Public profile YAML in [`configs/profiles/`](./profiles)
2. Local private text assets in `configs/local/` for prompts, examples, and other high-value wording

The goal is to keep the repo clean and shareable while protecting the parts of a workflow that can be a decisive competitive advantage.

## Why This Split Exists

Some configuration is safe and useful to keep in Git:

- profile ids
- runtime paths
- counts
- booleans
- rendering settings
- general workflow structure

Some configuration is often more sensitive:

- prompt engineering instructions
- title example corpora
- thumbnail concept prompts
- description prompts
- profile-specific wording that materially drives output quality

Those high-value text blocks can live in `configs/local/`, which is ignored by Git.

## How It Works

The config loader supports a small include mechanism for text fields:

```yaml
thumbnail:
  idea_prompt:
    $include_text: ../local/profiles/enchanted_melodies/thumbnail_idea_prompt.txt
```

When `load_settings(...)` reads the profile YAML, it replaces this object with the exact contents of the referenced text file.

That means you can keep long prompts in dedicated local files instead of storing them directly in the public YAML.

## Recommended Structure

Use this pattern:

```text
configs/
  profiles/
    lofi.yaml
    enchanted_melodies.yaml
  local/
    profiles/
      lofi/
        visual_system_prompt.txt
        visual_user_prompt.txt
        visual_variation_prompt.txt
        image_prompt_prefix.txt
      enchanted_melodies/
        thumbnail_idea_prompt.txt
        dynamic_intro_prompt.txt
```

`configs/local/` is ignored by Git, but its folder structure is preserved with `.gitkeep` files.

## What To Keep In Public YAML

Keep these in the tracked profile YAML when possible:

- numeric settings like `count`, `fps`, `duration`
- switches like `enabled`, `debug`, `include_audio_context`
- model names
- aspect ratios and resolutions
- path wiring
- profile metadata

These are usually implementation settings, not strategic wording.

## What To Move To Local Files

Good candidates for `configs/local/`:

- `thumbnail.idea_prompt`
- `description.dynamic_intro_prompt`
- `openai.title_examples_input`
- `openai.devotional_examples_input`
- `openai.title_generation.prompt_addendum`
- `openai.theme_generation.prompt_addendum`
- `replicate.image_prompt_prefix`
- `replicate.visual_prompt_generation.system_prompt`
- `replicate.visual_prompt_generation.user_prompt`
- `replicate.visual_prompt_generation.variation_prompt`

## How To Add Your Own Private Parameters

If you want to personalize a profile with your own wording:

1. Create a local text file under `configs/local/profiles/<profile>/`
2. Put your private text in that file
3. Reference it from the public profile YAML with `$include_text`

Example:

```yaml
openai:
  title_generation:
    prompt_addendum:
      $include_text: ../local/profiles/lofi/title_prompt_addendum.txt
```

Example file:

```text
Match the atmosphere of a calm Christian lofi channel.
Favor short, memorable YouTube titles that feel peaceful, prayerful, and study-friendly.
Blend rest, prayer, focus, worship, Scripture, night, and peace when relevant to the current visual.
```

## Rule Of Thumb

Use public YAML for structure.

Use local text includes for wording.

If a value mainly controls behavior, keep it in the public profile.
If a value mainly encodes creative know-how, move it to `configs/local/`.

## Team Workflow

If someone else wants their own private variations:

1. They keep the same public profile YAML shape
2. They create their own local files under `configs/local/`
3. They update only the included text files on their machine

This keeps the shared config stable while allowing each person to evolve their own prompts and prompt libraries independently.
