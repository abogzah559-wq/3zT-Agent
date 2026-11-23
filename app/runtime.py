"""Bundled runtime: puts the tools the installer ships (Python, ffmpeg, yt-dlp, Node and its packages) first
on PATH for this process and every child, so nothing has to be installed separately."""
import os
import shutil
from pathlib import Path

from config import GPU_LIBS_DIR, IS_WIN, NODE_DIR, NODE_PKG_DIR, RUNTIME_DIR


def browser_exe():
    """Edge or Chrome (used by hyperframes and agent-browser instead of downloading their own Chromium)."""
    if IS_WIN:
        for base in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles"), os.environ.get("LOCALAPPDATA")):
            if base:
                for rel in ("Microsoft/Edge/Application/msedge.exe", "Google/Chrome/Application/chrome.exe"):
                    p = Path(base) / rel
                    if p.exists():
                        return p
        return None
    for n in ("google-chrome", "chromium", "chromium-browser", "microsoft-edge"):
        w = shutil.which(n)
        if w:
            return Path(w)
    return None


def setup():
    dirs = [RUNTIME_DIR / "bin", RUNTIME_DIR / "python", RUNTIME_DIR / "python" / "Scripts",
            NODE_DIR, NODE_PKG_DIR / "node_modules" / ".bin"]
    have = [str(d) for d in dirs if d.exists()]
    if have:
        os.environ["PATH"] = os.pathsep.join(have + [os.environ.get("PATH", "")])
    mods = NODE_PKG_DIR / "node_modules"
    if mods.exists():
        os.environ["NODE_PATH"] = os.pathsep.join([str(mods)] + ([os.environ["NODE_PATH"]] if os.environ.get("NODE_PATH") else []))
    os.environ["AGENT_GPU_LIBS"] = str(GPU_LIBS_DIR)    # CUDA libraries for faster-whisper (media worker)
    b = browser_exe()
    if b:
        os.environ.setdefault("HYPERFRAMES_BROWSER_PATH", str(b))
        os.environ.setdefault("AGENT_BROWSER_EXECUTABLE_PATH", str(b))
    # no usage reports and no self-updates from bundled tools
    for k in ("HYPERFRAMES_NO_TELEMETRY", "HYPERFRAMES_NO_UPDATE_CHECK", "DO_NOT_TRACK"):
        os.environ.setdefault(k, "1")
    os.environ.setdefault("PUPPETEER_SKIP_DOWNLOAD", "1")
    os.environ["PYTHONIOENCODING"] = "utf-8"


def bundled():
    return RUNTIME_DIR.exists()
