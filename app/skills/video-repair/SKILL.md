---
name: video-repair
description: Fix damaged or ugly video - AI artifacts, strange glows/halos, flicker, noise, banding, blur, shaky footage, low resolution, choppy motion, wrong colors, over-sharpening. Arabic triggers - تشوهات، توهج، وميض، تشويش، نويز، تحسين جودة، ترقية، رفع الدقة، اهتزاز، ألوان.
---
# Video repair / enhancement

## Step 1 - Diagnose (never skip)
1. `media_info` on the file.
2. `video_frames` with count 8 to SEE the problem. Describe exactly what you see: where (left/center/right), what kind (glow/halo around edges, colored blotches, flicker between frames, grain, blocky compression, blur, banding in gradients, shake).
3. If the problem is only in one moment, find the time range from the frames and work on that range.

## Step 2 - Pick the fix (use the `video` tool `enhance` operation or `repair` presets)
| Problem | Fix (video tool) | Raw ffmpeg filter |
|---|---|---|
| Flicker / brightness pumping between frames | operation=repair, preset=deflicker | `deflicker=mode=pm:size=7` |
| Grain / noise | preset=denoise | `hqdn3d=3:3:6:6` (light) or `nlmeans=s=3` (strong, slow) |
| Temporal shimmering / AI boiling textures | preset=temporal | `atadenoise=s=9,tmix=frames=3:weights='1 2 1'` |
| Halos / glow around edges (over-sharpened or AI upscaled) | preset=dehalo | `gblur=sigma=0.6,unsharp=5:5:-0.3` then mild `eq` |
| Color banding in skies/gradients | preset=deband | `deband=1thr=0.02:2thr=0.02:3thr=0.02:blur=1` |
| Blocky compression | preset=deblock | `deblock=filter=strong:block=8` |
| Soft / blurry | preset=sharpen | `unsharp=5:5:0.8:3:3:0.4` or `cas=0.6` |
| Shaky | preset=stabilize | (vidstab if available, else `deshake`) |
| Dull / wrong colors | preset=color | `eq=contrast=1.06:saturation=1.12:gamma=0.98` |
| Low resolution | operation=upscale_ai (Real-ESRGAN per frame, best quality, slow) or operation=resize with lanczos (fast) |
| Choppy motion | operation=fps fps=60 smooth=true |

Combine presets with `presets: ["deflicker","denoise","dehalo"]` in one pass (order matters: deflicker → denoise → dehalo/deband → sharpen → color).

## Step 3 - Verify
- Run `video_frames` on the OUTPUT at the same moments and compare with the original. Say honestly if it improved.
- Show the result in chat (the video tool does it automatically).

## Honest limits (tell the user when relevant)
- Filters can soften glows, flicker and noise a lot, but they cannot invent missing details or redraw objects.
- Redrawing every frame with image AI (img2img) produces flicker - do not do that for videos. For a single bad frame you can export it, fix it with `edit_image`, and put it back.
- `edit_image` and `generate_image` work on IMAGES only, never pass a video to them.
