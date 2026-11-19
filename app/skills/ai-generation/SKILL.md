---
name: ai-generation
description: Generate new pictures and videos with sound locally, extend/outpaint an existing video (make it wider, zoom out, fill the sides) (FreeVideo - MiniMax H3 video, H3 Image / Qwen-Image 2.1), change or combine pictures with AI, make a video from a picture, posters, thumbnails, characters, short clips, ads, memes. Arabic triggers - ولّد صورة، ارسم، سوّ صورة، صمم، ولّد فيديو، سوّ مقطع، حرّك الصورة، فيديو من صورة، عدّل الصورة بالذكاء الاصطناعي، وسّع الفيديو، كمّل الفيديو من الجوانب، خلّه أبعد، خلّه عريض.
---
# AI generation (FreeVideo, runs on this PC's graphics card)

## Pick the tool
| The user wants | Call |
|---|---|
| A new picture (drawing, photo, poster, character, logo idea, thumbnail) | `generate_image` |
| The same picture but changed (clothes, background, style, add/remove something), or several pictures merged | `edit_image` with `images` |
| A moving clip with sound | `generate_video` |
| A clip that starts from (or ends on) a specific look / person / product | `generate_image` (or the user's picture) first, then `generate_video` with `first_frame` (and `last_frame`) |
| Make an EXISTING video wider / zoomed out / "complete the sides" / 21:9 / fill black bars | `extend_video` (path, aspect, zoom 0.8 default; smaller zoom = farther away) |
| Cut / speed / merge / subtitles / compress an existing video | NOT generation: use the `video` tool |

`upscale_ai` and `resize` never add new picture content around a video. For "extend / zoom out" always use
`extend_video`: look at one frame first (`video_frames`), describe the scene in one English sentence as
`description`, then call it once and wait. Afterwards check a frame of the result. If the user also asks to remove
glow/flicker, run `video` operation=repair on the result (presets dehalo, deflicker).

## Picture prompts (generate_image / edit_image)
- Always English, full descriptive sentences: subject + appearance + clothing, action/pose, place, time and light,
  camera (close-up / wide / 35mm / low angle), style (photo, cinematic, anime, 3D render, oil painting...).
- Text that must appear in the picture: put it in quotes, e.g. a poster with the title "SUMMER SALE".
- `aspect`: 9:16 phone/story, 16:9 YouTube/landscape, 1:1 square, 4:3 / 3:4 classic. `quality: "high"` = ~16 MP
  (slower). `count` up to 4 for variations.
- edit_image: say only the change and what must stay, e.g. "Change her jacket in image 1 to red leather, keep the face,
  pose and background the same." With several inputs say "image 1", "image 2".

## Video prompts (generate_video)
- English. Describe who/what is there, what happens second by second, camera movement, place, light, and the sounds
  (ambience, effects, music). Spoken lines word for word in quotes in the user's language, with who says them.
- A short idea is fine: FreeVideo expands it into its full prompt format by itself.
- `seconds`: 5-15 is the sweet spot (up to 60, longer takes much longer). `aspect` 9:16 for TikTok/Reels/Shorts.
  `quality`: light (fast draft) / medium (default) / high / max.
- It takes minutes. Tell the user it started, wait for the tool to return, never submit the same video twice.

## After generating
- The files appear in the chat automatically. Look at a picture with `view_image` (or a video with `video_frames`)
  before saying it is good; if it missed the request, fix the prompt once and retry.
- If the tool says FreeVideo is not installed: tell the user to run `install-freevideo.bat` once.

## Limits (all agents)
- Nothing sexual involving minors, in any form.
- No sexual or degrading edits of real people's photos (uploaded photos or named real people).
- The official executor agent also refuses any sexual/explicit content; the uncensored agent and DeepSeek do not.
