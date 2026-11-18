"""ComfyUI bridge: local image/video generation on the GPU.

Before generating, the chat model is unloaded from VRAM; ComfyUI is started if needed, the
workflow is queued, progress is streamed over its WebSocket, results are downloaded through
/view, and finally ComfyUI frees VRAM so the chat model can come back.
"""
import base64
import json
import os
import random
import socket
import struct
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

from config import NO_WINDOW

COMFY = {"dir": Path.home() / "ComfyUI"}
COMFY_URL = os.environ.get("COMFY_URL", "http://127.0.0.1:8188").rstrip("/")
IMAGE_MODELS = {"realistic": ("juggernaut", "realvis", "epicrealism"),
                "anime": ("animagine", "illustrious", "noobai", "pony")}
VIDEO_UNET = "wan2.1_vace_1.3B_fp16.safetensors"
VIDEO_CLIP = "umt5_xxl_fp8_e4m3fn_scaled.safetensors"
VIDEO_VAE = "wan_2.1_vae.safetensors"

_proc = {"p": None, "log": None}


def set_dir(d):
    COMFY["dir"] = Path(os.path.expandvars(os.path.expanduser(d)))


def _get(path, timeout=10):
    with urllib.request.urlopen(COMFY_URL + path, timeout=timeout) as r:
        return json.load(r)


def _post(path, body, timeout=30):
    req = urllib.request.Request(COMFY_URL + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
    return json.loads(raw) if raw.strip() else {}


def is_up():
    try:
        _get("/system_stats", 3)
        return True
    except Exception:
        return False


def python_exe():
    d = COMFY["dir"]
    cands = [d / "venv" / "Scripts" / "python.exe", d / ".venv" / "Scripts" / "python.exe",
             d.parent / "python_embeded" / "python.exe", d / "python_embeded" / "python.exe",
             d / "venv" / "bin" / "python", d / ".venv" / "bin" / "python"]
    return next((c for c in cands if c.exists()), None)


def main_py():
    d = COMFY["dir"]
    for c in (d / "main.py", d / "ComfyUI" / "main.py"):
        if c.exists():
            return c
    return None


def installed():
    return bool(main_py() and python_exe())


def models_root():
    m = main_py()
    return (m.parent if m else COMFY["dir"]) / "models"


def find_image_model(style="realistic"):
    d = models_root() / "checkpoints"
    if not d.exists():
        return None
    files = sorted(x.relative_to(d).as_posix() for x in d.rglob("*.safetensors"))
    for hint in IMAGE_MODELS.get(style, IMAGE_MODELS["realistic"]):
        for f in files:
            if hint in f.lower():
                return f
    return None


def video_ready():
    m = models_root()
    return ((m / "diffusion_models" / VIDEO_UNET).exists() and (m / "text_encoders" / VIDEO_CLIP).exists()
            and (m / "vae" / VIDEO_VAE).exists())


def ensure_running(status=lambda t: None):
    if is_up():
        return True
    if not installed():
        raise RuntimeError(f"ComfyUI مو موجود في {COMFY['dir']} — حدد مكانه من الإعدادات")
    mp = main_py()
    status("أشغّل ComfyUI...")
    log = open(mp.parent / "3zt_comfy_log.txt", "a", encoding="utf-8")
    _proc["log"] = log
    _proc["p"] = subprocess.Popen(
        [str(python_exe()), str(mp), "--port", COMFY_URL.rsplit(":", 1)[-1], "--disable-auto-launch"],
        cwd=str(mp.parent), stdout=log, stderr=log, creationflags=NO_WINDOW)
    for _ in range(240):
        if is_up():
            return True
        if _proc["p"].poll() is not None:
            raise RuntimeError("ComfyUI قفل وهو يشتغل. شوف 3zt_comfy_log.txt داخل مجلد ComfyUI")
        time.sleep(1)
    raise RuntimeError("ComfyUI أخذ وقت طويل وما اشتغل")


def free_vram():
    try:
        _post("/free", {"unload_models": True, "free_memory": True})
    except Exception:
        pass


def stop():
    """Close ComfyUI only if we started it."""
    p = _proc.get("p")
    if p and p.poll() is None:
        free_vram()
        p.kill()
    if _proc.get("log"):
        try:
            _proc["log"].close()
        except Exception:
            pass


def upload_image(path):
    """Upload through the API (works for any ComfyUI layout). Returns the stored name."""
    path = Path(path)
    boundary = uuid.uuid4().hex
    data = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"image\"; filename=\"3zt_{uuid.uuid4().hex[:8]}{path.suffix}\"\r\n"
            f"Content-Type: application/octet-stream\r\n\r\n").encode() + path.read_bytes() + \
        f"\r\n--{boundary}\r\nContent-Disposition: form-data; name=\"overwrite\"\r\n\r\ntrue\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(COMFY_URL + "/upload/image", data=data, method="POST",
                                 headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    with urllib.request.urlopen(req, timeout=60) as r:
        res = json.load(r)
    return (res.get("subfolder") + "/" if res.get("subfolder") else "") + res["name"]


# ---------- live progress (minimal WebSocket client, stdlib only) ----------
NODE_AR = {"CheckpointLoaderSimple": "يحمّل نموذج الصور", "UNETLoader": "يحمّل نموذج الفيديو",
           "CLIPLoader": "يحمّل مشفّر النص", "VAELoader": "يحمّل الـ VAE", "CLIPTextEncode": "يفهم الوصف",
           "WanVaceToVideo": "يجهّز الفيديو", "KSampler": "يرسم", "VAEDecode": "يطلّع الصورة",
           "VAEEncode": "يقرأ الصورة الأصلية", "LoadImage": "يحمّل الصورة", "SaveImage": "يحفظ",
           "TrimVideoLatent": "يرتّب الإطارات"}


def _watch(cid, prompt, state, stop_ev):
    try:
        host, port = urllib.parse.urlparse(COMFY_URL).hostname, urllib.parse.urlparse(COMFY_URL).port or 80
        sock = socket.create_connection((host, port), timeout=5)
        key = base64.b64encode(os.urandom(16)).decode()
        sock.sendall((f"GET /ws?clientId={cid} HTTP/1.1\r\nHost: {host}:{port}\r\nUpgrade: websocket\r\n"
                      f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            chunk = sock.recv(4096)
            if not chunk:
                return
            buf += chunk
        buf = buf.split(b"\r\n\r\n", 1)[1]
        sock.settimeout(1)

        def need(n):
            nonlocal buf
            while len(buf) < n:
                if stop_ev.is_set():
                    raise EOFError
                try:
                    chunk = sock.recv(65536)
                except socket.timeout:
                    continue
                if not chunk:
                    raise EOFError
                buf += chunk
            out, buf = buf[:n], buf[n:]
            return out

        while not stop_ev.is_set():
            h = need(2)
            op, ln = h[0] & 0x0F, h[1] & 0x7F
            if ln == 126:
                ln = struct.unpack(">H", need(2))[0]
            elif ln == 127:
                ln = struct.unpack(">Q", need(8))[0]
            data = need(ln)
            if op == 8:
                break
            if op != 1:
                continue
            msg = json.loads(data)
            d = msg.get("data", {})
            if msg.get("type") == "progress":
                state["value"], state["max"] = d.get("value", 0), d.get("max", 0)
            elif msg.get("type") == "executing" and d.get("node"):
                node = prompt.get(str(d["node"]), {}).get("class_type", "")
                state["stage"] = NODE_AR.get(node, node)
                if node != "KSampler":
                    state["value"] = state["max"] = 0
        sock.close()
    except Exception:
        pass


def run(prompt, cancel, status=lambda t: None, timeout=3600):
    """Queue a workflow and return the list of output file refs (dicts with filename/subfolder/type)."""
    cid = uuid.uuid4().hex
    state = {"stage": "في الطابور", "value": 0, "max": 0}
    stop_ev = threading.Event()
    threading.Thread(target=_watch, args=(cid, prompt, state, stop_ev), daemon=True).start()
    try:
        try:
            res = _post("/prompt", {"prompt": prompt, "client_id": cid})
        except urllib.error.HTTPError as e:
            raise RuntimeError("ComfyUI رفض الطلب: " + e.read().decode(errors="replace")[:800])
        pid = res["prompt_id"]
        t0 = time.time()
        while time.time() - t0 < timeout:
            if cancel.is_set():
                try:
                    _post("/interrupt", {})
                except Exception:
                    pass
                raise RuntimeError("انلغى")
            h = _get(f"/history/{pid}")
            if pid in h:
                entry = h[pid]
                st = entry.get("status", {})
                if st.get("status_str") == "error":
                    msgs = [m for m in st.get("messages", []) if m[0] == "execution_error"]
                    err = msgs[0][1].get("exception_message", "خطأ") if msgs else "خطأ"
                    raise RuntimeError("ComfyUI: " + str(err)[:800])
                outs = []
                for out in entry.get("outputs", {}).values():
                    outs += out.get("images", [])
                return outs
            el = int(time.time() - t0)
            if state["max"]:
                pct = int(state["value"] * 100 / state["max"])
                status(f"{state['stage']} — الخطوة {state['value']}/{state['max']} · {el} ثانية|{pct}")
            else:
                status(f"{state['stage']}... {el} ثانية")
            time.sleep(1.0)
        raise RuntimeError("انتهى الوقت")
    finally:
        stop_ev.set()


def fetch(ref, dst):
    q = urllib.parse.urlencode({"filename": ref["filename"], "subfolder": ref.get("subfolder", ""),
                                "type": ref.get("type", "output")})
    with urllib.request.urlopen(f"{COMFY_URL}/view?{q}", timeout=120) as r:
        Path(dst).write_bytes(r.read())
    return Path(dst)


# ---------------- workflows ----------------
def image_workflow(ckpt, prompt, negative, width, height, count, seed, prefix, anime):
    sampler = ("euler_ancestral", "normal", 28) if anime else ("dpmpp_2m", "karras", 30)
    return {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": ckpt}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["1", 1]}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"text": negative, "clip": ["1", 1]}},
        "4": {"class_type": "EmptyLatentImage", "inputs": {"width": width, "height": height, "batch_size": count}},
        "5": {"class_type": "KSampler", "inputs": {
            "model": ["1", 0], "positive": ["2", 0], "negative": ["3", 0], "latent_image": ["4", 0],
            "seed": seed, "steps": sampler[2], "cfg": 5.0, "sampler_name": sampler[0],
            "scheduler": sampler[1], "denoise": 1.0}},
        "6": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
        "7": {"class_type": "SaveImage", "inputs": {"images": ["6", 0], "filename_prefix": prefix}},
    }


def edit_workflow(ckpt, prompt, negative, image_name, strength, seed, prefix, anime):
    wf = image_workflow(ckpt, prompt, negative, 8, 8, 1, seed, prefix, anime)
    wf["4"] = {"class_type": "LoadImage", "inputs": {"image": image_name}}
    wf["9"] = {"class_type": "ImageScaleToTotalPixels", "inputs": {"image": ["4", 0], "upscale_method": "lanczos", "megapixels": 1.0}}
    wf["8"] = {"class_type": "VAEEncode", "inputs": {"pixels": ["9", 0], "vae": ["1", 2]}}
    wf["5"]["inputs"].update({"latent_image": ["8", 0], "denoise": strength})
    return wf


def video_workflow(prompt, negative, width, height, frames, seed, prefix):
    return {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": VIDEO_UNET, "weight_dtype": "default"}},
        "2": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["1", 0], "shift": 8.0}},
        "3": {"class_type": "CLIPLoader", "inputs": {"clip_name": VIDEO_CLIP, "type": "wan"}},
        "4": {"class_type": "VAELoader", "inputs": {"vae_name": VIDEO_VAE}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["3", 0]}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": negative, "clip": ["3", 0]}},
        "7": {"class_type": "WanVaceToVideo", "inputs": {
            "positive": ["5", 0], "negative": ["6", 0], "vae": ["4", 0],
            "width": width, "height": height, "length": frames, "batch_size": 1, "strength": 1.0}},
        "8": {"class_type": "KSampler", "inputs": {
            "model": ["2", 0], "positive": ["7", 0], "negative": ["7", 1], "latent_image": ["7", 2],
            "seed": seed, "steps": 20, "cfg": 6.0, "sampler_name": "uni_pc", "scheduler": "simple", "denoise": 1.0}},
        "9": {"class_type": "TrimVideoLatent", "inputs": {"samples": ["8", 0], "trim_amount": ["7", 3]}},
        "10": {"class_type": "VAEDecode", "inputs": {"samples": ["9", 0], "vae": ["4", 0]}},
        "11": {"class_type": "SaveImage", "inputs": {"images": ["10", 0], "filename_prefix": prefix}},
    }


IMG_NEG = "lowres, blurry, bad anatomy, deformed, extra fingers, watermark, text, logo, jpeg artifacts"
ANIME_POS = "masterpiece, high score, great score, absurdres, "
ANIME_NEG = ("lowres, bad anatomy, bad hands, text, error, missing finger, extra digits, fewer digits, cropped, "
             "worst quality, low quality, low score, bad score, average score, signature, watermark, username, blurry")
VID_NEG = "low quality, blurry, flicker, jitter, deformed, extra limbs, watermark, text, static frame"


def _snap(v, step, lo, hi):
    return max(lo, min(hi, int(round(float(v) / step)) * step))


def _model_for(args):
    style = "anime" if str(args.get("style") or "").lower().startswith("anim") else "realistic"
    ckpt = find_image_model(style)
    if not ckpt:
        other = find_image_model("anime" if style == "realistic" else "realistic")
        if not other:
            raise RuntimeError("ما فيه نموذج صور في ComfyUI. شغّل install-media.bat")
        ckpt = other
    anime = style == "anime"
    pos = (ANIME_POS + args["prompt"]) if anime else args["prompt"]
    neg = args.get("negative") or (ANIME_NEG if anime else IMG_NEG)
    return ckpt, pos, neg, anime


def _collect(refs, out_dir, tag):
    out = []
    stamp = time.strftime("%Y%m%d_%H%M%S")
    for i, ref in enumerate(refs):
        out.append(fetch(ref, Path(out_dir) / f"{tag}_{stamp}_{i + 1}{Path(ref['filename']).suffix}"))
    return out


def generate_image(args, out_dir, cancel, status):
    ckpt, pos, neg, anime = _model_for(args)
    w = _snap(args.get("width") or 1024, 8, 512, 1536)
    h = _snap(args.get("height") or 1024, 8, 512, 1536)
    n = max(1, min(4, int(args.get("count") or 1)))
    seed = int(args["seed"]) if str(args.get("seed", "")).isdigit() else random.randint(1, 2**31)
    wf = image_workflow(ckpt, pos, neg, w, h, n, seed, "3zt/img", anime)
    return _collect(run(wf, cancel, status, timeout=900), out_dir, "img")


def edit_image(args, out_dir, cancel, status):
    src = Path(os.path.expandvars(os.path.expanduser(str(args["image_path"]))))
    if not src.exists():
        raise RuntimeError(f"ما لقيت الصورة: {src}")
    ckpt, pos, neg, anime = _model_for(args)
    strength = max(0.15, min(0.9, float(args.get("strength") or 0.55)))
    name = upload_image(src)
    wf = edit_workflow(ckpt, pos, neg, name, strength, random.randint(1, 2**31), "3zt/edit", anime)
    return _collect(run(wf, cancel, status, timeout=900), out_dir, "edit")


def generate_video(args, out_dir, cancel, status):
    if not video_ready():
        raise RuntimeError("نماذج Wan للفيديو ناقصة في ComfyUI (شغّل install-media.bat)")
    secs = max(1.0, min(6.0, float(args.get("seconds") or 3)))
    frames = int(secs * 16) // 4 * 4 + 1          # must be 4n+1
    land = (args.get("orientation") or "landscape") != "portrait"
    w, h = (832, 480) if land else (480, 832)
    tag = uuid.uuid4().hex[:8]
    wf = video_workflow(args["prompt"], args.get("negative") or VID_NEG, w, h, frames,
                        random.randint(1, 2**31), f"3zt/vid_{tag}")
    refs = sorted(run(wf, cancel, status, timeout=3600), key=lambda r: r["filename"])
    if not refs:
        raise RuntimeError("ما طلع ولا إطار")
    status("أجمع الإطارات في فيديو...")
    tmp = Path(out_dir) / f"_frames_{tag}"
    tmp.mkdir(parents=True, exist_ok=True)
    out_root = models_root().parent / "output"
    for i, ref in enumerate(refs):
        fetch(ref, tmp / f"f_{i:05}.png")
        try:                                   # don't leave hundreds of frames in ComfyUI/output
            (out_root / ref.get("subfolder", "") / ref["filename"]).unlink()
        except OSError:
            pass
    dst = Path(out_dir) / f"vid_{time.strftime('%Y%m%d_%H%M%S')}.mp4"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-framerate", "16",
                    "-i", str(tmp / "f_%05d.png"), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18",
                    "-movflags", "+faststart", str(dst)], capture_output=True, creationflags=NO_WINDOW)
    for f in tmp.glob("*.png"):
        f.unlink(missing_ok=True)
    try:
        tmp.rmdir()
    except OSError:
        pass
    if not dst.exists():
        raise RuntimeError("ffmpeg ما قدر يجمع الفيديو")
    return [dst]
