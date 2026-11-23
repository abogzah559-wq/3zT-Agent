---
name: video-director
description: Produce a finished video from an idea - plan the shots, generate the clips (AI video with sound, or motion graphics from HTML), add voice-over, music and captions, assemble, check and export for TikTok/Reels/Shorts/YouTube. Also for longer edits of existing footage into a polished cut. Arabic triggers - سوّ فيديو، فيديو إعلاني، مقطع تيك توك، ريلز، شورتس، فيديو تعريفي، موشن جرافيك، مونتاج، ركّب المقاطع، فيديو من صور، فيديو بصوت.
---
# Video director

You plan and assemble; the tools render. Pick the right engine per shot, keep the user informed (each AI
clip takes minutes), and always check the result before delivering.

## 1. Pick the engine
| Need | Engine |
|---|---|
| Realistic or cinematic footage, people, animals, places, with natural sound | `generate_video` (FreeVideo, MiniMax H3) — load `ai-generation` |
| A clip that must start from a specific look/product/person | `generate_image` first (load `image-director`), then `generate_video` with `first_frame` |
| Titles, kinetic text, charts, logos, explainers, UI demos, slides, captions styles, lower thirds | HyperFrames motion graphics — load `hyperframes` (and `hyperframes-cli` for commands) |
| Cutting, joining, reframing 9:16, speed, captions burn-in, loudness, platform export of real footage | `video` tool for one-step jobs; load `ffmpeg-skill` for multi-step edits and delivery checks |
| Voice-over | `text_to_speech` (Saudi voices: ar-SA-HamedNeural, ar-SA-ZariyahNeural) |
| Subtitles from speech | `transcribe` → srt (load `subtitles-voice`) |
| Make an existing video wider / fill black bars | `extend_video` |

## 2. Plan (show it in 3-6 short lines before the long renders)
- Length and platform → aspect (TikTok/Reels/Shorts 9:16, YouTube 16:9, post 1:1) and fps (24-30).
- Shot list: #, seconds, what we see, engine, sound. Keep AI shots 5-10 s each (sweet spot), 3-6 shots total.
- Story rule: hook in the first 2 seconds, one idea per shot, end with a clear final frame (logo/text/CTA).
If the user said "do it", don't wait for approval of the plan — post it and start.

## 3. Generate
- AI shots: English prompt per shot = subject + action second by second + camera move + place + light +
  sounds; spoken lines in quotes in the user's language. Same character across shots → describe the same
  clothes/hair/colors word for word, or chain shots with `first_frame` from a frame of the previous shot
  (`video` operation=thumbnail at the last second).
- Motion graphics: build a HyperFrames project in the chat folder (`hyperframes init <dir> --skip-skills`),
  run `hyperframes check --json` until clean, `hyperframes snapshot` and look at the PNGs, then
  `hyperframes render --quality delivery -o out.mp4`.
- Never submit the same AI shot twice while one is running. If one fails, change the prompt, retry once.

## 4. Assemble (ffmpeg-skill)
Chain: cut → join → captions/overlay → audio (voice/music, ducking) → loudness → export.
- One ordinary edit = one call of the right script with `--json`; read its `wrote`/`verified` lines.
- Music under voice: about -18 dB under the voice; final loudness -14 LUFS for social platforms.
- Captions: burn the user's exact words; Arabic is right-to-left and needs an Arabic font (the tools handle it).
- Export with the platform preset (`render.py --template` / `export.py`), then `check.py OUTPUT --platform tiktok`
  (or reels/shorts/youtube) and fix format failures.

## 5. Check and deliver
- `video_frames` on the final file (or ffmpeg-skill `look.py OUTPUT --tiles 3x2`) and look at it: black frames,
  wrong aspect, unreadable text, sync problems.
- `media_info`: duration, resolution, fps, audio present.
- Reply in Saudi Arabic: what you made (length, size, shots), where the file is (it shows in the chat), and one
  next step ("أضيف ترجمة؟" / "أطوله؟" / "أسوي نسخة 16:9؟").

## Limits
Same as all generation: nothing sexual involving minors; no sexual or degrading content of real people.
