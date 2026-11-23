"""Local models on llama.cpp's llama-server (bundled with the app, or downloaded once).

One model sits in the GPU at a time. The server is a child process of the app: it starts when a local
agent needs it and stops when the app closes, so nothing keeps running in the background.

Memory plan (12 GB VRAM / 16 GB RAM is the reference PC):
- "fast" variant: the whole model in VRAM. Fastest, uses almost no RAM.
- "quality" variant: a bigger file; part of the MoE experts move to system RAM. Started only when enough
  RAM is free (4 GB always stay free for Windows), otherwise the app falls back to "fast".
- the context size is capped per model and the KV cache is 8-bit, so a long chat never spills over.
"""
import json
import logging
import os
import re
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

from config import IS_WIN, LLAMA_DIRS, LLAMA_PORT, LLAMA_URL, LOCAL_DIR, MODELS, MODELS_DIR, NO_WINDOW

LOG = logging.getLogger("3zt")

HF = "https://huggingface.co"
UA = {"User-Agent": "3zT-Agent"}
RAM_RESERVE_GB = 4.0          # never plan to use the last 4 GB of RAM
VRAM_RESERVE_GB = 1.2         # desktop, browser and the compute buffers

STATE = {"proc": None, "model": None, "variant": None, "ctx": 0, "log": None, "help": None}
LOCK = threading.RLock()
BROKEN = set()                # (model, variant) pairs that produced garbage this session


class LocalError(RuntimeError):
    pass


# ============================ helpers ============================
def _get(url, timeout=30, headers=None):
    req = urllib.request.Request(url, headers={**UA, **(headers or {})})
    return urllib.request.urlopen(req, timeout=timeout)


def _get_json(url, timeout=30):
    with _get(url, timeout) as r:
        return json.load(r)


def _free_ram_gb():
    if IS_WIN:
        import ctypes

        class MS(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
        m = MS()
        m.dwLength = ctypes.sizeof(MS)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
        return m.ullAvailPhys / 2**30
    try:
        with open("/proc/meminfo") as f:
            info = dict(line.split(":", 1) for line in f)
        return int(info["MemAvailable"].split()[0]) / 2**20
    except Exception:
        return 0.0


def _vram_gb():
    """(total, free) in GB of the first NVIDIA GPU, or (0, 0)."""
    if not shutil.which("nvidia-smi"):
        return 0.0, 0.0
    try:
        r = subprocess.run(["nvidia-smi", "--query-gpu=memory.total,memory.free", "--format=csv,noheader,nounits"],
                           capture_output=True, text=True, timeout=8, creationflags=NO_WINDOW)
        total, free = [float(x) for x in r.stdout.strip().splitlines()[0].split(",")]
        return total / 1024, free / 1024
    except Exception:
        return 0.0, 0.0


def has_nvidia():
    return shutil.which("nvidia-smi") is not None


# ============================ model files ============================
def _mdir(model):
    d = MODELS_DIR / model
    d.mkdir(parents=True, exist_ok=True)
    return d


def _manifest(model):
    try:
        return json.loads((_mdir(model) / "manifest.json").read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_manifest(model, data):
    (_mdir(model) / "manifest.json").write_text(json.dumps(data, indent=2), encoding="utf-8")


def _patterns(spec, variant):
    pats = spec["variants"][variant]
    return [pats] if isinstance(pats, str) else list(pats)


def _mm_patterns(spec):
    pats = spec.get("mmproj") or []
    return [pats] if isinstance(pats, str) else list(pats)


def variants(model):
    return list(MODELS[model]["variants"])


def _local_match(model, pats):
    files = [p for p in _mdir(model).glob("*.gguf")]
    for pat in pats:
        for f in files:
            if re.search(pat, f.name) and "mmproj" not in f.name.lower():
                return f
    return None


def resolve(model, variant):
    """File names for (model, variant): {"model": name, "mmproj": name or None}, using the manifest, the
    folder, then the Hugging Face file list."""
    spec = MODELS[model]
    man = _manifest(model)
    if variant in man.get("files", {}):
        return man["files"][variant]
    pats = _patterns(spec, variant)
    local = _local_match(model, pats)
    mm_pats = _mm_patterns(spec)
    mm_local = next((f.name for pat in mm_pats for f in _mdir(model).glob("*.gguf")
                     if "mmproj" in f.name.lower() and re.search(pat, f.name)), None)
    names = []
    try:
        names = [s["rfilename"] for s in _get_json(f"{HF}/api/models/{spec['repo']}", 30).get("siblings", [])]
    except Exception as e:
        if local:
            return {"model": local.name, "mmproj": mm_local}
        raise LocalError(f"ما قدرت أوصل Hugging Face عشان أعرف ملفات {spec['name']}: {e}") from None
    pick = None
    for pat in pats:
        pick = next((n for n in names if re.search(pat, n) and "mmproj" not in n.lower() and "/" not in n), None)
        if pick:
            break
    if not pick:
        raise LocalError(f"ما لقيت ملف {variant} لـ {spec['name']} في {spec['repo']}")
    mm = next((n for pat in mm_pats for n in names if "mmproj" in n.lower() and re.search(pat, n)), None)
    files = {"model": pick, "mmproj": mm}
    man.setdefault("files", {})[variant] = files
    man["repo"] = spec["repo"]
    _save_manifest(model, man)
    return files


def _complete(path):
    return path.exists() and not path.with_suffix(path.suffix + ".part").exists() and path.stat().st_size > 1 << 20


def installed(model, variant):
    """True when the model file (and its vision projector) are fully downloaded."""
    try:
        man = _manifest(model).get("files", {}).get(variant)
        if not man:
            f = _local_match(model, _patterns(MODELS[model], variant))
            return bool(f and _complete(f))
        ok = _complete(_mdir(model) / man["model"])
        if man.get("mmproj"):
            ok = ok and _complete(_mdir(model) / man["mmproj"])
        return ok
    except Exception:
        return False


_DL_LOCKS = {}
_DL_GUARD = threading.Lock()


def _download(url, dest, progress, cancel, label):
    """Resumable download into dest (dest.part while in progress). Two callers never write the same file."""
    with _DL_GUARD:
        lock = _DL_LOCKS.setdefault(str(dest), threading.Lock())
    with lock:
        if dest.exists() and not dest.with_suffix(dest.suffix + ".part").exists():
            return
        for attempt in range(6):            # big files: resume after a dropped connection
            try:
                return _download_unlocked(url, dest, progress, cancel, label)
            except LocalError:
                if cancel is not None and cancel.is_set():
                    raise
                if attempt == 5:
                    raise
            except (urllib.error.URLError, OSError) as e:
                if (cancel is not None and cancel.is_set()) or attempt == 5 or \
                        (isinstance(e, urllib.error.HTTPError) and e.code in (401, 403, 404)):
                    raise
            if progress:
                progress(f"انقطع تحميل {label}، أكمّل من مكانه...")
            time.sleep(3 + attempt * 3)


def _download_unlocked(url, dest, progress, cancel, label):
    part = dest.with_suffix(dest.suffix + ".part")
    have = part.stat().st_size if part.exists() else 0
    headers = {"Range": f"bytes={have}-"} if have else {}
    try:
        resp = _get(url, 60, headers)
    except urllib.error.HTTPError as e:
        if e.code == 416 and have:          # already complete
            os.replace(part, dest)
            return
        raise
    with resp:
        if have and resp.status != 206:     # server ignored the range: start over
            have = 0
        total = have + int(resp.headers.get("Content-Length") or 0)
        mode = "ab" if have else "wb"
        last, done = 0.0, have
        with open(part, mode) as f:
            while True:
                if cancel is not None and cancel.is_set():
                    raise LocalError("انلغى التحميل")
                chunk = resp.read(4 << 20)
                if not chunk:
                    break
                f.write(chunk)
                done += len(chunk)
                if progress and time.time() - last > 0.5:
                    pct = int(done * 100 / total) if total else 0
                    progress(f"ينزّل {label}: {done / 2**30:.2f} / {total / 2**30:.2f} GB|{pct}")
                    last = time.time()
    if total and done < total:
        raise LocalError(f"التحميل انقطع ({done / 2**30:.2f} من {total / 2**30:.2f} GB) — أعد المحاولة ويكمّل من مكانه")
    os.replace(part, dest)


def download(model, variant, progress=None, cancel=None):
    spec = MODELS[model]
    files = resolve(model, variant)
    for key in ("model", "mmproj"):
        name = files.get(key)
        if not name:
            continue
        dest = _mdir(model) / name
        if _complete(dest):
            continue
        url = f"{HF}/{spec['repo']}/resolve/main/{urllib.request.quote(name)}"
        label = spec["name"] + (" (الرؤية)" if key == "mmproj" else "")
        _download(url, dest, progress, cancel, label)


def remove_variant(model, variant):
    files = _manifest(model).get("files", {}).get(variant) or {}
    f = files.get("model")
    if f:
        for p in (_mdir(model) / f, _mdir(model) / (f + ".part")):
            p.unlink(missing_ok=True)


# ============================ llama.cpp ============================
def server_exe():
    name = "llama-server.exe" if IS_WIN else "llama-server"
    for d in LLAMA_DIRS:
        if d.exists():
            found = sorted(d.rglob(name), key=lambda p: len(p.parts))
            if found:
                return found[0]
    w = shutil.which("llama-server")
    return Path(w) if w else None


def install_server(progress=None, cancel=None):
    """Download the latest llama.cpp Windows build (CUDA 12 on NVIDIA, Vulkan otherwise)."""
    if not IS_WIN:
        raise LocalError("llama-server مو موجود. ثبّت llama.cpp وخله في PATH.")
    want, assets = [], {}
    # the newest release that carries Windows builds (the "latest" one can be a nightly marker)
    for rel in _get_json("https://api.github.com/repos/ggml-org/llama.cpp/releases?per_page=15", 30):
        assets = {a["name"]: a["browser_download_url"] for a in rel.get("assets", [])}
        if has_nvidia():
            main = sorted((n for n in assets if re.match(r"llama-.*-bin-win-cuda-12[\d.]*-x64\.zip$", n)), reverse=True)
            rt = sorted((n for n in assets if re.match(r"cudart-llama-bin-win-cuda-12[\d.]*-x64\.zip$", n)), reverse=True)
            if main and rt:
                want = [main[0], rt[0]]
        if not want:
            vk = [n for n in assets if re.match(r"llama-.*-bin-win-vulkan-x64\.zip$", n)]
            if vk:
                want = [vk[0]]
        if want:
            break
    if not want:
        raise LocalError("ما لقيت نسخة llama.cpp مناسبة للويندوز")
    dest = LLAMA_DIRS[-1]
    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True)
    dest.mkdir(parents=True, exist_ok=True)
    for n in want:
        z = dest / n
        _download(assets[n], z, progress, cancel, "محرك llama.cpp")
        with zipfile.ZipFile(z) as zf:
            zf.extractall(dest)
        z.unlink(missing_ok=True)
    STATE["help"] = None
    exe = server_exe()
    if not exe:
        raise LocalError("نزل llama.cpp بس ما لقيت llama-server.exe داخله")
    return exe


def _help_text(exe):
    if STATE["help"] is None:
        try:
            r = subprocess.run([str(exe), "--help"], capture_output=True, text=True, timeout=30,
                               creationflags=NO_WINDOW, encoding="utf-8", errors="replace")
            STATE["help"] = (r.stdout or "") + (r.stderr or "")
        except Exception:
            STATE["help"] = ""
    return STATE["help"]


def _supports(exe, flag):
    return re.search(r"(^|[\s,])" + re.escape(flag) + r"([\s,=]|$)", _help_text(exe), re.M) is not None


# ============================ server process ============================
def ctx_for(model, wanted):
    return max(4096, min(int(wanted or 0) or MODELS[model]["ctx"], MODELS[model]["ctx"]))


def pick_variant(model, setting):
    """'auto' -> quality only when it is downloaded and the RAM can hold its CPU part."""
    vs = variants(model)
    if setting in vs and (model, setting) not in BROKEN:
        return setting
    if "quality" in vs and setting == "auto" and (model, "quality") not in BROKEN and installed(model, "quality"):
        need = MODELS[model]["gb"]["quality"] - (_vram_gb()[0] - VRAM_RESERVE_GB)
        if need <= 0 or _free_ram_gb() - need >= RAM_RESERVE_GB:
            return "quality"
    return "fast"


def alive():
    p = STATE["proc"]
    return p is not None and p.poll() is None


def current():
    """(model, variant) loaded right now, or (None, None)."""
    if alive():
        return STATE["model"], STATE["variant"]
    return None, None


def healthy():
    try:
        with _get(LLAMA_URL + "/health", 3) as r:
            return r.status == 200
    except Exception:
        return False


def stop():
    with LOCK:
        p = STATE["proc"]
        STATE.update(proc=None, model=None, variant=None, ctx=0)
        if p is None or p.poll() is not None:
            return
        try:
            if IS_WIN:
                subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"], capture_output=True,
                               creationflags=NO_WINDOW, timeout=20)
            else:
                p.terminate()
            p.wait(10)
        except Exception:
            try:
                p.kill()
            except Exception:
                pass
        if STATE["log"]:
            try:
                STATE["log"].close()
            except Exception:
                pass
            STATE["log"] = None


def _log_tail(n=1500):
    try:
        return (LOCAL_DIR / "llama-server.log").read_text(encoding="utf-8", errors="replace")[-n:]
    except Exception:
        return ""


def _args(exe, model, variant, ctx, files):
    spec = MODELS[model]
    d = _mdir(model)
    a = [str(exe), "-m", str(d / files["model"]), "--host", "127.0.0.1", "--port", str(LLAMA_PORT),
         "-c", str(ctx), "-np", "1", "--jinja", "--alias", model]
    mm_mb = 0
    if files.get("mmproj") and (d / files["mmproj"]).exists():
        a += ["--mmproj", str(d / files["mmproj"])]
        mm_mb = (d / files["mmproj"]).stat().st_size // 2**20
    if _supports(exe, "--fit"):
        # llama.cpp measures free VRAM and puts what does not fit in system RAM by itself (layers left unset).
        # The margin keeps room for the vision projector, the desktop and other apps.
        a += ["--fit", "on"]
        if _supports(exe, "--fit-target"):
            a += ["--fit-target", str(1024 + mm_mb + 256)]
    else:
        a += ["-ngl", "999"]
        cpu = (spec.get("cpu_experts") or {}).get(variant)
        if cpu and _supports(exe, "--override-tensor"):
            a += ["--override-tensor", cpu]
    if _supports(exe, "--flash-attn"):
        takes_value = re.search(r"--flash-attn\s+\[?(on|FA)", _help_text(exe)) is not None
        a += ["--flash-attn", "on"] if takes_value else ["--flash-attn"]
        if _supports(exe, "--cache-type-k"):
            a += ["--cache-type-k", "q8_0", "--cache-type-v", "q8_0"]
    # Windows keeps a memory-mapped model in RAM too (6 GB+ wasted when it sits in VRAM)
    if _supports(exe, "--load-mode"):
        a += ["--load-mode", "none"]   # newer builds: --no-mmap is deprecated and ignored with tensor overrides
    elif _supports(exe, "--no-mmap"):
        a.append("--no-mmap")
    if _supports(exe, "--reasoning-format"):
        a += ["--reasoning-format", "deepseek"]
    if _supports(exe, "--no-webui"):
        a.append("--no-webui")
    return a


def prepare(model, variant, progress=None, cancel=None):
    """Download llama.cpp and the model files when missing (no lock held: this can take a while)."""
    exe = server_exe()
    if not exe:
        if progress:
            progress("ينزّل محرك llama.cpp (مرة وحدة بس)...")
        exe = install_server(progress, cancel)
    if not installed(model, variant):
        download(model, variant, progress, cancel)
    return exe, resolve(model, variant)


def load(model, variant, wanted_ctx, progress=None, cancel=None):
    """Start llama-server with this model (downloading what is missing). Returns '' or an error text."""
    if current() == (model, variant) and healthy():
        return ""
    try:
        exe, files = prepare(model, variant, progress, cancel)
    except LocalError as e:
        return str(e)
    except Exception as e:
        return f"ما قدرت أجهز {MODELS[model]['name']}: {type(e).__name__}: {e}"
    with LOCK:
        if current() == (model, variant) and healthy():
            return ""
        stop()
        _free_port()        # so the health check below can only be answered by the server we start now
        ctx = ctx_for(model, wanted_ctx)
        args = _args(exe, model, variant, ctx, files)
        LOCAL_DIR.mkdir(parents=True, exist_ok=True)
        logf = open(LOCAL_DIR / "llama-server.log", "w", encoding="utf-8", errors="replace")
        if progress:
            progress(f"يحمّل {MODELS[model]['name']} في كرت الشاشة...")
        LOG.info("llama-server: %s", " ".join(args))
        try:
            proc = subprocess.Popen(args, stdout=logf, stderr=subprocess.STDOUT, cwd=str(exe.parent),
                                    creationflags=NO_WINDOW)
        except Exception as e:
            logf.close()
            return f"ما قدرت أشغّل llama-server: {e}"
        STATE.update(proc=proc, model=model, variant=variant, ctx=ctx, log=logf)
        t0 = time.time()
        while time.time() - t0 < 600:
            if cancel is not None and cancel.is_set():
                stop()
                return "انلغى"
            if proc.poll() is not None:
                tail = _log_tail()
                stop()
                low = tail.lower()
                if "out of memory" in low or "failed to allocate" in low or "unable to allocate" in low:
                    return ("كرت الشاشة ما فيه مساحة كفاية للنموذج. سكّر الألعاب/البرامج الثقيلة، أو اختر النسخة "
                            "«السريعة» من الإعدادات.")
                return "llama-server وقف فجأة:\n" + tail[-700:]
            if healthy():
                return ""
            time.sleep(0.7)
        stop()
        return "النموذج أخذ وقت طويل وما اشتغل. شوف ملف llama-server.log في مجلد البيانات المحلي."


def _port_pids():
    """PIDs listening on our llama port. Windows lets several processes bind the same port
    (SO_REUSEADDR), so an old llama-server can keep answering there after a restart."""
    if not IS_WIN:
        return set()
    try:
        out = subprocess.run(["netstat", "-ano", "-p", "TCP"], capture_output=True, text=True,
                             creationflags=NO_WINDOW, timeout=15).stdout
    except Exception:
        return set()
    me = str(os.getpid())
    return {ln.split()[-1] for ln in out.splitlines()
            if f":{LLAMA_PORT} " in ln and "LISTENING" in ln and ln.split()[-1].isdigit() and ln.split()[-1] != me}


def _free_port():
    """Kill every process on our port (leftovers of crashes or restarts) before starting a new server."""
    try:
        pids = _port_pids()
        if IS_WIN:
            for pid in pids:
                subprocess.run(["taskkill", "/PID", pid, "/T", "/F"], capture_output=True,
                               creationflags=NO_WINDOW, timeout=20)
        elif healthy():
            subprocess.run(["pkill", "-f", f"llama-server.*--port {LLAMA_PORT}"], capture_output=True, timeout=15)
        for _ in range(20):
            if not healthy() and not (IS_WIN and _port_pids()):
                break
            time.sleep(0.5)
        if pids:
            LOG.info("freed llama port from %s", ",".join(sorted(pids)))
    except Exception:
        LOG.exception("free port")


def kill_stale():
    """At startup: nothing of ours runs yet, so anything on the port is a leftover."""
    if not alive():
        _free_port()


def kill_now():
    """Used at shutdown: never waits for a lock."""
    p = STATE["proc"]
    if p is not None and p.poll() is None:
        try:
            if IS_WIN:
                subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"], capture_output=True,
                               creationflags=NO_WINDOW, timeout=20)
            else:
                p.kill()
        except Exception:
            pass
    if IS_WIN:
        for pid in _port_pids():       # anything else still holding the port and the VRAM
            try:
                subprocess.run(["taskkill", "/PID", pid, "/T", "/F"], capture_output=True,
                               creationflags=NO_WINDOW, timeout=20)
            except Exception:
                pass


# ============================ chat ============================
def to_openai(msgs):
    """Internal messages -> OpenAI chat format with inline images (llama-server)."""
    out = []
    for m in msgs:
        r = m["role"]
        if r == "assistant":
            a = {"role": "assistant", "content": m.get("content") or ""}
            if m.get("tool_calls"):
                a["tool_calls"] = [{"id": t["id"], "type": "function", "function": {
                    "name": t["name"], "arguments": json.dumps(t["args"], ensure_ascii=False)}}
                    for t in m["tool_calls"]]
            out.append(a)
        elif r == "tool":
            out.append({"role": "tool", "tool_call_id": m.get("tool_call_id", ""), "content": m.get("content") or ""})
        else:
            imgs = m.get("images_b64") or []
            if imgs and r == "user":
                parts = [{"type": "text", "text": m.get("content") or ""}]
                parts += [{"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + b}} for b in imgs]
                out.append({"role": r, "content": parts})
            else:
                out.append({"role": r, "content": m.get("content") or ""})
    # templates want one leading system message; merge any later ones into the first
    sys_parts = [m["content"] for m in out if m["role"] == "system" and isinstance(m["content"], str)]
    rest = [m for m in out if m["role"] != "system"]
    return ([{"role": "system", "content": "\n\n".join(sys_parts)}] if sys_parts else []) + rest


def request_body(model, msgs, tools, think, stream=True, effort=None):
    spec = MODELS[model]
    body = {"model": model, "messages": to_openai(msgs), "stream": stream,
            **(spec["sampling"] if think else spec.get("sampling_nothink", spec["sampling"]))}
    if stream:
        body["stream_options"] = {"include_usage": True}
    if tools:
        body["tools"] = tools
    kind = spec.get("think")
    if kind == "enable_thinking":
        body["chat_template_kwargs"] = {"enable_thinking": bool(think)}
    elif kind == "reasoning_effort":
        body["chat_template_kwargs"] = {"reasoning_effort": effort or ("high" if think else "low")}
    return body


def caption(model, images_b64, question=None):
    prompt = question or ("Describe this image in detail for someone who cannot see it: objects, people, "
                          "text (transcribe it exactly), layout, colors, UI elements. Be factual.")
    msgs = [{"role": "user", "content": prompt, "images_b64": images_b64}]
    body = request_body(model, msgs, None, False, stream=False, effort="low")
    body["max_tokens"] = 1200
    req = urllib.request.Request(LLAMA_URL + "/v1/chat/completions",
                                 data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                                 headers={"Content-Type": "application/json", **UA}, method="POST")
    with urllib.request.urlopen(req, timeout=600) as r:
        data = json.load(r)
    return ((data.get("choices") or [{}])[0].get("message") or {}).get("content", "").strip()


def looks_broken(text):
    """The CUDA build can emit endless repeats when experts sit in RAM (llama.cpp issue #32710)."""
    t = re.sub(r"```.*?```", " ", text or "", flags=re.S)
    t = re.sub(r"^[\W_]+$", " ", t, flags=re.M).strip()        # separator lines (----, ====) are fine
    if len(t) < 120:
        return False
    if t.count("\ufffd") > 20:
        return True
    return re.search(r"(\w.{0,7}?)\1{50,}", t, re.S) is not None
