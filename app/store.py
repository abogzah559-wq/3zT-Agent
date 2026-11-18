"""Conversation storage: one JSON file per chat, written atomically, plus a light index."""
import json
import os
import threading
import time
import uuid

from config import CHATS_DIR

_lock = threading.RLock()
_cache = {}          # id -> conversation dict (loaded on demand)


def _path(cid):
    safe = "".join(ch for ch in cid if ch.isalnum() or ch in "-_")
    return CHATS_DIR / f"{safe}.json"


def _write(path, obj):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def new(agent):
    cid = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
    conv = {"id": cid, "title": "محادثة جديدة", "agent": agent, "pinned": False,
            "created": time.time(), "updated": time.time(), "messages": []}
    with _lock:
        _cache[cid] = conv
    return conv


def get(cid):
    with _lock:
        if cid in _cache:
            return _cache[cid]
        p = _path(cid)
        if not p.exists():
            return None
        try:
            conv = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return None
        conv.setdefault("messages", [])
        _cache[cid] = conv
        return conv


def save(conv):
    with _lock:
        conv["updated"] = time.time()
        if conv["messages"]:
            _write(_path(conv["id"]), conv)


def delete(cid):
    with _lock:
        _cache.pop(cid, None)
        p = _path(cid)
        if p.exists():
            trash = CHATS_DIR / "_deleted"
            trash.mkdir(exist_ok=True)
            os.replace(p, trash / p.name)


def listing():
    """Light summaries for the sidebar, newest first."""
    out = []
    with _lock:
        seen = set()
        for conv in _cache.values():
            if conv["messages"]:
                out.append(_summary(conv))
                seen.add(conv["id"])
        for p in CHATS_DIR.glob("*.json"):
            cid = p.stem
            if cid in seen:
                continue
            try:
                conv = json.loads(p.read_text(encoding="utf-8"))
                out.append(_summary(conv))
            except Exception:
                continue
    out.sort(key=lambda c: (not c.get("pinned"), -c["updated"]))
    return out


def _summary(conv):
    return {"id": conv["id"], "title": conv.get("title") or "محادثة", "agent": conv.get("agent"),
            "updated": conv.get("updated", 0), "pinned": bool(conv.get("pinned"))}


def auto_title(text):
    t = " ".join((text or "").split())
    if not t:
        return "محادثة جديدة"
    return t[:48] + ("…" if len(t) > 48 else "")
