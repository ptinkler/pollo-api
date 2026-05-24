# Pollo Ref (ref2video) Endpoint

## Overview

The `pollodanceref` model uses the ref2video endpoint to generate videos from reference images.
You provide one or more image references (up to 13) along with a prompt, and the model generates
a video incorporating those references.

## Project Setup for Ref Mode

To use the ref endpoint, create a project folder under `projects/` with:

### Required Files

- `prompt.txt` - The prompt describing what to generate

### Optional Reference Files

- `image_url.txt` - URL to a reference image (becomes first ref automatically)
- `subject_url.txt` - URL to a subject/character reference image (becomes second ref)
- `refs.txt` - Multiple refs, one per line: `name|url` or just `url`

## Example Project Structure

```
projects/my_ref_project/
├── prompt.txt          # "A cinematic dance scene in a studio"
├── image_url.txt       # https://example.com/style_ref.jpg
└── refs.txt            # (optional) multiple refs
```

### refs.txt format

```
character|https://example.com/character.jpg
style|https://example.com/style.jpg
background|https://example.com/bg.jpg
```

## Environment Variables

Set these in your `.env` file:

```bash
MODEL=pollodanceref
PROJECT=my_ref_project
POLLO_API_KEY=your_api_key

# Optional settings
ASPECT_RATIO=16:9            # portrait, landscape, or direct ratio
LENGTH=10                     # 4-15 seconds
RESOLUTION=720p               # 480p, 720p, or 1080p
GENERATE_AUDIO=true           # whether to generate audio
VIDEO_NUM=1                   # 1-4 videos to generate per request
```

## Usage

```bash
python -m img2vid.pollo
```

## Payload Structure

The ref2video endpoint accepts:

```json
{
  "input": {
    "prompt": "your prompt",
    "duration": 10,
    "resolution": "720p",
    "aspectRatio": "16:9",
    "generateAudio": true,
    "videoNum": 1,
    "refs": [
      {"type": "image", "name": "character", "image": "https://...", "order": 1},
      {"type": "image", "name": "style", "image": "https://...", "order": 2}
    ]
  }
}
```

### Refs Array

- 1-13 image reference objects
- Each ref has: `type` ("image"), `name` (max 20 chars), `image` (URL), `order` (>=1)
- Optional `avatarId` field

### Optional: imageMeta

Cropping/positioning metadata for refs (passed via API, not CLI).

## Metadata Database

All downloads are tracked in `data/metadata.db` (SQLite). This stores:
- Source URLs
- Local file paths
- Task IDs
- Model used
- Prompt used
- Additional metadata

You can query this database to find previous downloads or track video lineage.
