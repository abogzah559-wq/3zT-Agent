"""FreeVideo bridge: local picture and video generation (MiniMax H3 video+audio, H3 Image, Qwen-Image 2.1).

FreeVideo (github.com/FlashML-org/FreeVideo, Apache-2.0) runs as a ComfyUI plugin that its own Windows launcher
installs and starts. It exposes an agent API under /freevideo/agent/v1 on the ComfyUI address, protected by a
Bearer token stored in <FreeVideo home>/agent/token. This module only talks to that API: it starts the launcher
when FreeVideo is not running, uploads input pictures, submits jobs, waits with progress, downloads the results
into the chat folder, and stops what it started when the app closes.
"""
import base64
import json
import os
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from config import FREEVIDEO_EXE, IS_WIN, NO_WINDOW

API = "/freevideo/agent/v1"
DONE = ("succeeded", "failed", "cancelled", "interrupted")
VIDEO_ASPECTS = ("16:9", "9:16", "1:1", "4:3", "3:4", "21:9", "2:3", "3:2")
IMAGE_ASPECTS = ("1:1", "16:9", "9:16", "4:3", "3:4")
QUALITY = ("light", "medium", "high", "max")
SECTIONS = ("subject_definitions:", "summary:", "detailed_description:")
JSON_UPLOAD_LIMIT = 70 * 1024 * 1024      # base64 grows by a third; the server takes up to 96 MB of JSON

CFG = {"home": Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "FreeVideo", "url": ""}
STARTED = {"proc": None}                  # the launcher we started (stopped again on exit)
_NO_PROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))


class FVError(RuntimeError):
    pass


def _has_token(folder):
    try:
        return (Path(folder) / "agent" / "token").is_file()
    except OSError:
        return False


def find_home():
    """FreeVideo keeps its engine wherever the user chose in the launcher (often Downloads/FreeVideo-engine).
    Look in the usual places, then one level inside the user's main folders and the drive roots."""
    home = Path.home()
    local = Path(os.environ.get("LOCALAPPDATA", str(home)))
    names = ("FreeVideo-engine", "FreeVideo", "freevideo-engine")
    bases = [home / "Downloads", home / "Desktop", home / "Documents", home, local]
    bases += [Path(f"{d}:\\") for d in "CDEFG"] if IS_WIN else []
    for b in bases:
        for n in names:
            if _has_token(b / n):
                return b / n
    for b in bases:
        try:
            for c in b.iterdir():
                if c.is_dir() and (c / "machine.json").is_file() and _has_token(c):
                    return c
        except OSError:
            continue
    return None


def configure(home=None, url=None):
    if home:
        CFG["home"] = Path(os.path.expandvars(os.path.expanduser(str(home).strip())))
    if not _has_token(CFG["home"]):
        found = find_home()
        if found:
            CFG["home"] = found
    if url is not None:
        CFG["url"] = str(url or "").strip().rstrip("/")


def _agent_dir():
    if not _has_token(CFG["home"]):       # installed after the app started: look again
        found = find_home()
        if found:
            CFG["home"] = found
    return CFG["home"] / "agent"


def base_url():
    if CFG["url"]:
        return CFG["url"]
    try:
        value = json.loads((_agent_dir() / "endpoint.json").read_text(encoding="utf-8"))
        if isinstance(value, dict) and str(value.get("url", "")).startswith("http"):
            return str(value["url"]).rstrip("/")
    except (OSError, ValueError):
        pass
    return "http://127.0.0.1:8188"


def _token():
    try:
        return (_agent_dir() / "token").read_text(encoding="ascii").strip() or None
    except OSError:
        return None


def launcher():
    """The FreeVideo launcher executable, if one is on this PC."""
    local = Path(os.environ.get("LOCALAPPDATA", str(Path.home())))
    for c in (FREEVIDEO_EXE, CFG["home"] / "FreeVideo.exe", local / "FreeVideo-launcher" / "FreeVideo.exe",
              Path.home() / "Downloads" / "FreeVideo.exe", Path.home() / "Desktop" / "FreeVideo.exe"):
        if c.is_file():
            return c
    return None


def installed():
    """True once FreeVideo finished its setup at least once (it then writes the agent token)."""
    return _token() is not None


def _request(method, path, body=None, *, timeout=60, raw=False):
    token = _token()
    if not token:
        raise FVError("FreeVideo مو مثبت أو ما اكتمل تثبيته. شغّل install-freevideo.bat مرة وحدة.")
    data = None if body is None else json.dumps(body).encode()
    headers = {"Authorization": "Bearer " + token, "X-FreeVideo-Client": "3zT-Agent"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(base_url() + path, data=data, method=method, headers=headers)
    try:
        with _NO_PROXY.open(req, timeout=timeout) as r:
            payload = r.read()
    except urllib.error.HTTPError as e:
        try:
            problem = (json.loads(e.read()) or {}).get("error") or {}
        except (ValueError, AttributeError):
            problem = {}
        msg = problem.get("message") or f"HTTP {e.code}"
        nxt = problem.get("next")
        details = problem.get("details")
        text = f"FreeVideo رفض الطلب ({problem.get('code', e.code)}): {msg}"
        if nxt:
            text += f"\nالمطلوب: {nxt}"
        if details:
            text += "\n" + json.dumps(details, ensure_ascii=False)[:600]
        if problem.get("code") == "needs_confirmation":
            text += "\nوافق على الطلب في نافذة FreeVideo ثم أعد نفس الطلب."
        raise FVError(text) from None
    except (urllib.error.URLError, OSError, TimeoutError):
        raise FVError("FreeVideo مو شغال حاليًا.") from None
    return payload if raw else json.loads(payload or b"{}")


def status():
    """FreeVideo's own status (ready, version, problem), or None when it is not reachable."""
    try:
        return _request("GET", API, timeout=8)
    except FVError:
        return None


def health():
    s = status()
    return {"installed": installed(), "launcher": str(launcher() or ""), "running": bool(s),
            "ready": bool(s and s.get("ready")), "version": (s or {}).get("freevideo_version"),
            "problem": (s or {}).get("problem"), "home": str(CFG["home"]), "url": base_url()}


_UIA = r"""
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
$A = [System.Windows.Automation.AutomationElement]
$name = [System.Windows.Automation.AutomationElement]::NameProperty
$win = $A::RootElement.FindFirst([System.Windows.Automation.TreeScope]::Children,
  (New-Object System.Windows.Automation.PropertyCondition($name, 'FreeVideo')))
if (-not $win) { 'nowindow'; exit }
foreach ($n in @('Later', 'Launch FreeVideo', 'Open FreeVideo')) {
  $b = $win.FindFirst([System.Windows.Automation.TreeScope]::Descendants,
    (New-Object System.Windows.Automation.PropertyCondition($name, $n)))
  if ($b -and $b.Current.IsEnabled) {
    try { $b.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke(); "clicked:$n"; exit } catch {}
  }
}
'none'
"""


def _press_launch():
    """The launcher only starts ComfyUI after its Launch button is pressed: press it through UI Automation."""
    if not IS_WIN:
        return ""
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", _UIA],
                           capture_output=True, text=True, timeout=25, creationflags=NO_WINDOW)
        return (r.stdout or "").strip()
    except Exception:
        return ""


def ensure_running(progress, cancel, timeout=900):
    """Start FreeVideo through its launcher when needed and wait until its API answers ready."""
    s = status()
    if s and s.get("ready"):
        return s
    if s and not s.get("ready"):
        raise FVError("FreeVideo شغال بس مو جاهز: " + str(s.get("problem") or "افتح نافذة FreeVideo وكمّل التثبيت"))
    exe = launcher()
    if not installed() and not exe:
        raise FVError("FreeVideo مو مثبت. شغّل install-freevideo.bat (يحمّل ويثبت كل شي) ثم جرّب مرة ثانية.")
    if not exe:
        raise FVError("ما لقيت FreeVideo.exe. شغّل install-freevideo.bat عشان يرجع يحمّله.")
    proc = STARTED["proc"]
    if proc is None or proc.poll() is not None:
        progress("أشغّل FreeVideo...")
        STARTED["proc"] = subprocess.Popen([str(exe)], cwd=str(exe.parent), creationflags=NO_WINDOW if IS_WIN else 0)
    t0, hinted, pressed, tries = time.time(), False, False, 0
    while time.time() - t0 < timeout:
        if cancel is not None and cancel.is_set():
            raise FVError("انلغى.")
        s = status()
        if s and s.get("ready"):
            return s
        waited = int(time.time() - t0)
        if not pressed and waited >= 6 and tries < 12:
            tries += 1
            res = _press_launch()
            if res.startswith("clicked:Launch") or res.startswith("clicked:Open"):
                pressed = True
                progress("ضغطت تشغيل في FreeVideo — ينتظر ComfyUI يقوم")
        if waited > 45 and not hinted:
            hinted = True
            progress("FreeVideo لسا يفتح... إذا ظهرت نافذته اضغط Launch / تشغيل")
        else:
            progress(f"أنتظر FreeVideo يجهز ({waited} ث)")
        time.sleep(3)
    raise FVError("FreeVideo ما اشتغل خلال الوقت. افتح نافذة FreeVideo وتأكد إنه مشغّل ComfyUI.")


def free_vram():
    """Ask ComfyUI to unload its models so the chat model gets the card back (best effort)."""
    try:
        req = urllib.request.Request(base_url() + "/free", data=b'{"unload_models": true, "free_memory": true}',
                                     method="POST", headers={"Content-Type": "application/json"})
        _NO_PROXY.open(req, timeout=10).read()
    except Exception:
        pass


def stop():
    """Close the FreeVideo launcher (and its ComfyUI) if this app started it."""
    proc = STARTED["proc"]
    STARTED["proc"] = None
    if proc is None:
        return
    try:
        if IS_WIN:
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True,
                           creationflags=NO_WINDOW, timeout=20)
            home = str(CFG["home"]).replace("'", "''")
            # ComfyUI may be detached from the launcher: stop the python processes running from the FreeVideo folder.
            ps = ("Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath -and $_.ExecutablePath -like '"
                  + home + "*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }")
            subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True,
                           creationflags=NO_WINDOW, timeout=30)
        else:
            proc.terminate()
    except Exception:
        pass


# ---------------- jobs ----------------
def upload(path):
    """Send a local picture/video to FreeVideo; returns its input file id."""
    p = Path(path)
    size = p.stat().st_size
    if size > JSON_UPLOAD_LIMIT:
        raise FVError("الملف كبير مرة للرفع لـ FreeVideo (الحد 70MB). صغّره أول.")
    body = {"name": p.name, "data_base64": base64.b64encode(p.read_bytes()).decode()}
    return _request("POST", API + "/media", body, timeout=600)["file"]


def submit(spec):
    answer = _request("POST", API + "/jobs", spec, timeout=120)
    return answer.get("job") or answer


def wait(job_id, progress, cancel, label):
    """Poll the job until it ends. Cancels it in FreeVideo when the user presses stop."""
    last = None
    while True:
        if cancel is not None and cancel.is_set():
            try:
                _request("POST", f"{API}/jobs/{job_id}/cancel", {}, timeout=20)
            except FVError:
                pass
            raise FVError("انلغى التوليد.")
        view = _request("GET", f"{API}/jobs/{job_id}?wait=20", timeout=40)
        st = view.get("status")
        if st in DONE:
            return view
        pr = view.get("progress") or {}
        frac = pr.get("fraction")
        text = label + (f" — {pr.get('label')}" if pr.get("label") else "")
        if isinstance(frac, (int, float)):
            text += f" {round(frac * 100)}%"
        if st == "queued":
            text = label + " — بالطابور"
        if text != last:
            progress(text)
            last = text


def _check(view, what):
    if view.get("status") != "succeeded":
        err = view.get("error") or {}
        msg = err.get("message") if isinstance(err, dict) else str(err)
        nxt = err.get("next") if isinstance(err, dict) else None
        raise FVError(f"فشل {what} في FreeVideo ({view.get('status')}): {msg or 'بدون تفاصيل'}"
                      + (f"\nالمطلوب: {nxt}" if nxt else ""))
    return view.get("result") or {}


def download(url, target):
    if not url or not str(url).startswith("/"):
        raise FVError("FreeVideo ما رجّع رابط للنتيجة.")
    target = Path(target)
    data = _request("GET", url, timeout=600, raw=True)
    target.write_bytes(data)
    return target


def _unique(out_dir, stem, ext):
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    p = out_dir / f"{stem}-{stamp}{ext}"
    n = 2
    while p.exists():
        p = out_dir / f"{stem}-{stamp}-{n}{ext}"
        n += 1
    return p


def _ext(url, default):
    q = urllib.parse.urlparse(str(url or ""))
    name = urllib.parse.parse_qs(q.query).get("filename", [""])[0] or q.path
    ext = Path(name).suffix.lower()
    return ext if ext in (".png", ".jpg", ".jpeg", ".webp", ".mp4", ".webm", ".mov") else default


def generate_image(args, out_dir, cancel, progress, loras=None, model="auto"):
    """New picture(s), or a change to up to 4 input pictures (args["images"]). Returns saved paths."""
    prompt = str(args.get("prompt") or "").strip()[:2000]
    if not prompt:
        raise FVError("الوصف (prompt) فاضي.")
    spec = {"kind": "image", "prompt": prompt, "label": "3zT"}
    aspect = str(args.get("aspect") or "").strip()
    if aspect in IMAGE_ASPECTS:
        spec["aspect"] = aspect
    elif args.get("width") and args.get("height"):
        spec["width"] = max(256, min(4096, int(args["width"]) // 32 * 32))
        spec["height"] = max(256, min(4096, int(args["height"]) // 32 * 32))
    if args.get("quality") == "high":
        spec["tier"] = "high"
    if model in ("minimax-h3-image", "qwen-image-2.1-turbo"):
        spec["model"] = model
    if args.get("seed") is not None:
        spec["seed"] = int(args["seed"])
    if loras:
        spec["loras"] = [{"name": str(l["name"]), "strength": float(l.get("strength", 1.0))}
                         for l in loras if isinstance(l, dict) and l.get("name")][:8]
    images = [str(x) for x in (args.get("images") or []) if str(x).strip()][:4]
    if images:
        progress("أرفع الصور لـ FreeVideo...")
        spec["images"] = [{"file": upload(p)} for p in images]
    count = max(1, min(4, int(args.get("count") or 1)))
    paths = []
    for i in range(count):
        if i:
            spec.pop("seed", None)
        job = submit(spec)
        label = "يرسم الصورة" + (f" {i + 1}/{count}" if count > 1 else "")
        result = _check(wait(job["id"], progress, cancel, label), "رسم الصورة")
        url = result.get("url") or (result.get("image") or {}).get("url")
        paths.append(download(url, _unique(out_dir, "image", _ext(url, ".png"))))
    return paths


def _enhance(text, seconds, first, progress, cancel):
    """Turn a rough idea into a full H3 prompt with FreeVideo's own local helper model."""
    spec = {"kind": "enhance", "text": text[:12000], "seconds": seconds, "label": "3zT"}
    if first:
        spec["media"] = {"first": {"file": first}}
    try:
        result = _check(wait(submit(spec)["id"], progress, cancel, "يجهّز وصف الفيديو"), "تجهيز الوصف")
        return str(result.get("text") or "").strip() or text
    except FVError as e:
        if "انلغى" in str(e):
            raise
        return text                       # the generation itself still accepts the plain idea


def generate_video(args, out_dir, cancel, progress):
    """A new video with sound (MiniMax H3). Optional first/last frame pictures. Returns [path]."""
    prompt = str(args.get("prompt") or "").strip()
    if not prompt:
        raise FVError("الوصف (prompt) فاضي.")
    seconds = float(args.get("seconds") or 10)
    seconds = max(1.625, min(60.0, seconds))
    first = last = None
    if args.get("first_frame"):
        progress("أرفع الصورة الأولى...")
        first = upload(args["first_frame"])
    if args.get("last_frame"):
        last = upload(args["last_frame"])
    if not any(s in prompt.lower() for s in SECTIONS):
        prompt = _enhance(prompt, seconds, first, progress, cancel)
    spec = {"prompt": prompt, "seconds": round(seconds, 3), "label": "3zT"}
    aspect = str(args.get("aspect") or "").strip()
    spec["aspect"] = aspect if aspect in VIDEO_ASPECTS else "16:9"
    q = str(args.get("quality") or "medium")
    spec["quality"] = q if q in QUALITY else "medium"
    if args.get("seed") is not None:
        spec["seed"] = int(args["seed"])
    media = {}
    if first:
        media["first"] = {"file": first}
    if last:
        media["last"] = {"file": last}
    if media:
        spec["media"] = media
    job = submit(spec)
    result = _check(wait(job["id"], progress, cancel, "يولّد الفيديو"), "توليد الفيديو")
    video = result.get("video") or {}
    url = video.get("url")
    if not url and isinstance(result.get("blocks"), list):
        for b in reversed(result["blocks"]):
            url = ((b or {}).get("video") or {}).get("url")
            if url:
                break
    return [download(url, _unique(out_dir, "video", _ext(url, ".mp4")))]
