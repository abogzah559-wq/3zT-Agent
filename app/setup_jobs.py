"""First-run setup and add-ons, done from inside the app (no separate installers to run):
the two local models, llama.cpp (when the installer did not ship it), FreeVideo for picture/video
generation, and the CUDA libraries that make speech-to-text run on the GPU.

Every job runs in a thread with live progress and can be cancelled; closing the app cancels them all.
"""
import logging
import shutil
import subprocess
import threading
import time

import freevideo
import localai
from config import AGENTS, EXTRAS_PY, FREEVIDEO_EXE, GPU_LIBS_DIR, MODELS, NO_WINDOW, model_of

LOG = logging.getLogger("3zt")
S = {}                       # live settings (set by the server)
JOBS = {}                    # what -> {"state", "pct", "text", "error", "cancel"}
_LOCK = threading.Lock()
FREEVIDEO_URL = "https://github.com/FlashML-org/FreeVideo/releases/latest/download/FreeVideo.exe"
OLD_OLLAMA_MODELS = ("qwen3.5:9b", "huihui_ai/qwen3.5-abliterated:9b")


def gpu_libs_ok():
    return any(GPU_LIBS_DIR.glob("nvidia/cudnn/bin/*.dll")) or any(GPU_LIBS_DIR.glob("nvidia/cudnn/lib/*.so*"))


def _ollama():
    return shutil.which("ollama")


def _items():
    """Everything the setup screen lists, in order."""
    ex, fr = model_of("executor", S), model_of("free", S)
    items = [
        {"id": "llama", "title": "محرك النماذج المحلية (llama.cpp)", "gb": 0.6, "required": True,
         "done": localai.server_exe() is not None},
        {"id": "executor", "title": f"{AGENTS['executor']['short']} — {MODELS[ex]['name']}", "required": True,
         "gb": MODELS[ex]["gb"]["fast"], "done": localai.installed(ex, "fast")},
        {"id": "free", "title": f"{AGENTS['free']['short']} — {MODELS[fr]['name']} (السريعة، كاملة في الكرت)",
         "required": True, "gb": MODELS[fr]["gb"]["fast"], "done": localai.installed(fr, "fast")},
    ]
    if "quality" in MODELS[fr]["variants"]:
        items.append({"id": "free_quality", "title": f"{MODELS[fr]['name']} — نسخة أعلى جودة (جزء منها بالرام)",
                      "required": False, "gb": MODELS[fr]["gb"]["quality"], "done": localai.installed(fr, "quality")})
    items += [
        {"id": "freevideo", "title": "FreeVideo — توليد الصور والفيديو (يفتح مثبته، 40–60GB)", "required": False,
         "gb": 50, "done": freevideo.installed()},
        {"id": "gpu_libs", "title": "تسريع التفريغ والترجمة بكرت الشاشة (CUDA لـ Whisper)", "required": False,
         "gb": 1.2, "done": gpu_libs_ok()},
    ]
    if _ollama():
        done = (JOBS.get("ollama_cleanup") or {}).get("state") == "done"
        items.append({"id": "ollama_cleanup", "title": "احذف موديلات Ollama القديمة من الإصدار 1 (توفر ~13GB)",
                      "required": False, "gb": 0, "done": done})
    for it in items:
        j = JOBS.get(it["id"])
        it["job"] = {k: v for k, v in j.items() if k != "cancel"} if j else None
    return items


def status():
    return {"items": _items(), "seen": bool(S.get("setup_seen"))}


_SUMMARY = {"t": 0.0, "missing": []}


def summary():
    """Small part of /api/state (polled every few seconds): is anything required missing, is a job running."""
    running = [k for k, j in JOBS.items() if j["state"] == "running"]
    if running or time.time() - _SUMMARY["t"] > 15:
        try:
            _SUMMARY["missing"] = [it["id"] for it in _items() if it["required"] and not it["done"]]
        except Exception:
            _SUMMARY["missing"] = []
        _SUMMARY["t"] = time.time()
    return {"missing": _SUMMARY["missing"], "running": running, "seen": bool(S.get("setup_seen"))}


def _progress(job):
    def hook(text):
        txt, _, pct = text.rpartition("|") if "|" in text else (text, "", "")
        job["text"] = txt or text
        if pct.isdigit():
            job["pct"] = int(pct)
    return hook


def _run(what, job):
    cancel = job["cancel"]
    hook = _progress(job)
    try:
        if what == "llama":
            localai.install_server(hook, cancel)
        elif what in ("executor", "free", "free_quality"):
            key = "executor" if what == "executor" else "free"
            variant = "quality" if what == "free_quality" else "fast"
            localai.download(model_of(key, S), variant, hook, cancel)
        elif what == "freevideo":
            FREEVIDEO_EXE.parent.mkdir(parents=True, exist_ok=True)
            if not FREEVIDEO_EXE.exists():
                localai._download(FREEVIDEO_URL, FREEVIDEO_EXE, hook, cancel, "FreeVideo")
            job["text"] = "فتحت مثبّت FreeVideo: اختر Install a new ComfyUI ثم Install & launch، وكمّل فيه."
            subprocess.Popen([str(FREEVIDEO_EXE)], cwd=str(FREEVIDEO_EXE.parent))
        elif what == "gpu_libs":
            if not EXTRAS_PY.exists():
                raise RuntimeError("بايثون المدمج مو موجود (ثبّت البرنامج من ملف الـ Setup)")
            GPU_LIBS_DIR.mkdir(parents=True, exist_ok=True)
            job["text"] = "ينزّل مكتبات CUDA (حوالي 1.2GB)..."
            proc = subprocess.Popen([str(EXTRAS_PY), "-m", "pip", "install", "--disable-pip-version-check",
                                     "--no-warn-script-location", "--upgrade", "--target", str(GPU_LIBS_DIR),
                                     "nvidia-cublas-cu12", "nvidia-cudnn-cu12==9.*"],
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                    encoding="utf-8", errors="replace", creationflags=NO_WINDOW)
            tail = []
            for line in proc.stdout:
                tail = (tail + [line.strip()])[-12:]
                if line.strip():
                    job["text"] = line.strip()[:160]
                if cancel.is_set():
                    proc.kill()
                    raise RuntimeError("انلغى")
            if proc.wait() != 0:
                raise RuntimeError("pip فشل: " + " | ".join(tail[-4:]))
        elif what == "ollama_cleanup":
            exe = _ollama()
            for m in OLD_OLLAMA_MODELS:
                job["text"] = f"يحذف {m}..."
                subprocess.run([exe, "rm", m], capture_output=True, timeout=120, creationflags=NO_WINDOW)
        else:
            raise RuntimeError("مهمة غير معروفة")
        job.update(state="done", pct=100, text=job.get("text") if what == "freevideo" else "تم ✓")
    except Exception as e:
        LOG.warning("setup %s: %s", what, e)
        job.update(state="error", error=str(e) if not cancel.is_set() else "انلغى")


def start(what):
    valid = {it["id"] for it in _items()}
    if what not in valid:
        return False, "غير متاح"
    with _LOCK:
        j = JOBS.get(what)
        if j and j["state"] == "running":
            return True, ""
        job = {"state": "running", "pct": 0, "text": "يبدأ...", "error": "", "cancel": threading.Event()}
        JOBS[what] = job
    threading.Thread(target=_run, args=(what, job), daemon=True, name=f"setup-{what}").start()
    return True, ""


def cancel(what):
    j = JOBS.get(what)
    if j:
        j["cancel"].set()


def cancel_all():
    for j in list(JOBS.values()):
        j["cancel"].set()

