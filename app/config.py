"""3zT Agent configuration: agents, paths and persisted settings."""
import json
import os
import sys
import threading
from pathlib import Path

APP_NAME = "3zT-Agent"
VERSION = "2.0.0"
PORT = int(os.environ.get("AGENT_PORT", "7272"))
IS_WIN = sys.platform == "win32"
NO_WINDOW = 0x08000000 if IS_WIN else 0

ROOT = Path(__file__).resolve().parent
UI_DIR = ROOT / "ui"

LLAMA_PORT = int(os.environ.get("AGENT_LLAMA_PORT", str(PORT + 1)))
LLAMA_URL = f"http://127.0.0.1:{LLAMA_PORT}"
DEEPSEEK_URL = os.environ.get("DEEPSEEK_URL", "https://api.deepseek.com").rstrip("/")

# Roaming data (settings, chats, memory, logs)
DATA_DIR = Path(os.environ.get("AGENT_DATA_DIR") or
                Path(os.environ.get("APPDATA", str(Path.home() / ".config"))) / APP_NAME)
CHATS_DIR = DATA_DIR / "chats"
MEDIA_DIR = DATA_DIR / "media"          # thumbnails, frames and images the model sees
SETTINGS_FILE = DATA_DIR / "settings.json"
MEMORY_FILE = DATA_DIR / "memory.md"
LOG_FILE = DATA_DIR / "log.txt"

# Local, machine-specific files: downloaded models, llama.cpp (when not bundled), GPU add-ons
LOCAL_DIR = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / ".local" / "share"))) / APP_NAME
MODELS_DIR = LOCAL_DIR / "models"
GPU_LIBS_DIR = LOCAL_DIR / "gpu-libs"         # CUDA libraries for faster-whisper (optional download)

# Everything the installer ships next to the app: Python, ffmpeg, yt-dlp, Node + packages, llama.cpp, Real-ESRGAN
RUNTIME_DIR = Path(os.environ.get("AGENT_RUNTIME_DIR") or ROOT.parent / "runtime")
BUNDLED_PY = RUNTIME_DIR / "python" / ("python.exe" if IS_WIN else "bin/python3")
NODE_DIR = RUNTIME_DIR / "node"
NODE_PKG_DIR = RUNTIME_DIR / "node-packages"     # docx, pptxgenjs, hyperframes, agent-browser
_OLD_VENV_PY = LOCAL_DIR / "venv" / ("Scripts/python.exe" if IS_WIN else "bin/python")    # v1.x extras
EXTRAS_PY = BUNDLED_PY if BUNDLED_PY.exists() else _OLD_VENV_PY
REALESRGAN_DIR = RUNTIME_DIR / "realesrgan" if (RUNTIME_DIR / "realesrgan").exists() else LOCAL_DIR / "tools" / "realesrgan"
LLAMA_DIRS = [RUNTIME_DIR / "llama", LOCAL_DIR / "tools" / "llama"]
FREEVIDEO_EXE = LOCAL_DIR / "tools" / "FreeVideo.exe"     # FreeVideo launcher (image + video generation)
DEFAULT_FREEVIDEO_HOME = str(Path(os.environ.get("LOCALAPPDATA", str(Path.home() / ".local" / "share"))) / "FreeVideo")

for _d in (DATA_DIR, CHATS_DIR, MEDIA_DIR, MODELS_DIR):
    _d.mkdir(parents=True, exist_ok=True)

DEFAULT_WORKSPACE = str(Path.home() / "agent-workspace")

AGENTS = {
    "planner": {
        "name": "DeepSeek",
        "short": "DeepSeek",
        "kind": "deepseek",
        "role": "planner",
        "policy": "open",
        "setting": "deepseek_model",
        "desc": "الأذكى. يخطط لك إذا طلبت خطة، وينفذ بكل الأدوات إذا طلبت تنفيذ — على كيفك. سحابي وما ياخذ من كرتك شي.",
    },
    "executor": {
        "name": "Qwen 3.5 — المنفذ",
        "short": "المنفذ",
        "kind": "local",
        "role": "executor",
        "policy": "safe",
        "setting": "executor_model",
        "desc": "الرسمي من علي بابا، بقيود: ما يولّد محتوى جنسي. ينفذ بالأدوات، يتحكم بالجهاز بإذنك، ويشوف الصور والفيديو.",
    },
    "free": {
        "name": "Inkling 2 Mini — بدون قيود",
        "short": "بدون قيود",
        "kind": "local",
        "role": "executor",
        "policy": "open",
        "setting": "free_model",
        "desc": "Inkling 2 Mini بدون رفض (Thinking Machines، نسخة AtomicChat). يشوف الصور، ينفذ بالأدوات، وتوليد صور وفيديو بدون قيود؛ "
                "تبقى بس الحدود الأساسية (القاصرين وتعديل صور ناس حقيقيين بشكل جنسي أو مهين).",
    },
}

# Local models run on the bundled llama.cpp server. Files are resolved on Hugging Face by pattern,
# so a re-upload with a slightly different name still works. "variants" = speed/quality choices.
MODELS = {
    "qwen3.5-9b": {
        "name": "Qwen 3.5 9B (Q4_K_M)",
        "repo": "unsloth/Qwen3.5-9B-GGUF",
        "variants": {"fast": [r"(?<!UD-)Q4_K_M\.gguf$", r"UD-Q4_K_XL\.gguf$"]},
        "mmproj": [r"mmproj-F16\.gguf$", r"mmproj.*(?<!B)(F16|f16)\.gguf$", r"mmproj.*\.gguf$"],
        "gb": {"fast": 6.7},
        "ctx": 32768,
        "think": "enable_thinking",
        "sampling": {"temperature": 0.6, "top_p": 0.95, "top_k": 20},
        "sampling_nothink": {"temperature": 0.7, "top_p": 0.8, "top_k": 20},
    },
    "inkling-2-mini-uncensored": {
        "name": "Inkling 2 Mini Uncensored",
        "repo": "AtomicChat/Inkling-2-Mini-Uncensored-GGUF",
        # fast: the whole model sits in a 12 GB card. quality: bigger file, part of the experts move to RAM.
        "variants": {"fast": [r"AD-IQ2_M\.gguf$", r"IQ2_M\.gguf$"], "quality": [r"AD-IQ3_S\.gguf$", r"IQ3_S\.gguf$"]},
        "mmproj": [r"mmproj-.*-F16\.gguf$", r"mmproj.*\.gguf$"],
        "gb": {"fast": 9.3, "quality": 14.0},
        "ctx": 16384,
        "cpu_experts": {"quality": r"blk\.(1[6-9]|2[0-3])\.ffn_.*_exps\.=CPU"},
        "think": "reasoning_effort",
        "sampling": {"temperature": 1.0},
        "sampling_nothink": {"temperature": 1.0},
    },
}
MODEL_VARIANTS = ("auto", "fast", "quality")

DEEPSEEK_MODELS = ["deepseek-flash", "deepseek-v4-pro"]

DEFAULT_SETTINGS = {
    "deepseek_key": "",
    "deepseek_model": "deepseek-flash",
    "deepseek_effort": "high",          # low | high | max
    "executor_model": "qwen3.5-9b",
    "free_model": "inkling-2-mini-uncensored",
    "free_variant": "auto",             # auto | fast | quality (quality uses RAM for part of the model)
    "workspace": DEFAULT_WORKSPACE,
    "freevideo_home": DEFAULT_FREEVIDEO_HOME,   # FreeVideo installation (token + endpoint live in <home>/agent)
    "freevideo_url": "",                      # empty: read <home>/agent/endpoint.json, else http://127.0.0.1:8188
    "image_model": "auto",                    # auto | minimax-h3-image | qwen-image-2.1-turbo
    "image_loras": [],                        # [{"name": "x.safetensors", "strength": 1.0}] for the free agents
    "stop_freevideo_on_exit": True,
    "active": "executor",
    "keep_executor_warm": True,         # keep the executor in VRAM while on DeepSeek
    "num_ctx": 32768,                   # upper limit; each model also has its own limit
    "think": True,                      # local models: think before answering (much better with tools)
    "max_steps": 40,
    "setup_seen": False,                # the first-run setup screen was shown
    "rev": 4,
}

_lock = threading.Lock()


def load_settings():
    s = dict(DEFAULT_SETTINGS)
    if SETTINGS_FILE.exists():
        try:
            data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                s.update({k: v for k, v in data.items() if k in DEFAULT_SETTINGS})
        except Exception:
            pass
    if int(s.get("rev") or 1) < 2:        # v1.1: thinking on by default for local models
        s["think"], s["rev"] = True, 2
    if int(s.get("rev") or 1) < 3:        # v1.2: FreeVideo replaces the old ComfyUI setup
        s["rev"] = 3
    if int(s.get("rev") or 1) < 4:        # v2.0: llama.cpp models instead of Ollama tags
        s["executor_model"], s["free_model"] = DEFAULT_SETTINGS["executor_model"], DEFAULT_SETTINGS["free_model"]
        s["rev"] = 4
    for k in ("executor_model", "free_model"):
        if s.get(k) not in MODELS:
            s[k] = DEFAULT_SETTINGS[k]
    if s.get("free_variant") not in MODEL_VARIANTS:
        s["free_variant"] = "auto"
    if s.get("image_model") not in ("auto", "minimax-h3-image", "qwen-image-2.1-turbo"):
        s["image_model"] = "auto"
    if not isinstance(s.get("image_loras"), list):
        s["image_loras"] = []
    if s.get("active") not in AGENTS:
        s["active"] = "executor"
    if s.get("deepseek_model") not in DEEPSEEK_MODELS:
        s["deepseek_model"] = DEFAULT_SETTINGS["deepseek_model"]
    try:
        Path(s["workspace"]).mkdir(parents=True, exist_ok=True)
    except Exception:
        s["workspace"] = DEFAULT_WORKSPACE
        Path(s["workspace"]).mkdir(parents=True, exist_ok=True)
    return s


def save_settings(s):
    with _lock:
        tmp = SETTINGS_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, SETTINGS_FILE)


def model_of(key, s):
    """Model tag for an agent according to current settings."""
    return s[AGENTS[key]["setting"]]
