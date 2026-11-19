"""Video outpainting: make an existing video wider / "zoom out" so the new parts look like they were always there.

How it works (all local, through FreeVideo):
1. A few keyframes are taken from the original video.
2. Each keyframe is placed small in the middle of the new, wider canvas; the border is pre-filled with a blurred
   stretch of the frame (colour hints) and the picture model repaints only that border. Later keyframes get the
   first finished one as a reference so the surroundings stay the same.
3. MiniMax H3 animates a new video that passes through those keyframes (first / middle / last frames).
4. The ORIGINAL video is laid back over the middle with soft edges, so the centre stays 100% original
   (full resolution and frame rate) and only the new border comes from the generated video.
"""
import shutil
import tempfile
from pathlib import Path

import freevideo
import videotools

# generation size (multiples of 32, ~1 MP) and the aspect it stands for
SIZES = {"21:9": (1568, 672), "16:9": (1344, 768), "9:16": (768, 1344), "1:1": (1024, 1024),
         "4:3": (1152, 864), "3:4": (864, 1152)}
FINAL_SHORT = 1080              # final short side in pixels


def _even(v):
    v = int(round(v))
    return v - (v % 2)


def _ff(args, dur, progress, label):
    code, log = videotools.run_ffmpeg(args, dur, progress, label)
    if code != 0:
        raise RuntimeError(f"ffmpeg فشل ({label}): {log[-500:]}")


def _layout(src_w, src_h, can_w, can_h, zoom):
    """Size and position of the original inside a canvas (centred)."""
    w = min(zoom * can_h * src_w / src_h, zoom * can_w)
    h = w * src_h / src_w
    w, h = _even(w), _even(h)
    return w, h, (can_w - w) // 2 // 2 * 2, (can_h - h) // 2 // 2 * 2


def describe(frame, progress, cancel):
    """One English sentence about the scene, from FreeVideo's own vision model (None if it is not available)."""
    try:
        file = freevideo.upload(frame)
        spec = {"kind": "vlm", "max_tokens": 160, "label": "3zT extend",
                "questions": [{"text": "Describe this frame for an artist who must extend it outward: art style, setting, "
                                       "background, colours and lighting, in 2 short English sentences. No guessing "
                                       "beyond what is visible.", "images": [{"file": file}]}]}
        res = freevideo._check(freevideo.wait(freevideo.submit(spec)["id"], progress, cancel, "يتأمل الفيديو"), "الوصف")
        ans = (res.get("answers") or [""])[0]
        if isinstance(ans, dict):
            ans = ans.get("text") or ans.get("answer") or ""
        ans = " ".join(str(ans).split())[:600]
        return ans or None
    except freevideo.FVError as e:
        if "انلغى" in str(e):
            raise
        return None


def extend_video(args, src, out_dir, cancel, progress):
    src = Path(src)
    info = videotools._info(src)
    if not info["w"] or not info["dur"]:
        raise RuntimeError("ما قدرت أقرأ الفيديو.")
    dur = info["dur"]
    if dur > 60:
        raise RuntimeError("الفيديو أطول من 60 ثانية. قصّه لمقاطع (video operation=trim) ووسّع كل مقطع لحاله.")
    aspect = str(args.get("aspect") or "21:9")
    if aspect not in SIZES:
        aspect = "21:9"
    gw, gh = SIZES[aspect]
    try:
        zoom = float(args.get("zoom") or 0.8)
    except (TypeError, ValueError):
        zoom = 0.8
    zoom = max(0.5, min(0.95, zoom))
    desc = str(args.get("description") or "").strip()[:600]
    quality = str(args.get("quality") or "medium")
    quality = quality if quality in freevideo.QUALITY else "medium"

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="3zt_ext_", dir=str(out_dir)))
    try:
        # ---- 1-2: keyframes, extended by the picture model
        last_t = max(0.0, dur - 1.0 / max(info["fps"], 1))
        times = [0.0, dur * 0.25, dur * 0.5, dur * 0.75, last_t] if dur >= 3 else [0.0, last_t]
        cw, ch, cx, cy = _layout(info["w"], info["h"], gw, gh, zoom)
        first = work / "look.png"
        _ff(["-ss", f"{dur / 2:.3f}", "-i", str(src), "-frames:v", "1", "-vf", "scale=1280:-2", str(first)], 0,
            progress, "يطلّع فريم للوصف")
        seen = describe(first, progress, cancel)
        if seen:
            desc = seen                   # what is really in the video beats a guess written by the chat model
        scene = (f" The scene: {desc.rstrip('.')}." if desc else "")
        base_prompt = ("Outpaint image 1: it is ONE single continuous frame of a scene. The soft, smeared area around "
                       "the sharp centre is unfinished: paint it as more of the very same place, as if the camera had "
                       "pulled back. Continue every shape, wall, light, line and pattern that touches the edge of the "
                       "sharp area outward so there is no visible border, frame, seam or picture-in-picture."
                       + scene + " Same art style, line work, colours, darkness and lighting as the centre. Do not change "
                       "the sharp centre. No blur, no black bars, no vignette, no extra glow or bloom, no text, "
                       "no new characters, no sky or landscape unless the centre already shows one.")
        keys = []
        for i, t in enumerate(times):
            if cancel is not None and cancel.is_set():
                raise RuntimeError("انلغى.")
            frame, padded = work / f"f{i}.png", work / f"p{i}.png"
            _ff(["-ss", f"{t:.3f}", "-i", str(src), "-frames:v", "1", str(frame)], 0, progress,
                f"يطلّع الفريم {i + 1}/{len(times)}")
            px, py = cx, cy
            mode = "mirror" if px < cw and py < ch else "smear"
            _ff(["-i", str(frame), "-filter_complex",
                 f"[0]scale={cw}:{ch}:flags=lanczos,split=2[c][m];"
                 f"[m]pad={cw + 2 * px}:{ch + 2 * py}:{px}:{py},"
                 f"fillborders=left={px}:right={px}:top={py}:bottom={py}:mode={mode},"
                 f"scale={gw}:{gh},gblur=sigma=22[bg];"
                 f"[bg][c]overlay={cx}:{cy}", "-frames:v", "1", str(padded)], 0, progress, "يجهّز الإطار")
            spec = {"prompt": base_prompt, "width": gw, "height": gh, "count": 1, "images": [str(padded)]}
            if keys:
                spec["images"].append(str(keys[0]))
                spec["prompt"] = base_prompt + (" Image 2 is the same scene already extended: keep the surroundings "
                                                "identical to image 2, only the middle changes.")
            if args.get("seed") is not None:
                spec["seed"] = int(args["seed"])
            label_dir = work / f"k{i}"
            made = freevideo.generate_image(spec, label_dir, cancel,
                                            lambda s, i=i: progress(f"يوسّع الفريم {i + 1}/{len(times)}: {s}"))
            key = work / f"3zt-key-{i}-{label_dir.stat().st_mtime_ns % 10**9}{made[0].suffix}"
            shutil.copy2(made[0], key)        # unique upload names: FreeVideo stores inputs by file name
            keys.append(key)

        # ---- 3: animate through the keyframes
        progress("يرفع الفريمات لـ FreeVideo...")
        files = [freevideo.upload(k) for k in keys]
        media = {"first": {"file": files[0]}, "last": {"file": files[-1]}}
        if len(files) > 2:
            media["middle"] = [{"file": f, "at": round(max(1 / 24, min(dur - 1 / 24, t)), 3)}
                               for f, t in zip(files[1:-1], times[1:-1])]
        vprompt = ((desc + ". ") if desc else "") + (
            "The same shot as the keyframes, wider view. Static camera, no zoom, no cuts. Everything moves exactly "
            "as between the given frames. Same 2D art style and colours, no extra glow, no text, quiet ambience.")
        spec = {"prompt": vprompt, "seconds": round(max(1.625, dur), 3), "width": gw, "height": gh,
                "quality": quality, "media": media, "label": "3zT extend"}
        if args.get("seed") is not None:
            spec["seed"] = int(args["seed"])
        job = freevideo.submit(spec)
        result = freevideo._check(freevideo.wait(job["id"], progress, cancel, "يولّد الأطراف الجديدة"),
                                  "توليد الأطراف")
        url = (result.get("video") or {}).get("url")
        gen = freevideo.download(url, work / "gen.mp4")

        # ---- 4: original back in the middle, soft edges, at the original fps
        scale = FINAL_SHORT / min(gw, gh)
        fw, fh = _even(gw * scale), _even(gh * scale)
        ow, oh, ox, oy = _layout(info["w"], info["h"], fw, fh, zoom)
        feather = max(8, int(min(ow, oh) * 0.035))
        mask = work / "mask.png"
        _ff(["-f", "lavfi", "-i", f"color=white:s={ow}x{oh}", "-vf",
             f"format=gray,geq=lum='255*min(1\\,min(min(X\\,W-1-X)\\,min(Y\\,H-1-Y))/{feather})'",
             "-frames:v", "1", str(mask)], 0, progress, "يجهّز الدمج")
        fps = f"{info['fps']:.3f}"
        out = videotools._out(out_dir, src, f"extended_{aspect.replace(':', 'x')}", ".mp4")
        graph = (f"[0:v]scale={fw}:{fh}:flags=lanczos,fps={fps},tpad=stop_mode=clone:stop_duration=2,setsar=1[bg];"
                 f"[1:v]scale={ow}:{oh}:flags=lanczos,fps={fps},format=yuva420p[fg0];"
                 f"[2:v]scale={ow}:{oh},format=gray[m];[fg0][m]alphamerge[fg];"
                 f"[bg][fg]overlay={ox}:{oy}:shortest=1,format=yuv420p[v]")
        audio = ["-map", "1:a?", "-c:a", "aac", "-b:a", "192k"]
        code, log = videotools._encode(["-i", str(gen), "-i", str(src), "-loop", "1", "-i", str(mask),
                                        "-filter_complex", graph, "-map", "[v]", *audio, "-t", f"{dur:.3f}"],
                                       out, dur, progress, "يدمج الأصل مع الأطراف", crf=16)
        if code != 0 or not out.exists() or out.stat().st_size == 0:
            raise RuntimeError(f"الدمج فشل: {log[-600:]}")
        # keep the extended keyframes next to the result so they can be reviewed
        kdir = out_dir / (out.stem + "_keyframes")
        kdir.mkdir(exist_ok=True)
        for i, k in enumerate(keys):
            shutil.copy2(k, kdir / f"key{i + 1}{Path(k).suffix}")
        return [out]
    finally:
        shutil.rmtree(work, ignore_errors=True)
