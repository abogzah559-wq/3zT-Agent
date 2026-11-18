"""The agent loop, model/VRAM management and run bookkeeping.

A Run lives on the server, independent of the browser: the UI can refresh or reconnect and
pick the stream back up from any event index. Every event mirrors a mutation of the stored
conversation, so the UI renders live runs and saved chats with the same code.
"""
import json
import logging
import threading
import time
import urllib.parse
import uuid
from pathlib import Path

import comfy
import llm
import media
import store
import tools
from config import AGENTS, MEMORY_FILE, OLLAMA_URL, model_of

LOG = logging.getLogger("3zt")

S = {}                      # live settings (set by server)
STATUS = {k: "off" for k in AGENTS}       # off | loading | ready | cloud | nokey | missing
PULL = {}                   # model -> {"pct", "text"} while downloading
VRAM_LOCK = threading.RLock()
ALWAYS = set()              # approval categories allowed for the whole session
CREATED = set()             # files the agent created this session (editable without asking)
RUNS = {}                   # run_id -> Run
WINDOW = {"gone": False}

TOOL_CAP = {"ollama": 12_000, "deepseek": 50_000}
STORE_CAP = 50_000


def media_url(path):
    return "/media?p=" + urllib.parse.quote(str(path))


# ============================ model management ============================
def local_models():
    return {model_of(k, S) for k, a in AGENTS.items() if a["kind"] == "ollama"}


def refresh_status():
    loaded = set(llm.ollama_loaded())
    installed = None
    for k, a in AGENTS.items():
        if a["kind"] == "deepseek":
            STATUS[k] = "cloud" if S.get("deepseek_key") else "nokey"
            continue
        if STATUS[k] in ("loading", "pulling"):
            continue
        m = llm.norm_tag(model_of(k, S))
        if m in loaded:
            STATUS[k] = "ready"
        else:
            if installed is None:
                installed = set(llm.ollama_installed())
            STATUS[k] = "off" if (m in installed or not installed) else "missing"


def pull_model(model, progress=None):
    """Download a model through Ollama with progress. Returns (ok, error)."""
    PULL[model] = {"pct": 0, "text": "يبدأ التحميل..."}
    try:
        resp = llm._post(OLLAMA_URL + "/api/pull", {"model": model, "stream": True}, timeout=7200)
        last = 0
        for raw in resp:
            try:
                ev = json.loads(raw)
            except Exception:
                continue
            if ev.get("error"):
                return False, ev["error"]
            st = ev.get("status", "")
            if ev.get("total"):
                pct = int(ev.get("completed", 0) * 100 / ev["total"])
                txt = f"ينزّل {model}: {ev.get('completed', 0) / 2**30:.2f} / {ev['total'] / 2**30:.2f} GB"
            else:
                pct, txt = PULL[model]["pct"], f"{model}: {st}"
            PULL[model] = {"pct": pct, "text": txt}
            if progress and time.time() - last > 0.5:
                progress(f"{txt}|{pct}")
                last = time.time()
        return True, ""
    except Exception as e:
        return False, llm.describe_error(e)
    finally:
        PULL.pop(model, None)


def ensure_local(key, progress=None):
    """Make sure the agent's local model is the one in VRAM. Returns error text or ''."""
    model = model_of(key, S)
    with VRAM_LOCK:
        if llm.norm_tag(model) in llm.ollama_loaded():
            STATUS[key] = "ready"
            return ""
        if not llm.ollama_ok():
            return "Ollama مو شغال. سكّر البرنامج وافتحه من الاختصار، أو شغّل Ollama."
        for k, a in AGENTS.items():
            if a["kind"] == "ollama" and k != key and model_of(k, S) != model:
                llm.ollama_unload(model_of(k, S))
                STATUS[k] = "off"
        if llm.norm_tag(model) not in llm.ollama_installed():
            STATUS[key] = "pulling"
            ok, err = pull_model(model, progress)
            if not ok:
                STATUS[key] = "missing"
                return f"ما قدرت أنزّل النموذج {model}: {err}"
        STATUS[key] = "loading"
        if progress:
            progress("يحمّل النموذج في كرت الشاشة...")
        ok, err = llm.ollama_load(model, S["num_ctx"])
        STATUS[key] = "ready" if ok else "off"
        return "" if ok else f"ما قدرت أحمّل {model}: {err}"


def switch(key):
    """The agent you switch to starts; the others switch off (except a warm executor while on DeepSeek)."""
    S["active"] = key
    target = AGENTS[key]

    def work():
        with VRAM_LOCK:
            for k, a in AGENTS.items():
                if k == key or a["kind"] != "ollama":
                    continue
                keep = target["kind"] == "deepseek" and k == "executor" and S.get("keep_executor_warm")
                if not keep and model_of(k, S) != (model_of(key, S) if target["kind"] == "ollama" else None):
                    llm.ollama_unload(model_of(k, S))
                    STATUS[k] = "off"
            if target["kind"] == "ollama":
                ensure_local(key)
            elif S.get("keep_executor_warm") and llm.ollama_ok():
                ensure_local("executor")
            refresh_status()

    if not any(r.running() for r in RUNS.values()):
        threading.Thread(target=work, daemon=True).start()


def warmup():
    for _ in range(40):
        if llm.ollama_ok():
            break
        time.sleep(1)
    key = S.get("active", "executor")
    try:
        if AGENTS[key]["kind"] == "ollama":
            ensure_local(key)
        elif S.get("keep_executor_warm"):
            ensure_local("executor")
    except Exception:
        LOG.exception("warmup")
    refresh_status()


def unload_all():
    for m in local_models():
        llm.ollama_unload(m)


# ============================ prompts ============================
def read_memory():
    try:
        return MEMORY_FILE.read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def system_prompt(key):
    ws = S["workspace"]
    now = time.strftime("%Y-%m-%d %H:%M (%A)")
    mem = read_memory()
    base = f"""أنت 3zT Agent، مساعد شخصي ذكي يشتغل على كمبيوتر صاحبه مباشرة.
- الوقت الحالي: {now}. الجهاز: ويندوز، كرت NVIDIA RTX 4070 Super (12GB)، رام 16GB.
- رد دايمًا بالعربي باللهجة السعودية، بوضوح واختصار، واستخدم Markdown (عناوين وقوائم وجداول وكود) لما يفيد.
- مجلد الشغل: {ws} — أي ملف تسويه احفظه فيه إذا ما انطلب مكان ثاني. المرفقات تنحفظ في {ws}\\_uploads.
- الأوامر تشتغل في PowerShell. ffmpeg و ffprobe متوفرين للفيديو والصوت والصور.

## الصلاحيات
- القراءة والبحث وأخذ لقطة شاشة وإنشاء ملفات جديدة في مجلد الشغل: تسويها مباشرة.
- تعديل ملف موجود، الكتابة برا مجلد الشغل، النقل، تشغيل الأوامر والبرامج، والتحكم بالماوس والكيبورد: النظام يطلب موافقة صاحب الجهاز تلقائيًا، فلا تسأله قبلها، استدعِ الأداة وهو يوافق أو يرفض.
- الحذف يروح لسلة المحذوفات ويحتاج موافقته كل مرة. إذا رفض أي خطوة لا تعيدها ولا تلتف عليها.

## الحدود الثابتة (ما تتغير أبد)
- ممنوع أي محتوى جنسي أو إيحائي فيه قاصرين، بأي شكل أو صيغة.
- ممنوع تعديل صور أشخاص حقيقيين بشكل جنسي أو مهين.

## طريقة الشغل
- افهم الطلب، وإذا كان واضح نفّذه على طول بدون أسئلة كثيرة. إذا فيه غموض حقيقي اسأل سؤال واحد.
- بعد أي خطوة مهمة تأكد من النتيجة (اقرأ الملف، شيك على الفيديو بـ media_info، أو خذ لقطة شاشة).
- التحكم بالجهاز: خذ screenshot أول، والإحداثيات تكون بمقاس الصورة اللي شفتها. كل أداة تحكم ترجع لك لقطة جديدة؛ تأكد إن الخطوة نجحت قبل اللي بعدها.
- الإنترنت: web_search للبحث و fetch_url لقراءة صفحة، و download للتحميل (يدعم يوتيوب وتيك توك وإكس).
- الصور والفيديو: لتعديل صورة موجودة edit_image، لصورة جديدة generate_image، للفيديو generate_video، وكلها بوصف إنجليزي ينفذ الطلب حرفيًا.
  ولتفريغ الكلام وترجمات SRT استخدم transcribe، وللتعليق الصوتي text_to_speech، ولإزالة الخلفية remove_background، وللتكبير upscale_image.
- إذا عرفت معلومة دايمة عن صاحب الجهاز أو تفضيلاته وطلب تحفظها، استخدم remember.
- في النهاية قل باختصار وش سويت بالضبط ووين الملفات. الصور والفيديو الناتجة تطلع له في المحادثة تلقائيًا."""
    if mem:
        base += f"\n\n## ملاحظات محفوظة عن صاحب الجهاز\n{mem[-4000:]}"
    if AGENTS[key]["role"] == "planner":
        return base + """

## دورك: المخطط
فكّر بعمق قبل ما ترد. تقدر تتصفح الملفات وتقرأها وتبحث في النت وتشوف الشاشة عشان تفهم الوضع، لكن ما تنفذ أي تغيير.
اكتب خطة محكمة: الهدف، الخطوات بالتفصيل (مسارات وأوامر ffmpeg / PowerShell دقيقة)، المخاطر، وكيف نتأكد إن الشغل تم صح.
اختم دايمًا بقسم عنوانه بالضبط "## خطة للمنفذ" فيه خطوات مرقمة جاهزة للتنفيذ فقط."""
    return base + """

## دورك: المنفذ
استخدم الأدوات وخلّص المهمة كاملة خطوة خطوة. إذا فيه خطة من المخطط في المحادثة اتبعها بالترتيب."""


# ============================ context building ============================
def _msg_chars(m):
    n = len(m.get("content") or "")
    n += sum(len(json.dumps(t.get("args", {}), ensure_ascii=False)) for t in m.get("tool_calls") or [])
    return n + 2400 * len(m.get("images") or [])


def _turns(msgs):
    turns, cur = [], []
    for m in msgs:
        if m["role"] == "user" and not m.get("internal") and cur:
            turns.append(cur)
            cur = []
        cur.append(m)
    if cur:
        turns.append(cur)
    return turns


def build_context(conv, kind, budget):
    """Stored messages -> model messages, within a char budget. Images stay as paths here."""
    src = [m for m in conv["messages"] if m["role"] in ("user", "assistant", "tool")]
    cap = TOOL_CAP[kind]
    out = []
    for m in src:
        m2 = {k: v for k, v in m.items() if k in ("role", "content", "reasoning", "tool_calls", "tool_call_id",
                                                     "name", "images")}
        if m["role"] == "tool":
            c = m2.get("content") or ""
            if len(c) > cap:
                m2["content"] = c[:cap] + f"\n...(الناتج أطول: {len(c):,} حرف)"
        out.append(m2)
        if m["role"] == "tool" and m.get("images"):
            out[-1] = {**m2, "images": None}
            out.append({"role": "user", "internal": True, "images": m["images"],
                        "content": f"(هذي الصورة من نتيجة الأداة {m.get('name', '')})"})

    # keep images only on the 3 most recent image-bearing messages (max 12 images)
    kept, n_img = 0, 0
    for m in reversed(out):
        if m.get("images"):
            if kept < 3 and n_img + len(m["images"]) <= 12:
                kept += 1
                n_img += len(m["images"])
            else:
                m["content"] = (m.get("content") or "") + "\n[صورة قديمة انشالت من الذاكرة — استخدم view_image إذا تحتاجها]"
                m["images"] = None

    turns = _turns(out)
    total = lambda: sum(_msg_chars(m) for t in turns for m in t)  # noqa: E731
    if total() > budget:      # 1) shrink old tool outputs
        for t in turns[:-1]:
            for m in t:
                if m["role"] == "tool" and len(m.get("content") or "") > 1500:
                    m["content"] = m["content"][:1500] + "\n...(انقص لأنه قديم)"
    dropped = 0
    while total() > budget and len(turns) > 1:   # 2) drop oldest turns
        turns.pop(0)
        dropped += 1
    if total() > budget:      # 3) last turn alone is huge: shrink its tool outputs too
        for m in turns[-1]:
            if m["role"] == "tool" and len(m.get("content") or "") > 3000:
                m["content"] = m["content"][:3000] + "\n...(انقص عشان الذاكرة)"
    res = [m for t in turns for m in t]
    if dropped:
        res = [{"role": "user", "content": f"(ملاحظة النظام: المحادثة طويلة، فانشال أقدم {dropped} جزء منها من الذاكرة.)"},
               {"role": "assistant", "content": "تمام."}] + res
    return res


def attach_images(msgs, kind, run):
    """Ollama: base64 images. DeepSeek: replace images with captions from the local vision model."""
    for m in msgs:
        imgs = [p for p in (m.get("images") or []) if Path(p).exists()]
        m.pop("images", None)
        if not imgs:
            continue
        if kind == "ollama":
            m["images_b64"] = [run.b64(p) for p in imgs]
        else:
            m["content"] = (m.get("content") or "") + "\n\n" + run.caption(imgs)
    return msgs


# ============================ run ============================
class Run:
    def __init__(self, conv, key, think):
        self.id = uuid.uuid4().hex[:10]
        self.conv, self.key, self.think = conv, key, think
        self.kind = AGENTS[key]["kind"]
        self.cancel = threading.Event()
        self.events, self.cond = [], threading.Condition()
        self.done = False
        self.pending = {}
        self._b64 = {}
        self.started = time.time()
        self.base = len(conv["messages"])      # messages that existed before this run

    def running(self):
        return not self.done

    # ---- events ----
    def emit(self, type_, **kw):
        with self.cond:
            self.events.append({"seq": len(self.events), "type": type_, **kw})
            self.cond.notify_all()

    def finish(self):
        with self.cond:
            self.events.append({"seq": len(self.events), "type": "done"})
            self.done = True
            self.cond.notify_all()

    def events_from(self, i, timeout=15):
        with self.cond:
            self.cond.wait_for(lambda: len(self.events) > i or self.done, timeout)
            return self.events[i:], self.done

    def progress(self, text):
        self.emit("progress", text=text)

    # ---- conversation mutations (mirrored by events) ----
    def add(self, msg):
        self.conv["messages"].append(msg)
        self.emit("msg", message=msg)
        store.save(self.conv)

    def notice(self, text, level="error"):
        self.add({"role": "notice", "level": level, "content": text})

    # ---- images ----
    def b64(self, p):
        if p not in self._b64:
            self._b64[p] = media.b64(p)
        return self._b64[p]

    def caption(self, paths):
        caps = self.conv.setdefault("captions", {})
        k = "|".join(paths)
        if k in caps:
            return caps[k]
        if not llm.ollama_ok():
            return "[صورة مرفقة — ما قدرت أوصفها لأن Ollama مو شغال]"
        loaded = [m for m in llm.ollama_loaded() if m in {llm.norm_tag(x) for x in local_models()}]
        model = loaded[0] if loaded else model_of("executor", S)
        if not loaded:
            err = ensure_local("executor", self.progress)
            if err:
                return f"[صورة مرفقة — ما قدرت أوصفها: {err}]"
        self.progress("أخلي Qwen يوصف الصورة للمخطط...")
        q = None
        if len(paths) > 1:
            q = (f"These are {len(paths)} images in order (e.g. video frames or screenshots). Describe each one briefly "
                 "(numbered), then summarize what happens overall. Transcribe any visible text exactly.")
        text = llm.ollama_caption(model, [self.b64(p) for p in paths], S["num_ctx"], q)
        caps[k] = f"[وصف الصورة (من نموذج الرؤية المحلي)]:\n{text}"
        return caps[k]

    # ---- approvals ----
    def ask(self, call_id, info):
        if info["cat"] != "delete" and info["cat"] in ALWAYS:
            return "always"
        aid = uuid.uuid4().hex[:10]
        ev = threading.Event()
        self.pending[aid] = {"event": ev, "answer": None, "call_id": call_id, **info}
        self.emit("approval", id=aid, call_id=call_id, cat=info["cat"], title=info["title"],
                  detail=info.get("detail", ""), diff=info.get("diff", ""), code=bool(info.get("code")),
                  can_always=info["cat"] != "delete")
        while not ev.wait(0.4):
            if self.cancel.is_set() or WINDOW["gone"]:
                break
        p = self.pending.pop(aid, {})
        ans = p.get("answer") or "no"
        if ans == "always" and info["cat"] != "delete":
            ALWAYS.add(info["cat"])
        elif ans == "always":
            ans = "yes"
        self.emit("approval_done", id=aid, answer=ans)
        return ans

    def answer(self, aid, ans):
        p = self.pending.get(aid)
        if p:
            p["answer"] = ans if ans in ("yes", "always", "no") else "no"
            p["event"].set()
        return bool(p)

    def stop(self):
        self.cancel.set()
        for p in list(self.pending.values()):
            p["event"].set()

    # ---- generation (VRAM juggling) ----
    def generate(self, name, args):
        out_dir = Path(S["workspace"]) / "generated"
        out_dir.mkdir(parents=True, exist_ok=True)
        self.progress("أفضّي الكرت للتوليد...")
        with VRAM_LOCK:
            unload_all()
            for k, a in AGENTS.items():
                if a["kind"] == "ollama":
                    STATUS[k] = "off"
            try:
                comfy.ensure_running(self.progress)
                fn = {"generate_image": comfy.generate_image, "edit_image": comfy.edit_image,
                      "generate_video": comfy.generate_video}[name]
                return fn(args, out_dir, self.cancel, self.progress)
            finally:
                comfy.free_vram()
                if self.kind == "ollama":
                    ensure_local(self.key, self.progress)


def _strip_think_tags(text):
    """Some local models leak <think>...</think> into content; keep only the answer."""
    if "</think>" in text:
        return text.split("</think>", 1)[1].lstrip()
    return text


def run_agent(run: Run):
    conv, key = run.conv, run.key
    a = AGENTS[key]
    kind = a["kind"]
    names = tools.PLANNER_TOOLS if a["role"] == "planner" else tools.ALL
    schemas = tools.schemas(names)
    ctx = {"workspace": S["workspace"], "created": CREATED, "progress": run.progress,
           "cancel": run.cancel, "generate": run.generate}
    try:
        if kind == "deepseek" and not S.get("deepseek_key"):
            run.notice("حط مفتاح DeepSeek من الإعدادات ⚙️ عشان يشتغل المخطط.")
            return
        if kind == "ollama":
            err = ensure_local(key, run.progress)
            if err:
                run.notice(err)
                return
        sysmsg = {"role": "system", "content": system_prompt(key)}
        budget = 500_000 if kind == "deepseek" else int(S["num_ctx"] * 2.3) - len(sysmsg["content"]) - 9000
        budget = max(budget, 12_000)
        max_steps = int(S.get("max_steps") or 40)
        fails, repeats, last_sig, stop_tools = {}, 0, None, False

        for step in range(max_steps + 1):
            if run.cancel.is_set():
                break
            final_step = step == max_steps
            msgs = [sysmsg] + attach_images(build_context(conv, kind, budget), kind, run)
            use_tools = None if (stop_tools or final_step) else schemas
            if final_step:
                msgs.append({"role": "user", "content": "(النظام: وصلت حد الخطوات. وقف الأدوات واكتب ملخص وش خلصت ووش باقي.)"})
            am = {"role": "assistant", "content": "", "reasoning": "", "agent": key}
            conv["messages"].append(am)
            run.emit("assistant", agent=key)
            if kind == "deepseek":
                gen = llm.stream_deepseek(S["deepseek_key"], S["deepseek_model"], S.get("deepseek_effort", "high"),
                                          msgs, use_tools, run.cancel)
            else:
                gen = llm.stream_ollama(model_of(key, S), msgs, use_tools, run.cancel, run.think, S["num_ctx"])
            calls, err = [], None
            last_save = time.time()
            for t, v in gen:
                if t == "think":
                    am["reasoning"] += v
                    run.emit("think", text=v)
                elif t == "text":
                    am["content"] += v
                    run.emit("text", text=v)
                elif t == "tool_calls":
                    calls = v
                elif t == "usage":
                    conv["usage"] = conv.get("usage", 0) + int(v.get("prompt_tokens", 0)) + int(v.get("completion_tokens", 0))
                    run.emit("usage", total=conv["usage"])
                elif t == "error":
                    err = v
                if time.time() - last_save > 3:
                    store.save(conv)
                    last_save = time.time()
            if calls and stop_tools:          # told to stop using tools: never execute more
                calls = []
                if not am["content"]:
                    am["content"] = "ما قدرت أكمل: نفس الخطوة فشلت أكثر من مرة. شوف آخر خطأ فوق وقل لي كيف تبيني أكمل."
                    run.emit("text", text=am["content"])
            cleaned = _strip_think_tags(am["content"])
            if cleaned != am["content"]:
                am["content"] = cleaned
                run.emit("replace_text", text=cleaned)
            if calls:
                am["tool_calls"] = calls
                run.emit("tool_calls", calls=calls)
            if not am["content"] and not am["reasoning"] and not calls:
                if conv["messages"] and conv["messages"][-1] is am:
                    conv["messages"].pop()
                    run.emit("drop_assistant")
            store.save(conv)
            if err:
                run.notice(err)
                return
            if not calls or run.cancel.is_set():
                break

            for c in calls:
                if run.cancel.is_set():
                    break
                name, args = c["name"], c.get("args") or {}
                tm = {"role": "tool", "tool_call_id": c["id"], "name": name}
                if "_raw" in args:
                    res = tools.Result("خطأ: المدخلات مو JSON صحيح. أعد الاستدعاء بمدخلات صحيحة.", error=True)
                elif name not in names:
                    res = tools.Result(f"خطأ: الأداة {name} مو متاحة لك" +
                                       (" (المخطط يقرأ بس؛ التنفيذ للمنفذ)." if a["role"] == "planner" else "."), error=True)
                else:
                    info = tools.needs_approval(name, args, S["workspace"], CREATED)
                    ans = "yes"
                    if info:
                        ans = run.ask(c["id"], info)
                        tm["approval"] = {"title": info["title"], "detail": info.get("detail", "")[:2000], "answer": ans}
                    if ans == "no":
                        res = tools.Result("صاحب الجهاز رفض هالخطوة. لا تعيدها ولا تلتف عليها؛ كمّل بغيرها أو اسأله.", error=True)
                        tm["denied"] = True
                    else:
                        run.emit("tool_start", id=c["id"], name=name)
                        t0 = time.time()
                        res = tools.execute(name, args, ctx)
                        tm["ms"] = int((time.time() - t0) * 1000)
                text = res.text
                if len(text) > STORE_CAP:
                    text = text[:STORE_CAP] + f"\n...(انقص الناتج، كان {len(text):,} حرف)"
                sig = name + json.dumps(args, sort_keys=True, ensure_ascii=False)
                repeats = repeats + 1 if sig == last_sig else 0
                last_sig = sig
                fails[name] = fails.get(name, 0) + 1 if res.error else 0
                if fails[name] >= 3 or repeats >= 2:
                    stop_tools = True
                    text += ("\n\n[النظام: نفس المحاولة تتكرر بدون فايدة. وقف استخدام الأدوات واشرح لصاحب الجهاز "
                             "باختصار وش المشكلة ووش تقترح.]")
                tm["content"] = text
                tm["error"] = bool(res.error)
                if res.images:
                    tm["images"] = res.images
                if res.media:
                    tm["media"] = [{"url": media_url(p), "path": str(p), "kind": _kind(p)} for p in res.media]
                run.add(tm)
    except Exception as e:
        LOG.exception("agent error")
        run.notice(f"خطأ داخلي: {type(e).__name__}: {e}")
    finally:
        _close_open_calls(run)
        if run.cancel.is_set():
            run.notice("وقفته.", "info")
        conv["agent"] = key
        store.save(conv)
        run.finish()


def _close_open_calls(run):
    """Every tool call must have a result, or the next request to the API is rejected."""
    msgs = run.conv["messages"]
    answered = {m.get("tool_call_id") for m in msgs if m["role"] == "tool"}
    missing = []
    for m in reversed(msgs):
        if m["role"] == "user" and not m.get("internal"):
            break
        if m["role"] == "assistant":
            missing += [c for c in m.get("tool_calls") or [] if c["id"] not in answered]
    for c in reversed(missing):
        run.add({"role": "tool", "tool_call_id": c["id"], "name": c["name"],
                 "content": "انلغت هالخطوة قبل ما تتنفذ.", "error": True, "denied": True})


def _kind(p):
    ext = Path(p).suffix.lower()
    if ext in media.VIDEO_EXT:
        return "video"
    if ext in media.AUDIO_EXT:
        return "audio"
    return "image"


def start(conv, key, think):
    r = Run(conv, key, think)
    RUNS[r.id] = r
    threading.Thread(target=run_agent, args=(r,), daemon=True, name=f"run-{r.id}").start()
    # forget finished runs after a while so memory stays flat
    for rid, old in list(RUNS.items()):
        if old.done and time.time() - old.started > 3600:
            RUNS.pop(rid, None)
    return r


def active_run():
    return next((r for r in RUNS.values() if r.running()), None)
