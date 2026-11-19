---
name: video-editing
description: Edit videos - cut/trim, merge, compress for Discord/WhatsApp/TikTok, resize, crop, vertical 9:16, speed, reverse, GIF, audio replace/extract, fps change, watermark/logo, text. Arabic triggers - قص، دمج، ضغط، تصغير الحجم، تسريع، تبطيء، تحويل، فيديو عمودي، تيك توك.
---
# Video editing

## Golden rules
1. ALWAYS start with `media_info` on the input to know duration, resolution, fps, codecs.
2. Prefer the `video` tool (one operation per call). It writes the result into the chat folder and shows it to the user automatically. Use raw `ffmpeg` only for things the `video` tool cannot do.
3. Never overwrite the input. Every output gets a new name.
4. After finishing, verify the output with `media_info` (duration/resolution as expected) and tell the user what changed in one or two lines.
5. If one approach fails twice, switch approach; do not repeat the same failing command.
6. "Extend / complete the sides / zoom out / make it wider or 21:9 with real content" is NOT editing: use
   `extend_video` (see the ai-generation skill). Upscaling or resizing never adds new content.

## `video` tool operations (cheat sheet)
| Goal | operation | key params |
|---|---|---|
| Cut a part | trim | start, end (seconds or HH:MM:SS) |
| Smaller file for Discord (≤10MB) / WhatsApp | compress | target_mb (e.g. 9.5) or crf (lower = better, 18-28) |
| Change resolution | resize | width or height (other side auto) |
| Vertical TikTok 9:16 | vertical | mode: blur (blurred background) or crop |
| Crop area | crop | x, y, width, height |
| Faster / slower | speed | factor (2 = twice as fast, 0.5 = slow motion) |
| Reverse | reverse | — |
| Join clips | merge | inputs: [paths] (same resolution is best) |
| Make GIF | gif | start, end, width, fps |
| Extract audio | extract_audio | format: mp3/wav |
| Replace music | replace_audio | audio |
| Remove sound | mute | — |
| Smooth motion / 60fps | fps | fps: 60, smooth: true (motion interpolation, slow but smooth) |
| Burn subtitles | burn_subtitles | subtitles: path to .srt |
| Add logo/watermark | overlay | image, position (top-left, top-right, bottom-left, bottom-right) |
| Rotate | rotate | degrees: 90, 180, 270 |
| Louder / even audio | normalize_audio | — |
| Thumbnail | thumbnail | time |

## Raw ffmpeg recipes (when needed)
- Precise cut with re-encode: `-ss 00:00:05 -to 00:00:12 -i "in.mp4" -c:v libx264 -crf 18 -preset medium -c:a aac "out.mp4"`
- NVIDIA fast encode (RTX GPU): replace `-c:v libx264 -crf 18` with `-c:v h264_nvenc -preset p5 -cq 19`
- Text on video: `-vf "drawtext=fontfile='C\:/Windows/Fonts/arial.ttf':text='Hello':x=(w-tw)/2:y=h-80:fontsize=48:fontcolor=white:box=1:boxcolor=black@0.5"`
  For Arabic text use `fontfile='C\:/Windows/Fonts/tahoma.ttf'` and put the text in a UTF-8 file with `textfile=`.
- Fade in/out: `-vf "fade=t=in:st=0:d=1,fade=t=out:st=9:d=1"`
- Picture-in-picture: `-i main.mp4 -i small.mp4 -filter_complex "[1]scale=iw/3:-2[s];[0][s]overlay=W-w-20:20"`
- Concatenate different clips: re-encode each to same size/fps first, then the `merge` operation.

## Quality defaults
- H.264 `-crf 18` = visually lossless; `-crf 23` = good; `-crf 28` = small.
- Always `-pix_fmt yuv420p -movflags +faststart` for phone/web compatibility.
- Keep the original fps unless asked.
