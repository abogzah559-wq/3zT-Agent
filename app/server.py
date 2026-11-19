"""3zT Agent — local server (Python standard library only) and window lifecycle.

Runs on http://127.0.0.1:7272 and opens itself as an app window (Edge/Chrome --app with a
private profile). Closing that window shuts everything down: models leave VRAM, Ollama and
FreeVideo (if the app started it) are stopped, and this process exits.
"""
import json
import logging
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from logging.handlers import RotatingFileHandler
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import agent  # noqa: E402
import freevideo  # noqa: E402
import llm  # noqa: E402
import media  # noqa: E402
import pc  # noqa: E402
import skills_mgr  # noqa: E402
import stats  # noqa: E402
import store  # noqa: E402
import tools  # noqa: E402
from config import (AGENTS, DATA_DIR, DEEPSEEK_MODELS, IS_WIN, LOG_FILE, MEDIA_DIR, MEMORY_FILE,  # noqa: E402
                    NO_WINDOW, PORT, UI_DIR, VERSION, load_settings, model_of, save_settings)

_h = RotatingFileHandler(LOG_FILE, maxBytes=2 << 20, backupCount=2, encoding="utf-8")
_h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
LOG = logging.getLogger("3zt")
LOG.setLevel(logging.INFO)
LOG.addHandler(_h)

S = load_settings()
agent.S = S
freevideo.configure(S["freevideo_home"], S["freevideo_url"])
if freevideo.installed() and str(freevideo.CFG["home"]) != S["freevideo_home"]:
    S["freevideo_home"] = str(freevideo.CFG["home"])    # remember where the launcher put the engine
    save_settings(S)

SEEN = {"last": 0.0, "bye": 0.0}
WINDOW = {"proc": None, "started": 0.0, "closed_at": 0.0}
IDLE_LIMIT = 200        # seconds without any request from the window = closed (minimized windows poll slowly)
BYE_GRACE = 6           # after a close beacon: wait, so a refresh (F5) doesn't shut the app down
ALLOWED_HOSTS = {f"127.0.0.1:{PORT}", f"localhost:{PORT}"}

TEXT_EXT = {".txt", ".md", ".py", ".js", ".ts", ".tsx", ".jsx", ".json", ".csv", ".log", ".html", ".css", ".xml",
            ".yml", ".yaml", ".ini", ".cfg", ".bat", ".ps1", ".srt", ".vtt", ".sql", ".java", ".c", ".cpp", ".h",
            ".cs", ".rs", ".go", ".kt", ".swift", ".lua", ".sh", ".toml", ".env", ".ass", ".php", ".rb", ".dart"}


# ============================ helpers ============================
def media_allowed(p: Path):
    roots = [Path(S["workspace"]), MEDIA_DIR, DATA_DIR]
    for r in roots:
        try:
            p.relative_to(r.resolve())
            return True
        except ValueError:
            continue
    # anything the agent showed in a chat (e.g. a download outside the workspace)
    return p.suffix.lower() in media.IMAGE_EXT | media.VIDEO_EXT | media.AUDIO_EXT and p.is_file()


def health():
    ok = llm.ollama_ok()
    installed = set(llm.ollama_installed()) if ok else set()
    nv = shutil.which("nvidia-smi") is not None
    return {
        "ollama": ok, "ollama_version": llm.ollama_version() if ok else "",
        "models": {k: (llm.norm_tag(model_of(k, S)) in installed) for k, a in AGENTS.items() if a["kind"] == "ollama"},
        "deepseek_key": bool(S.get("deepseek_key")),
        "ffmpeg": media.have("ffmpeg"), "ytdlp": media.ytdlp_cmd() is not None,
        "freevideo": freevideo.health(),
        "extras": media.extras_ok(), "realesrgan": media.realesrgan_exe() is not None,
        "nvidia": nv, "pc_control": IS_WIN,
    }


def public_settings():
    return {k: v for k, v in S.items() if k != "deepseek_key"} | {"has_key": bool(S.get("deepseek_key")),
                                                                    "key_hint": ("…" + S["deepseek_key"][-4:]) if S.get("deepseek_key") else ""}


def build_user_message(text, atts):
    """Turn typed text + uploaded attachments into the stored user message."""
    content, images, shown = text, [], []
    for a in atts or []:
        p = Path(a.get("path") or "")
        if not p.exists():
            continue
        kind = a.get("kind")
        shown.append({"name": a.get("name") or p.name, "kind": kind, "path": str(p), "thumb": a.get("thumb")})
        if kind == "image":
            content += f"\n\n(صورة مرفقة: {p})"
            images += [x for x in a.get("images", []) if Path(x).exists()]
        elif kind == "video":
            content += f"\n\n{a.get('desc', '')}\n(مسار الفيديو: {p})"
            images += [x for x in a.get("images", []) if Path(x).exists()]
        elif kind == "audio":
            content += f"\n\n(ملف صوت مرفق: {p} — {a.get('desc', '')})"
        elif kind == "text":
            body = a.get("text", "")
            cut = " — هذا أول جزء بس، اقرأ الباقي بـ read_file" if a.get("cut") else ""
            content += f"\n\n--- محتوى الملف {p.name} (المسار: {p}){cut} ---\n{body}\n--- نهاية الملف ---"
        else:
            content += f"\n\n(ملف مرفق: {p})"
    msg = {"role": "user", "content": content.strip(), "display": text, "ts": time.time()}
    if images:
        msg["images"] = images
    if shown:
        msg["attachments"] = shown
    return msg


def conv_files(conv):
    """Files on disk that belong to a chat: its folder + new files it created elsewhere."""
    out = []
    d = Path(S["workspace"]) / "chats" / conv["id"]
    if d.exists():
        out.append(str(d))
    for f in conv.get("files", []):
        p = Path(f)
        if p.exists() and not _within(p, d):
            out.append(str(p))
    return out


def _within(p, d):
    try:
        Path(p).resolve().relative_to(Path(d).resolve())
        return True
    except ValueError:
        return False


def delete_conv_files(conv):
    """Recycle the chat's files and drop its cached frames/thumbnails."""
    n = tools.recycle(conv_files(conv))
    for m in conv.get("messages", []):
        for img in m.get("images") or []:
            if _within(img, MEDIA_DIR):
                Path(img).unlink(missing_ok=True)
    return n


# ============================ lifecycle ============================
def find_browser():
    cands = []
    if IS_WIN:
        for base in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles"), os.environ.get("LOCALAPPDATA")):
            if base:
                cands += [Path(base) / "Microsoft/Edge/Application/msedge.exe",
                          Path(base) / "Google/Chrome/Application/chrome.exe"]
    else:
        for n in ("microsoft-edge", "google-chrome", "chromium", "chromium-browser"):
            w = shutil.which(n)
            if w:
                cands.append(Path(w))
    return next((c for c in cands if c.exists()), None)


def open_window():
    url = f"http://127.0.0.1:{PORT}/"
    exe = find_browser()
    if not exe:
        import webbrowser
        webbrowser.open(url)
        return
    profile = DATA_DIR / "window"
    args = [str(exe), f"--app={url}", f"--user-data-dir={profile}", "--window-size=1360,900",
            "--no-first-run", "--no-default-browser-check", "--disable-background-mode",
            "--disable-features=msEdgeStartupBoost,Translate,msHubApps,msEdgeSidebarV2", "--lang=ar"]
    try:
        proc = subprocess.Popen(args, creationflags=NO_WINDOW)
        old = WINDOW["proc"]
        if old is None or old.poll() is not None:     # keep watching the main browser process
            WINDOW["proc"], WINDOW["started"] = proc, time.time()
        LOG.info("window opened with %s", exe.name)
    except Exception:
        LOG.exception("open window")
        import webbrowser
        webbrowser.open(url)


def shutdown():
    LOG.info("shutdown")
    try:
        agent.unload_all()
    except Exception:
        pass
    if S.get("stop_freevideo_on_exit", True):
        try:
            freevideo.stop()
        except Exception:
            pass
    if IS_WIN:
        subprocess.run(["taskkill", "/F", "/IM", "ollama app.exe", "/IM", "ollama.exe"],
                       capture_output=True, creationflags=NO_WINDOW)
    logging.shutdown()
    os._exit(0)


def window_closed():
    """True when the app window is gone (process exit, close beacon or long silence)."""
    now = time.time()
    p = WINDOW["proc"]
    if p is not None and p.poll() is not None and now - WINDOW["started"] > 6:
        # the browser process we launched has exited: window closed
        return SEEN["last"] < now - 10
    if SEEN["bye"] > SEEN["last"] and now - SEEN["bye"] > BYE_GRACE:
        return True
    return bool(SEEN["last"]) and now - SEEN["last"] > IDLE_LIMIT


def watchdog():
    started = time.time()
    while True:
        time.sleep(1.5)
        if not SEEN["last"]:
            if time.time() - started > 240 and not agent.active_run():
                LOG.info("window never connected")
                shutdown()           # no window ever showed up: don't linger in the background
            continue
        if window_closed():
            agent.WINDOW["gone"] = True          # pending approvals are auto-denied
            if agent.active_run():               # let a running task finish first
                continue
            shutdown()
        else:
            agent.WINDOW["gone"] = False


def cleanup():
    """Delete temporary screenshots older than a week."""
    cutoff = time.time() - 7 * 86400
    d = Path(S["workspace"]) / "_shots"
    if d.exists():
        for c in d.iterdir():
            try:
                if c.stat().st_mtime < cutoff:
                    c.unlink()
            except OSError:
                pass


# ============================ HTTP ============================
class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "3zT-Agent"

    def log_message(self, *a):
        pass

    # ---- plumbing ----
    def _send(self, code, body=b"", ctype="application/json; charset=utf-8", extra=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"))

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > 20 << 20:
            raise ValueError("الطلب كبير")
        raw = self.rfile.read(n) if n else b""
        return json.loads(raw or b"{}")

    def _trusted(self, need_header=True):
        """Blocks other websites from talking to the agent (CSRF / DNS-rebinding)."""
        if self.headers.get("Host", "") not in ALLOWED_HOSTS:
            return False
        origin = self.headers.get("Origin")
        if origin and urllib.parse.urlparse(origin).netloc not in ALLOWED_HOSTS:
            return False
        return not need_header or self.headers.get("X-3zT") == "1"

    # ---- GET ----
    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        if not self._trusted(need_header=False):
            return self._send(403, b"forbidden", "text/plain")
        path, _, qs = self.path.partition("?")
        q = urllib.parse.parse_qs(qs)
        if path.startswith("/api/"):
            SEEN["last"] = time.time()
        try:
            if path in ("/", "/index.html"):
                return self._static(UI_DIR / "index.html")
            if path.startswith("/ui/"):
                return self._static(UI_DIR / path[4:])
            if path == "/favicon.ico":
                return self._static(UI_DIR / "icon.svg")
            if path == "/media":
                return self._media(q.get("p", [""])[0])
            if path == "/api/events":
                return self._events(q.get("run", [""])[0], int(q.get("from", ["0"])[0] or 0))
            if path == "/api/state":
                agent.refresh_status()
                run = agent.active_run()
                return self._json({
                    "version": VERSION, "settings": public_settings(), "status": agent.STATUS,
                    "agents": {k: {**a, "model": model_of(k, S)} for k, a in AGENTS.items()},
                    "deepseek_models": DEEPSEEK_MODELS, "pull": agent.PULL,
                    "run": {"id": run.id, "conv": run.conv["id"]} if run else None,
                    "ollama": llm.ollama_ok(), "always": sorted(agent.ALWAYS),
                })
            if path == "/api/stats":
                return self._json(stats.get())
            if path == "/api/health":
                return self._json(health())
            if path == "/api/convs":
                return self._json(store.listing())
            if path == "/api/conv":
                conv = store.get(q.get("id", [""])[0])
                if not conv:
                    return self._json({"error": "المحادثة مو موجودة"}, 404)
                run = next((r for r in agent.RUNS.values() if r.running() and r.conv["id"] == conv["id"]), None)
                extra = {"run": run.id if run else None, "base": run.base if run else None}
                for _ in range(20):        # the run thread may be appending right now
                    try:
                        body = json.dumps({**conv, **extra}, ensure_ascii=False).encode("utf-8")
                        break
                    except RuntimeError:
                        time.sleep(0.01)
                return self._send(200, body)
            if path == "/api/memory":
                return self._json({"text": agent.read_memory()})
            if path == "/api/skills":
                return self._json(sorted(skills_mgr.all_skills().values(), key=lambda x: (not x["builtin"], x["name"])))
            return self._send(404, b"not found", "text/plain")
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:
            LOG.exception("GET %s", self.path)
            try:
                self._json({"error": str(e)}, 500)
            except Exception:
                pass

    def _static(self, p: Path):
        try:
            p = p.resolve()
            p.relative_to(UI_DIR.resolve())
        except (ValueError, OSError):
            return self._send(403, b"", "text/plain")
        if not p.is_file():
            return self._send(404, b"", "text/plain")
        ctype = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript",):
            ctype += "; charset=utf-8"
        if p.suffix == ".js":
            ctype = "text/javascript; charset=utf-8"
        self._send(200, p.read_bytes(), ctype)

    def _media(self, raw):
        p = Path(raw).resolve()
        if not p.is_file() or not media_allowed(p):
            return self._send(404, b"", "text/plain")
        ctype = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
        size = p.stat().st_size
        start, end = 0, size - 1
        rng = self.headers.get("Range")
        code = 200
        if rng and (m := re.match(r"bytes=(\d*)-(\d*)", rng)):
            if m.group(1):
                start = int(m.group(1))
                end = int(m.group(2)) if m.group(2) else size - 1
            elif m.group(2):
                start = max(0, size - int(m.group(2)))
            end = min(end, size - 1)
            if start > end:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            code = 206
        length = end - start + 1
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "private, max-age=3600")
        if code == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        if self.command == "HEAD":
            return
        with open(p, "rb") as f:
            f.seek(start)
            left = length
            while left > 0:
                chunk = f.read(min(left, 1 << 20))
                if not chunk:
                    break
                self.wfile.write(chunk)
                left -= len(chunk)

    def _events(self, run_id, frm):
        run = agent.RUNS.get(run_id)
        if not run:
            return self._json({"error": "التشغيل انتهى"}, 404)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        i = frm
        try:
            while True:
                evs, done = run.events_from(i, 15)
                SEEN["last"] = time.time()
                if evs:
                    payload = "".join("data: " + json.dumps(e, ensure_ascii=False) + "\n\n" for e in evs)
                    self.wfile.write(payload.encode("utf-8"))
                    i += len(evs)
                else:
                    self.wfile.write(b": ping\n\n")
                self.wfile.flush()
                if done and i >= len(run.events):
                    break
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
            pass        # the run keeps going; the window can reconnect

    # ---- POST ----
    def do_POST(self):
        path = self.path.split("?")[0]
        if path == "/api/bye":
            if self._trusted(need_header=False):
                SEEN["bye"] = time.time()
            return self._send(204)
        if not self._trusted():
            return self._send(403, b"forbidden", "text/plain")
        SEEN["last"] = time.time()
        try:
            if path == "/api/upload":
                return self._upload()
            b = self._body()
            if path == "/api/chat":
                return self._chat(b)
            if path == "/api/retry":
                return self._retry(b)
            if path == "/api/approve":
                run = agent.RUNS.get(b.get("run"))
                return self._json({"ok": bool(run and run.answer(b.get("id"), b.get("answer")))})
            if path == "/api/stop":
                run = agent.RUNS.get(b.get("run")) or agent.active_run()
                if run:
                    run.stop()
                return self._json({"ok": True})
            if path == "/api/switch":
                if b.get("agent") not in AGENTS:
                    return self._json({"error": "إيجنت غير معروف"}, 400)
                agent.switch(b["agent"])
                save_settings(S)
                return self._json({"ok": True})
            if path == "/api/settings":
                return self._settings(b)
            if path == "/api/check_key":
                ok, msg = llm.deepseek_check((b.get("key") or S.get("deepseek_key") or "").strip())
                return self._json({"ok": ok, "msg": msg})
            if path == "/api/memory":
                text = str(b.get("text", ""))[:20000]
                MEMORY_FILE.write_text(text.strip() + ("\n" if text.strip() else ""), encoding="utf-8")
                return self._json({"ok": True})
            if path == "/api/conv/rename":
                conv = store.get(b.get("id", ""))
                if conv:
                    conv["title"] = (str(b.get("title") or "").strip() or conv["title"])[:80]
                    store.save(conv)
                return self._json({"ok": bool(conv)})
            if path == "/api/conv/pin":
                conv = store.get(b.get("id", ""))
                if conv:
                    conv["pinned"] = not conv.get("pinned")
                    store.save(conv)
                return self._json({"ok": bool(conv)})
            if path == "/api/conv/new":
                conv = store.new(b.get("agent") if b.get("agent") in AGENTS else S["active"])
                return self._json({"id": conv["id"]})
            if path == "/api/conv/files":
                conv = store.get(b.get("id", ""))
                return self._json({"files": conv_files(conv) if conv else []})
            if path == "/api/conv/delete":
                if any(r.running() and r.conv["id"] == b.get("id") for r in agent.RUNS.values()):
                    return self._json({"error": "المحادثة شغالة، وقفها أول"}, 409)
                conv = store.get(b.get("id", ""))
                removed = 0
                if conv and b.get("files", True):
                    removed = delete_conv_files(conv)
                store.delete(b.get("id", ""))
                return self._json({"ok": True, "removed": removed})
            if path == "/api/open_path":
                p = Path(str(b.get("path") or ""))
                if not p.exists():
                    return self._json({"error": "الملف مو موجود (ممكن انحذف أو انتقل)"}, 404)
                if IS_WIN:
                    if b.get("reveal"):
                        subprocess.Popen(["explorer", "/select,", str(p)], creationflags=NO_WINDOW)
                    else:
                        os.startfile(str(p))  # noqa
                return self._json({"ok": True})
            if path == "/api/skills/install":
                names = skills_mgr.install(str(b.get("url") or ""))
                return self._json({"ok": True, "installed": names})
            if path == "/api/skills/toggle":
                skills_mgr.set_enabled(str(b.get("name")), bool(b.get("on")))
                return self._json({"ok": True})
            if path == "/api/skills/remove":
                return self._json({"ok": skills_mgr.remove(str(b.get("name")))})
            if path == "/api/reset_always":
                agent.ALWAYS.clear()
                return self._json({"ok": True})
            if path == "/api/open_folder":
                target = {"workspace": S["workspace"], "data": str(DATA_DIR)}.get(b.get("which"), S["workspace"])
                if IS_WIN:
                    os.startfile(target)  # noqa
                return self._json({"ok": True})
            if path == "/api/freevideo/start":
                def _start():
                    try:
                        freevideo.ensure_running(lambda t: None, None, timeout=900)
                    except Exception as e:
                        LOG.warning("freevideo start: %s", e)
                if not freevideo.launcher() and not freevideo.installed():
                    return self._json({"ok": False, "error": "FreeVideo مو مثبت. شغّل install-freevideo.bat"})
                threading.Thread(target=_start, daemon=True).start()
                return self._json({"ok": True})
            if path == "/api/window":
                open_window()
                return self._json({"ok": True})
            return self._send(404, b"not found", "text/plain")
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:
            LOG.exception("POST %s", self.path)
            try:
                self._json({"error": f"{type(e).__name__}: {e}"}, 500)
            except Exception:
                pass

    def _settings(self, b):
        if "deepseek_key" in b and str(b["deepseek_key"]).strip():
            S["deepseek_key"] = str(b["deepseek_key"]).strip()
        if b.get("clear_key"):
            S["deepseek_key"] = ""
        if b.get("deepseek_model") in DEEPSEEK_MODELS:
            S["deepseek_model"] = b["deepseek_model"]
        if b.get("deepseek_effort") in ("low", "high", "max"):
            S["deepseek_effort"] = b["deepseek_effort"]
        for k in ("executor_model", "free_model"):
            v = str(b.get(k) or "").strip()
            if v and re.match(r"^[\w.\-/:]+$", v) and v != S[k]:
                llm.ollama_unload(S[k])
                S[k] = v
        if b.get("workspace"):
            ws = Path(os.path.expandvars(os.path.expanduser(str(b["workspace"]).strip())))
            ws.mkdir(parents=True, exist_ok=True)
            S["workspace"] = str(ws.resolve())
        if b.get("freevideo_home"):
            S["freevideo_home"] = str(b["freevideo_home"]).strip()
        if "freevideo_url" in b:
            u = str(b.get("freevideo_url") or "").strip().rstrip("/")
            S["freevideo_url"] = u if re.match(r"^https?://(127\.0\.0\.1|localhost|\[::1\])(:\d+)?$", u) else ""
        freevideo.configure(S["freevideo_home"], S["freevideo_url"])
        if b.get("image_model") in ("auto", "minimax-h3-image", "qwen-image-2.1-turbo"):
            S["image_model"] = b["image_model"]
        if "image_loras" in b:
            ls = []
            for row in b.get("image_loras") or []:
                name = str((row or {}).get("name") or "").strip()
                if name and re.match(r"^[\w .\-/()\[\]]+\.(safetensors|ckpt|pt)$", name, re.I) and ".." not in name:
                    try:
                        st = max(-2.0, min(2.0, float((row or {}).get("strength", 1.0))))
                    except (TypeError, ValueError):
                        st = 1.0
                    ls.append({"name": name, "strength": st})
            S["image_loras"] = ls[:8]
        if "stop_freevideo_on_exit" in b:
            S["stop_freevideo_on_exit"] = bool(b["stop_freevideo_on_exit"])
        if "keep_executor_warm" in b:
            S["keep_executor_warm"] = bool(b["keep_executor_warm"])
        if "think" in b:
            S["think"] = bool(b["think"])
        if b.get("num_ctx"):
            n = max(4096, min(int(b["num_ctx"]), 131072))
            if n != S["num_ctx"]:
                S["num_ctx"] = n
                for m in agent.local_models():          # reload with the new context size next time
                    llm.ollama_unload(m)
        if b.get("max_steps"):
            S["max_steps"] = max(5, min(int(b["max_steps"]), 150))
        save_settings(S)
        agent.refresh_status()
        return self._json({"ok": True, "settings": public_settings()})

    def _upload(self):
        name = Path(urllib.parse.unquote(self.headers.get("X-File-Name") or "file")).name or "file"
        name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)[:120]
        conv = store.get(self.headers.get("X-Conv") or "") or store.new(S["active"])
        up = agent.chat_dir(conv) / "uploads"
        up.mkdir(parents=True, exist_ok=True)
        p = up / name
        if p.exists():
            p = up / f"{p.stem}_{int(time.time())}{p.suffix}"
        left = int(self.headers.get("Content-Length") or 0)
        with open(p, "wb") as f:                  # chunks: big videos never sit in RAM
            while left > 0:
                chunk = self.rfile.read(min(left, 4 << 20))
                if not chunk:
                    break
                f.write(chunk)
                left -= len(chunk)
        ext = p.suffix.lower()
        rec = {"name": name, "path": str(p), "size": p.stat().st_size, "conv": conv["id"]}
        if ext in media.VIDEO_EXT:
            desc, frames = media.video_frames(p)
            rec.update(kind="video", desc=desc, images=frames,
                       thumb=agent.media_url(frames[0]) if frames else None)
        elif ext in media.IMAGE_EXT:
            jpg, w, h = media.to_jpeg(p)
            rec.update(kind="image", images=[str(jpg)] if jpg else [], thumb=agent.media_url(jpg or p),
                       desc=f"{w}x{h}")
        elif ext in media.AUDIO_EXT:
            rec.update(kind="audio", desc=f"المدة {media.duration(p):.1f} ثانية")
        elif ext in (".docx", ".xlsx", ".xlsm"):
            try:
                txt = tools._read_docx(p) if ext == ".docx" else tools._read_xlsx(p)
                rec.update(kind="text", text=txt[:30_000], cut=len(txt) > 30_000)
            except Exception:
                rec.update(kind="file")
        elif ext in TEXT_EXT or (rec["size"] < 300_000 and _looks_text(p)):
            txt = p.read_text(encoding="utf-8-sig", errors="replace")
            rec.update(kind="text", text=txt[:30_000], cut=len(txt) > 30_000)
        else:
            rec.update(kind="file")
        return self._json(rec)

    def _start(self, conv, key):
        run = agent.start(conv, key, bool(S.get("think")))
        return {"run": run.id}

    def _chat(self, b):
        if agent.active_run():
            return self._json({"error": "فيه مهمة شغالة، انتظرها أو وقفها"}, 409)
        key = b.get("agent") if b.get("agent") in AGENTS else S["active"]
        text = str(b.get("text") or "").strip()
        atts = b.get("attachments") or []
        if not text and not atts:
            return self._json({"error": "اكتب شي"}, 400)
        conv = store.get(b.get("conv") or "") or store.new(key)
        msg = build_user_message(text, atts)
        agent.chat_dir(conv)
        if not conv["messages"]:
            conv["title"] = store.auto_title(text or (atts[0].get("name") if atts else ""))
        conv["messages"].append(msg)
        conv["agent"] = key
        store.save(conv)
        return self._json({"conv": conv["id"], "title": conv["title"], "message": msg, **self._start(conv, key)})

    def _retry(self, b):
        if agent.active_run():
            return self._json({"error": "فيه مهمة شغالة"}, 409)
        conv = store.get(b.get("conv", ""))
        if not conv:
            return self._json({"error": "المحادثة مو موجودة"}, 404)
        msgs = conv["messages"]
        last_user = max((i for i, m in enumerate(msgs) if m["role"] == "user" and not m.get("internal")), default=-1)
        if last_user < 0:
            return self._json({"error": "ما فيه رسالة أعيدها"}, 400)
        del msgs[last_user + 1:]
        key = b.get("agent") if b.get("agent") in AGENTS else conv.get("agent") or S["active"]
        store.save(conv)
        return self._json({"conv": conv["id"], **self._start(conv, key)})


def _looks_text(p):
    try:
        b = p.read_bytes()[:4000]
        b.decode("utf-8")
        return b"\x00" not in b
    except Exception:
        return False


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = not IS_WIN     # on Windows this flag would let two servers share the port


def _ping_existing():
    import urllib.request
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{PORT}/api/window", data=b"{}", method="POST",
                                     headers={"X-3zT": "1", "Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=3).read()
        return True
    except Exception:
        return False


def main():
    no_window = "--no-window" in sys.argv
    pc.init_dpi()
    LOG.info("start v%s", VERSION)
    srv = None
    for _ in range(20):
        try:
            srv = Server(("127.0.0.1", PORT), H)
            break
        except OSError:
            if _ping_existing():        # already running: just ask it to show a window
                return
            time.sleep(0.5)
    if srv is None:
        LOG.error("port %s is busy", PORT)
        return
    try:
        cleanup()
    except Exception:
        pass
    threading.Thread(target=agent.warmup, daemon=True).start()
    if not no_window:
        threading.Thread(target=watchdog, daemon=True).start()
        threading.Timer(0.3, open_window).start()
    print(f"3zT Agent v{VERSION} on http://127.0.0.1:{PORT}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
