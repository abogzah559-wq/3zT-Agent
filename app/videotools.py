"""Reliable, pre-built video & image operations (ffmpeg / Real-ESRGAN) with live progress.

Small local models make many mistakes writing raw ffmpeg commands; these operations are tested
recipes the model only has to pick and parameterize.
"""
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import media
from config import NO_WINDOW

VIDEO_OPS = ["trim", "compress", "resize", "vertical", "crop", "speed", "reverse", "merge", "gif",
             "extract_audio", "replace_audio", "mute", "fps", "burn_subtitles", "overlay", "rotate",
             "normalize_audio", "thumbnail", "repair", "upscale_ai"]
REPAIR_PRESETS = ["deflicker", "denoise", "strong_denoise", "temporal", "dehalo", "deband", "deblock",
                  "sharpen", "color", "stabilize"]
IMAGE_OPS = ["resize", "crop", "rotate", "flip", "convert", "compress", "grayscale", "blur", "sharpen",
             "brightness", "denoise"]

_caps = {}


def _ffmpeg_has(kind, name):
    key = (kind, name)
    if key not in _caps:
        try:
            out = subprocess.run(["ffmpeg", "-hide_banner", f"-{kind}"], capture_output=True, text=True,
                                 timeout=20, creationflags=NO_WINDOW).stdout
            _caps[key] = re.search(rf"\s{re.escape(name)}\s", out) is not None
        except Exception:
            _caps[key] = False
    return _caps[key]


def _t(v):
    """Seconds from '75', '1:15', '00:01:15.5'."""
    if v is None or v == "":
        return None
    s = str(v).strip()
    if ":" in s:
        parts = [float(x) for x in s.split(":")]
        sec = 0.0
        for p in parts:
            sec = sec * 60 + p
        return sec
    return float(s)


def _out(out_dir, src, tag, ext=None):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = re.sub(r"[^\w\-. ]", "_", Path(src).stem)[:60]
    p = out_dir / f"{stem}_{tag}{ext or Path(src).suffix or '.mp4'}"
    i = 2
    while p.exists():
        p = out_dir / f"{stem}_{tag}_{i}{ext or Path(src).suffix or '.mp4'}"
        i += 1
    return p


def _venc(crf=18):
    """Video encoder args: NVENC on NVIDIA GPUs (fast), else x264."""
    if _ffmpeg_has("encoders", "h264_nvenc") and not _caps.get("nvenc_broken"):
        return ["-c:v", "h264_nvenc", "-preset", "p5", "-rc", "vbr", "-cq", str(crf + 1), "-b:v", "0",
                "-pix_fmt", "yuv420p"]
    return ["-c:v", "libx264", "-preset", "medium", "-crf", str(crf), "-pix_fmt", "yuv420p"]


def _x264(crf=18):
    return ["-c:v", "libx264", "-preset", "medium", "-crf", str(crf), "-pix_fmt", "yuv420p"]


def run_ffmpeg(args, duration, progress, label, cwd=None, timeout=4 * 3600):
    """Run ffmpeg with a live percentage. Returns (code, tail_of_log)."""
    cmd = ["ffmpeg", "-hide_banner", "-nostdin", "-y", "-loglevel", "error", "-progress", "pipe:1", *args]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8",
                         errors="replace", creationflags=NO_WINDOW, cwd=cwd)
    err_lines = []
    import threading

    def read_err():
        for line in p.stderr:
            err_lines.append(line.rstrip())
            del err_lines[:-40]

    threading.Thread(target=read_err, daemon=True).start()
    t0, last = time.time(), 0
    for line in p.stdout:
        if line.startswith("out_time_ms=") or line.startswith("out_time_us="):
            try:
                cur = int(line.split("=")[1]) / 1e6
            except ValueError:
                continue
            if time.time() - last > 0.7:
                last = time.time()
                el = int(time.time() - t0)
                if duration and duration > 0:
                    pct = max(0, min(99, int(cur * 100 / duration)))
                    eta = int(el * (100 - pct) / pct) if pct > 2 else None
                    progress(f"{label} — {pct}%" + (f" · باقي ~{eta} ث" if eta else "") + f"|{pct}")
                else:
                    progress(f"{label} — {cur:.0f} ث معالجة · {el} ث")
        if time.time() - t0 > timeout:
            p.kill()
            break
    p.wait()
    time.sleep(0.1)
    return p.returncode, "\n".join(err_lines[-12:])


def _encode(args_before_out, out, duration, progress, label, crf=18, cwd=None, extra_out=None):
    """Encode with NVENC, falling back to x264 if NVENC fails."""
    venc = _venc(crf)
    code, log = run_ffmpeg([*args_before_out, *venc, *(extra_out or []), "-movflags", "+faststart", str(out)],
                           duration, progress, label, cwd)
    if (code != 0 or not Path(out).exists()) and "nvenc" in " ".join(venc):
        _caps["nvenc_broken"] = True
        code, log = run_ffmpeg([*args_before_out, *_x264(crf), *(extra_out or []), "-movflags", "+faststart",
                                str(out)], duration, progress, label + " (CPU)", cwd)
    return code, log


def _info(src):
    info = media.probe(src)
    v = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), {})
    a = next((s for s in info.get("streams", []) if s.get("codec_type") == "audio"), None)
    try:
        n, d = (v.get("avg_frame_rate") or "30/1").split("/")
        fps = float(n) / float(d) if float(d) else 30.0
    except Exception:
        fps = 30.0
    return {"w": int(v.get("width") or 0), "h": int(v.get("height") or 0), "fps": fps or 30.0,
            "dur": float(info.get("format", {}).get("duration") or 0), "audio": a is not None}


def _atempo(f):
    parts = []
    while f > 2.0:
        parts.append("atempo=2.0")
        f /= 2.0
    while f < 0.5:
        parts.append("atempo=0.5")
        f /= 0.5
    parts.append(f"atempo={f:.4f}")
    return ",".join(parts)


def repair_chain(presets, info):
    order = REPAIR_PRESETS
    chosen = [p for p in order if p in presets]
    f = []
    for p in chosen:
        if p == "deflicker":
            f.append("deflicker=mode=pm:size=7")
        elif p == "denoise":
            f.append("hqdn3d=2.5:2.5:5:5")
        elif p == "strong_denoise":
            f.append("nlmeans=s=3.5:p=7:r=11" if _ffmpeg_has("filters", "nlmeans") else "hqdn3d=5:4:9:8")
        elif p == "temporal":
            f.append("atadenoise=0a=0.04:0b=0.08:1a=0.04:1b=0.08:2a=0.04:2b=0.08:s=9")
        elif p == "dehalo":
            f.append("gblur=sigma=0.7,unsharp=5:5:0.35:5:5:0")
        elif p == "deband":
            f.append("deband=1thr=0.02:2thr=0.02:3thr=0.02:blur=1")
        elif p == "deblock":
            f.append("deblock=filter=strong:block=8" if _ffmpeg_has("filters", "deblock") else "pp=hb/vb/dr")
        elif p == "sharpen":
            f.append("cas=0.5" if _ffmpeg_has("filters", "cas") else "unsharp=5:5:0.7:3:3:0.3")
        elif p == "color":
            f.append("eq=contrast=1.05:saturation=1.12:gamma=0.98")
        elif p == "stabilize" and not _ffmpeg_has("filters", "vidstabtransform"):
            f.append("deshake")
    return ",".join(f), "stabilize" in chosen and _ffmpeg_has("filters", "vidstabtransform")


def video(args, src, out_dir, progress, cancel, realesrgan_exe=None):
    """Returns (output_paths, message)."""
    op = (args.get("operation") or "").strip().lower()
    if op not in VIDEO_OPS:
        raise ValueError(f"العملية غير معروفة. المتاح: {', '.join(VIDEO_OPS)}")
    src = Path(src)
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    if op != "merge" and not src.is_file():
        raise FileNotFoundError(f"ما لقيت الفيديو: {src}")
    if op != "merge" and src.suffix.lower() in media.IMAGE_EXT:
        raise ValueError("هذي صورة مو فيديو؛ استخدم أداة image")
    info = _info(src) if op != "merge" else None
    dur = info["dur"] if info else 0
    audio = ["-c:a", "aac", "-b:a", "192k"]
    lab = {"trim": "يقص", "compress": "يضغط", "resize": "يغيّر المقاس", "vertical": "يحوّله عمودي",
           "crop": "يقص الإطار", "speed": "يغيّر السرعة", "reverse": "يعكس", "merge": "يدمج", "gif": "يسوي GIF",
           "extract_audio": "يطلّع الصوت", "replace_audio": "يركّب الصوت", "mute": "يشيل الصوت",
           "fps": "يغيّر الفريمات", "burn_subtitles": "يحرق الترجمة", "overlay": "يحط الشعار",
           "rotate": "يدوّر", "normalize_audio": "يضبط الصوت", "thumbnail": "يطلّع صورة",
           "repair": "يصلّح الفيديو", "upscale_ai": "يرفع الدقة بالذكاء"}[op]

    if op == "trim":
        s, e = _t(args.get("start")) or 0.0, _t(args.get("end"))
        if e is not None and e <= s:
            raise ValueError("النهاية لازم تكون بعد البداية")
        out = _out(out_dir, src, "cut")
        pre = ["-ss", f"{s:.3f}"] + (["-to", f"{e:.3f}"] if e is not None else []) + ["-i", str(src)]
        code, log = _encode(pre + audio, out, (e or dur) - s, progress, lab)
    elif op == "compress":
        out = _out(out_dir, src, "small", ".mp4")
        target = float(args.get("target_mb") or 0)
        if target > 0 and dur > 0:
            a_kbps = 96 if info["audio"] else 0
            kbps = max(150, int(target * 8192 * 0.94 / dur) - a_kbps)
            scale = []
            if kbps < 1500 and info["h"] > 720:
                scale = ["-vf", "scale=-2:720:flags=lanczos"]
            elif kbps < 700 and info["h"] > 480:
                scale = ["-vf", "scale=-2:480:flags=lanczos"]
            for attempt in range(2):
                vargs = ["-c:v", "libx264", "-preset", "medium", "-b:v", f"{kbps}k", "-maxrate", f"{int(kbps * 1.4)}k",
                         "-bufsize", f"{kbps * 2}k", "-pix_fmt", "yuv420p"]
                code, log = run_ffmpeg(["-i", str(src), *scale, *vargs, "-c:a", "aac", "-b:a", "96k",
                                        "-movflags", "+faststart", str(out)], dur, progress, lab)
                if code != 0 or not out.exists() or out.stat().st_size <= target * 1048576:
                    break
                kbps = int(kbps * 0.82)
                out.unlink(missing_ok=True)
        else:
            crf = int(args.get("crf") or 26)
            code, log = _encode(["-i", str(src), *audio], out, dur, progress, lab, crf=crf)
    elif op == "resize":
        w, h = args.get("width"), args.get("height")
        vf = f"scale={int(w)}:-2:flags=lanczos" if w else f"scale=-2:{int(h or 720)}:flags=lanczos"
        out = _out(out_dir, src, "resized")
        code, log = _encode(["-i", str(src), "-vf", vf, *audio], out, dur, progress, lab)
    elif op == "vertical":
        out = _out(out_dir, src, "vertical", ".mp4")
        if (args.get("mode") or "blur") == "crop":
            fc = "scale=-2:1920:flags=lanczos,crop=1080:1920"
            code, log = _encode(["-i", str(src), "-vf", fc, *audio], out, dur, progress, lab)
        else:
            fc = ("[0:v]split[a][b];[a]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=24:2,"
                  "eq=brightness=-0.06[bg];[b]scale=1080:1920:force_original_aspect_ratio=decrease:flags=lanczos[fg];"
                  "[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1[v]")
            code, log = _encode(["-i", str(src), "-filter_complex", fc, "-map", "[v]", "-map", "0:a?", *audio],
                                out, dur, progress, lab)
    elif op == "crop":
        x, y, w, h = (int(args.get(k) or 0) for k in ("x", "y", "width", "height"))
        if w <= 0 or h <= 0:
            raise ValueError("حدد width و height للقص")
        out = _out(out_dir, src, "cropped")
        code, log = _encode(["-i", str(src), "-vf", f"crop={w - w % 2}:{h - h % 2}:{x}:{y}", *audio],
                            out, dur, progress, lab)
    elif op == "speed":
        f = float(args.get("factor") or 2)
        if not 0.1 <= f <= 10:
            raise ValueError("السرعة لازم بين 0.1 و 10")
        out = _out(out_dir, src, f"x{f:g}")
        a = ["-af", _atempo(f)] + audio if info["audio"] else ["-an"]
        code, log = _encode(["-i", str(src), "-vf", f"setpts=PTS/{f}", *a], out, dur / f, progress, lab)
    elif op == "reverse":
        if dur > 120:
            raise ValueError("العكس يحتاج رام كثير؛ قص الفيديو لأقل من دقيقتين أول")
        out = _out(out_dir, src, "reversed")
        a = ["-af", "areverse"] + audio if info["audio"] else ["-an"]
        code, log = _encode(["-i", str(src), "-vf", "reverse", *a], out, dur, progress, lab)
    elif op == "merge":
        inputs = [Path(x) for x in (args.get("inputs") or [])]
        if len(inputs) < 2:
            raise ValueError("أعط inputs فيها مقطعين أو أكثر")
        for x in inputs:
            if not x.is_file():
                raise FileNotFoundError(f"ما لقيت: {x}")
        infos = [_info(x) for x in inputs]
        W, H = infos[0]["w"] - infos[0]["w"] % 2, infos[0]["h"] - infos[0]["h"] % 2
        F = round(infos[0]["fps"], 3)
        fc, ins = "", []
        for i, (x, inf) in enumerate(zip(inputs, infos)):
            ins += ["-i", str(x)]
            fc += (f"[{i}:v]scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,"
                   f"setsar=1,fps={F},format=yuv420p[v{i}];")
            if inf["audio"]:
                fc += f"[{i}:a]aresample=48000,aformat=channel_layouts=stereo[a{i}];"
            else:
                fc += f"aevalsrc=0|0:d={inf['dur']:.3f}:s=48000[a{i}];"
        fc += "".join(f"[v{i}][a{i}]" for i in range(len(inputs))) + f"concat=n={len(inputs)}:v=1:a=1[v][a]"
        out = _out(out_dir, inputs[0], "merged", ".mp4")
        code, log = _encode([*ins, "-filter_complex", fc, "-map", "[v]", "-map", "[a]", *audio], out,
                            sum(i["dur"] for i in infos), progress, lab)
    elif op == "gif":
        s, e = _t(args.get("start")) or 0.0, _t(args.get("end"))
        e = e if e is not None else min(dur, s + 8)
        fps, w = int(args.get("fps") or 15), int(args.get("width") or 480)
        out = _out(out_dir, src, "anim", ".gif")
        fc = f"fps={fps},scale={w}:-1:flags=lanczos,split[s0][s1];[s0]palettegen=stats_mode=diff[p];[s1][p]paletteuse=dither=sierra2_4a"
        code, log = run_ffmpeg(["-ss", f"{s:.3f}", "-to", f"{e:.3f}", "-i", str(src), "-filter_complex", fc,
                                "-loop", "0", str(out)], e - s, progress, lab)
    elif op == "extract_audio":
        fmt = (args.get("format") or "mp3").lower()
        out = _out(out_dir, src, "audio", f".{fmt if fmt in ('mp3', 'wav', 'm4a') else 'mp3'}")
        enc = {"mp3": ["-c:a", "libmp3lame", "-q:a", "2"], "wav": ["-c:a", "pcm_s16le"], "m4a": ["-c:a", "aac", "-b:a", "192k"]}
        code, log = run_ffmpeg(["-i", str(src), "-vn", *enc.get(out.suffix[1:], enc["mp3"]), str(out)], dur, progress, lab)
    elif op == "replace_audio":
        a = Path(str(args.get("audio") or ""))
        if not a.is_file():
            raise FileNotFoundError(f"ما لقيت ملف الصوت: {a}")
        out = _out(out_dir, src, "newaudio", ".mp4")
        code, log = run_ffmpeg(["-i", str(src), "-i", str(a), "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
                                *audio, "-shortest", "-movflags", "+faststart", str(out)], dur, progress, lab)
    elif op == "mute":
        out = _out(out_dir, src, "muted")
        code, log = run_ffmpeg(["-i", str(src), "-c:v", "copy", "-an", str(out)], dur, progress, lab)
    elif op == "fps":
        fps = int(args.get("fps") or 60)
        out = _out(out_dir, src, f"{fps}fps", ".mp4")
        if str(args.get("smooth", "true")).lower() in ("true", "1", "yes"):
            vf = f"minterpolate=fps={fps}:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1"
            lab = "ينعّم الحركة (بطيء شوي)"
        else:
            vf = f"fps={fps}"
        code, log = _encode(["-i", str(src), "-vf", vf, *audio], out, dur, progress, lab)
    elif op == "burn_subtitles":
        subs = Path(str(args.get("subtitles") or ""))
        if not subs.is_file():
            raise FileNotFoundError(f"ما لقيت ملف الترجمة: {subs}")
        out = _out(out_dir, src, "subbed", ".mp4")
        tmp = Path(tempfile.mkdtemp(prefix="3zt_sub_"))
        shutil.copy2(subs, tmp / ("subs" + subs.suffix.lower()))
        style = "FontName=Tahoma,FontSize=20,Outline=2,Shadow=0,BorderStyle=1,MarginV=28"
        vf = f"subtitles=subs{subs.suffix.lower()}:force_style='{style}'" if subs.suffix.lower() == ".srt" else f"subtitles=subs{subs.suffix.lower()}"
        try:
            code, log = _encode(["-i", str(src.resolve()), "-vf", vf, *audio], out.resolve(), dur, progress, lab, cwd=str(tmp))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    elif op == "overlay":
        img = Path(str(args.get("image") or ""))
        if not img.is_file():
            raise FileNotFoundError(f"ما لقيت الشعار: {img}")
        pos = {"top-left": "20:20", "top-right": "W-w-20:20", "bottom-left": "20:H-h-20",
               "bottom-right": "W-w-20:H-h-20", "center": "(W-w)/2:(H-h)/2"}.get(args.get("position") or "top-right", "W-w-20:20")
        frac = float(args.get("scale") or 0.15)
        out = _out(out_dir, src, "logo", ".mp4")
        fc = f"[1:v]scale={max(16, int(info['w'] * frac))}:-1[l];[0:v][l]overlay={pos}[v]"
        code, log = _encode(["-i", str(src), "-i", str(img), "-filter_complex", fc, "-map", "[v]", "-map", "0:a?", *audio],
                            out, dur, progress, lab)
    elif op == "rotate":
        deg = int(args.get("degrees") or 90) % 360
        vf = {90: "transpose=1", 180: "hflip,vflip", 270: "transpose=2"}.get(deg)
        if not vf:
            raise ValueError("الدوران 90 أو 180 أو 270")
        out = _out(out_dir, src, f"rot{deg}")
        code, log = _encode(["-i", str(src), "-vf", vf, *audio], out, dur, progress, lab)
    elif op == "normalize_audio":
        out = _out(out_dir, src, "loud", ".mp4")
        code, log = run_ffmpeg(["-i", str(src), "-c:v", "copy", "-af", "loudnorm=I=-14:TP=-1.5:LRA=11", *audio,
                                str(out)], dur, progress, lab)
    elif op == "thumbnail":
        t = _t(args.get("time"))
        t = t if t is not None else dur / 3
        out = _out(out_dir, src, f"frame_{int(t)}s", ".jpg")
        code, log = run_ffmpeg(["-ss", f"{t:.3f}", "-i", str(src), "-frames:v", "1", "-q:v", "2", str(out)], 0,
                               progress, lab)
    elif op == "repair":
        presets = args.get("presets") or ([args["preset"]] if args.get("preset") else ["deflicker", "denoise", "dehalo"])
        if isinstance(presets, str):
            presets = [p.strip() for p in presets.split(",")]
        bad = [p for p in presets if p not in REPAIR_PRESETS]
        if bad:
            raise ValueError(f"إعدادات غير معروفة: {bad}. المتاح: {REPAIR_PRESETS}")
        chain, vidstab = repair_chain(presets, info)
        out = _out(out_dir, src, "fixed", ".mp4")
        if vidstab:
            tmp = Path(tempfile.mkdtemp(prefix="3zt_stab_"))
            try:
                run_ffmpeg(["-i", str(src.resolve()), "-vf", "vidstabdetect=shakiness=6:accuracy=12:result=t.trf",
                            "-f", "null", "-"], dur, progress, "يحلل الاهتزاز", cwd=str(tmp))
                chain = "vidstabtransform=input=t.trf:smoothing=20:zoom=1," + chain if chain else \
                    "vidstabtransform=input=t.trf:smoothing=20:zoom=1"
                code, log = _encode(["-i", str(src.resolve()), "-vf", chain, *audio], out.resolve(), dur, progress, lab,
                                    crf=16, cwd=str(tmp))
            finally:
                shutil.rmtree(tmp, ignore_errors=True)
        else:
            code, log = _encode(["-i", str(src), "-vf", chain or "null", *audio], out, dur, progress, lab, crf=16)
    elif op == "upscale_ai":
        return _upscale_ai(args, src, info, out_dir, progress, cancel, realesrgan_exe)

    if code != 0 or not out.exists() or out.stat().st_size == 0:
        raise RuntimeError(f"ffmpeg فشل: {log[-700:] or 'بدون تفاصيل'}")
    return [out], f"تم ({lab}): {out} — {out.stat().st_size / 1048576:.1f} MB"


def _upscale_ai(args, src, info, out_dir, progress, cancel, exe):
    if not exe:
        raise RuntimeError("Real-ESRGAN مو مثبت. شغّل install-extras.bat")
    scale = 4 if int(args.get("scale") or 2) >= 4 else 2
    anime = str(args.get("anime", "false")).lower() in ("true", "1", "yes")
    model = f"realesr-animevideov3-x{scale}" if anime else "realesrgan-x4plus"
    if not anime:
        scale = 4
    if max(info["w"], info["h"]) * scale > 7680:
        raise ValueError(f"الفيديو دقته {info['w']}x{info['h']} عالية أصلاً؛ رفعها {scale}x يطلع أكبر من 8K. "
                         "رفع الدقة ما يضيف أطراف ولا يصلّح شي هنا.")
    frames_total = int(info["dur"] * info["fps"])
    if frames_total > 6000:
        raise ValueError(f"الفيديو طويل ({frames_total} فريم). قصه لأقل من ~3 دقايق أول، الترقية بطيئة.")
    work = Path(tempfile.mkdtemp(prefix="3zt_up_", dir=str(out_dir)))
    fin, fout = work / "in", work / "out"
    fin.mkdir()
    fout.mkdir()
    try:
        code, log = run_ffmpeg(["-i", str(src), "-qscale:v", "1", "-qmin", "1", "-qmax", "1", "-vsync", "0",
                                str(fin / "f%06d.png")], info["dur"], progress, "يطلّع الفريمات")
        n = len(list(fin.glob("*.png")))
        if not n:
            raise RuntimeError("ما قدرت أطلّع الفريمات: " + log[-300:])
        p = subprocess.Popen([str(exe), "-i", str(fin), "-o", str(fout), "-n", model, "-s", str(scale), "-f", "png"],
                             cwd=str(Path(exe).parent), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             creationflags=NO_WINDOW)
        t0 = time.time()
        while p.poll() is None:
            if cancel.is_set():
                p.kill()
                raise RuntimeError("انلغى")
            done = len(list(fout.glob("*.png")))
            el = time.time() - t0
            pct = int(done * 100 / n)
            eta = int(el * (n - done) / done) if done > 3 else None
            progress(f"يرفع الدقة بـ Real-ESRGAN — {done}/{n} فريم" + (f" · باقي ~{eta // 60}د {eta % 60}ث" if eta else "") + f"|{pct}")
            time.sleep(1.5)
        if len(list(fout.glob("*.png"))) < n:
            raise RuntimeError("Real-ESRGAN وقف قبل ما يخلص (ممكن الذاكرة)")
        out = _out(out_dir, src, f"ai_x{scale}", ".mp4")
        target_h = int(args.get("height") or 0)
        vf = ["-vf", f"scale=-2:{target_h}:flags=lanczos"] if target_h else []
        code, log = _encode(["-framerate", f"{info['fps']:.5f}", "-i", str(fout / "f%06d.png"), "-i", str(src),
                             "-map", "0:v", "-map", "1:a?", *vf, "-c:a", "aac", "-b:a", "192k", "-shortest"],
                            out, info["dur"], progress, "يجمع الفيديو", crf=16)
        if code != 0 or not out.exists():
            raise RuntimeError("ffmpeg فشل وهو يجمع الفيديو: " + log[-500:])
        return [out], f"تم رفع الدقة x{scale} ({model}): {out}"
    finally:
        shutil.rmtree(work, ignore_errors=True)


def image(args, src, out_dir, progress):
    op = (args.get("operation") or "").strip().lower()
    if op not in IMAGE_OPS:
        raise ValueError(f"العملية غير معروفة. المتاح: {', '.join(IMAGE_OPS)}")
    src = Path(src)
    if not src.is_file():
        raise FileNotFoundError(f"ما لقيت الصورة: {src}")
    if src.suffix.lower() in media.VIDEO_EXT:
        raise ValueError("هذا فيديو؛ استخدم أداة video")
    ext = src.suffix.lower() if src.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp", ".bmp") else ".png"
    extra = []
    if op == "resize":
        w, h = args.get("width"), args.get("height")
        vf = f"scale={int(w)}:-1:flags=lanczos" if w else f"scale=-1:{int(h or 1080)}:flags=lanczos"
        tag = "resized"
    elif op == "crop":
        x, y, w, h = (int(args.get(k) or 0) for k in ("x", "y", "width", "height"))
        if w <= 0 or h <= 0:
            raise ValueError("حدد width و height")
        vf, tag = f"crop={w}:{h}:{x}:{y}", "cropped"
    elif op == "rotate":
        deg = int(args.get("degrees") or 90) % 360
        vf, tag = {90: "transpose=1", 180: "hflip,vflip", 270: "transpose=2"}.get(deg, "transpose=1"), f"rot{deg}"
    elif op == "flip":
        vf, tag = ("vflip" if args.get("direction") == "vertical" else "hflip"), "flipped"
    elif op == "convert":
        fmt = (args.get("format") or "png").lower().lstrip(".")
        ext = "." + {"jpeg": "jpg"}.get(fmt, fmt)
        if ext not in (".png", ".jpg", ".webp", ".bmp", ".gif", ".tif"):
            raise ValueError("الصيغ المتاحة: png, jpg, webp, bmp, gif, tif")
        vf, tag = "null", "converted"
        if ext == ".jpg":
            extra = ["-q:v", "2"]
    elif op == "compress":
        q = int(args.get("quality") or 80)
        ext = ".webp" if (args.get("format") or "").lower() == "webp" else ".jpg"
        vf, tag = "null", "compressed"
        extra = ["-quality", str(q)] if ext == ".webp" else ["-q:v", str(max(2, min(31, int((100 - q) / 3) + 2)))]
    elif op == "grayscale":
        vf, tag = "format=gray", "gray"
    elif op == "blur":
        vf, tag = f"gblur=sigma={float(args.get('amount') or 6)}", "blur"
    elif op == "sharpen":
        vf, tag = f"unsharp=5:5:{float(args.get('amount') or 1.0)}:5:5:0", "sharp"
    elif op == "brightness":
        b, c, s = float(args.get("brightness") or 0.05), float(args.get("contrast") or 1.05), float(args.get("saturation") or 1.1)
        vf, tag = f"eq=brightness={b}:contrast={c}:saturation={s}", "adjusted"
    else:  # denoise
        vf, tag = "nlmeans=s=4" if _ffmpeg_has("filters", "nlmeans") else "hqdn3d=4:4:6:6", "clean"
    out = _out(out_dir, src, tag, ext)
    code, log = run_ffmpeg(["-i", str(src), "-vf", vf, *extra, "-frames:v", "1", str(out)], 0, progress, "يعدّل الصورة")
    if code != 0 or not out.exists():
        raise RuntimeError("فشل: " + log[-500:])
    return [out], f"تم: {out} ({out.stat().st_size / 1024:.0f} KB)"
