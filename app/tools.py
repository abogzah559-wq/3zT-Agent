"""Agent tools + the approval layer.

Rules:
- Reading, browsing, searching the web, screenshots: no approval.
- Creating NEW files inside the workspace (or editing files the agent created this session): no approval.
- Editing an existing file, writing outside the workspace, moving, running commands/scripts,
  opening programs, and mouse/keyboard control: approval (with "always this session" option).
- Deleting: approval EVERY time, and it always goes to the Recycle Bin.
"""
import csv
import difflib
import fnmatch
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

import media
import pc
import skills_mgr
import videotools
import web
from config import EXTRAS_PY, IS_WIN, LOCAL_DIR, MEMORY_FILE, NO_WINDOW

MAX_READ = 60_000
SKIP_DIRS = {"node_modules", ".git", "__pycache__", "venv", ".venv", "site-packages", "$RECYCLE.BIN",
             "System Volume Information", "AppData"}
EXEC_EXT = {".exe", ".bat", ".cmd", ".ps1", ".vbs", ".js", ".msi", ".com", ".scr", ".lnk", ".reg", ".jar", ".py"}

# ---------------- hard limits (always on, every agent) ----------------
_MINOR = r"\b(child|children|kid|kids|minor|minors|underage|under[- ]?age|teen|teens|teenager|preteen|loli|lolita|shota|toddler|schoolgirl|schoolboy|young girl|young boy|little girl|little boy|\d{1,2}[- ]?(yo|year[- ]old))\b|طفل|طفلة|أطفال|اطفال|قاصر|قاصرة|مراهق|مراهقة|بنت صغيرة|ولد صغير"
_SEXUAL = r"\b(nude|nudes|naked|nsfw|sex|sexual|sexy|porn|porno|erotic|explicit|lingerie|topless|bottomless|genital|genitals|breasts?|nipples?|undress(ed)?|strip(ping)?|hentai|seductive|provocative)\b|عاري|عارية|جنس|جنسي|إباحي|اباحي|مثير|مثيرة|بدون ملابس"


def hard_limit(text):
    """Returns a refusal reason if a generation request crosses the built-in limits (every agent)."""
    t = (text or "").lower()
    if re.search(_MINOR, t) and re.search(_SEXUAL, t):
        return "مرفوض: أي محتوى جنسي أو إيحائي فيه قاصرين ممنوع نهائيًا."
    return None


def sexual(text):
    return bool(re.search(_SEXUAL, (text or "").lower()))


def generated_by_app(path, root):
    """Pictures the app generated itself live in <workspace>/chats/<id>/generated."""
    try:
        p = Path(path).resolve()
        return p.parent.name == "generated" and inside(p, Path(root) / "chats")
    except Exception:
        return False


def generation_policy(name, args, policy, root):
    """None, or the reason a generation is refused for this agent.

    - every agent: nothing sexual involving minors; no sexual edits of photos the app did not make itself
      (they may show real people).
    - "safe" agent (the official executor): no sexual or explicit content at all."""
    prompt = str(args.get("prompt", ""))
    reason = hard_limit(prompt)
    if reason:
        return reason
    if policy == "safe" and sexual(prompt):
        return ("المنفذ الرسمي عليه قيود وما يولّد محتوى جنسي أو فاضح. حوّل لوكيل «بدون قيود» أو DeepSeek من فوق "
                "إذا تبي بدون قيود.")
    inputs = list(args.get("images") or []) + [args.get(k) for k in ("first_frame", "last_frame", "path") if args.get(k)]
    if sexual(prompt) and any(not generated_by_app(i, root) for i in inputs):
        return ("مرفوض: ما أسوي تعديل جنسي أو فاضح على صور حقيقية مرفوعة (ممكن تكون لناس حقيقيين). "
                "أقدر أسويه على صور ولّدتها أنا.")
    return None


# ---------------- helpers ----------------
def _p(path, ws):
    p = Path(os.path.expandvars(os.path.expanduser(str(path or "").strip().strip('"'))))
    if not str(path or "").strip():
        p = Path(ws)
    if not p.is_absolute():
        p = Path(ws) / p
    return p.resolve()


def inside(p, ws):
    try:
        Path(p).resolve().relative_to(Path(ws).resolve())
        return True
    except ValueError:
        return False


def _env():
    """Child processes see the extras venv and the bundled node modules (used by skills)."""
    env = dict(os.environ)
    node_mods = LOCAL_DIR / "node" / "node_modules"
    if node_mods.exists():
        env["NODE_PATH"] = str(node_mods) + os.pathsep + env.get("NODE_PATH", "")
    if EXTRAS_PY.exists():
        env["PATH"] = str(EXTRAS_PY.parent) + os.pathsep + env.get("PATH", "")
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def _run(cmd, timeout=600, shell=False, cwd=None):
    r = subprocess.run(cmd, shell=shell, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=timeout, creationflags=NO_WINDOW, cwd=cwd, env=_env())
    out = (r.stdout or "") + (("\n" + r.stderr) if r.stderr else "")
    if len(out) > MAX_READ:
        out = out[:4000] + f"\n...(قطعت {len(out) - MAX_READ + 4000:,} حرف من النص)...\n" + out[-(MAX_READ - 4000):]
    return r.returncode, out


def _ps(script, timeout=900, cwd=None):
    prefix = "[Console]::OutputEncoding=[Text.Encoding]::UTF8; $OutputEncoding=[Text.Encoding]::UTF8; $ProgressPreference='SilentlyContinue'; "
    return _run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command",
                 prefix + script], timeout, cwd=cwd)


def _human(n):
    for u in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or u == "TB":
            return f"{n:.0f} {u}" if u == "B" else f"{n:.1f} {u}"
        n /= 1024


def _unique(p: Path):
    if not p.exists():
        return p
    for i in range(2, 9999):
        c = p.with_name(f"{p.stem} ({i}){p.suffix}")
        if not c.exists():
            return c
    return p


def _read_docx(p):
    with zipfile.ZipFile(p) as z:
        xml = z.read("word/document.xml").decode("utf-8", errors="replace")
    xml = re.sub(r"</w:p>", "\n", xml)
    return re.sub(r"<[^>]+>", "", xml)


def _read_xlsx(p):
    with zipfile.ZipFile(p) as z:
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            s = z.read("xl/sharedStrings.xml").decode("utf-8", errors="replace")
            shared = [re.sub(r"<[^>]+>", "", x) for x in re.findall(r"<si>(.*?)</si>", s, re.S)]
        out = []
        for name in sorted(n for n in z.namelist() if n.startswith("xl/worksheets/sheet")):
            out.append(f"# {Path(name).stem}")
            xml = z.read(name).decode("utf-8", errors="replace")
            for row in re.findall(r"<row[^>]*>(.*?)</row>", xml, re.S)[:2000]:
                cells = []
                for attrs, val in re.findall(r"<c([^>]*)>(.*?)</c>", row, re.S):
                    v = re.search(r"<v>(.*?)</v>", val, re.S)
                    t = re.search(r'\bt="(\w+)"', attrs)
                    txt = v.group(1) if v else re.sub(r"<[^>]+>", "", val)
                    if t and t.group(1) == "s" and v and txt.isdigit() and int(txt) < len(shared):
                        txt = shared[int(txt)]
                    cells.append(txt)
                out.append("\t".join(cells))
    return "\n".join(out)


def _diff(old, new, name):
    d = difflib.unified_diff(old.splitlines(), new.splitlines(), "قبل/" + name, "بعد/" + name, lineterm="", n=2)
    txt = "\n".join(d)
    return txt[:6000] + ("\n..." if len(txt) > 6000 else "")


# ---------------- schemas ----------------
def _fn(name, desc, props, req):
    return {"type": "function", "function": {
        "name": name, "description": desc,
        "parameters": {"type": "object", "properties": props, "required": req}}}


S = {"type": "string"}
I = {"type": "integer"}
N = {"type": "number"}
B = {"type": "boolean"}

TOOLS = {
    # ---- files ----
    "list_dir": _fn("list_dir", "List files and folders in a directory (with sizes and dates).",
                    {"path": S}, ["path"]),
    "read_file": _fn("read_file", "Read a text file (also .docx/.xlsx). Use start_line/max_lines for big files.",
                     {"path": S, "start_line": I, "max_lines": I}, ["path"]),
    "search_files": _fn("search_files", "Find files by name pattern recursively, e.g. pattern '*.mp4' or '*invoice*'.",
                        {"path": S, "pattern": S, "max_results": I}, ["path", "pattern"]),
    "grep": _fn("grep", "Search text inside files (regex, case-insensitive) under a folder.",
                {"path": S, "query": S, "glob": {"type": "string", "description": "e.g. *.py (default all text files)"}}, ["path", "query"]),
    "write_file": _fn("write_file", "Create a new text file (or overwrite with approval). Prefer edit_file for small changes.",
                      {"path": S, "content": S}, ["path", "content"]),
    "edit_file": _fn("edit_file", "Replace an exact unique snippet in a text file with new text.",
                     {"path": S, "old_text": S, "new_text": S}, ["path", "old_text", "new_text"]),
    "make_dir": _fn("make_dir", "Create a folder.", {"path": S}, ["path"]),
    "copy_path": _fn("copy_path", "Copy a file or folder.", {"src": S, "dst": S}, ["src", "dst"]),
    "move_path": _fn("move_path", "Move or rename a file or folder.", {"src": S, "dst": S}, ["src", "dst"]),
    "delete_path": _fn("delete_path", "Delete a file or folder (to the Recycle Bin). Always asks the user.",
                       {"path": S}, ["path"]),
    "find_duplicates": _fn("find_duplicates", "Find duplicate files (same content) in folders. Read-only; writes a CSV report.",
                           {"paths": {"type": "array", "items": S}, "min_size_mb": N}, ["paths"]),
    # ---- system ----
    "run_command": _fn("run_command", "Run a PowerShell command/script on the user's Windows PC and return its output.",
                       {"command": S, "cwd": S, "timeout_sec": I}, ["command"]),
    "run_python": _fn("run_python", "Run a Python script (code string) and return its output.",
                      {"code": S, "timeout_sec": I}, ["code"]),
    "open": _fn("open", "Open a file, folder, URL or app with Windows (like double-clicking it).",
                {"target": S}, ["target"]),
    "system_info": _fn("system_info", "PC status: disks free space, RAM, GPU, top processes by memory.", {}, []),
    # ---- screen / control ----
    "screenshot": _fn("screenshot", "See the user's screen. Coordinates for mouse tools are in THIS image's pixels.",
                      {"screen": {"type": "string", "enum": ["all", "primary"]}}, []),
    "mouse_click": _fn("mouse_click", "Click at x,y (pixels of the latest screenshot). Returns a new screenshot.",
                       {"x": N, "y": N, "button": {"type": "string", "enum": ["left", "right", "middle"]},
                        "clicks": {"type": "integer", "description": "2 = double click"}}, ["x", "y"]),
    "mouse_drag": _fn("mouse_drag", "Drag with the left button from (x1,y1) to (x2,y2).",
                      {"x1": N, "y1": N, "x2": N, "y2": N}, ["x1", "y1", "x2", "y2"]),
    "scroll": _fn("scroll", "Scroll the mouse wheel at x,y. amount>0 up, <0 down (notches).",
                  {"x": N, "y": N, "amount": I}, ["amount"]),
    "type_text": _fn("type_text", "Type text (any language) into the focused window.", {"text": S}, ["text"]),
    "press_keys": _fn("press_keys", "Press a key or shortcut, e.g. 'enter', 'ctrl+s', 'alt+tab', 'win+r'.",
                      {"keys": S}, ["keys"]),
    "list_windows": _fn("list_windows", "List titles of open windows.", {}, []),
    "focus_window": _fn("focus_window", "Bring a window to the front by (part of) its title.", {"title": S}, ["title"]),
    "clipboard": _fn("clipboard", "Read or set the clipboard text.",
                     {"action": {"type": "string", "enum": ["get", "set"]}, "text": S}, ["action"]),
    # ---- web ----
    "web_search": _fn("web_search", "Search the internet. Returns titles, links and snippets.",
                      {"query": S, "count": I}, ["query"]),
    "fetch_url": _fn("fetch_url", "Read a web page as text.", {"url": S}, ["url"]),
    "download": _fn("download", "Download a file, or a video/audio from YouTube/TikTok/X/etc (yt-dlp), into the workspace.",
                    {"url": S, "audio_only": B}, ["url"]),
    # ---- media ----
    "view_image": _fn("view_image", "Look at an image file from disk.", {"path": S}, ["path"]),
    "video_frames": _fn("video_frames", "Look at a video: extracts evenly spaced frames so you can see it.",
                        {"path": S, "count": I}, ["path"]),
    "media_info": _fn("media_info", "Video/audio details (duration, resolution, fps, codecs) via ffprobe.",
                      {"path": S}, ["path"]),
    "ffmpeg": _fn("ffmpeg", "Run ffmpeg to edit/convert/cut/merge/compress video, audio or images. Pass the arguments "
                  "WITHOUT the word ffmpeg, e.g. -i \"C:\\in.mp4\" -vf \"scale=1280:-2\" \"C:\\out.mp4\". "
                  "Never overwrites existing files; pick a new output name.", {"args": S}, ["args"]),
    "transcribe": _fn("transcribe", "Speech-to-text for a video/audio (Whisper large-v3-turbo on GPU). Writes .srt + .txt subtitles.",
                      {"path": S, "language": {"type": "string", "description": "ar, en ... or auto"}}, ["path"]),
    "text_to_speech": _fn("text_to_speech", "Make a natural voice-over MP3 (Microsoft neural voices). Arabic voices: "
                          "ar-SA-HamedNeural (male), ar-SA-ZariyahNeural (female). English: en-US-AndrewNeural, en-US-AvaNeural.",
                          {"text": S, "voice": S, "rate": {"type": "string", "description": "e.g. +10% or -10%"}}, ["text"]),
    "remove_background": _fn("remove_background", "Remove the background of an image -> transparent PNG.",
                             {"path": S}, ["path"]),
    "upscale_image": _fn("upscale_image", "Upscale an image x2 or x4 with Real-ESRGAN (sharper, more detail).",
                         {"path": S, "scale": I, "anime": B}, ["path"]),
    "generate_image": _fn("generate_image", "Create NEW picture(s) from text with the local FreeVideo image model "
                          "(MiniMax H3 Image or Qwen-Image 2.1, up to 16 MP). Write the prompt in ENGLISH with every detail "
                          "the user asked for (subject, style, lighting, composition, any text to draw in quotes). "
                          "To change an existing picture use edit_image.",
                          {"prompt": S, "aspect": {"type": "string", "enum": ["1:1", "16:9", "9:16", "4:3", "3:4"]},
                           "quality": {"type": "string", "enum": ["standard", "high"]}, "count": I, "seed": I},
                          ["prompt"]),
    "edit_image": _fn("edit_image", "Change or combine EXISTING picture(s) (up to 4) with the local FreeVideo image model: "
                      "change clothes/background/style, add or remove things, merge people or products. Prompt in ENGLISH "
                      "saying the change; refer to inputs as image 1, image 2. Pictures only (for video use the video tool).",
                      {"images": {"type": "array", "items": S}, "prompt": S,
                       "aspect": {"type": "string", "enum": ["1:1", "16:9", "9:16", "4:3", "3:4"]}},
                      ["images", "prompt"]),
    "extend_video": _fn("extend_video", "Make an EXISTING video wider / zoomed out (outpainting): the AI paints new "
                        "surroundings around the original as if the camera pulled back, and the original stays untouched "
                        "in the middle. Use this for: extend / complete the sides, make it 21:9 or wider, zoom out, fill "
                        "black bars with real content. (upscale and resize do NOT add new picture content.) Up to 60 s; "
                        "takes several minutes. The tool looks at the video itself; description is optional.",
                        {"path": S, "aspect": {"type": "string", "enum": ["21:9", "16:9", "9:16", "1:1", "4:3", "3:4"]},
                         "zoom": N, "description": S,
                         "quality": {"type": "string", "enum": ["light", "medium", "high", "max"]}}, ["path"]),
    "generate_video": _fn("generate_video", "Generate a NEW video WITH SOUND locally (FreeVideo, MiniMax H3; 2-60 s, 24 fps). "
                          "Prompt in ENGLISH: who/what is there, the action, camera, place, sounds; spoken lines word for word "
                          "in quotes in the user's language. A short idea is fine: FreeVideo expands it. Optional first_frame/"
                          "last_frame pictures (make one with generate_image first to control the look). Takes minutes.",
                          {"prompt": S, "seconds": N,
                           "aspect": {"type": "string", "enum": ["16:9", "9:16", "1:1", "4:3", "3:4", "21:9"]},
                           "quality": {"type": "string", "enum": ["light", "medium", "high", "max"]},
                           "first_frame": S, "last_frame": S, "seed": I}, ["prompt"]),
    # ---- reliable media operations (prefer these over raw ffmpeg) ----
    "video": _fn("video", "Edit/repair a VIDEO with a ready, tested operation (preferred over raw ffmpeg). "
                 "operation: trim(start,end) | compress(target_mb or crf) | resize(width/height) | vertical(mode blur|crop) | "
                 "crop(x,y,width,height) | speed(factor) | reverse | merge(inputs[]) | gif(start,end,width,fps) | "
                 "extract_audio(format) | replace_audio(audio) | mute | fps(fps, smooth) | burn_subtitles(subtitles) | "
                 "overlay(image, position, scale) | rotate(degrees) | normalize_audio | thumbnail(time) | "
                 "repair(presets[]: deflicker, denoise, strong_denoise, temporal, dehalo, deband, deblock, sharpen, color, stabilize) | "
                 "upscale_ai(scale 2|4, anime, height). Output is saved in the chat folder and shown to the user.",
                 {"path": S, "operation": {"type": "string", "enum": videotools.VIDEO_OPS},
                  "start": S, "end": S, "time": S, "target_mb": N, "crf": I, "width": I, "height": I, "x": I, "y": I,
                  "mode": S, "factor": N, "inputs": {"type": "array", "items": S}, "fps": I, "smooth": B,
                  "format": S, "audio": S, "subtitles": S, "image": S, "position": S, "scale": N, "degrees": I,
                  "presets": {"type": "array", "items": {"type": "string", "enum": videotools.REPAIR_PRESETS}},
                  "anime": B}, ["operation"]),
    "image": _fn("image", "Edit an IMAGE with a ready operation: resize(width/height) | crop(x,y,width,height) | rotate(degrees) | "
                 "flip(direction) | convert(format png/jpg/webp) | compress(quality, format) | grayscale | blur(amount) | "
                 "sharpen(amount) | brightness(brightness, contrast, saturation) | denoise. Output shown to the user.",
                 {"path": S, "operation": {"type": "string", "enum": videotools.IMAGE_OPS}, "width": I, "height": I,
                  "x": I, "y": I, "degrees": I, "direction": S, "format": S, "quality": I, "amount": N,
                  "brightness": N, "contrast": N, "saturation": N}, ["path", "operation"]),
    "send_file": _fn("send_file", "Show files to the user in the chat (images/videos/audio play inline, other files get "
                     "open buttons). Use it to deliver results.", {"paths": {"type": "array", "items": S}}, ["paths"]),
    # ---- skills ----
    "load_skill": _fn("load_skill", "Load the full instructions of a skill from the skills list before doing that kind of task.",
                      {"name": S}, ["name"]),
    "install_skill": _fn("install_skill", "Install agent skill(s) from a GitHub link to a folder containing SKILL.md.",
                         {"url": S}, ["url"]),
    # ---- memory ----
    "remember": _fn("remember", "Save a lasting note about the user or his preferences for future chats.",
                    {"note": S}, ["note"]),
}

GENERATE = {"generate_image", "edit_image", "generate_video", "extend_video"}
READ_ONLY = ["list_dir", "read_file", "search_files", "grep", "find_duplicates", "system_info", "screenshot",
             "list_windows", "web_search", "fetch_url", "view_image", "video_frames", "media_info", "load_skill"]
CONTROL = {"mouse_click", "mouse_drag", "scroll", "type_text", "press_keys", "focus_window"}
ALL = list(TOOLS)


def schemas(names):
    return [TOOLS[n] for n in names if n in TOOLS]


# ---------------- approval ----------------
def needs_approval(name, args, ctx):
    """Returns None, or {"cat", "title", "detail", "diff"?} describing what will happen.

    cat "delete" can never be auto-approved; the others accept "always for this session"."""
    ws, root, created = ctx["base"], ctx["workspace"], ctx["created"]
    try:
        if name in READ_ONLY or name in GENERATE or name in ("remember", "make_dir", "download", "ffmpeg",
                                                              "transcribe", "text_to_speech", "remove_background",
                                                              "upscale_image", "video", "image", "load_skill",
                                                              "send_file"):
            if name == "make_dir" and not inside(_p(args.get("path"), ws), root):
                return {"cat": "write", "title": "إنشاء مجلد خارج مجلد الشغل", "detail": str(_p(args.get("path"), ws))}
            return None
        if name == "clipboard":
            return None
        if name == "install_skill":
            return {"cat": "write", "title": "تثبيت مهارة من GitHub", "detail": str(args.get("url", ""))}
        if name in ("write_file", "edit_file"):
            p = _p(args.get("path"), ws)
            mine = str(p) in created
            if not p.exists():
                if inside(p, root):
                    return None
                return {"cat": "write", "title": "إنشاء ملف خارج مجلد الشغل", "detail": str(p)}
            if mine and inside(p, root):
                return None
            try:
                old = p.read_text(encoding="utf-8", errors="replace")
            except Exception:
                old = ""
            if name == "edit_file":
                new = old.replace(args.get("old_text", ""), args.get("new_text", ""), 1)
            else:
                new = args.get("content", "")
            return {"cat": "write", "title": "تعديل ملف موجود", "detail": str(p), "diff": _diff(old, new, p.name)}
        if name == "copy_path":
            d = _p(args.get("dst"), ws)
            if inside(d, root) and not d.exists():
                return None
            return {"cat": "write", "title": "نسخ", "detail": f"{_p(args.get('src'), ws)}\n← إلى: {d}"}
        if name == "delete_path":
            p = _p(args.get("path"), ws)
            size = ""
            if p.is_file():
                size = f" ({_human(p.stat().st_size)})"
            elif p.is_dir():
                size = " (مجلد كامل بكل اللي فيه)"
            return {"cat": "delete", "title": "حذف إلى سلة المحذوفات", "detail": f"{p}{size}"}
        if name == "move_path":
            return {"cat": "move", "title": "نقل / إعادة تسمية",
                    "detail": f"{_p(args.get('src'), ws)}\n← إلى: {_p(args.get('dst'), ws)}"}
        if name == "run_command":
            return {"cat": "command", "title": "تشغيل أمر PowerShell", "detail": args.get("command", ""), "code": True}
        if name == "run_python":
            return {"cat": "command", "title": "تشغيل كود Python", "detail": args.get("code", ""), "code": True}
        if name == "open":
            t = str(args.get("target", "")).strip().strip('"')
            if re.match(r"^https?://", t, re.I):
                return None
            tp = _p(t, ws)
            if tp.suffix.lower() not in EXEC_EXT and tp.exists():
                return None             # opening a document / folder / image is harmless
            return {"cat": "open", "title": "تشغيل برنامج / سكربت", "detail": t}
        if name in CONTROL:
            what = {"mouse_click": f"ضغطة عند ({args.get('x')}, {args.get('y')})",
                    "mouse_drag": f"سحب من ({args.get('x1')}, {args.get('y1')}) إلى ({args.get('x2')}, {args.get('y2')})",
                    "scroll": f"تمرير {args.get('amount')}",
                    "type_text": "كتابة: " + str(args.get("text", ""))[:300],
                    "press_keys": "ضغط: " + str(args.get("keys", "")),
                    "focus_window": "تفعيل نافذة: " + str(args.get("title", ""))}[name]
            return {"cat": "control", "title": "التحكم بالماوس والكيبورد", "detail": what}
    except Exception as e:
        return {"cat": "write", "title": name, "detail": f"{args} ({e})"}
    return {"cat": "command", "title": name, "detail": json.dumps(args, ensure_ascii=False)[:1000]}


# ---------------- execution ----------------
class Result:
    def __init__(self, text, images=None, media=None, error=False, created=None):
        self.text, self.images, self.media, self.error = text, images or [], media or [], error
        self.created = created or []      # new files outside the chat folder (deleted with the chat)


def _shot_result(ws, screen="all", note=""):
    raw = Path(ws) / "_shots" / f"shot_{time.strftime('%Y%m%d_%H%M%S')}_{int(time.time() * 1000) % 1000}.png"
    geo = pc.capture(raw, screen)
    jpg, w, h = media.to_jpeg(raw, 1280, 5)
    if jpg is None:
        jpg, w, h = raw, geo["w"], geo["h"]
    pc.set_scaled(w, h)
    try:
        raw.unlink()
    except OSError:
        pass
    return Result(f"{note}لقطة الشاشة ({w}x{h} بكسل، الشاشة الحقيقية {geo['w']}x{geo['h']}). "
                  f"أي إحداثيات تعطيها للماوس تكون بمقاس هالصورة.", images=[str(jpg)])


def execute(name, args, ctx):
    """ctx: workspace, created(set), progress(fn), cancel(Event), generate(fn)."""
    res = _execute(name, args, ctx)
    if res.text.startswith("خطأ"):
        res.error = True
    return res


def _execute(name, args, ctx):
    ws = ctx["base"]          # this chat's folder: relative paths and all outputs go here
    try:
        if name == "list_dir":
            p = _p(args.get("path"), ws)
            if not p.is_dir():
                return Result(f"خطأ: مو مجلد: {p}", error=True)
            items = sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
            lines = []
            for c in items[:400]:
                try:
                    st = c.stat()
                    when = time.strftime("%Y-%m-%d %H:%M", time.localtime(st.st_mtime))
                    lines.append(f"[DIR] {c.name}  · {when}" if c.is_dir() else f"{c.name}  ({_human(st.st_size)}) · {when}")
                except OSError:
                    lines.append(c.name)
            more = f"\n... و{len(items) - 400} عنصر ثاني" if len(items) > 400 else ""
            return Result(f"{p} — {len(items)} عنصر\n" + "\n".join(lines) + more)

        if name == "read_file":
            p = _p(args.get("path"), ws)
            if not p.is_file():
                return Result(f"خطأ: الملف مو موجود: {p}", error=True)
            ext = p.suffix.lower()
            if ext in media.IMAGE_EXT:
                return _execute("view_image", {"path": str(p)}, ctx)
            if ext == ".docx":
                text = _read_docx(p)
            elif ext in (".xlsx", ".xlsm"):
                text = _read_xlsx(p)
            else:
                raw = p.read_bytes()[:8 << 20]
                if b"\x00" in raw[:4000]:
                    return Result(f"خطأ: هذا ملف ثنائي ({ext}, {_human(p.stat().st_size)}) ما ينقرا كنص.", error=True)
                text = raw.decode("utf-8-sig", errors="replace")
            lines = text.splitlines()
            start = max(1, int(args.get("start_line") or 1))
            count = int(args.get("max_lines") or 0) or len(lines)
            chunk = lines[start - 1:start - 1 + count]
            body = "\n".join(f"{i:>5}│ {ln}" for i, ln in enumerate(chunk, start))
            if len(body) > MAX_READ:
                body = body[:MAX_READ] + "\n...(الملف طويل، استخدم start_line و max_lines للباقي)"
            return Result(f"{p} — {len(lines)} سطر\n{body}")

        if name == "search_files":
            root = _p(args.get("path"), ws)
            pat = args.get("pattern") or "*"
            if not any(ch in pat for ch in "*?["):
                pat = f"*{pat}*"
            cap = min(int(args.get("max_results") or 200), 1000)
            hits = []
            for dp, dns, fns in os.walk(root):
                dns[:] = [d for d in dns if d not in SKIP_DIRS and not d.startswith(".")]
                for n in dns + fns:
                    if fnmatch.fnmatch(n.lower(), pat.lower()):
                        hits.append(os.path.join(dp, n))
                        if len(hits) >= cap or ctx["cancel"].is_set():
                            break
                if len(hits) >= cap or ctx["cancel"].is_set():
                    break
            return Result(f"لقيت {len(hits)} نتيجة{' (وقفت عند الحد)' if len(hits) >= cap else ''}:\n" + "\n".join(hits))

        if name == "grep":
            root = _p(args.get("path"), ws)
            rx = re.compile(args["query"], re.I)
            glob = args.get("glob") or "*"
            out, files_seen = [], 0
            targets = [root] if root.is_file() else None
            walker = ((str(root.parent), [], [root.name]),) if targets else os.walk(root)
            for dp, dns, fns in walker:
                dns[:] = [d for d in dns if d not in SKIP_DIRS and not d.startswith(".")]
                for fn in fns:
                    if not fnmatch.fnmatch(fn.lower(), glob.lower()):
                        continue
                    fp = os.path.join(dp, fn)
                    try:
                        if os.path.getsize(fp) > 5 << 20:
                            continue
                        with open(fp, "rb") as f:
                            data = f.read()
                        if b"\x00" in data[:2000]:
                            continue
                        files_seen += 1
                        for i, line in enumerate(data.decode("utf-8", errors="replace").splitlines(), 1):
                            if rx.search(line):
                                out.append(f"{fp}:{i}: {line.strip()[:220]}")
                                if len(out) >= 300:
                                    break
                    except OSError:
                        continue
                    if len(out) >= 300 or ctx["cancel"].is_set():
                        break
                if len(out) >= 300 or ctx["cancel"].is_set():
                    break
            return Result(f"فحصت {files_seen} ملف، {len(out)} تطابق:\n" + "\n".join(out))

        if name == "write_file":
            p = _p(args.get("path"), ws)
            p.parent.mkdir(parents=True, exist_ok=True)
            existed = p.exists()
            p.write_text(args.get("content", ""), encoding="utf-8", newline="")
            if not existed:
                ctx["created"].add(str(p))
            return Result(f"{'تم التعديل' if existed else 'تم الإنشاء'}: {p} ({_human(p.stat().st_size)})",
                          media=[str(p)] if not existed else [], created=[str(p)] if not existed else [])

        if name == "edit_file":
            p = _p(args.get("path"), ws)
            old = p.read_text(encoding="utf-8", errors="replace")
            needle = args.get("old_text", "")
            n = old.count(needle) if needle else 0
            if n == 0:
                return Result("خطأ: النص المطلوب تبديله مو موجود في الملف حرفيًا. اقرأ الملف وانسخ المقطع بالضبط.", error=True)
            if n > 1:
                return Result(f"خطأ: النص موجود {n} مرات؛ وسّع المقطع عشان يكون فريد.", error=True)
            p.write_text(old.replace(needle, args.get("new_text", ""), 1), encoding="utf-8", newline="")
            return Result(f"تم التعديل: {p}")

        if name == "make_dir":
            p = _p(args.get("path"), ws)
            p.mkdir(parents=True, exist_ok=True)
            return Result(f"المجلد جاهز: {p}")

        if name == "copy_path":
            src, dst = _p(args["src"], ws), _p(args["dst"], ws)
            if dst.is_dir() and src.name:
                dst = dst / src.name
            dst.parent.mkdir(parents=True, exist_ok=True)
            if src.is_dir():
                shutil.copytree(src, dst, dirs_exist_ok=True)
            else:
                shutil.copy2(src, dst)
            ctx["created"].add(str(dst))
            return Result(f"انتسخ إلى: {dst}", created=[str(dst)])

        if name == "move_path":
            src, dst = _p(args["src"], ws), _p(args["dst"], ws)
            if not src.exists():
                return Result(f"خطأ: ما لقيت {src}", error=True)
            if dst.is_dir():
                dst = dst / src.name
            if dst.exists():
                return Result(f"خطأ: الوجهة موجودة أصلًا: {dst} — اختر اسم ثاني.", error=True)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
            return Result(f"انتقل إلى: {dst}")

        if name == "delete_path":
            p = _p(args["path"], ws)
            if not p.exists():
                return Result(f"خطأ: ما لقيت {p}", error=True)
            if len(p.parts) <= 2 or p == Path.home():
                return Result("خطأ: مرفوض حذف جذر قرص أو مجلد المستخدم كامل.", error=True)
            if IS_WIN:
                kind = "DeleteDirectory" if p.is_dir() else "DeleteFile"
                lit = str(p).replace("'", "''")
                code, out = _ps("Add-Type -AssemblyName Microsoft.VisualBasic; "
                                f"[Microsoft.VisualBasic.FileIO.FileSystem]::{kind}('{lit}', 'OnlyErrorDialogs', 'SendToRecycleBin')", 300)
                if code != 0 or p.exists():
                    return Result(f"خطأ: فشل الحذف: {out.strip()[-500:]}", error=True)
                return Result(f"انحذف لسلة المحذوفات: {p}")
            trash = Path.home() / ".3zt-trash"
            trash.mkdir(exist_ok=True)
            shutil.move(str(p), str(trash / f"{int(time.time())}_{p.name}"))
            return Result(f"انحذف (انتقل للسلة): {p}")

        if name == "find_duplicates":
            return Result(find_duplicates([_p(x, ws) for x in args.get("paths") or [ws]],
                                          float(args.get("min_size_mb") or 1), ws, ctx["cancel"]))

        if name == "run_command":
            cwd = str(_p(args.get("cwd"), ws)) if args.get("cwd") else ws
            to = max(5, min(int(args.get("timeout_sec") or 900), 7200))
            if IS_WIN:
                code, out = _ps(args["command"], to, cwd=cwd)
            else:
                code, out = _run(args["command"], to, shell=True, cwd=cwd)
            return Result(f"exit={code}\n{out}", error=code != 0)

        if name == "run_python":
            scripts = Path(ws) / "_scripts"
            scripts.mkdir(parents=True, exist_ok=True)
            f = scripts / f"script_{time.strftime('%Y%m%d_%H%M%S')}.py"
            f.write_text(args["code"], encoding="utf-8")
            to = max(5, min(int(args.get("timeout_sec") or 600), 7200))
            py = str(EXTRAS_PY) if EXTRAS_PY.exists() else sys.executable.replace("pythonw.exe", "python.exe")
            env_code, out = _run([py, "-X", "utf8", str(f)], to, cwd=ws)
            return Result(f"exit={env_code}\n{out}", error=env_code != 0)

        if name == "open":
            t = str(args["target"]).strip().strip('"')
            if not re.match(r"^\w+://", t):
                tp = _p(t, ws)
                if tp.exists():
                    t = str(tp)
            if IS_WIN:
                os.startfile(t)  # noqa
            else:
                subprocess.Popen(["xdg-open", t])
            return Result(f"انفتح: {t}")

        if name == "system_info":
            return Result(system_info())

        if name == "screenshot":
            return _shot_result(ws, args.get("screen") or "all")

        if name in CONTROL:
            if name == "mouse_click":
                rx, ry = pc.click(args["x"], args["y"], args.get("button") or "left", args.get("clicks") or 1)
                note = f"ضغطت عند ({args['x']}, {args['y']}) = شاشة ({rx}, {ry}). "
            elif name == "mouse_drag":
                pc.drag(args["x1"], args["y1"], args["x2"], args["y2"])
                note = "سحبت. "
            elif name == "scroll":
                pc.scroll(args.get("x"), args.get("y"), args.get("amount") or -3)
                note = "مررت. "
            elif name == "type_text":
                pc.type_text(str(args.get("text", "")))
                note = "كتبت النص. "
            elif name == "press_keys":
                pc.press(str(args["keys"]))
                note = f"ضغطت {args['keys']}. "
            else:
                got = pc.focus_window(str(args["title"]))
                if not got:
                    return Result(f"خطأ: ما لقيت نافذة فيها \"{args['title']}\"", error=True)
                note = f"فعّلت النافذة: {got}. "
            time.sleep(0.7)
            return _shot_result(ws, "all", note + "هذي الشاشة بعدها. ")

        if name == "list_windows":
            return Result("\n".join(f"• {t}" for _, t in pc.list_windows()) or "ما فيه نوافذ")

        if name == "clipboard":
            if not IS_WIN:
                return Result("خطأ: متاح على ويندوز بس", error=True)
            if args.get("action") == "set":
                lit = str(args.get("text", "")).replace("'", "''")
                _ps(f"Set-Clipboard -Value '{lit}'", 30)
                return Result("انحفظ النص في الحافظة")
            code, out = _ps("Get-Clipboard -Raw", 30)
            return Result(out.strip() or "(الحافظة فاضية أو فيها شي مو نص)")

        if name == "web_search":
            return Result(web.search(args["query"], max(3, min(int(args.get("count") or 8), 15))))

        if name == "fetch_url":
            return Result(web.read_page(args["url"]))

        if name == "download":
            out_dir = Path(ws) / "downloads"
            files = media.download(args["url"], out_dir, bool(args.get("audio_only")))
            return Result("تم التحميل:\n" + "\n".join(f"{f} ({_human(Path(f).stat().st_size)})" for f in files), media=files)

        if name == "view_image":
            p = _p(args["path"], ws)
            if not p.is_file():
                return Result(f"خطأ: ما لقيت {p}", error=True)
            jpg, w, h = media.to_jpeg(p)
            if not jpg:
                return Result("خطأ: ما قدرت أفتح الصورة", error=True)
            return Result(f"الصورة: {p}", images=[str(jpg)])

        if name == "video_frames":
            p = _p(args["path"], ws)
            if not p.is_file():
                return Result(f"خطأ: ما لقيت {p}", error=True)
            desc, frames = media.video_frames(p, max(2, min(int(args.get("count") or 8), 16)))
            return Result(desc, images=frames)

        if name == "media_info":
            return Result(media.summarize_probe(_p(args["path"], ws)))

        if name == "ffmpeg":
            argv = shlex.split(args["args"], posix=not IS_WIN)
            argv = [a[1:-1] if len(a) >= 2 and a[0] == a[-1] and a[0] in "\"'" else a for a in argv]
            if argv and argv[0].lower() in ("ffmpeg", "ffmpeg.exe"):
                argv = argv[1:]
            argv = [a for a in argv if a not in ("-y", "-n")]
            code, out = _run(["ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "warning", "-n", *argv], 7200, cwd=ws)
            outp = Path(argv[-1]) if argv else None
            if outp is not None and not outp.is_absolute():
                outp = Path(ws) / outp
            if "already exists" in out:
                return Result(f"خطأ: الملف {outp} موجود أصلًا وما أكتب فوقه. اختر اسم جديد للناتج.", error=True)
            ok = code == 0 and outp is not None and outp.exists() and outp.stat().st_size > 0
            info = f"تم: {outp} ({_human(outp.stat().st_size)})" if ok else ""
            return Result(f"exit={code}\n{info}\n{out[-3500:]}".strip(), media=[str(outp)] if ok else [],
                          error=not ok, created=[str(outp)] if ok else [])

        if name == "transcribe":
            p = _p(args["path"], ws)
            ctx["progress"]("يفرّغ الصوت بـ Whisper... (أول مرة ينزل النموذج)")
            res = media.transcribe(p, Path(ws) / "subtitles", args.get("language") or "auto")
            return Result(f"تم التفريغ ({res['language']}, {res['duration']} ثانية, على {res['device']} خلال {res['seconds']} ث)\n"
                          f"SRT: {res['srt']}\nTXT: {res['txt']}\n\nالنص:\n{res['text']}", media=[res["srt"], res["txt"]])

        if name == "text_to_speech":
            voice = args.get("voice") or "ar-SA-HamedNeural"
            out = Path(ws) / "audio" / f"tts_{time.strftime('%Y%m%d_%H%M%S')}.mp3"
            out.parent.mkdir(parents=True, exist_ok=True)
            media.tts(args["text"], voice, out, args.get("rate") or "+0%")
            return Result(f"تم الصوت: {out}", media=[str(out)])

        if name == "remove_background":
            p = _p(args["path"], ws)
            out = _unique(Path(ws) / "edited" / f"{p.stem}_nobg.png")
            out.parent.mkdir(parents=True, exist_ok=True)
            ctx["progress"]("يشيل الخلفية...")
            media.remove_background(p, out)
            jpg, _, _ = media.to_jpeg(out, 768)
            return Result(f"تم: {out}", images=[str(jpg)] if jpg else [], media=[str(out)])

        if name == "upscale_image":
            p = _p(args["path"], ws)
            scale = 2 if int(args.get("scale") or 4) <= 2 else 4
            out = _unique(Path(ws) / "edited" / f"{p.stem}_x{scale}.png")
            out.parent.mkdir(parents=True, exist_ok=True)
            ctx["progress"](f"يكبّر الصورة x{scale} بـ Real-ESRGAN...")
            media.upscale(p, out, scale, bool(args.get("anime")))
            return Result(f"تم التكبير: {out}", media=[str(out)])

        if name == "video":
            src = _p(args.get("path") or (args.get("inputs") or [""])[0], ws)
            if args.get("operation") == "merge":
                args = {**args, "inputs": [str(_p(x, ws)) for x in args.get("inputs") or []]}
            for k in ("audio", "subtitles", "image"):
                if args.get(k):
                    args = {**args, k: str(_p(args[k], ws))}
            outs, msg = videotools.video(args, src, Path(ws) / "edited", ctx["progress"], ctx["cancel"],
                                         media.realesrgan_exe())
            return Result(msg, media=[str(o) for o in outs])

        if name == "image":
            outs, msg = videotools.image(args, _p(args.get("path"), ws), Path(ws) / "edited", ctx["progress"])
            jpg, _, _ = media.to_jpeg(outs[0], 768)
            return Result(msg, images=[str(jpg)] if jpg else [], media=[str(o) for o in outs])

        if name == "send_file":
            ok, missing = [], []
            for x in args.get("paths") or []:
                p = _p(x, ws)
                (ok if p.exists() else missing).append(str(p))
            if not ok:
                return Result("خطأ: ما لقيت الملفات: " + ", ".join(missing), error=True)
            return Result("انعرضت للمستخدم: " + ", ".join(ok) + (f"\nما لقيت: {missing}" if missing else ""), media=ok)

        if name == "load_skill":
            _, text = skills_mgr.load(str(args.get("name", "")).strip())
            return Result(text)

        if name == "install_skill":
            names = skills_mgr.install(str(args["url"]))
            return Result("تثبتت المهارات: " + ", ".join(names) + " — تقدر تستخدمها بـ load_skill")

        if name in GENERATE:
            args = dict(args)
            if name == "edit_image":
                imgs = args.get("images") or ([args["image_path"]] if args.get("image_path") else [])
                if isinstance(imgs, str):
                    imgs = [imgs]
                args["images"] = [str(_p(i, ws)) for i in imgs][:4]
                if not args["images"]:
                    return Result("خطأ: حدد صورة وحدة على الأقل في images.", error=True)
                for i in args["images"]:
                    if Path(i).suffix.lower() in media.VIDEO_EXT:
                        return Result("خطأ: edit_image للصور بس. للفيديو استخدم أداة video (مثلاً operation=repair) "
                                      "أو اطلع صورة منه بـ video operation=thumbnail.", error=True)
                    if not Path(i).is_file():
                        return Result(f"خطأ: الصورة مو موجودة: {i}", error=True)
            if name == "extend_video":
                args["path"] = str(_p(args.get("path"), ws))
                if not Path(args["path"]).is_file():
                    return Result(f"خطأ: الفيديو مو موجود: {args['path']}", error=True)
                if Path(args["path"]).suffix.lower() not in media.VIDEO_EXT:
                    return Result("خطأ: extend_video للفيديو بس.", error=True)
                args["prompt"] = args.get("description", "")
            for k in ("first_frame", "last_frame"):
                if args.get(k):
                    args[k] = str(_p(args[k], ws))
                    if not Path(args[k]).is_file():
                        return Result(f"خطأ: الصورة مو موجودة: {args[k]}", error=True)
            reason = generation_policy(name, args, ctx.get("policy", "safe"), ctx["workspace"])
            if reason:
                return Result(reason, error=True)
            files = ctx["generate"](name, args)
            imgs = []
            if name not in ("generate_video", "extend_video"):
                for f in files[:4]:
                    jpg, _, _ = media.to_jpeg(f, 768)
                    if jpg:
                        imgs.append(str(jpg))
            return Result("تم التوليد وانحفظ في:\n" + "\n".join(str(f) for f in files),
                          images=imgs, media=[str(f) for f in files])

        if name == "remember":
            note = " ".join(str(args.get("note", "")).split())
            if not note:
                return Result("خطأ: الملاحظة فاضية", error=True)
            with open(MEMORY_FILE, "a", encoding="utf-8") as f:
                f.write(f"- {note}\n")
            return Result("انحفظت في الذاكرة.")

    except subprocess.TimeoutExpired:
        return Result("خطأ: انتهى الوقت قبل ما يخلص الأمر", error=True)
    except KeyError as e:
        return Result(f"خطأ: ناقص المدخل {e}", error=True)
    except RuntimeError as e:             # our own readable errors (generation, media helpers)
        return Result(f"خطأ: {e}", error=True)
    except Exception as e:
        return Result(f"خطأ: {type(e).__name__}: {e}", error=True)
    return Result(f"خطأ: أداة غير معروفة: {name}", error=True)


# ---------------- recycle (used when a chat is deleted) ----------------
def recycle(paths):
    """Send files/folders to the Recycle Bin (Windows) or ~/.3zt-trash. Returns how many were removed."""
    paths = [Path(p) for p in paths if p and Path(p).exists()]
    if not paths:
        return 0
    if IS_WIN:
        lst = Path(os.environ.get("TEMP", ".")) / f"3zt_recycle_{int(time.time() * 1000)}.txt"
        lst.write_text("\n".join(str(p) for p in paths), encoding="utf-8")
        lit = str(lst).replace("'", "''")
        _ps("Add-Type -AssemblyName Microsoft.VisualBasic; "
            f"Get-Content -LiteralPath '{lit}' -Encoding UTF8 | ForEach-Object {{ "
            "if (Test-Path -LiteralPath $_ -PathType Container) { [Microsoft.VisualBasic.FileIO.FileSystem]::DeleteDirectory($_, 'OnlyErrorDialogs', 'SendToRecycleBin') } "
            "elseif (Test-Path -LiteralPath $_) { [Microsoft.VisualBasic.FileIO.FileSystem]::DeleteFile($_, 'OnlyErrorDialogs', 'SendToRecycleBin') } }", 600)
        lst.unlink(missing_ok=True)
    else:
        trash = Path.home() / ".3zt-trash"
        trash.mkdir(exist_ok=True)
        for p in paths:
            try:
                shutil.move(str(p), str(trash / f"{int(time.time() * 1000)}_{p.name}"))
            except OSError:
                pass
    return sum(1 for p in paths if not p.exists())


# ---------------- system info ----------------
def system_info():
    import stats
    lines = []
    s = stats.get()
    if s.get("ram_total"):
        lines.append(f"الرام: {s['ram_used']} / {s['ram_total']} GB")
    if s.get("cpu") is not None:
        lines.append(f"المعالج: {s['cpu']}%")
    g = s.get("gpu")
    if g:
        lines.append(f"الكرت: {g['name']} — VRAM {g['vram_used']} / {g['vram_total']} GB، استخدام {g['util']}%، حرارة {g['temp']}°")
    if IS_WIN:
        for d in "CDEFGHIJ":
            root = f"{d}:\\"
            if os.path.exists(root):
                try:
                    u = shutil.disk_usage(root)
                    lines.append(f"القرص {d}: فاضي {_human(u.free)} من {_human(u.total)}")
                except OSError:
                    pass
        code, out = _ps("Get-Process | Sort-Object WorkingSet64 -Descending | Select-Object -First 12 "
                        "Name,Id,@{n='MB';e={[math]::Round($_.WorkingSet64/1MB)}} | Format-Table -AutoSize | Out-String -Width 200", 30)
        lines.append("أكثر البرامج استهلاكًا للرام:\n" + out.strip())
    else:
        u = shutil.disk_usage("/")
        lines.append(f"القرص /: فاضي {_human(u.free)} من {_human(u.total)}")
    return "\n".join(lines)


# ---------------- duplicates ----------------
def _fingerprint(path, size, chunk=4 << 20):
    h = hashlib.blake2b(digest_size=20)
    h.update(str(size).encode())
    with open(path, "rb") as f:
        if size <= chunk * 3:
            h.update(f.read())
        else:
            for off in (0, size // 2 - chunk // 2, size - chunk):
                f.seek(off)
                h.update(f.read(chunk))
    return h.hexdigest()


def find_duplicates(roots, min_mb, ws, cancel):
    min_size = int(min_mb * (1 << 20))
    by_size, scanned = {}, 0
    for root in roots:
        if not root.exists():
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            if cancel.is_set():
                return "انلغى"
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
            for fn in filenames:
                fp = os.path.join(dirpath, fn)
                try:
                    st = os.stat(fp)
                except OSError:
                    continue
                scanned += 1
                if st.st_size >= min_size:
                    by_size.setdefault(st.st_size, []).append(fp)
    groups = []
    for size, files in by_size.items():
        if len(files) < 2:
            continue
        by_fp = {}
        for fp in files:
            try:
                by_fp.setdefault(_fingerprint(fp, size), []).append(fp)
            except OSError:
                pass
        for same in by_fp.values():
            if len(same) > 1:
                same.sort(key=lambda x: os.path.getmtime(x))
                groups.append((size, same))
    groups.sort(key=lambda g: g[0] * (len(g[1]) - 1), reverse=True)
    wasted = sum(sz * (len(fs) - 1) for sz, fs in groups)
    Path(ws).mkdir(parents=True, exist_ok=True)
    out = Path(ws) / f"duplicates_{time.strftime('%Y%m%d_%H%M%S')}.csv"
    with open(out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["group", "size_MB", "keep_or_dup", "path"])
        for i, (sz, fs) in enumerate(groups, 1):
            for j, fp in enumerate(fs):
                w.writerow([i, round(sz / 2**20, 1), "original(oldest)" if j == 0 else "duplicate", fp])
    lines = [f"فحصت {scanned:,} ملف. لقيت {len(groups)} مجموعة مكررة، والمساحة المهدرة {_human(wasted)}.",
             f"التقرير الكامل: {out}", ""]
    for i, (sz, fs) in enumerate(groups[:40], 1):
        lines.append(f"[{i}] {_human(sz)} × {len(fs)} نسخ:")
        lines += [f"   {'الأصل' if j == 0 else 'نسخة'}: {fp}" for j, fp in enumerate(fs)]
    if len(groups) > 40:
        lines.append(f"... و{len(groups) - 40} مجموعة ثانية في التقرير")
    return "\n".join(lines)
