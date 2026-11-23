"""Image/video helpers: thumbnails, frames, probing, plus optional open-source extras
(faster-whisper, rembg, Real-ESRGAN, edge-tts, yt-dlp)."""
import base64
import json
import os
import shutil
import subprocess
import tempfile
import time
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

from config import EXTRAS_PY, IS_WIN, MEDIA_DIR, NO_WINDOW, REALESRGAN_DIR, ROOT

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff"}
VIDEO_EXT = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v", ".wmv", ".flv", ".3gp"}
AUDIO_EXT = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac", ".opus", ".wma"}


def run(cmd, timeout=600, cwd=None):
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=timeout, creationflags=NO_WINDOW, cwd=cwd)
    return r.returncode, (r.stdout or "") + (("\n" + r.stderr) if r.stderr else "")


def have(exe):
    return shutil.which(exe) is not None


# ---------------- images the model sees ----------------
def to_jpeg(src, max_side=1280, quality=4):
    """Make a JPEG copy for the model in MEDIA_DIR. Returns (path, width, height) or (None,0,0)."""
    src = Path(src)
    dst = MEDIA_DIR / f"{time.strftime('%Y%m')}" / f"{uuid.uuid4().hex[:12]}.jpg"
    dst.parent.mkdir(parents=True, exist_ok=True)
    if have("ffmpeg"):
        run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(src), "-frames:v", "1",
             "-vf", f"scale='if(gt(iw,ih),min({max_side},iw),-2)':'if(gt(iw,ih),-2,min({max_side},ih))'",
             "-q:v", str(quality), str(dst)], 90)
    if not dst.exists():
        if src.suffix.lower() in (".jpg", ".jpeg"):
            shutil.copy2(src, dst)
        else:
            return None, 0, 0
    w, h = image_size(dst)
    return dst, w, h


def image_size(p):
    """Width/height of a JPEG or PNG using only the stdlib."""
    try:
        with open(p, "rb") as f:
            head = f.read(26)
            if head[:8] == b"\x89PNG\r\n\x1a\n":
                return int.from_bytes(head[16:20], "big"), int.from_bytes(head[20:24], "big")
            f.seek(2)
            while True:
                marker = f.read(2)
                if len(marker) < 2 or marker[0] != 0xFF:
                    break
                ln = int.from_bytes(f.read(2), "big")
                if marker[1] in (0xC0, 0xC1, 0xC2):
                    f.read(1)
                    h = int.from_bytes(f.read(2), "big")
                    w = int.from_bytes(f.read(2), "big")
                    return w, h
                f.seek(ln - 2, 1)
    except Exception:
        pass
    return 0, 0


def b64(path):
    return base64.b64encode(Path(path).read_bytes()).decode()


def probe(path):
    code, out = run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)], 60)
    if code != 0:
        raise RuntimeError(out.strip()[-400:] or "ffprobe فشل")
    return json.loads(out[out.find("{"):])


def duration(path):
    try:
        return float(probe(path)["format"].get("duration") or 0)
    except Exception:
        return 0.0


def video_frames(path, count=8):
    """Evenly spaced frames for the model. Returns (description, [jpg paths])."""
    path = Path(path)
    dur = duration(path)
    outdir = MEDIA_DIR / time.strftime("%Y%m") / f"frames_{uuid.uuid4().hex[:8]}"
    outdir.mkdir(parents=True, exist_ok=True)
    frames = []
    if dur > 0:
        for i in range(count):
            t = dur * (i + 0.5) / count
            out = outdir / f"f_{i:02}.jpg"
            run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{t:.3f}", "-i", str(path),
                 "-frames:v", "1", "-vf", "scale='min(960,iw)':-2", "-q:v", "5", str(out)], 60)
            if out.exists():
                frames.append((t, out))
    desc = (f"[فيديو: {path.name} — المدة {dur:.1f} ثانية — هذي {len(frames)} لقطات موزعة بالترتيب عند الثواني: "
            + ", ".join(f"{t:.1f}" for t, _ in frames) + "]")
    return desc, [str(p) for _, p in frames]


def summarize_probe(path):
    info = probe(path)
    fmt = info.get("format", {})
    lines = [f"الملف: {path}", f"الصيغة: {fmt.get('format_long_name', fmt.get('format_name'))}",
             f"المدة: {float(fmt.get('duration') or 0):.2f} ثانية",
             f"الحجم: {int(fmt.get('size') or 0) / 2**20:.1f} MB", f"البت ريت: {int(fmt.get('bit_rate') or 0) // 1000} kb/s"]
    for s in info.get("streams", []):
        if s.get("codec_type") == "video":
            fr = s.get("avg_frame_rate", "0/1")
            try:
                n, d = fr.split("/")
                fps = float(n) / float(d) if float(d) else 0
            except Exception:
                fps = 0
            lines.append(f"فيديو: {s.get('codec_name')} {s.get('width')}x{s.get('height')} @ {fps:.2f}fps")
        elif s.get("codec_type") == "audio":
            lines.append(f"صوت: {s.get('codec_name')} {s.get('sample_rate')}Hz {s.get('channels')}ch")
        elif s.get("codec_type") == "subtitle":
            lines.append(f"ترجمة: {s.get('codec_name')} ({(s.get('tags') or {}).get('language', '?')})")
    return "\n".join(lines)


# ---------------- optional extras ----------------
def extras_ok():
    return EXTRAS_PY.exists()


def _worker(args, timeout=7200):
    if not extras_ok():
        raise RuntimeError("الإضافات (Whisper / إزالة الخلفية / الصوت) مو موجودة. أعد تثبيت البرنامج من ملف الـ Setup")
    code, out = run([str(EXTRAS_PY), str(ROOT / "workers" / "media_worker.py"), *args], timeout)
    line = next((x for x in reversed(out.strip().splitlines()) if x.startswith("{")), "")
    if not line:
        raise RuntimeError("الأداة ما رجعت نتيجة: " + out.strip()[-500:])
    res = json.loads(line)
    if not res.get("ok"):
        raise RuntimeError(res.get("error", "فشل"))
    return res


def transcribe(src, out_dir, language="auto", model="large-v3-turbo"):
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    return _worker(["transcribe", str(src), str(out_dir), language or "auto", model])


def remove_background(src, out_png):
    return _worker(["rmbg", str(src), str(out_png)], 900)


def tts(text, voice, out_mp3, rate="+0%"):
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
        f.write(text)
        tmp = f.name
    try:
        return _worker(["tts", tmp, voice, str(out_mp3), rate], 600)
    finally:
        os.unlink(tmp)


def realesrgan_exe():
    if not REALESRGAN_DIR.exists():
        return None
    name = "realesrgan-ncnn-vulkan.exe" if IS_WIN else "realesrgan-ncnn-vulkan"
    found = list(REALESRGAN_DIR.rglob(name))
    return found[0] if found else None


def upscale(src, out_png, scale=4, anime=False):
    exe = realesrgan_exe()
    if not exe:
        raise RuntimeError("Real-ESRGAN مو موجود. أعد تثبيت البرنامج من ملف الـ Setup")
    model = "realesrgan-x4plus-anime" if anime else "realesrgan-x4plus"
    code, out = run([str(exe), "-i", str(src), "-o", str(out_png), "-n", model, "-s", "4", "-f", "png"],
                    1800, cwd=str(exe.parent))
    if not Path(out_png).exists():
        raise RuntimeError("Real-ESRGAN فشل: " + out.strip()[-400:])
    if int(scale) == 2 and have("ffmpeg"):     # x4 model then high-quality downscale to x2
        tmp = Path(out_png).with_suffix(".x4.png")
        os.replace(out_png, tmp)
        run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(tmp), "-vf",
             "scale=iw/2:ih/2:flags=lanczos", str(out_png)], 300)
        tmp.unlink(missing_ok=True)
    return out_png


def ytdlp_cmd():
    if have("yt-dlp"):
        return ["yt-dlp"]
    if extras_ok():
        code, _ = run([str(EXTRAS_PY), "-m", "yt_dlp", "--version"], 30)
        if code == 0:
            return [str(EXTRAS_PY), "-m", "yt_dlp"]
    return None


def download(url, out_dir, audio_only=False):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    direct = Path(url.split("?")[0]).suffix.lower() in IMAGE_EXT | VIDEO_EXT | AUDIO_EXT | {".pdf", ".zip", ".txt", ".json", ".csv"}
    cmd = ytdlp_cmd()
    if cmd and not direct:
        before = set(out_dir.iterdir())
        args = cmd + ["--no-playlist", "--restrict-filenames", "-o", str(out_dir / "%(title).80s [%(id)s].%(ext)s")]
        args += ["-x", "--audio-format", "mp3"] if audio_only else ["-f", "bv*+ba/b", "--merge-output-format", "mp4"]
        code, out = run(args + [url], 3600)
        new = sorted(set(out_dir.iterdir()) - before, key=lambda p: p.stat().st_mtime)
        new = [p for p in new if not p.name.endswith((".part", ".ytdl"))]
        if code == 0 and new:
            return [str(p) for p in new]
        if "Unsupported URL" not in out:
            raise RuntimeError("yt-dlp: " + out.strip()[-600:])
    name = Path(urllib.parse.unquote(url.split("?")[0].rstrip("/").split("/")[-1] or "")).name
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        if "text/html" in (r.headers.get("Content-Type") or "") and not direct:
            raise RuntimeError("هذا رابط صفحة مو ملف. yt-dlp مو موجود (يجي مع ملف الـ Setup).")
        dst = out_dir / (name or f"download_{int(time.time())}")
        if dst.exists():
            dst = dst.with_name(f"{dst.stem}_{int(time.time())}{dst.suffix}")
        with open(dst, "wb") as f:
            shutil.copyfileobj(r, f, 1 << 20)
    return [str(dst)]
