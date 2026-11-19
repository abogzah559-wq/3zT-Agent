"""3zT Agent configuration: agents, paths and persisted settings."""
import json
import os
import sys
import threading
from pathlib import Path

APP_NAME = "3zT-Agent"
VERSION = "1.2.0"
PORT = int(os.environ.get("AGENT_PORT", "7272"))
IS_WIN = sys.platform == "win32"
NO_WINDOW = 0x08000000 if IS_WIN else 0

ROOT = Path(__file__).resolve().parent
UI_DIR = ROOT / "ui"

OLLAMA_URL = os.environ.get("OLLAMA_HOST_URL", "http://127.0.0.1:11434").rstrip("/")
DEEPSEEK_URL = os.environ.get("DEEPSEEK_URL", "https://api.deepseek.com").rstrip("/")

# Roaming data (settings, chats, memory, logs)
DATA_DIR = Path(os.environ.get("AGENT_DATA_DIR") or
                Path(os.environ.get("APPDATA", str(Path.home() / ".config"))) / APP_NAME)
CHATS_DIR = DATA_DIR / "chats"
MEDIA_DIR = DATA_DIR / "media"          # thumbnails, frames and images the model sees
SETTINGS_FILE = DATA_DIR / "settings.json"
MEMORY_FILE = DATA_DIR / "memory.md"
LOG_FILE = DATA_DIR / "log.txt"

# Local, machine-specific tools (optional extras venv, Real-ESRGAN)
LOCAL_DIR = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / ".local" / "share"))) / APP_NAME
EXTRAS_VENV = LOCAL_DIR / "venv"
EXTRAS_PY = EXTRAS_VENV / ("Scripts/python.exe" if IS_WIN else "bin/python")
REALESRGAN_DIR = LOCAL_DIR / "tools" / "realesrgan"
FREEVIDEO_EXE = LOCAL_DIR / "tools" / "FreeVideo.exe"     # FreeVideo launcher (image + video generation)
DEFAULT_FREEVIDEO_HOME = str(Path(os.environ.get("LOCALAPPDATA", str(Path.home() / ".local" / "share"))) / "FreeVideo")

for _d in (DATA_DIR, CHATS_DIR, MEDIA_DIR):
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
        "kind": "ollama",
        "role": "executor",
        "policy": "safe",
        "setting": "executor_model",
        "desc": "الرسمي من علي بابا، بقيود: ما يولّد محتوى جنسي. ينفذ بالأدوات، يتحكم بالجهاز بإذنك، ويشوف الصور والفيديو.",
    },
    "free": {
        "name": "Qwen 3.5 — بدون قيود",
        "short": "بدون قيود",
        "kind": "ollama",
        "role": "executor",
        "policy": "open",
        "setting": "free_model",
        "desc": "نسخة Qwen 3.5 بدون رفض (huihui-ai). توليد صور وفيديو بدون قيود؛ تبقى بس الحدود الأساسية (القاصرين وتعديل صور ناس حقيقيين بشكل جنسي).",
    },
}

DEEPSEEK_MODELS = ["deepseek-flash", "deepseek-v4-pro"]

DEFAULT_SETTINGS = {
    "deepseek_key": "",
    "deepseek_model": "deepseek-flash",
    "deepseek_effort": "high",          # low | high | max
    "executor_model": "qwen3.5:9b",
    "free_model": "huihui_ai/qwen3.5-abliterated:9b",
    "workspace": DEFAULT_WORKSPACE,
    "freevideo_home": DEFAULT_FREEVIDEO_HOME,   # FreeVideo installation (token + endpoint live in <home>/agent)
    "freevideo_url": "",                      # empty: read <home>/agent/endpoint.json, else http://127.0.0.1:8188
    "image_model": "auto",                    # auto | minimax-h3-image | qwen-image-2.1-turbo
    "image_loras": [],                        # [{"name": "x.safetensors", "strength": 1.0}] for the free agents
    "stop_freevideo_on_exit": True,
    "active": "executor",
    "keep_executor_warm": True,         # keep the executor in VRAM while on DeepSeek
    "num_ctx": 32768,
    "think": True,                      # local models: think before answering (much better with tools)
    "max_steps": 40,
    "rev": 3,
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
