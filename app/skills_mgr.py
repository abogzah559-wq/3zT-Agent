"""Agent skills (SKILL.md folders, same format as Anthropic's agent skills).

Built-in skills ship in app/skills; user-installed ones live in %APPDATA%/3zT-Agent/skills.
The model only sees names + descriptions; `load_skill` returns the full instructions.
"""
import io
import json
import re
import shutil
import urllib.request
import zipfile
from pathlib import Path

from config import DATA_DIR, ROOT

BUILTIN = ROOT / "skills"
USER = DATA_DIR / "skills"
USER.mkdir(parents=True, exist_ok=True)
DISABLED_FILE = DATA_DIR / "skills_disabled.json"


def _front(text):
    """YAML front matter (flat keys; supports quoted values and > / | block values)."""
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?", text, re.S)
    meta = {}
    if m:
        lines = m.group(1).splitlines()
        i = 0
        while i < len(lines):
            line = lines[i]
            i += 1
            if not line.strip() or line[:1] in (" ", "\t") or ":" not in line:
                continue
            k, _, v = line.partition(":")
            v = v.strip()
            if v in (">", "|", ">-", "|-", ">+", "|+"):
                block = []
                while i < len(lines) and (lines[i][:1] in (" ", "\t") or not lines[i].strip()):
                    block.append(lines[i].strip())
                    i += 1
                v = ("\n" if v.startswith("|") else " ").join(x for x in block if x).strip()
            if k.strip() and v:
                meta[k.strip().lower()] = v.strip('"').strip("'")
        text = text[m.end():]
    return meta, text


def disabled():
    try:
        return set(json.loads(DISABLED_FILE.read_text(encoding="utf-8")))
    except Exception:
        return set()


def set_enabled(name, on):
    d = disabled()
    (d.discard if on else d.add)(name)
    DISABLED_FILE.write_text(json.dumps(sorted(d)), encoding="utf-8")


def all_skills():
    """name -> {name, description, path, builtin, enabled}"""
    out, off = {}, disabled()
    for base, builtin in ((BUILTIN, True), (USER, False)):
        if not base.exists():
            continue
        for f in sorted(base.glob("*/SKILL.md")):
            try:
                meta, _ = _front(f.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                continue
            name = meta.get("name") or f.parent.name
            out[name] = {"name": name, "description": meta.get("description", "")[:600],
                         "path": str(f.parent), "builtin": builtin, "enabled": name not in off}
    return out


def catalog():
    """Compact list for the system prompt."""
    items = [s for s in all_skills().values() if s["enabled"]]
    return "\n".join(f"- {s['name']}: {s['description'][:260]}" for s in items)


def load(name):
    s = all_skills().get(name)
    if not s:
        names = ", ".join(all_skills())
        return None, f"ما فيه مهارة بهالاسم. المتاح: {names}"
    folder = Path(s["path"])
    _, body = _front((folder / "SKILL.md").read_text(encoding="utf-8", errors="replace"))
    useful = {".py", ".js", ".mjs", ".ts", ".md", ".sh", ".ps1", ".txt", ".json", ".html", ".css", ".yaml", ".yml"}
    files = [p.relative_to(folder).as_posix() for p in sorted(folder.rglob("*"))
             if p.is_file() and p.suffix.lower() in useful and p.name not in ("SKILL.md", "LICENSE.txt")
             and not {"__pycache__", "schemas", "node_modules"} & set(p.parts)]
    extra = ""
    if files:
        shown = files[:60]
        extra = (f"\n\n---\nملفات المهارة موجودة في: {folder}\n(أي مسار نسبي مثل scripts/... يعني داخل هالمجلد؛ "
                 f"شغّل السكربتات بمسارها الكامل)\n" + "\n".join(f"- {x}" for x in shown)
                 + (f"\n... و{len(files) - 60} ملف ثاني" if len(files) > 60 else ""))
    if len(body) > 30_000:
        body = body[:30_000] + "\n...(المهارة أطول من كذا؛ اقرأ الباقي من SKILL.md بـ read_file)"
    return folder, f"# مهارة: {name}\n{body.strip()}{extra}"


def install(url):
    """Install a skill folder from a GitHub link:
    https://github.com/OWNER/REPO/tree/BRANCH/path/to/skill  (or a repo root that has SKILL.md folders)."""
    m = re.match(r"https?://github\.com/([^/]+)/([^/#?]+)(?:/(?:tree|blob)/([^/]+)/?(.*))?", url.strip())
    if not m:
        raise ValueError("الرابط لازم يكون من GitHub، مثل https://github.com/owner/repo/tree/main/skills/name")
    owner, repo, branch, sub = m.group(1), m.group(2).removesuffix(".git"), m.group(3), (m.group(4) or "").strip("/")
    sub = re.sub(r"/?SKILL\.md$", "", sub)
    branches = [branch] if branch else ["main", "master"]
    data = None
    for br in branches:
        try:
            req = urllib.request.Request(f"https://codeload.github.com/{owner}/{repo}/zip/refs/heads/{br}",
                                         headers={"User-Agent": "3zT-Agent"})
            with urllib.request.urlopen(req, timeout=120) as r:
                data = r.read(200 << 20)
            break
        except Exception:
            continue
    if data is None:
        raise RuntimeError("ما قدرت أنزّل الريبو (تأكد من الرابط واسم الفرع)")
    z = zipfile.ZipFile(io.BytesIO(data))
    top = z.namelist()[0].split("/")[0]
    prefix = f"{top}/{sub}/" if sub else f"{top}/"
    skill_dirs = sorted({n[:-len("SKILL.md")] for n in z.namelist()
                         if n.startswith(prefix) and n.endswith("/SKILL.md")}, key=len)
    if not skill_dirs:
        raise RuntimeError("ما لقيت SKILL.md في هالرابط")
    if prefix + "SKILL.md" in z.namelist():
        skill_dirs = [prefix]
    installed = []
    for d in skill_dirs[:40]:
        meta, _ = _front(z.read(d + "SKILL.md").decode("utf-8", errors="replace"))
        name = re.sub(r"[^\w.-]", "-", meta.get("name") or d.rstrip("/").split("/")[-1])[:60]
        dest = USER / name
        if dest.exists():
            shutil.rmtree(dest)
        for n in z.namelist():
            if n.startswith(d) and not n.endswith("/"):
                rel = n[len(d):]
                if ".." in Path(rel).parts:
                    continue
                out = dest / rel
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(z.read(n))
        installed.append(name)
    return installed


def remove(name):
    s = all_skills().get(name)
    if not s or s["builtin"]:
        return False
    shutil.rmtree(s["path"], ignore_errors=True)
    return True
