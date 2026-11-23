"""Model backends: DeepSeek (cloud) and the local llama.cpp server. Both speak OpenAI-style SSE.

Both stream generators yield (kind, value) tuples:
  ("think", str) ("text", str) ("tool_calls", [..]) ("usage", {..}) ("error", str)
"""
import json
import socket
import time
import urllib.error
import urllib.request
import uuid

import localai
from config import DEEPSEEK_URL, LLAMA_URL


def _post(url, body, headers=None, timeout=600):
    req = urllib.request.Request(
        url, data=json.dumps(body, ensure_ascii=False).encode("utf-8"), method="POST",
        headers={"Content-Type": "application/json", **(headers or {})})
    return urllib.request.urlopen(req, timeout=timeout)


def _get_json(url, timeout=5):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.load(r)


def describe_error(e):
    if isinstance(e, urllib.error.HTTPError):
        try:
            body = e.read().decode("utf-8", errors="replace")[:600]
        except Exception:
            body = ""
        try:
            msg = json.loads(body).get("error")
            if isinstance(msg, dict):
                msg = msg.get("message")
            body = msg or body
        except Exception:
            pass
        return f"HTTP {e.code}: {body}".strip()
    if isinstance(e, urllib.error.URLError):
        return f"ما قدرت أتصل: {e.reason}"
    if isinstance(e, (socket.timeout, TimeoutError)):
        return "انتهت مهلة الاتصال"
    return f"{type(e).__name__}: {e}"


def new_call_id():
    return "call_" + uuid.uuid4().hex[:12]


# ===================== message conversion =====================
def to_deepseek(msgs, flatten=False):
    """Internal messages -> DeepSeek chat format. Images must already be replaced by captions.

    reasoning_content is passed back on every assistant message (DeepSeek returns 400 otherwise
    when tools are in use). flatten=True turns tool traffic into plain text (fallback path).
    """
    out = []
    for m in msgs:
        r = m["role"]
        if r == "assistant":
            if flatten:
                txt = m.get("content") or ""
                for t in m.get("tool_calls") or []:
                    txt += f"\n[استخدمت الأداة {t['name']} بـ {json.dumps(t['args'], ensure_ascii=False)[:800]}]"
                out.append({"role": "assistant", "content": txt.strip() or "..."})
                continue
            a = {"role": "assistant", "content": m.get("content") or "",
                 "reasoning_content": m.get("reasoning") or ""}
            if m.get("tool_calls"):
                a["tool_calls"] = [{"id": t["id"], "type": "function", "function": {
                    "name": t["name"], "arguments": json.dumps(t["args"], ensure_ascii=False)}}
                    for t in m["tool_calls"]]
            out.append(a)
        elif r == "tool":
            if flatten:
                out.append({"role": "user", "content": f"[نتيجة {m.get('name', 'الأداة')}]\n{m['content']}"})
            else:
                out.append({"role": "tool", "tool_call_id": m["tool_call_id"], "content": m["content"]})
        else:
            out.append({"role": r, "content": m.get("content") or ""})
    if flatten:   # merge consecutive same-role messages (API requires alternation for some models)
        merged = []
        for m in out:
            if merged and merged[-1]["role"] == m["role"] and m["role"] != "system":
                merged[-1]["content"] += "\n\n" + m["content"]
            else:
                merged.append(dict(m))
        out = merged
    return out


# ===================== streaming =====================
def stream_deepseek(key, model, effort, msgs, tools, cancel):
    """msgs are internal messages (captions already applied)."""
    attempt, flatten = 0, False
    while True:
        attempt += 1
        body = {"model": model, "messages": to_deepseek(msgs, flatten), "stream": True,
                "stream_options": {"include_usage": True},
                "thinking": {"type": "enabled"}, "reasoning_effort": effort}
        if tools and not flatten:
            body["tools"] = tools
        try:
            resp = _post(DEEPSEEK_URL + "/chat/completions", body,
                         {"Authorization": "Bearer " + key, "Accept": "text/event-stream"}, timeout=300)
            break
        except urllib.error.HTTPError as e:
            err = describe_error(e)
            if e.code == 400 and not flatten and attempt <= 2:
                flatten = True          # history shape rejected -> retry with plain-text history
                continue
            if e.code in (429, 500, 502, 503, 504) and attempt <= 3 and not cancel.is_set():
                time.sleep(2 * attempt)
                continue
            if e.code == 401:
                err = "مفتاح DeepSeek غلط أو منتهي. غيّره من الإعدادات."
            elif e.code == 402:
                err = "رصيد DeepSeek خلص. اشحن من platform.deepseek.com"
            yield "error", "DeepSeek: " + err
            return
        except Exception as e:
            if attempt <= 3 and not cancel.is_set():
                time.sleep(2 * attempt)
                continue
            yield "error", "DeepSeek: " + describe_error(e)
            return

    yield from _sse(resp, cancel, "DeepSeek")


def _sse(resp, cancel, label):
    """Parse an OpenAI-style SSE stream into (kind, value) tuples."""
    calls = {}
    try:
        for raw in resp:
            if cancel.is_set():
                break
            line = raw.decode("utf-8", errors="replace").strip()
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            try:
                obj = json.loads(data)
            except Exception:
                continue
            if obj.get("error"):
                err = obj["error"]
                yield "error", f"{label}: " + str(err.get("message") if isinstance(err, dict) else err)
                return
            if obj.get("usage"):
                yield "usage", obj["usage"]
            if not obj.get("choices"):
                continue
            d = obj["choices"][0].get("delta") or {}
            if d.get("reasoning_content"):
                yield "think", d["reasoning_content"]
            if d.get("content"):
                yield "text", d["content"]
            for tc in d.get("tool_calls") or []:
                c = calls.setdefault(tc.get("index", 0), {"id": "", "name": "", "args": ""})
                c["id"] = tc.get("id") or c["id"]
                f = tc.get("function") or {}
                c["name"] += f.get("name") or ""
                c["args"] += f.get("arguments") or ""
    except Exception as e:
        yield "error", f"{label}: انقطع الاتصال (" + describe_error(e) + ")"
        return
    finally:
        try:
            resp.close()
        except Exception:
            pass
    if calls and not cancel.is_set():
        res = []
        for i in sorted(calls):
            c = calls[i]
            try:
                args = json.loads(c["args"] or "{}")
                if not isinstance(args, dict):
                    args = {"value": args}
            except Exception:
                args = {"_raw": c["args"]}
            res.append({"id": c["id"] or new_call_id(), "name": c["name"].strip(), "args": args})
        yield "tool_calls", res


def stream_local(model, msgs, tools, cancel, think):
    """Local llama.cpp server. msgs carry images_b64 on user messages."""
    body = localai.request_body(model, msgs, tools, think)
    resp = None
    for attempt in range(3):
        try:
            resp = _post(LLAMA_URL + "/v1/chat/completions", body, {"Accept": "text/event-stream"}, timeout=900)
            break
        except urllib.error.HTTPError as e:
            err = describe_error(e)
            if e.code == 503 and attempt < 2 and not cancel.is_set():   # still loading
                time.sleep(3)
                continue
            if "image" in err.lower() and any(isinstance(m.get("content"), list) for m in body["messages"]):
                yield "error", "النموذج المحلي ما قدر يقرأ الصورة (ملف الرؤية mmproj ناقص؟): " + err
                return
            yield "error", "النموذج المحلي: " + err
            return
        except Exception as e:
            if attempt < 2 and not cancel.is_set():
                time.sleep(2)
                continue
            yield "error", "النموذج المحلي: " + describe_error(e) + " — النموذج مو شغال، جرّب ترسل مرة ثانية."
            return
    yield from _sse(resp, cancel, "النموذج المحلي")


def deepseek_check(key):
    """Validate a key quickly (used by the settings screen)."""
    try:
        req = urllib.request.Request(DEEPSEEK_URL + "/user/balance",
                                     headers={"Authorization": "Bearer " + key})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.load(r)
        infos = data.get("balance_infos") or []
        bal = ", ".join(f"{b.get('total_balance')} {b.get('currency')}" for b in infos)
        return True, bal or "شغال"
    except Exception as e:
        return False, describe_error(e)
