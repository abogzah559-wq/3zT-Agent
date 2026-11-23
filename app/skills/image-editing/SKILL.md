---
name: image-editing
description: Edit or create images - resize, crop, convert format, compress, rotate, remove background, upscale x2/x4, fix noise, change colors, add text, make collages/thumbnails, generate new images or redraw existing ones with AI. Arabic triggers - صورة، قص الصورة، تكبير، شيل الخلفية، تحويل صيغة، ضغط، توليد صورة، تعديل صورة، ثمنيل.
---
# Image editing

## Which tool
| Goal | Tool |
|---|---|
| Resize / crop / rotate / convert (png↔jpg↔webp) / compress / blur / sharpen / grayscale / text | `image` tool (operation=...) |
| Remove background → transparent PNG | `remove_background` |
| Upscale with detail (photos or anime) | `upscale_image` (scale 2 or 4, anime=true for drawings) |
| NEW image from a description | `generate_image` (English prompt, very detailed) — see the `ai-generation` skill |
| Change / combine EXISTING images with AI | `edit_image` (images: up to 4, prompt says the change) |
| Look at an image | `view_image` |

## Prompt writing for generate_image / edit_image
- Load the `image-director` skill for the full guide (brief → generate → inspect → fix). Short version: English, full sentences, concrete subject, setting,
  lighting, camera and style; any text to draw goes in quotes; aspect 9:16 for phone/portrait, 16:9 for landscape.

## Rules
- Never overwrite the original; outputs go to the chat folder and appear in chat automatically.
- After an AI edit, `view_image` the result and check it matches the request; if not, adjust the prompt once and retry.
- Hard limits: no sexual content involving minors in any form; no sexual or degrading edits of real people.
