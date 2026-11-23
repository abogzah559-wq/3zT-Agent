"""The agent loop, model/VRAM management and run bookkeeping.

A Run lives on the server, independent of the browser: the UI can refresh or reconnect and
pick the stream back up from any event index. Every event mirrors a mutation of the stored
conversation, so the UI renders live runs and saved chats with the same code.
"""
import json
import logging
import re
import threading
import time
import urllib.parse
import uuid
from pathlib import Path

import freevideo
import llm
import localai
import outpaint
import media
import skills_mgr
import store
import tools
from config import AGENTS, MEMORY_FILE, model_of

LOG = logging.getLogger("3zt")

S = {}                      # live settings (set by server)
STATUS = {k: "off" for k in AGENTS}       # off | loading | pulling | ready | cloud | nokey | missing
PULL = {}                   # model -> {"pct", "text"} while downloading
VRAM_LOCK = threading.RLock()
ALWAYS = set()              # approval categories allowed for the whole session
CREATED = set()             # files the agent created this session (editable without asking)
RUNS = {}                   # run_id -> Run
WINDOW = {"gone": False}

TOOL_CAP = {"local": 12_000, "deepseek": 50_000}
STORE_CAP = 50_000


def media_url(path):
    return "/media?p=" + urllib.parse.quote(str(path))


def chat_dir(conv):
    """Every chat has its own folder; deleting the chat deletes it."""
    d = Path(S["workspace"]) / "chats" / conv["id"]
    d.mkdir(parents=True, exist_ok=True)
    return d


def file_card(p):
    p = Path(p)
    try:
        size = p.stat().st_size
    except OSError:
        size = 0
    return {"url": media_url(p), "path": str(p), "name": p.name, "size": size, "kind": _kind(p)}


# ============================ model management ============================
def local_models():
    return {model_of(k, S) for k, a in AGENTS.items() if a["kind"] == "local"}


def variant_of(key):
    """Which file of the agent's model to run: the free agent has a speed/quality choice."""
    model = model_of(key, S)
    setting = S.get("free_variant", "auto") if key == "free" else "auto"
    return localai.pick_variant(model, setting)


def refresh_status():
    cur_model, cur_var = localai.current()
    for k, a in AGENTS.items():
        if a["kind"] == "deepseek":
            STATUS[k] = "cloud" if S.get("deepseek_key") else "nokey"
            continue
        if STATUS[k] in ("loading", "pulling"):
            continue
        m = model_of(k, S)
        if cur_model == m:
            STATUS[k] = "ready"
        else:
            STATUS[k] = "off" if localai.installed(m, "fast") or localai.installed(m, "quality") else "missing"


def _progress_hook(model, progress):
    """Mirror download progress into PULL (banner) and the run's progress line."""
    def hook(text):
        if "|" in text:
            txt, pct = text.rsplit("|", 1)
            try:
                PULL[model] = {"pct": int(pct), "text": txt}
            except ValueError:
                pass
        if progress:
            progress(text)
    return hook


def ensure_local(key, progress=None, cancel=None):
    """Make sure the agent's local model is the one running. Returns error text or ''."""
    model = model_of(key, S)
    if not VRAM_LOCK.acquire(blocking=False):
        if progress:      # another task is loading or downloading a model right now: say so instead of freezing
            progress("ينتظر النموذج يخلص تحميل أو تشغيل... (تشوف التقدم في شريط فوق)")
        while not VRAM_LOCK.acquire(timeout=0.5):
            if cancel is not None and cancel.is_set():
                return "انلغى."
    try:
        return _ensure_local(key, model, progress, cancel)
    finally:
        VRAM_LOCK.release()


def _ensure_local(key, model, progress, cancel):
    variant = variant_of(key)
    if localai.current() == (model, variant) and localai.healthy():
        STATUS[key] = "ready"
        return ""
    for k, a in AGENTS.items():
        if a["kind"] == "local" and k != key:
            STATUS[k] = "off"
    missing = not localai.installed(model, variant)
    STATUS[key] = "pulling" if missing else "loading"
    try:
        err = localai.load(model, variant, S.get("num_ctx"), _progress_hook(model, progress), cancel)
    finally:
        PULL.pop(model, None)
    if err and variant != "fast":          # the bigger variant did not fit: fall back
        if progress:
            progress("النسخة الأعلى جودة ما ركبت، أشغّل النسخة السريعة...")
        localai.BROKEN.add((model, variant))
        err2 = localai.load(model, "fast", S.get("num_ctx"), _progress_hook(model, progress), cancel)
        PULL.pop(model, None)
        err = err2 or ""
    STATUS[key] = "ready" if not err else ("missing" if not localai.installed(model, "fast") else "off")
    return err


def switch(key):
    """The agent you switch to starts; the others switch off (except a warm executor while on DeepSeek)."""
    S["active"] = key
    target = AGENTS[key]

    def work():
        with VRAM_LOCK:
            if target["kind"] == "local":
                ensure_local(key)
            elif S.get("keep_executor_warm") and _downloaded("executor"):
                ensure_local("executor")        # never start a big download just to keep it warm
            else:
                localai.stop()
            refresh_status()

    if not any(r.running() for r in RUNS.values()):
        threading.Thread(target=work, daemon=True).start()


def _downloaded(key):
    m = model_of(key, S)
    return any(localai.installed(m, v) for v in localai.variants(m))


def warmup():
    key = S.get("active", "executor")
    try:
        target = key if AGENTS[key]["kind"] == "local" else ("executor" if S.get("keep_executor_warm") else None)
        # only start a model that is already downloaded: big downloads wait for the user to send something
        if target and any(localai.installed(model_of(target, S), v) for v in localai.variants(model_of(target, S))):
            ensure_local(target)
    except Exception:
        LOG.exception("warmup")
    refresh_status()


def unload_all():
    localai.stop()


# ============================ prompts ============================
def read_memory():
    try:
        return MEMORY_FILE.read_text(encoding="utf-8").strip()
    except Exception:
        return ""


_HW = {}


def _hardware_line():
    """', كرت NVIDIA ... (12GB)، رام 16GB' measured once (the app is public: never assume one PC)."""
    if "line" not in _HW:
        try:
            import stats
            g = stats.get()
            parts = []
            if g.get("gpu"):
                parts.append(f"كرت {g['gpu']['name']} ({g['gpu']['vram_total']:.0f}GB)")
            if g.get("ram_total"):
                parts.append(f"رام {g['ram_total']:.0f}GB")
            _HW["line"] = ("، " + "، ".join(parts)) if parts else ""
        except Exception:
            _HW["line"] = ""
    return _HW["line"]


def system_prompt(key, conv=None):
    ws = S["workspace"]
    folder = str(chat_dir(conv)) if conv else ws
    now = time.strftime("%Y-%m-%d %H:%M (%A)")
    mem = read_memory()
    hw = _hardware_line()
    base = f"""أنت 3zT Agent، مساعد شخصي ذكي يشتغل على كمبيوتر صاحبه مباشرة.
- الوقت الحالي: {now}. الجهاز: ويندوز{hw}.
- رد دايمًا بالعربي باللهجة السعودية البيضاء، بوضوح واختصار، واستخدم Markdown لما يفيد.
  قل: وش، ليش، أبي/تبي، الحين، كذا، مو، زين، مرة، عشان، وين، إيه، أبشر، تم.
  لا تقول أبد (مصري): عايز، إزاي، دلوقتي، كده، بتاع، أوي، مش، النهارده. ولا فصحى ثقيلة.
- مجلد هالمحادثة: {folder} — المرفقات فيه، وكل ملف تسويه يتحفظ فيه تلقائيًا (المسارات النسبية تبدأ منه). مجلد الشغل العام: {ws}.
- الأوامر تشتغل في PowerShell. متوفر لك بدون تثبيت: ffmpeg و ffprobe و yt-dlp و python و node، وأوامر
  hyperframes (فيديو موشن من HTML) و agent-browser (تحكم بالمتصفح) — حمّل مهارتها قبل ما تستخدمها.

## الصلاحيات
- القراءة والبحث وأخذ لقطة شاشة وإنشاء ملفات جديدة في مجلد الشغل: تسويها مباشرة.
- تعديل ملف موجود، الكتابة برا مجلد الشغل، النقل، تشغيل الأوامر والبرامج، والتحكم بالماوس والكيبورد: النظام يطلب موافقة صاحب الجهاز تلقائيًا، فلا تسأله قبلها، استدعِ الأداة وهو يوافق أو يرفض.
- الحذف يروح لسلة المحذوفات ويحتاج موافقته كل مرة. إذا رفض أي خطوة لا تعيدها ولا تلتف عليها.

## الحدود الثابتة (ما تتغير أبد)
- ممنوع أي محتوى جنسي أو إيحائي فيه قاصرين، بأي شكل أو صيغة.
- ممنوع تعديل صور أشخاص حقيقيين (أو تسمية شخص حقيقي معروف) بشكل جنسي أو مهين.
{{POLICY}}

## طريقة الشغل
- افهم الطلب، وإذا كان واضح نفّذه على طول بدون أسئلة كثيرة. إذا فيه غموض حقيقي اسأل سؤال واحد.
- بعد أي خطوة مهمة تأكد من النتيجة (اقرأ الملف، شيك على الفيديو بـ media_info، أو خذ لقطة شاشة).
- التحكم بالجهاز: خذ screenshot أول، والإحداثيات تكون بمقاس الصورة اللي شفتها. كل أداة تحكم ترجع لك لقطة جديدة؛ تأكد إن الخطوة نجحت قبل اللي بعدها.
- الإنترنت: web_search للبحث و fetch_url لقراءة صفحة، و download للتحميل (يدعم يوتيوب وتيك توك وإكس).
- تعديل الفيديو: استخدم أداة video (عمليات جاهزة ومجربة: قص، ضغط، دمج، تحويل عمودي، إصلاح تشوهات وتوهج ووميض repair، رفع دقة upscale_ai...) بدل ما تكتب أوامر ffmpeg طويلة. ffmpeg الخام بس للأشياء اللي ما تغطيها.
- تعديل الصور العادي (قص، تكبير، ألوان...): أداة image.
- التوليد بالذكاء الاصطناعي محلي على كرت الجهاز عن طريق FreeVideo: generate_image لصورة جديدة (حتى 16 ميقا)، edit_image لتعديل أو دمج صور موجودة (صور بس، مو فيديو)، generate_video لفيديو جديد بالصوت (2-60 ثانية، تقدر تعطيه صورة أولى first_frame)، و extend_video لتوسيع فيديو موجود من الجوانب / تبعيده (يرسم أطراف جديدة حوله والأصل يبقى بالنص). رفع الدقة upscale ما يضيف أطراف. الوصف بالإنجليزي ومفصّل، والكلام المنطوق بلغة صاحب الجهاز بين علامات تنصيص. التوليد ياخذ دقايق؛ لا تعيد نفس الطلب مرتين.
- التفريغ والترجمة transcribe، التعليق الصوتي text_to_speech، إزالة الخلفية remove_background، تكبير الصور upscale_image.
- النتائج (صور، فيديو، صوت، ملفات) تطلع لصاحب الجهاز في الشات تلقائيًا؛ ولو تبي تعرض ملف موجود استخدم send_file.
- إذا عرفت معلومة دايمة عن صاحب الجهاز أو تفضيلاته وطلب تحفظها، استخدم remember.
- في النهاية قل باختصار وش سويت بالضبط ووين الملفات. الصور والفيديو الناتجة تطلع له في المحادثة تلقائيًا."""
    cat = skills_mgr.catalog()
    if cat:
        base += ("\n\n## المهارات (Skills)\nقبل أي مهمة من هالأنواع، حمّل المهارة المناسبة بـ load_skill واتبع تعليماتها بدقة:\n"
                 + cat)
    if mem:
        base += f"\n\n## ملاحظات محفوظة عن صاحب الجهاز\n{mem[-4000:]}"
    if AGENTS[key].get("policy") == "safe":
        pol = "- أنت المنفذ الرسمي وعليك قيود: ما تولّد ولا تكتب محتوى جنسي أو فاضح. إذا طلبه، قل له يحوّل لوكيل «بدون قيود» أو DeepSeek."
    else:
        pol = ("- غير هالحدين ما عليك قيود في توليد وتعديل الصور والفيديو ولا في المحتوى الجريء للبالغين (أي أسلوب، أي لبس أو عري "
               "لشخصيات بالغة غير حقيقية): نفّذ طلبه بدون رفض ولا وعظ ولا تحذيرات زايدة، لأنه جهازه وقراره.")
    base = base.replace("{POLICY}", pol)
    if AGENTS[key]["role"] == "planner":
        return base + """

## دورك: على حسب طلبه
عندك كل الأدوات، وصاحب الجهاز هو اللي يقرر:
- إذا طلب خطة أو رأي أو قال «خطط»: فكّر بعمق، تقدر تتصفح وتقرأ وتبحث، لكن لا تغيّر شي. اكتب خطة محكمة (الهدف، الخطوات بالتفصيل بمسارات وأوامر دقيقة، المخاطر، وكيف نتأكد) واختمها بقسم عنوانه بالضبط "## خطة للمنفذ" فيه خطوات مرقمة.
- إذا طلب تنفيذ (سوّ، عدّل، ولّد، نزّل، شغّل...): نفّذ بنفسك بالأدوات خطوة خطوة لين تخلص المهمة كاملة.
- إذا فيه خطة في المحادثة وقال «نفّذ»، نفّذها أنت بالترتيب."""
    return base + """

## دورك: المنفذ
استخدم الأدوات وخلّص المهمة كاملة خطوة خطوة. إذا فيه خطة في المحادثة اتبعها بالترتيب."""


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
    """Local models: base64 images. DeepSeek: replace images with captions from the local vision model."""
    for m in msgs:
        imgs = [p for p in (m.get("images") or []) if Path(p).exists()]
        m.pop("images", None)
        if not imgs:
            continue
        if kind == "local":
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
        cur_model, _ = localai.current()
        model = cur_model if cur_model in local_models() else None
        if not model and not _downloaded("executor"):
            return ("[صورة مرفقة — نموذج الرؤية المحلي (المنفذ) لسا ما نزل، فما أقدر أشوفها الحين. "
                    "نزّله من الإعدادات ← الإعداد والتحميلات]")
        if not model:
            self.progress("يشغّل نموذج الرؤية المحلي عشان يوصف الصورة...")
            err = ensure_local("executor", self.progress, self.cancel)
            if err:
                return f"[صورة مرفقة — ما قدرت أوصفها: {err}]"
            model = model_of("executor", S)
        self.progress("أخلي النموذج المحلي يوصف الصورة للمخطط...")
        q = None
        if len(paths) > 1:
            q = (f"These are {len(paths)} images in order (e.g. video frames or screenshots). Describe each one briefly "
                 "(numbered), then summarize what happens overall. Transcribe any visible text exactly.")
        try:
            text = localai.caption(model, [self.b64(p) for p in paths], q)
        except Exception as e:
            return f"[صورة مرفقة — ما قدرت أوصفها: {llm.describe_error(e)}]"     # not cached: retried next time
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
        out_dir = chat_dir(self.conv) / "generated"
        out_dir.mkdir(parents=True, exist_ok=True)
        open_policy = AGENTS[self.key].get("policy") == "open"
        loras = S.get("image_loras") if open_policy else None
        self.progress("أفضّي كرت الشاشة للتوليد...")
        with VRAM_LOCK:
            unload_all()
            for k, a in AGENTS.items():
                if a["kind"] == "local":
                    STATUS[k] = "off"
            try:
                freevideo.ensure_running(self.progress, self.cancel)
                if name == "generate_video":
                    return freevideo.generate_video(args, out_dir, self.cancel, self.progress)
                if name == "extend_video":
                    return outpaint.extend_video(args, args["path"], chat_dir(self.conv) / "edited", self.cancel,
                                                 self.progress)
                return freevideo.generate_image(args, out_dir, self.cancel, self.progress, loras=loras,
                                                model=S.get("image_model", "auto"))
            except freevideo.FVError as e:
                raise RuntimeError(str(e)) from None
            finally:
                freevideo.free_vram()
                if self.kind == "local":
                    ensure_local(self.key, self.progress, self.cancel)


# ============================ Saudi dialect ============================
# Words that are clearly Egyptian (not used in Saudi speech). Two different ones in a reply = rewrite it.
_AR_LETTER = "\u0621-\u064A\u066E-\u06D3\u06FA-\u06FF"      # letters only: ، ؟ ؛ count as punctuation
_EGY = re.compile(r"(?<![" + _AR_LETTER + r"])(عايز|عايزة|عاوز|عاوزة|إزاي|ازاي|دلوقتي|دلوقت|كده|كدا|بتاعك|بتاعي|بتاعه|بتاعها|"
                  r"بتاعة|بتاعت|بتاع|أوي|اوي|مش|النهارده|النهاردة|امبارح|إمبارح|هعمل|هتعمل|بيعمل|علشان كده|يا باشا|ده|دى|"
                  r"هيك|هلق|هلأ|كتير|منيح|بدي|بدك|شو|ليش لأ|بيأخذ|بياخد|بيضيف|بيشتغل|عايزين|برضه|خلاص كده|أعمل إيه|اعمل ايه|أعمل ايه|"
                  r"إيه اللي|ايه اللي|زي كده)"
                  r"(?![" + _AR_LETTER + r"])")
DIALECT_NOTE = "\n\n(رد باللهجة السعودية.)"


def egyptian_score(text):
    """(distinct markers, total markers) outside code blocks."""
    plain = re.sub(r"```.*?```|`[^`\n]*`", " ", text or "", flags=re.S)
    found = _EGY.findall(plain)
    return len(set(found)), len(found)


def needs_dialect_fix(text):
    distinct, total = egyptian_score(text)
    return distinct >= 2 or total >= 3


def remind_dialect(msgs):
    """Append a short reminder to the newest user message (request copy only, never stored)."""
    for m in reversed(msgs):
        if m.get("role") == "user":
            if isinstance(m.get("content"), str) and not m["content"].endswith(DIALECT_NOTE):
                m["content"] += DIALECT_NOTE
            return msgs
    return msgs


def _fix_dialect(run, am, key, kind):
    """Rewrite a reply that slipped into Egyptian dialect, keeping its meaning, code and paths."""
    text = am.get("content") or ""
    if not needs_dialect_fix(text):
        return
    _phase(run, "يعدّل اللهجة للسعودي")
    msgs = [{"role": "system", "content": "أنت محرر لغوي. أعد كتابة النص اللي يجيك باللهجة السعودية البيضاء "
                                          "(وش، ليش، أبي، الحين، كذا، مو، زين، مرة، عشان)، بنفس المعنى والترتيب والتنسيق "
                                          "(Markdown). لا تغيّر الكود ولا المسارات ولا الأرقام ولا الروابط ولا الأسماء "
                                          "الإنجليزية. رجّع النص الجديد بس، بدون أي مقدمة."},
            {"role": "user", "content": text}]
    if kind == "deepseek":
        gen = llm.stream_deepseek(S["deepseek_key"], S["deepseek_model"], "low", msgs, None, run.cancel)
    else:
        gen = llm.stream_local(model_of(key, S), msgs, None, run.cancel, False)
    out = ""
    for t, v in gen:
        if t == "text":
            out += v
        elif t == "error":
            return
    out = _strip_think_tags(out).strip()
    if out and len(out) > len(text) * 0.5 and egyptian_score(out)[1] < egyptian_score(text)[1]:
        am["content"] = out
        run.emit("replace_text", text=out)


def _strip_think_tags(text):
    """Some local models leak <think>...</think> into content; keep only the answer."""
    if "</think>" in text:
        return text.split("</think>", 1)[1].lstrip()
    return text


UNFINISHED = ("لنبدأ", "نبدأ", "بنبدأ", "هبدأ", "هنبدأ", "سأبدأ", "سأقوم", "بسوي الحين", "راح أسوي", "خلني أ", "الحين ب",
              "الخطوة الجاية", "الخطوة التالية", "let's start", "let me", "i will now", "i'll now", "next, i", "now i will")


def _looks_unfinished(text):
    """Small models often announce the next step and then stop without calling a tool."""
    t = (text or "").strip()
    if not t or t.endswith(("?", "؟")):
        return False
    tail = t[-160:].lower()
    return t.endswith((":", "：", "...", "…")) or any(w in tail for w in UNFINISHED)


def _phase(run, text):
    run.emit("phase", text=text)


def run_agent(run: Run):
    conv, key = run.conv, run.key
    a = AGENTS[key]
    kind = a["kind"]
    names = tools.ALL                     # every agent gets every tool; DeepSeek plans or executes as asked
    schemas = tools.schemas(names)
    base = chat_dir(conv)
    ctx = {"workspace": S["workspace"], "base": str(base), "created": CREATED, "progress": run.progress,
           "cancel": run.cancel, "generate": run.generate, "policy": a.get("policy", "safe")}
    try:
        if kind == "deepseek" and not S.get("deepseek_key"):
            run.notice("حط مفتاح DeepSeek من الإعدادات ⚙️ عشان يشتغل DeepSeek.")
            return
        if kind == "local":
            _phase(run, "يجهّز النموذج في كرت الشاشة")
            err = ensure_local(key, run.progress, run.cancel)
            if err:
                run.notice(err)
                return
        sysmsg = {"role": "system", "content": system_prompt(key, conv)}
        n_ctx = localai.ctx_for(model_of(key, S), S.get("num_ctx")) if kind == "local" else 0
        # chars the chat history may use: context (~2.3 chars/token for Arabic) minus the system prompt, the tool
        # definitions (English JSON packs ~1.5x more chars per token) and room for the reply
        schema_chars = int(len(json.dumps(schemas, ensure_ascii=False)) / 1.5)
        budget = (500_000 if kind == "deepseek" else
                  int(n_ctx * 2.3) - len(sysmsg["content"]) - schema_chars - 6000)
        budget = max(budget, 12_000)
        max_steps = int(S.get("max_steps") or 40)
        fails, repeats, last_sig, stop_tools = {}, 0, None, False
        nudges, empties, bad_calls = 0, 0, 0

        step = 0
        while step <= max_steps:
            if run.cancel.is_set():
                break
            final_step = step == max_steps
            _phase(run, "يجهّز الطلب" if step == 0 else f"يكمّل — الخطوة {step + 1}")
            msgs = remind_dialect([sysmsg] + attach_images(build_context(conv, kind, budget), kind, run))
            use_tools = None if (stop_tools or final_step) else schemas
            if final_step:
                msgs.append({"role": "user", "content": "(النظام: وصلت حد الخطوات. وقف الأدوات واكتب ملخص وش خلصت ووش باقي.)"})
            am = {"role": "assistant", "content": "", "reasoning": "", "agent": key}
            conv["messages"].append(am)
            run.emit("assistant", agent=key)
            _phase(run, "النموذج يقرأ المحادثة ويفكر" if kind == "local" else "DeepSeek يفكر")
            if kind == "deepseek":
                gen = llm.stream_deepseek(S["deepseek_key"], S["deepseek_model"], S.get("deepseek_effort", "high"),
                                          msgs, use_tools, run.cancel)
            else:
                gen = llm.stream_local(model_of(key, S), msgs, use_tools, run.cancel, run.think)
            calls, err = [], None
            last_save, said_think, said_text = time.time(), False, False
            for t, v in gen:
                if t == "think":
                    am["reasoning"] += v
                    run.emit("think", text=v)
                    if not said_think:
                        _phase(run, "يفكر")
                        said_think = True
                elif t == "text":
                    am["content"] += v
                    run.emit("text", text=v)
                    if not said_text:
                        _phase(run, "يكتب")
                        said_text = True
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
            cleaned = _strip_think_tags(am["content"])
            if cleaned != am["content"]:
                am["content"] = cleaned
                run.emit("replace_text", text=cleaned)
            if (kind == "local" and not run.cancel.is_set() and localai.current()[1] not in (None, "fast")
                    and localai.looks_broken(am["content"] + am["reasoning"])):
                # known llama.cpp CUDA issue when experts sit in RAM: switch to the in-VRAM variant and redo the step
                localai.BROKEN.add(localai.current())
                if conv["messages"] and conv["messages"][-1] is am:
                    conv["messages"].pop()
                    run.emit("drop_assistant")
                run.notice("النسخة الأعلى جودة طلّعت كلام مكرر (مشكلة معروفة لما جزء من النموذج يكون بالرام). "
                           "رجعت للنسخة السريعة وأعيد المحاولة.", "info")
                err = ensure_local(key, run.progress, run.cancel)
                if err:
                    run.notice(err)
                    return
                continue
            if calls:
                am["tool_calls"] = calls
                run.emit("tool_calls", calls=calls)
            elif am["content"].strip() and not err and not run.cancel.is_set():
                _fix_dialect(run, am, key, kind)
            empty = not am["content"].strip() and not calls
            if not am["content"] and not am["reasoning"] and not calls:
                if conv["messages"] and conv["messages"][-1] is am:
                    conv["messages"].pop()
                    run.emit("drop_assistant")
            store.save(conv)
            if err:
                low = err.lower()
                if (kind == "local" and bad_calls < 2 and not run.cancel.is_set()
                        and any(k in low for k in ("xml syntax", "parsing tool call", "tool call", "unexpected end",
                                                   "invalid character", "unmarshal"))):
                    bad_calls += 1            # the model wrote a broken tool call: tell it and try again
                    _phase(run, "النموذج كتب أداة غلط — يعيد المحاولة")
                    run.add({"role": "user", "internal": True,
                             "content": "(تنبيه من النظام: آخر استدعاء أداة كتبته كان مكسور وما تنفذ. أعد استدعاء الأداة "
                                        "الصحيحة بمدخلات JSON سليمة، بدون أي XML أو نص داخل الاستدعاء.)"})
                    continue
                run.notice(err + " — أعد المحاولة بزر ↻ تحت.")
                return
            if run.cancel.is_set():
                break

            if not calls:
                # --- never end silently ---
                if empty and any(m["role"] == "tool" for m in conv["messages"][run.base:]):
                    break                     # work was done: the final summary below takes over
                if empty:
                    empties += 1
                    if empties <= 2:
                        _phase(run, "النموذج ما رد، أعيد المحاولة")
                        run.add({"role": "user", "internal": True,
                                 "content": "(النظام: ما كتبت أي رد. كمّل المهمة الحين: استخدم الأدوات أو اكتب ردك النهائي.)"})
                        step += 1
                        continue
                    run.notice("النموذج ما رجّع أي رد. جرّب المنفذ أو DeepSeek، أو شغّل «تفكير عميق».")
                    break
                if (_looks_unfinished(am["content"]) and nudges < 2 and not stop_tools and not final_step
                        and "خطة للمنفذ" not in (am["content"] or "")):
                    nudges += 1
                    _phase(run, "يكمّل التنفيذ")
                    run.add({"role": "user", "internal": True,
                             "content": "(النظام: لا توقف عند الكلام. نفّذ الخطوة اللي قلتها الحين باستدعاء الأداة المناسبة، "
                                        "وكمّل لين تخلص المهمة كاملة.)"})
                    step += 1
                    continue
                break

            for c in calls:
                if run.cancel.is_set():
                    break
                name, args = c["name"], c.get("args") or {}
                tm = {"role": "tool", "tool_call_id": c["id"], "name": name}
                if "_raw" in args:
                    res = tools.Result("خطأ: المدخلات مو JSON صحيح. أعد الاستدعاء بمدخلات صحيحة.", error=True)
                elif name not in names:
                    res = tools.Result(f"خطأ: الأداة {name} مو موجودة.", error=True)
                else:
                    info = tools.needs_approval(name, args, ctx)
                    ans = "yes"
                    if info:
                        _phase(run, "ينتظر موافقتك")
                        ans = run.ask(c["id"], info)
                        tm["approval"] = {"title": info["title"], "detail": info.get("detail", "")[:2000], "answer": ans}
                    if ans == "no":
                        res = tools.Result("صاحب الجهاز رفض هالخطوة. لا تعيدها ولا تلتف عليها؛ كمّل بغيرها أو اسأله.", error=True)
                        tm["denied"] = True
                    else:
                        run.emit("tool_start", id=c["id"], name=name)
                        _phase(run, "ينفّذ: " + name)
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
                    tm["media"] = [file_card(p) for p in dict.fromkeys(res.media) if Path(p).exists()]
                if res.created:
                    files = conv.setdefault("files", [])
                    files += [p for p in res.created if p not in files]
                run.add(tm)
            step += 1

        # --- guarantee a final answer after tool work ---
        msgs_now = conv["messages"]
        last_tool = max((i for i, m in enumerate(msgs_now) if m["role"] == "tool" and i >= run.base), default=-1)
        has_final = any(m["role"] == "assistant" and (m.get("content") or "").strip() and not m.get("tool_calls")
                        for m in msgs_now[last_tool + 1:])
        if not run.cancel.is_set() and last_tool >= 0 and not has_final:
            _phase(run, "يكتب الملخص")
            am = {"role": "assistant", "content": "", "reasoning": "", "agent": key}
            conv["messages"].append(am)
            run.emit("assistant", agent=key)
            msgs = [sysmsg] + attach_images(build_context(conv, kind, budget), kind, run)
            msgs.append({"role": "user", "content": "(النظام: اكتب الحين ردك النهائي لصاحب الجهاز: وش سويت بالضبط، "
                                                    "وش نجح ووش ما نجح، ووين الملفات.)"})
            gen = (llm.stream_deepseek(S["deepseek_key"], S["deepseek_model"], "low", msgs, None, run.cancel)
                   if kind == "deepseek" else
                   llm.stream_local(model_of(key, S), msgs, None, run.cancel, False))
            for t, v in gen:
                if t == "text":
                    am["content"] += v
                    run.emit("text", text=v)
                elif t == "think":
                    am["reasoning"] += v
                    run.emit("think", text=v)
            am["content"] = _strip_think_tags(am["content"])
            if not am["content"].strip():
                am["content"] = "خلصت الخطوات اللي فوق. افتح «خطوات العمل» تشوف نتيجة كل خطوة."
                run.emit("text", text=am["content"])
            else:
                run.emit("replace_text", text=am["content"])
                _fix_dialect(run, am, key, kind)
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
    if ext in media.IMAGE_EXT:
        return "image"
    return "file"


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
