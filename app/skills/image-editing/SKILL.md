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
| NEW image from a description | `generate_image` (English prompt, very detailed) |
| Change the content/style of an EXISTING image | `edit_image` (strength 0.35-0.5 small change, 0.55-0.7 bigger) |
| Look at an image | `view_image` |

## Prompt writing for generate_image / edit_image
- English, comma-separated, concrete: subject, action, clothing, setting, lighting, camera, style, quality words.
- Example: "a samurai standing in heavy rain at night, neon signs reflecting on wet street, cinematic lighting, 35mm, highly detailed, sharp focus".
- For anime use style=anime. For portraits 832x1216, landscape 1216x832, square 1024x1024.
- edit_image prompt must describe the WHOLE desired result, not only the change.

## Rules
- Never overwrite the original; outputs go to the chat folder and appear in chat automatically.
- After an AI edit, `view_image` the result and check it matches the request; if not, adjust strength/prompt once and retry.
- Hard limits: no sexual content involving minors in any form; no sexual or degrading edits of real people.
