"use strict";
/* 3zT Agent UI — no frameworks, no build step. */
const UI_VERSION = "1.2.0";

// ================= icons =================
const ICONS = {
  plus: '<path d="M12 5v14M5 12h14"/>', search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
  settings: '<path d="M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1Z"/>',
  folder: '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z"/>',
  sidebar: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M15 4v16"/>',
  alert: '<path d="M12 9v4M12 17h.01"/><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z"/>',
  down: '<path d="m6 9 6 6 6-6"/>', up: '<path d="M12 19V5M5 12l7-7 7 7"/>',
  clip: '<path d="m21.4 11-8.9 8.9a5.5 5.5 0 0 1-7.8-7.8l8.9-8.9a3.7 3.7 0 0 1 5.2 5.2l-8.9 8.9a1.8 1.8 0 0 1-2.6-2.6l8.2-8.2"/>',
  brain: '<path d="M9.5 2A2.5 2.5 0 0 1 12 4.5v15a2.5 2.5 0 0 1-4.96.44 2.5 2.5 0 0 1-2.96-3.08 3 3 0 0 1-.34-5.58 2.5 2.5 0 0 1 1.32-4.24A2.5 2.5 0 0 1 9.5 2Z"/><path d="M14.5 2A2.5 2.5 0 0 0 12 4.5v15a2.5 2.5 0 0 0 4.96.44 2.5 2.5 0 0 0 2.96-3.08 3 3 0 0 0 .34-5.58 2.5 2.5 0 0 0-1.32-4.24A2.5 2.5 0 0 0 14.5 2Z"/>',
  x: '<path d="M18 6 6 18M6 6l12 12"/>', check: '<path d="M20 6 9 17l-5-5"/>',
  stop: '<rect x="6" y="6" width="12" height="12" rx="2" fill="currentColor"/>',
  copy: '<rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>',
  refresh: '<path d="M21 12a9 9 0 1 1-3-6.7L21 8"/><path d="M21 3v5h-5"/>',
  trash: '<path d="M3 6h18M8 6V4h8v2M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>',
  pin: '<path d="M12 17v5M9 10.8V4h6v6.8l3 3.2H6Z"/>', edit: '<path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z"/>',
  dots: '<circle cx="12" cy="5" r="1.2"/><circle cx="12" cy="12" r="1.2"/><circle cx="12" cy="19" r="1.2"/>',
  terminal: '<path d="m4 17 6-6-6-6M12 19h8"/>', globe: '<circle cx="12" cy="12" r="10"/><path d="M2 12h20M12 2a15 15 0 0 1 0 20M12 2a15 15 0 0 0 0 20"/>',
  image: '<rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="9" cy="9" r="2"/><path d="m21 15-5-5L5 21"/>',
  video: '<rect x="2" y="6" width="14" height="12" rx="2"/><path d="m22 8-6 4 6 4Z"/>',
  mouse: '<rect x="6" y="3" width="12" height="18" rx="6"/><path d="M12 7v4"/>',
  file: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z"/><path d="M14 2v6h6"/>',
  filePen: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h5"/><path d="M14 2v6h6M18.4 13.6a1.9 1.9 0 0 1 2.7 2.7L16 21l-3.5 1 1-3.5Z"/>',
  download: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3"/>',
  mic: '<rect x="9" y="2" width="6" height="12" rx="3"/><path d="M19 10a7 7 0 0 1-14 0M12 17v5"/>',
  wand: '<path d="m15 4-1 1M20 9l-1 1M18 2l.5 1.5L20 4l-1.5.5L18 6l-.5-1.5L16 4l1.5-.5ZM3 21l12-12 2 2L5 23Z"/>',
  cpu: '<rect x="5" y="5" width="14" height="14" rx="2"/><rect x="9" y="9" width="6" height="6"/><path d="M9 2v3M15 2v3M9 19v3M15 19v3M2 9h3M2 15h3M19 9h3M19 15h3"/>',
  chip: '<rect x="4" y="4" width="16" height="16" rx="2"/><path d="M9 9h6v6H9z"/>',
  rocket: '<path d="M4.5 16.5c-1.5 1.3-2 5-2 5s3.7-.5 5-2c.7-.8.7-2.1-.1-2.9a2.2 2.2 0 0 0-2.9-.1Z"/><path d="m12 15-3-3a22 22 0 0 1 2-3.9A12.9 12.9 0 0 1 22 2c0 2.7-.8 7.5-6 11a22 22 0 0 1-4 2Z"/><path d="M9 12H4s.6-3 2-4c1.6-1.1 5 0 5 0M12 15v5s3-.6 4-2c1.1-1.6 0-5 0-5"/>',
  cloud: '<path d="M17.5 19H9a7 7 0 1 1 6.7-9h1.8a4.5 4.5 0 1 1 0 9Z"/>',
  bookmark: '<path d="m19 21-7-4-7 4V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2Z"/>',
  pulse: '<path d="M22 12h-4l-3 9L9 3l-3 9H2"/>', shield: '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z"/>',
  eye: '<path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/>',
  keyboard: '<rect x="2" y="5" width="20" height="14" rx="2"/><path d="M6 9h.01M10 9h.01M14 9h.01M18 9h.01M7 15h10"/>',
  move: '<path d="M5 12h14M13 6l6 6-6 6"/>', sparkle: '<path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8Z"/>',
  layers: '<path d="m12 2 10 5-10 5L2 7Z"/><path d="m2 17 10 5 10-5M2 12l10 5 10-5"/>', info: '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/>',
  ext: '<path d="M15 3h6v6M10 14 21 3M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>',
  music: '<path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/>',
};
const icon = (n, cls = "") => `<svg class="i ${cls}" viewBox="0 0 24 24">${ICONS[n] || ICONS.info}</svg>`;
function hydrateIcons(root = document) {
  root.querySelectorAll("svg[data-i]").forEach(s => { s.setAttribute("viewBox", "0 0 24 24"); s.innerHTML = ICONS[s.dataset.i] || ""; s.removeAttribute("data-i"); });
}

// ================= utils =================
const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
const fmtSize = n => n < 1024 ? n + " B" : n < 1 << 20 ? (n / 1024).toFixed(0) + " KB" : n < 1 << 30 ? (n / 1048576).toFixed(1) + " MB" : (n / 1073741824).toFixed(2) + " GB";
const mediaUrl = p => "/media?p=" + encodeURIComponent(p);
const store = {
  get(k, d) { try { const v = localStorage.getItem("3zt." + k); return v === null ? d : JSON.parse(v); } catch (e) { return d; } },
  set(k, v) { try { localStorage.setItem("3zt." + k, JSON.stringify(v)); } catch (e) {} },
};

async function api(path, body) {
  const opt = body === undefined ? {headers: {"X-3zT": "1"}} :
    {method: "POST", headers: {"Content-Type": "application/json", "X-3zT": "1"}, body: JSON.stringify(body)};
  const r = await fetch(path, opt);
  let data = {};
  try { data = await r.json(); } catch (e) {}
  if (!r.ok) throw new Error(data.error || ("HTTP " + r.status));
  return data;
}
function toast(text, err = false) {
  const t = document.createElement("div");
  t.className = "toast" + (err ? " err" : "");
  t.innerHTML = icon(err ? "alert" : "check", "sm") + `<span>${esc(text)}</span>`;
  $("#toasts").appendChild(t);
  setTimeout(() => t.remove(), 3800);
}
async function copyText(t) {
  try { await navigator.clipboard.writeText(t); toast("انسخ"); }
  catch (e) { const ta = document.createElement("textarea"); ta.value = t; document.body.appendChild(ta); ta.select(); document.execCommand("copy"); ta.remove(); toast("انسخ"); }
}

// ================= markdown =================
const KW = /\b(def|class|return|if|elif|else|for|while|in|import|from|as|with|try|except|finally|raise|lambda|yield|async|await|function|const|let|var|new|this|true|false|null|None|True|False|public|private|static|void|int|string|bool|fn|struct|impl|use|mod|pub|match|echo|param|foreach|switch|case|break|continue|and|or|not|is)\b/g;
const PH = i => "\uE000" + String.fromCharCode(0xE100 + i);          // placeholders without digits/letters
const unPH = (s, arr) => s.replace(/\uE000([\uE100-\uF8FF])/g, (_, c) => arr[c.charCodeAt(0) - 0xE100]);
function highlight(code, lang) {
  let h = esc(code);
  if (!lang || /^(text|txt|plain|md|markdown)$/i.test(lang) || code.length > 20000) return h;
  const slots = [];
  const keep = (re, cls) => { h = h.replace(re, m => { slots.push(`<span class="${cls}">${m}</span>`); return PH(slots.length - 1); }); };
  keep(/(&quot;|&#39;|`)(?:(?!\1)[^\\\n]|\\.)*?\1/g, "tk-s");
  keep(/((?<!&)#(?!!)[^\n]*|\/\/[^\n]*|\/\*[\s\S]*?\*\/|&lt;!--[\s\S]*?--&gt;)/g, "tk-c");
  h = h.replace(KW, '<span class="tk-k">$1</span>').replace(/\b(\d+(?:\.\d+)?)\b/g, '<span class="tk-n">$1</span>')
       .replace(/\b([A-Za-z_]\w*)(?=\()/g, '<span class="tk-f">$1</span>');
  return unPH(h, slots);
}
function inline(s) {
  const codes = [];
  s = s.replace(/`([^`\n]+)`/g, (_, c) => { codes.push(`<code>${esc(c)}</code>`); return PH(codes.length - 1); });
  s = esc(s);
  s = s.replace(/!\[([^\]]*)\]\(([^)\s]+)\)/g, (m, alt, url) => /^(https?:|\/media)/.test(url) ? `<img src="${url}" alt="${alt}" style="max-width:100%;border-radius:10px">` : m)
       .replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (m, t, url) => /^(https?:|mailto:)/.test(url.replace(/&amp;/g, "&")) ? `<a href="${url}" target="_blank" rel="noopener">${t}</a>` : m)
       .replace(/(^|[\s(])(https?:\/\/[^\s<)]+)/g, '$1<a href="$2" target="_blank" rel="noopener">$2</a>')
       .replace(/\*\*([^*\n]+?)\*\*/g, "<strong>$1</strong>").replace(/__([^_\n]+?)__/g, "<strong>$1</strong>")
       .replace(/(^|[^*\w])\*([^*\n]+?)\*(?!\w)/g, "$1<em>$2</em>").replace(/~~([^~\n]+?)~~/g, "<del>$1</del>");
  return unPH(s, codes);
}
function md(src, streaming = false) {
  const lines = String(src || "").replace(/\r\n?/g, "\n").split("\n");
  let out = "", i = 0;
  const listStack = [];
  const closeLists = (to = 0) => { while (listStack.length > to) out += `</${listStack.pop().t}>`; };
  while (i < lines.length) {
    const ln = lines[i];
    const fence = ln.match(/^\s*(```|~~~)\s*([\w+#.-]*)\s*$/);
    if (fence) {
      closeLists();
      const lang = fence[2] || ""; const body = []; i++;
      while (i < lines.length && !lines[i].trim().startsWith(fence[1])) body.push(lines[i++]);
      i++;
      out += `<div class="code"><div class="ch"><span>${esc(lang || "code")}</span><button data-copy>${icon("copy", "sm")}نسخ</button></div><pre><code>${highlight(body.join("\n"), lang)}</code></pre></div>`;
      continue;
    }
    if (/^\s*$/.test(ln)) { closeLists(); i++; continue; }
    const h = ln.match(/^(#{1,4})\s+(.*)$/);
    if (h) { closeLists(); out += `<h${h[1].length}>${inline(h[2])}</h${h[1].length}>`; i++; continue; }
    if (/^\s*([-*_])(\s*\1){2,}\s*$/.test(ln)) { closeLists(); out += "<hr>"; i++; continue; }
    if (/^\s*>/.test(ln)) {
      closeLists(); const q = [];
      while (i < lines.length && /^\s*>/.test(lines[i])) q.push(lines[i++].replace(/^\s*>\s?/, ""));
      out += `<blockquote>${md(q.join("\n"))}</blockquote>`; continue;
    }
    if (/^\s*\|.*\|\s*$/.test(ln) && i + 1 < lines.length && /^\s*\|?\s*:?-{2,}/.test(lines[i + 1])) {
      closeLists();
      const cells = r => r.trim().replace(/^\||\|$/g, "").split("|").map(c => c.trim());
      const head = cells(ln); i += 2;
      let t = "<table><thead><tr>" + head.map(c => `<th>${inline(c)}</th>`).join("") + "</tr></thead><tbody>";
      while (i < lines.length && /^\s*\|.*\|\s*$/.test(lines[i])) t += "<tr>" + cells(lines[i++]).map(c => `<td>${inline(c)}</td>`).join("") + "</tr>";
      out += t + "</tbody></table>"; continue;
    }
    const li = ln.match(/^(\s*)([-*+]|\d+[.)])\s+(.*)$/);
    if (li) {
      const depth = Math.min(3, Math.floor(li[1].replace(/\t/g, "    ").length / 2) + 1);
      const type = /\d/.test(li[2]) ? "ol" : "ul";
      while (listStack.length > depth) out += `</${listStack.pop().t}>`;
      while (listStack.length < depth) { listStack.push({t: type}); out += `<${type}>`; }
      if (listStack[listStack.length - 1].t !== type) { out += `</${listStack.pop().t}><${type}>`; listStack.push({t: type}); }
      out += `<li>${inline(li[3])}</li>`; i++; continue;
    }
    closeLists();
    const para = [ln]; i++;
    while (i < lines.length && lines[i].trim() && !/^(\s*(```|~~~)|#{1,4}\s|\s*>|\s*([-*+]|\d+[.)])\s|\s*\|.*\|\s*$)/.test(lines[i])) para.push(lines[i++]);
    out += `<p>${para.map(inline).join("<br>")}</p>`;
  }
  closeLists();
  return out;
}

// ================= state =================
let S = null;                 // /api/state
let convs = [];
let cur = null;               // {id,title,agent,messages,usage}
let live = null;              // {run, from, approvals:{}, running:{}, progress, done, conv}
let active = "executor";
let atts = [];
let think = false;
const folds = new Map();      // remembered open/closed states
const mediaCache = new Map(); // url -> element (keeps videos playing across re-renders)
let renderQueued = false, stickBottom = true;

const TOOL_META = {
  list_dir: ["folder", "يتصفح مجلد"], read_file: ["file", "يقرأ ملف"], search_files: ["search", "يدور ملفات"],
  grep: ["search", "يبحث داخل الملفات"], write_file: ["filePen", "يكتب ملف"], edit_file: ["edit", "يعدّل ملف"],
  make_dir: ["folder", "ينشئ مجلد"], copy_path: ["copy", "ينسخ"], move_path: ["move", "ينقل"],
  delete_path: ["trash", "يحذف"], find_duplicates: ["layers", "يدور المكرر"], run_command: ["terminal", "يشغّل أمر"],
  run_python: ["terminal", "يشغّل بايثون"], open: ["ext", "يفتح"], system_info: ["cpu", "يشيك على الجهاز"],
  screenshot: ["eye", "يشوف الشاشة"], mouse_click: ["mouse", "يضغط"], mouse_drag: ["mouse", "يسحب"],
  scroll: ["mouse", "يمرر"], type_text: ["keyboard", "يكتب"], press_keys: ["keyboard", "يضغط أزرار"],
  list_windows: ["layers", "يشوف النوافذ"], focus_window: ["layers", "يفعّل نافذة"], clipboard: ["copy", "الحافظة"],
  web_search: ["globe", "يبحث في النت"], fetch_url: ["globe", "يقرأ صفحة"], download: ["download", "ينزّل"],
  view_image: ["image", "يشوف صورة"], video_frames: ["video", "يشوف فيديو"], media_info: ["info", "معلومات ملف"],
  ffmpeg: ["video", "ffmpeg"], transcribe: ["mic", "يفرّغ الكلام"], text_to_speech: ["music", "يسوي صوت"],
  remove_background: ["wand", "يشيل الخلفية"], upscale_image: ["wand", "يكبّر الصورة"],
  generate_image: ["sparkle", "يولّد صورة"], edit_image: ["sparkle", "يعدّل صورة"], generate_video: ["video", "يولّد فيديو"],
  remember: ["bookmark", "يحفظ ملاحظة"],
};
const ST_LABEL = {off: "مطفي", loading: "يتحمّل…", pulling: "ينزل…", ready: "جاهز", cloud: "جاهز", nokey: "يحتاج مفتاح", missing: "مو منزّل"};
function argPreview(name, a) {
  a = a || {};
  const v = a.path || a.command || a.url || a.query || a.target || a.prompt || a.keys || a.text || a.title || a.args || a.code || a.src || a.image_path || a.note
    || (a.x !== undefined ? `${a.x}, ${a.y}` : "") || (a.paths ? a.paths.join(", ") : "");
  return String(v || "").replace(/\s+/g, " ").slice(0, 160);
}

// ================= turns =================
function turnsOf(messages) {
  const turns = [];
  messages.forEach((m, idx) => {
    if (m.role === "user" && !m.internal) turns.push({type: "user", m, idx});
    else {
      let t = turns[turns.length - 1];
      if (!t || t.type !== "ai") { t = {type: "ai", msgs: [], idx}; turns.push(t); }
      t.msgs.push(m);
    }
  });
  return turns;
}

function renderUser(t) {
  const d = document.createElement("div"); d.className = "u";
  const m = t.m;
  if (m.attachments && m.attachments.length) {
    const a = document.createElement("div"); a.className = "atts";
    for (const x of m.attachments) {
      const ic = {video: "video", audio: "music", text: "file"}[x.kind] || "file";
      a.insertAdjacentHTML("beforeend", `<div class="att">${x.thumb ? `<img src="${esc(x.thumb)}" data-zoom="${esc(x.kind === "image" ? mediaUrl(x.path) : x.thumb)}">` : `<div class="ic">${icon(ic)}</div>`}<span title="${esc(x.path)}">${esc(x.name)}</span></div>`);
    }
    d.appendChild(a);
  }
  const text = m.display !== undefined ? m.display : m.content;
  if (text) { const b = document.createElement("div"); b.className = "bubble"; b.textContent = text; d.appendChild(b); }
  return d;
}

function foldEl(key, cls, head, bodyHTML, defOpen) {
  const open = folds.has(key) ? folds.get(key) : defOpen;
  const f = document.createElement("div");
  f.className = `fold ${cls}` + (open ? " open" : "");
  f.innerHTML = `<div class="hd">${head}<span class="chev">${icon("down", "sm")}</span></div><div class="bd">${bodyHTML}</div>`;
  f.firstChild.onclick = () => { const o = !f.classList.contains("open"); f.classList.toggle("open", o); folds.set(key, o); };
  return f;
}

function renderAI(t, isLive) {
  const d = document.createElement("div"); d.className = "a";
  const msgs = t.msgs;
  const firstA = msgs.find(m => m.role === "assistant");
  const agentKey = (firstA && firstA.agent) || (cur && cur.agent) || active;
  const ag = S && S.agents[agentKey] ? S.agents[agentKey] : {short: agentKey};
  d.insertAdjacentHTML("beforeend", `<div class="who"><span class="av ${agentKey}">${agentKey === "planner" ? "DS" : "Q"}</span>${esc(ag.name || ag.short)}</div>`);

  const results = {};
  msgs.forEach(m => { if (m.role === "tool") results[m.tool_call_id] = m; });
  let lastToolPos = -1;
  msgs.forEach((m, i) => { if (m.role === "tool" || (m.role === "assistant" && m.tool_calls && m.tool_calls.length)) lastToolPos = i; });

  // thinking
  const thinking = msgs.filter(m => m.role === "assistant" && m.reasoning).map(m => m.reasoning.trim()).join("\n\n— — —\n\n");
  const lastA = [...msgs].reverse().find(m => m.role === "assistant");
  const thinkingNow = isLive && lastA && lastA.reasoning && !lastA.content && !(lastA.tool_calls || []).length;
  if (thinking) {
    const head = thinkingNow ? `<i class="spin"></i>يفكر…` : `${icon("brain", "sm")}فكّر <span class="sub">· ${thinking.length.toLocaleString("ar")} حرف</span>`;
    d.appendChild(foldEl(`${cur.id}:${t.idx}:think`, "think", head, esc(thinking), false));
  }

  // steps
  const steps = [];
  msgs.forEach((m, i) => {
    if (m.role !== "assistant") return;
    const hasCalls = (m.tool_calls || []).length > 0;
    if (!hasCalls && i > lastToolPos) return;               // final answer, shown below
    if (m.content && m.content.trim()) steps.push({note: m.content});
    if (hasCalls) m.tool_calls.forEach(c => steps.push({call: c, res: results[c.id]}));
  });
  if (steps.length) {
    const calls = steps.filter(s => s.call);
    const nFail = calls.filter(s => s.res && (s.res.error || s.res.denied)).length;
    const runningStep = isLive ? calls.find(s => !s.res) : null;
    const anyPending = isLive && live && Object.keys(live.approvals).length;
    const head = (runningStep && !anyPending ? `<i class="spin"></i>` : icon("layers", "sm")) +
      `${runningStep ? esc((TOOL_META[runningStep.call.name] || [0, runningStep.call.name])[1]) + "…" : "خطوات العمل"}` +
      ` <span class="sub">· ${calls.length} ${calls.length === 1 ? "خطوة" : "خطوات"}${nFail ? ` · <span style="color:var(--bad)">${nFail} ما نجحت</span>` : ""}</span>`;
    let body = "";
    steps.forEach((s, k) => {
      if (s.note) { body += `<div class="note md">${md(s.note)}</div>`; return; }
      const [ic, label] = TOOL_META[s.call.name] || ["sparkle", s.call.name];
      const r = s.res;
      let st;
      if (!r) st = live && live.running[s.call.id] ? `<span class="st"><i class="spin"></i></span>` : `<span class="st" style="opacity:.5"><i class="spin"></i></span>`;
      else if (r.denied) st = `<span class="st no" title="رفضتها">${icon("x", "sm")}</span>`;
      else if (r.error) st = `<span class="st bad" title="ما نجحت">${icon("alert", "sm")}</span>`;
      else st = `<span class="st ok">${icon("check", "sm")}</span>`;
      const ms = r && r.ms ? `<span class="ms">${r.ms < 1000 ? r.ms + "ms" : (r.ms / 1000).toFixed(1) + "s"}</span>` : "";
      const key = `${cur.id}:${s.call.id}`;
      const open = folds.get(key) ? " open" : "";
      const args = JSON.stringify(s.call.args || {}, null, 2);
      body += `<div class="step${open}" data-k="${esc(key)}"><div class="row"><span class="ico">${icon(ic, "sm")}</span><span class="lbl">${esc(label)}</span><span class="arg">${esc(argPreview(s.call.name, s.call.args))}</span>${ms}${st}</div>
        <div class="det"><div class="lab">المدخلات</div><pre class="out">${esc(args)}</pre>${r ? `<div class="lab">النتيجة</div><pre class="out" dir="auto">${esc((r.content || "").slice(0, 20000))}</pre>` : ""}</div></div>`;
      if (r && r.approval) body += `<div class="appr-rec">${r.approval.answer === "no" ? "❌ رفضت" : r.approval.answer === "always" ? "✔️ وافقت (دايم لهالجلسة)" : "✔️ وافقت"}: ${esc(r.approval.title)}</div>`;
    });
    const f = foldEl(`${cur.id}:${t.idx}:steps`, "steps", head, body, isLive);
    f.querySelectorAll(".step>.row").forEach(row => row.onclick = () => {
      const st = row.parentElement; const o = !st.classList.contains("open"); st.classList.toggle("open", o); folds.set(st.dataset.k, o);
    });
    d.appendChild(f);
  }

  // approvals (live)
  if (isLive && live) {
    for (const ap of Object.values(live.approvals)) d.appendChild(renderApproval(ap));
  }
  // live status: always visible while working, with timers
  if (isLive && live && !live.done) {
    const p = document.createElement("div"); p.className = "prog livebar";
    let bar = "";
    if (live.progress) {
      const [, pct] = live.progress.split("|");
      bar = pct !== undefined ? `<div class="bar"><i style="width:${+pct}%"></i></div>` : `<div class="bar ind"><i></i></div>`;
    }
    p.innerHTML = `<div class="l"><i class="spin"></i><span class="ph"></span><span class="tm"></span></div>${bar}`;
    d.appendChild(p);
    setTimeout(tickLive, 0);
  }
  // media
  const medias = [];
  msgs.forEach(m => (m.media || []).forEach(x => medias.push(x)));
  if (medias.length) {
    const g = document.createElement("div"); g.className = "gallery";
    for (const x of medias) g.appendChild(mediaEl(x));
    d.appendChild(g);
  }
  // final answer = assistant text after the last tool step
  const finals = msgs.filter((m, i) => m.role === "assistant" && i > lastToolPos && !(m.tool_calls || []).length && m.content);
  const finalText = finals.map(m => m.content).join("\n\n");
  if (finalText) {
    const b = document.createElement("div"); b.className = "md" + (isLive && live && !live.done ? " cursor" : "");
    b.innerHTML = md(finalText, isLive);
    d.appendChild(b);
  }
  // notices
  msgs.filter(m => m.role === "notice").forEach(n => {
    d.insertAdjacentHTML("beforeend", `<div class="notice ${n.level === "info" ? "info" : "error"}">${icon(n.level === "info" ? "info" : "alert", "sm")}<span>${esc(n.content)}</span></div>`);
  });
  // actions
  if (!isLive || (live && live.done)) {
    const acts = document.createElement("div"); acts.className = "actions";
    if (agentKey === "planner" && finalText && /خطة للمنفذ/.test(finalText) && isLastTurn(t)) {
      const h = document.createElement("button"); h.className = "handoff"; h.innerHTML = icon("rocket", "sm") + "نفّذها يا DeepSeek";
      h.onclick = () => handoff("planner"); acts.appendChild(h);
      const h2 = document.createElement("button"); h2.className = "handoff"; h2.innerHTML = icon("chip", "sm") + "سلّمها للمحلي";
      h2.onclick = () => handoff("executor"); acts.appendChild(h2);
    }
    if (finalText) acts.appendChild(iconBtn("copy", "نسخ الرد", () => copyText(finalText)));
    if (isLastTurn(t)) acts.appendChild(iconBtn("refresh", "أعد المحاولة", retry));
    d.appendChild(acts);
  }
  return d;
}
function isLastTurn(t) { const ts = turnsOf(cur.messages); return ts.length && ts[ts.length - 1].idx === t.idx; }
function iconBtn(ic, title, fn) { const b = document.createElement("button"); b.className = "icon-btn"; b.title = title; b.innerHTML = icon(ic, "sm"); b.onclick = fn; return b; }

function mediaEl(x) {
  if (mediaCache.has(x.url)) return mediaCache.get(x.url);
  const it = document.createElement("div"); it.className = "it";
  if (x.kind === "file") {
    it.className = "it filecard";
    const ext = (x.name || x.path).split(".").pop().toUpperCase().slice(0, 5);
    it.innerHTML = `<div class="fic">${icon("file")}<b>${esc(ext)}</b></div><div class="fmeta"><span class="fn" title="${esc(x.path)}">${esc(x.name || x.path)}</span><span class="fs">${x.size ? fmtSize(x.size) : ""}</span></div>`;
    const row = document.createElement("div"); row.className = "fbtns";
    row.appendChild(textBtn("ext", "افتح", () => openPath(x.path)));
    row.appendChild(textBtn("folder", "مكانه", () => openPath(x.path, true)));
    it.appendChild(row); mediaCache.set(x.url, it); return it;
  }
  let el;
  if (x.kind === "video") { el = document.createElement("video"); el.controls = true; el.preload = "metadata"; el.src = x.url; }
  else if (x.kind === "audio") { el = document.createElement("audio"); el.controls = true; el.src = x.url; it.style.background = "var(--panel)"; }
  else { el = document.createElement("img"); el.src = x.url; el.loading = "lazy"; el.dataset.zoom = x.url; }
  it.appendChild(el);
  const acts = document.createElement("div"); acts.className = "acts";
  acts.appendChild(iconBtn("ext", "افتح", () => openPath(x.path)));
  acts.appendChild(iconBtn("folder", "افتح مكانه", () => openPath(x.path, true)));
  acts.appendChild(iconBtn("copy", "انسخ المسار", () => copyText(x.path)));
  it.appendChild(acts);
  mediaCache.set(x.url, it);
  return it;
}

function textBtn(ic, label, fn) { const b = document.createElement("button"); b.className = "btn soft sm"; b.innerHTML = icon(ic, "sm") + label; b.onclick = fn; return b; }
async function openPath(path, reveal = false) { try { await api("/api/open_path", {path, reveal}); } catch (e) { toast(e.message, true); } }
function fmtDur(ms) { const s = Math.max(0, Math.floor(ms / 1000)); return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`; }
function tickLive() {
  if (!live || live.done) return;
  const el = document.querySelector(".livebar"); if (!el) return;
  const now = Date.now();
  let ph = live.phase || "يشتغل";
  if (live.offline) ph = "انقطع الاتصال بالسيرفر… أحاول أرجع";
  else if (Object.keys(live.approvals).length) ph = "ينتظر موافقتك 👇";
  else if (live.progress) ph = live.progress.split("|")[0];
  else if (now - live.lastEvent > 25000 && /يقرأ|يفكر/.test(ph)) ph += " (النماذج المحلية تاخذ وقت مع المحادثات الطويلة، لسا شغال)";
  el.querySelector(".ph").textContent = ph;
  el.querySelector(".tm").textContent = `${fmtDur(now - live.phaseAt)} · الكل ${fmtDur(now - live.startAt)}`;
  $("#hint").textContent = "شغال · " + fmtDur(now - live.startAt);
}
setInterval(tickLive, 1000);

function renderApproval(ap) {
  const d = document.createElement("div"); d.className = "appr";
  const danger = ap.cat === "delete";
  let pre = "";
  if (ap.diff) pre = `<pre class="out diff">${ap.diff.split("\n").map(l => `<span class="${l.startsWith("+") ? "add" : l.startsWith("-") ? "del" : l.startsWith("@@") ? "hunk" : ""}">${esc(l)}</span>`).join("\n")}</pre>`;
  else if (ap.code) pre = `<pre class="out">${esc(ap.detail)}</pre>`;
  d.innerHTML = `<div class="h">${icon(danger ? "trash" : "shield")}<span>يحتاج موافقتك</span><span class="tag${danger ? " danger" : ""}">${esc(ap.title)}</span></div>
    ${ap.code ? "" : `<div class="detail">${esc(ap.detail)}</div>`}${pre}<div class="btns"></div>`;
  const btns = d.querySelector(".btns");
  const mk = (cls, ic, label, ans) => {
    const b = document.createElement("button"); b.className = "btn " + cls; b.innerHTML = icon(ic, "sm") + label;
    b.onclick = async () => { btns.querySelectorAll("button").forEach(x => x.disabled = true); try { await api("/api/approve", {run: live.run, id: ap.id, answer: ans}); } catch (e) { toast(e.message, true); } };
    btns.appendChild(b);
  };
  mk(danger ? "danger" : "ok", "check", danger ? "احذف" : "موافق", "yes");
  if (ap.can_always) mk("soft", "shield", "موافق دايم لهالجلسة", "always");
  mk(danger ? "soft" : "danger", "x", "رفض", "no");
  return d;
}

function welcome() {
  const a = S ? S.agents[active] : null;
  const ex = [
    ["video", "عدّل فيديو", "قص أول 10 ثواني من آخر فيديو في التنزيلات وصغّر حجمه"],
    ["mic", "ترجمة وتفريغ", "طلّع ترجمة SRT عربية للفيديو اللي بأرفقه"],
    ["sparkle", "ولّد صورة", "ولّد صورة أنمي لمحارب ساموراي تحت المطر بإضاءة نيون"],
    ["eye", "تحكم بالجهاز", "خذ لقطة لشاشتي وقل لي وش البرامج المفتوحة"],
    ["globe", "ابحث في النت", "ابحث عن أحدث إصدار من ffmpeg ولخص الجديد فيه"],
    ["layers", "رتّب ملفاتي", "دور الملفات المكررة في سطح المكتب والتنزيلات"],
  ];
  return `<div class="welcome"><div class="logo big">3zT</div><h1>وش نسوي اليوم؟</h1>
    <p>${esc(a ? a.desc : "")}</p><div class="chips">${ex.map(([ic, t, p]) => `<button class="chip" data-p="${esc(p)}">${icon(ic)}<div><b>${t}</b>${esc(p)}</div></button>`).join("")}</div></div>`;
}

function renderThread() {
  const th = $("#thread");
  th.innerHTML = "";
  if (!cur || !cur.messages.length) {
    th.innerHTML = welcome();
    th.querySelectorAll(".chip").forEach(c => c.onclick = () => { $("#inp").value = c.dataset.p; autoGrow(); $("#inp").focus(); updateSend(); });
  } else {
    const ts = turnsOf(cur.messages);
    ts.forEach((t, k) => {
      const isLive = live && live.conv === cur.id && k === ts.length - 1 && t.type === "ai";
      const el = t.type === "user" ? renderUser(t) : renderAI(t, isLive);
      el.dataset.turn = t.idx;
      th.appendChild(el);
    });
    if (live && live.conv === cur.id && !live.done && ts.length && ts[ts.length - 1].type === "user") {
      const el = renderAI({type: "ai", msgs: [], idx: cur.messages.length}, true); el.dataset.turn = "pending"; th.appendChild(el);
    }
  }
  $("#title").textContent = cur && cur.messages.length ? cur.title : "";
  const u = $("#usage");
  if (cur && cur.usage) { u.style.display = "flex"; u.querySelector("span").textContent = (cur.usage / 1000).toFixed(1) + "K توكن"; } else u.style.display = "none";
  if (stickBottom) scrollBottom();
}
function scheduleRender() {
  if (renderQueued) return;
  renderQueued = true;
  requestAnimationFrame(() => { renderQueued = false; renderLast(); });
}
function renderLast() {
  // re-render only the live (last) turn for smooth streaming
  if (!cur) return;
  const th = $("#thread");
  const ts = turnsOf(cur.messages);
  const last = ts[ts.length - 1];
  const lastEl = th.lastElementChild;
  if (!last || !lastEl || th.querySelector(".welcome") || (last.type === "ai" && lastEl.dataset.turn !== String(last.idx) && lastEl.dataset.turn !== "pending")) { renderThread(); return; }
  if (last.type === "user") { renderThread(); return; }
  const scrollEl = $("#scroll");
  const prev = scrollEl.scrollTop;
  const el = renderAI(last, live && live.conv === cur.id);
  el.dataset.turn = last.idx;
  lastEl.replaceWith(el);
  if (stickBottom) scrollBottom(); else scrollEl.scrollTop = prev;
}
function scrollBottom() { const s = $("#scroll"); s.scrollTop = s.scrollHeight; }

// ================= live runs =================
function applyEvent(ev) {
  const msgs = cur && cur.id === live.conv ? cur.messages : null;
  const lastA = () => { if (!msgs) return null; const m = msgs[msgs.length - 1]; return m && m.role === "assistant" ? m : null; };
  switch (ev.type) {
    case "assistant": msgs && msgs.push({role: "assistant", content: "", reasoning: "", agent: ev.agent}); live.progress = ""; break;
    case "think": { const a = lastA(); if (a) a.reasoning += ev.text; break; }
    case "text": { const a = lastA(); if (a) a.content += ev.text; live.progress = ""; break; }
    case "replace_text": { const a = lastA(); if (a) a.content = ev.text; break; }
    case "tool_calls": { const a = lastA(); if (a) a.tool_calls = ev.calls; break; }
    case "drop_assistant": if (lastA()) msgs.pop(); break;
    case "msg": msgs && msgs.push(ev.message); if (ev.message.role === "tool") { delete live.running[ev.message.tool_call_id]; live.progress = ""; } break;
    case "tool_start": live.running[ev.id] = true; break;
    case "approval": live.approvals[ev.id] = ev; notifyAttention(); break;
    case "approval_done": delete live.approvals[ev.id]; break;
    case "progress": live.progress = ev.text; break;
    case "phase": live.phase = ev.text; live.phaseAt = Date.now(); if (/^ينفّذ|^يكمّل/.test(ev.text)) live.progress = ""; break;
    case "usage": if (cur && cur.id === live.conv) cur.usage = ev.total; break;
    case "done": live.done = true; live.progress = ""; live.approvals = {}; break;
  }
}
async function connect(runId, convId, from = 0) {
  const me = {run: runId, conv: convId, from, approvals: {}, running: {}, progress: "", done: false,
    phase: "يبدأ", startAt: Date.now(), phaseAt: Date.now(), lastEvent: Date.now(), offline: false};
  live = me;
  updateSend(); renderThread(); renderConvs();
  while (live === me && !me.done) {
    try {
      const r = await fetch(`/api/events?run=${runId}&from=${me.from}`, {headers: {"X-3zT": "1"}});
      if (r.status === 404) { me.done = true; break; }
      const reader = r.body.getReader(); const dec = new TextDecoder(); let buf = "";
      while (true) {
        if (live !== me) { try { reader.cancel(); } catch (e) {} break; }
        const {value, done} = await reader.read();
        if (done) break;
        if (live !== me) { try { reader.cancel(); } catch (e) {} break; }
        buf += dec.decode(value, {stream: true});
        let k;
        while ((k = buf.indexOf("\n\n")) >= 0) {
          const chunk = buf.slice(0, k); buf = buf.slice(k + 2);
          if (!chunk.startsWith("data:")) continue;
          let ev; try { ev = JSON.parse(chunk.slice(5)); } catch (e) { continue; }
          if (ev.seq !== me.from) continue;   // already applied
          me.from = ev.seq + 1;
          me.lastEvent = Date.now(); me.offline = false;
          applyEvent(ev);
        }
        if (cur && cur.id === me.conv) scheduleRender();
      }
    } catch (e) { me.offline = true; tickLive(); await new Promise(r => setTimeout(r, 1000)); }
  }
  if (live !== me) return;        // replaced by a fresh connection
  // sync with the saved conversation
  live = null;
  try {
    const fresh = await api("/api/conv?id=" + encodeURIComponent(me.conv));
    if (cur && cur.id === me.conv) cur = fresh;
  } catch (e) {}
  updateSend(); renderThread(); loadConvs();
  if (document.hidden) document.title = "✓ خلص — 3zT Agent";
}
function notifyAttention() { if (document.hidden) document.title = "⏳ ينتظر موافقتك — 3zT Agent"; }
document.addEventListener("visibilitychange", () => { if (!document.hidden) document.title = "3zT Agent"; });

// ================= conversations =================
async function loadConvs() { try { convs = await api("/api/convs"); renderConvs(); } catch (e) {} }
function renderConvs() {
  const box = $("#convs"); const q = $("#q").value.trim().toLowerCase();
  const list = convs.filter(c => !q || (c.title || "").toLowerCase().includes(q));
  if (!list.length) { box.innerHTML = `<div class="empty-list">${q ? "ما فيه نتائج" : "ما فيه محادثات للحين"}</div>`; return; }
  const now = new Date(); const day = 86400000;
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const grp = c => c.pinned ? "مثبتة" : c.updated * 1000 >= today ? "اليوم" : c.updated * 1000 >= today - day ? "أمس" : c.updated * 1000 >= today - 7 * day ? "آخر ٧ أيام" : "أقدم";
  let html = "", last = "";
  for (const c of list) {
    const g = grp(c);
    if (g !== last) { html += `<div class="grp">${g}</div>`; last = g; }
    const isLive = live && live.conv === c.id && !live.done;
    html += `<div class="conv${cur && cur.id === c.id ? " on" : ""}" data-id="${esc(c.id)}" role="button">${isLive ? '<i class="live"></i>' : ""}<span class="t">${esc(c.title)}</span><button class="more" data-more>${icon("dots", "sm")}</button></div>`;
  }
  box.innerHTML = html;
  box.querySelectorAll(".conv").forEach(el => {
    el.onclick = e => { if (e.target.closest("[data-more]")) { openMenu(e, el.dataset.id); return; } openConv(el.dataset.id); };
  });
}
async function openConv(id) {
  try {
    const c = await api("/api/conv?id=" + encodeURIComponent(id));
    store.set("last", id); folds.clear(); mediaCache.clear();
    if (c.run) {                    // running: rebuild from the run start and replay the live stream
      c.messages = c.messages.slice(0, c.base);
      cur = c;
      connect(c.run, c.id, 0);
    } else { cur = c; renderThread(); }
    renderConvs(); stickBottom = true; scrollBottom();
    $("#app").classList.remove("mobile-open");
  } catch (e) { toast(e.message, true); }
}
function newChat() {
  if (live && !live.done && cur && live.conv === cur.id) { /* keep the run going in the background */ }
  cur = null; folds.clear(); mediaCache.clear(); store.set("last", null);
  renderThread(); renderConvs(); $("#inp").focus();
}
function openMenu(e, id) {
  e.stopPropagation();
  const c = convs.find(x => x.id === id); const m = $("#menu");
  m.innerHTML = "";
  const add = (ic, label, fn, cls = "") => { const b = document.createElement("button"); b.className = cls; b.innerHTML = icon(ic, "sm") + label; b.onclick = () => { closeMenu(); fn(); }; m.appendChild(b); };
  add("pin", c && c.pinned ? "إلغاء التثبيت" : "تثبيت", async () => { await api("/api/conv/pin", {id}); loadConvs(); });
  add("edit", "إعادة تسمية", () => renameConv(id));
  add("trash", "حذف", async () => {
    let n = 0;
    try { n = (await api("/api/conv/files", {id})).files.length; } catch (er) {}
    if (!confirm(n ? "تحذف المحادثة وكل ملفاتها (مجلدها والملفات اللي سواها الإيجنت)؟\nتروح لسلة المحذوفات وتقدر ترجعها منها." : "تحذف المحادثة؟")) return;
    try { const r = await api("/api/conv/delete", {id}); if (cur && cur.id === id) newChat(); loadConvs(); toast(r.removed ? "انحذفت المحادثة وملفاتها" : "انحذفت المحادثة"); } catch (er) { toast(er.message, true); }
  }, "danger");
  m.classList.add("on");
  const r = e.target.closest("button").getBoundingClientRect();
  m.style.top = Math.min(r.bottom + 4, innerHeight - 140) + "px"; m.style.left = Math.max(8, r.left - 120) + "px";
}
function closeMenu() { $("#menu").classList.remove("on"); }
function renameConv(id) {
  const el = $(`.conv[data-id="${CSS.escape(id)}"]`); if (!el) return;
  const t = el.querySelector(".t"); const inp = document.createElement("input"); inp.value = t.textContent; t.replaceWith(inp); inp.focus(); inp.select();
  const done = async ok => { if (ok && inp.value.trim()) { await api("/api/conv/rename", {id, title: inp.value.trim()}); if (cur && cur.id === id) cur.title = inp.value.trim(), renderThread(); } loadConvs(); };
  inp.onkeydown = e => { if (e.key === "Enter") done(true); if (e.key === "Escape") done(false); };
  inp.onblur = () => done(true);
  inp.onclick = e => e.stopPropagation();
}

// ================= agents / state =================
function renderAgents() {
  if (!S) return;
  const box = $("#agents");
  box.innerHTML = "";
  for (const [k, a] of Object.entries(S.agents)) {
    const st = S.status[k] || "off";
    const b = document.createElement("button");
    b.className = `ag ${k}` + (k === active ? " on" : "");
    b.title = `${a.name}\n${a.model}\n${ST_LABEL[st] || st}`;
    b.innerHTML = `<i class="dot ${st}"></i><span class="nm">${esc(a.short)}</span>`;
    b.onclick = () => switchTo(k);
    box.appendChild(b);
  }
  $("#think").style.display = S.agents[active].kind === "ollama" ? "" : "none";
  const st = S.status[active];
  if (!(live && !live.done)) $("#hint").textContent = st === "loading" ? "يتحمّل في الكرت…" : st === "pulling" ? "ينزّل النموذج…" : "";
}
async function switchTo(k) {
  if (k === active) return;
  if (live && !live.done) { toast("انتظر المهمة تخلص أو وقفها", true); return; }
  active = k;
  if (S && S.agents[k].kind === "ollama" && S.status[k] !== "ready") S.status[k] = "loading";
  renderAgents(); if (!cur || !cur.messages.length) renderThread();
  try { await api("/api/switch", {agent: k}); } catch (e) { toast(e.message, true); }
  pollState();
}
let firstState = true;
async function pollState() {
  try {
    S = await api("/api/state");
    if (firstState) {
      firstState = false; active = S.settings.active; think = !!S.settings.think;
      $("#think").classList.toggle("on", think); $("#ver").textContent = "v" + S.version;
    }
    renderAgents(); banner();
  } catch (e) {
    showBanner("err", "البرنامج مو متصل بالسيرفر. إذا قفلته، افتحه من جديد من الاختصار.");
  }
}
function showBanner(kind, text, actText, act) {
  const b = $("#banner"); b.className = "banner on " + kind; b.querySelector("span").textContent = text;
  const btn = b.querySelector(".act");
  if (actText) { btn.style.display = ""; btn.textContent = actText; btn.onclick = act; } else btn.style.display = "none";
}
function banner() {
  const b = $("#banner"); const a = S.agents[active];
  const pulls = Object.values(S.pull || {});
  if (pulls.length) return showBanner("warn", pulls[0].text + ` (${pulls[0].pct}%)`);
  if (S.version !== UI_VERSION) return showBanner("warn", "البرنامج تحدّث — سكّره وافتحه من جديد.");
  if (a.kind === "ollama" && !S.ollama) return showBanner("err", "Ollama مو شغال. سكّر البرنامج وافتحه من الاختصار، أو شغّل Ollama يدويًا.");
  if (a.kind === "deepseek" && !S.settings.has_key) return showBanner("warn", "حط مفتاح DeepSeek عشان يشتغل.", "افتح الإعدادات", () => openSettings("ds"));
  if (S.status[active] === "missing") return showBanner("warn", `النموذج ${a.model} مو منزّل — بينزل تلقائيًا أول ما ترسل (حوالي 6.6GB).`);
  b.className = "banner";
}
async function pollStats() {
  try {
    const s = await api("/api/stats");
    const setBar = (id, pct) => { const el = $(id); el.style.width = Math.min(100, pct) + "%"; el.className = pct > 92 ? "crit" : pct > 80 ? "hi" : ""; };
    if (s.gpu) {
      $("#mVram").textContent = `${s.gpu.vram_used}/${s.gpu.vram_total} GB`; setBar("#bVram", s.gpu.vram_used / s.gpu.vram_total * 100);
      $("#mTemp").textContent = `${s.gpu.temp}° · ${s.gpu.util}%`; setBar("#bTemp", s.gpu.temp);
    }
    if (s.ram_total) { $("#mRam").textContent = `${s.ram_used}/${s.ram_total} GB`; setBar("#bRam", s.ram_used / s.ram_total * 100); }
    if (s.cpu !== null && s.cpu !== undefined) { $("#mCpu").textContent = s.cpu + "%"; setBar("#bCpu", s.cpu); }
  } catch (e) {}
}

// ================= composer =================
const inp = $("#inp");
function autoGrow() { inp.style.height = "auto"; inp.style.height = Math.min(inp.scrollHeight, 240) + "px"; }
function updateSend() {
  const btn = $("#send");
  if (live && !live.done) { btn.disabled = false; btn.classList.add("stop"); btn.innerHTML = icon("stop"); btn.title = "إيقاف"; return; }
  btn.classList.remove("stop"); btn.innerHTML = icon("up"); btn.title = "إرسال";
  btn.disabled = (!inp.value.trim() && !atts.some(a => a.rec)) || atts.some(a => a.status === "up");
}
inp.addEventListener("input", () => { autoGrow(); updateSend(); });
inp.addEventListener("keydown", e => { if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); if (!(live && !live.done)) send(); } });
$("#send").onclick = () => (live && !live.done) ? stop() : send();
$("#think").onclick = async () => { think = !think; $("#think").classList.toggle("on", think); try { await api("/api/settings", {think}); } catch (e) {} };

let convPending = null;
function ensureConv() {
  if (cur) return Promise.resolve(cur.id);
  if (!convPending) {
    convPending = api("/api/conv/new", {agent: active}).then(r => {
      cur = {id: r.id, title: "محادثة جديدة", agent: active, messages: [], usage: 0};
      return r.id;
    }).finally(() => { convPending = null; });
  }
  return convPending;
}
async function uploadFile(f) {
  if (live && !live.done && cur && live.conv === cur.id) { toast("انتظر المهمة تخلص قبل ما ترفق", true); return; }
  const convId = await ensureConv().catch(e => { toast(e.message, true); return null; });
  if (!convId) return;
  const a = {name: f.name || "paste.png", size: f.size, status: "up", pct: 0, rec: null};
  atts.push(a); renderAtts(); updateSend();
  const xhr = new XMLHttpRequest();
  xhr.open("POST", "/api/upload");
  xhr.setRequestHeader("X-3zT", "1");
  xhr.setRequestHeader("X-Conv", convId);
  xhr.setRequestHeader("X-File-Name", encodeURIComponent(a.name));
  xhr.upload.onprogress = e => { if (e.lengthComputable) { a.pct = Math.round(e.loaded / e.total * 100); renderAtts(); } };
  xhr.onload = () => {
    try { const r = JSON.parse(xhr.responseText); if (xhr.status !== 200) throw new Error(r.error || "فشل"); a.rec = r; a.status = "ok"; }
    catch (e) { a.status = "err"; toast("ما قدرت أرفع " + a.name, true); }
    renderAtts(); updateSend();
  };
  xhr.onerror = () => { a.status = "err"; renderAtts(); updateSend(); toast("ما قدرت أرفع " + a.name, true); };
  xhr.send(f);
}
function renderAtts() {
  const box = $("#atts"); box.innerHTML = "";
  atts.forEach((a, i) => {
    const d = document.createElement("div"); d.className = "chipatt";
    const kind = a.rec ? a.rec.kind : "";
    const ic = {video: "video", audio: "music", text: "file", image: "image"}[kind] || "file";
    const thumb = a.rec && a.rec.thumb ? `<img src="${esc(a.rec.thumb)}">` : `<div class="ic">${a.status === "up" ? '<i class="spin"></i>' : icon(ic, "sm")}</div>`;
    const sub = a.status === "up" ? `يرفع… ${a.pct}%` : a.status === "err" ? "فشل الرفع" : (a.rec.desc && kind !== "video" ? a.rec.desc : fmtSize(a.size));
    d.innerHTML = `${thumb}<div style="min-width:0"><span class="n">${esc(a.name)}</span><span class="s">${esc(sub)}</span></div>` + (a.status === "up" ? `<div class="pb"><i style="width:${a.pct}%"></i></div>` : "");
    const x = document.createElement("button"); x.className = "x"; x.innerHTML = icon("x", "sm"); x.onclick = () => { atts.splice(i, 1); renderAtts(); updateSend(); };
    d.appendChild(x); box.appendChild(d);
  });
}
$("#attach").onclick = () => $("#file").click();
$("#file").onchange = e => { [...e.target.files].forEach(uploadFile); e.target.value = ""; };
let dragN = 0;
addEventListener("dragenter", e => { if (![...(e.dataTransfer?.types || [])].includes("Files")) return; e.preventDefault(); dragN++; $("#drop").classList.add("on"); });
addEventListener("dragleave", e => { if (--dragN <= 0) { dragN = 0; $("#drop").classList.remove("on"); } });
addEventListener("dragover", e => e.preventDefault());
addEventListener("drop", e => { e.preventDefault(); dragN = 0; $("#drop").classList.remove("on"); [...(e.dataTransfer?.files || [])].forEach(uploadFile); });
addEventListener("paste", e => { const fs = [...(e.clipboardData?.files || [])]; if (fs.length) { e.preventDefault(); fs.forEach(uploadFile); } });

async function send(textOverride) {
  if (live && !live.done) return;
  const text = (textOverride ?? inp.value).trim();
  const ready = atts.filter(a => a.status === "ok").map(a => a.rec);
  if (atts.some(a => a.status === "up")) return;
  if (!text && !ready.length) return;
  const body = {conv: cur ? cur.id : null, agent: active, text, attachments: ready};
  inp.value = ""; autoGrow(); const saved = atts; atts = []; renderAtts(); updateSend();
  try {
    const r = await api("/api/chat", body);
    if (!cur || cur.id !== r.conv) { cur = {id: r.conv, title: r.title, agent: active, messages: [], usage: 0}; folds.clear(); mediaCache.clear(); }
    cur.messages.push(r.message);
    store.set("last", r.conv);
    stickBottom = true;
    loadConvs();
    connect(r.run, r.conv, 0);
  } catch (e) {
    toast(e.message, true); inp.value = text; atts = saved; renderAtts(); autoGrow(); updateSend();
  }
}
async function stop() { if (live) { try { await api("/api/stop", {run: live.run}); } catch (e) {} } }
async function retry() {
  if (!cur || (live && !live.done)) return;
  try {
    const r = await api("/api/retry", {conv: cur.id, agent: active});
    const lastU = cur.messages.map((m, i) => m.role === "user" && !m.internal ? i : -1).filter(i => i >= 0).pop();
    cur.messages = cur.messages.slice(0, lastU + 1);
    stickBottom = true;
    connect(r.run, r.conv, 0);
  } catch (e) { toast(e.message, true); }
}
async function handoff(target) {
  if (target !== active) await switchTo(target);
  send("نفّذ «خطة للمنفذ» اللي فوق بنفسك الحين، خطوة خطوة، وتأكد من النتيجة بعد كل خطوة. وإذا خلصت قل لي وش سويت ووين الملفات.");
}

// ================= settings =================
let warm = true, fvStop = true;
function openSettings(tab) {
  const s = S.settings;
  $("#sKey").value = ""; $("#sKey").placeholder = s.has_key ? `محفوظ (${s.key_hint}) — اكتب مفتاح جديد لتغييره` : "sk-...";
  $("#sDsModel").innerHTML = S.deepseek_models.map(m => `<option ${m === s.deepseek_model ? "selected" : ""}>${m}</option>`).join("");
  $("#sEffort").value = s.deepseek_effort; $("#sExec").value = s.executor_model; $("#sFree").value = s.free_model;
  $("#sCtx").value = String(s.num_ctx); if (!$("#sCtx").value) $("#sCtx").insertAdjacentHTML("beforeend", `<option value="${s.num_ctx}" selected>${s.num_ctx}</option>`);
  $("#sSteps").value = s.max_steps; warm = !!s.keep_executor_warm; $("#sWarm").classList.toggle("on", warm);
  fvStop = s.stop_freevideo_on_exit !== false; $("#sFvStop").classList.toggle("on", fvStop);
  $("#sWs").value = s.workspace; $("#sFvHome").value = s.freevideo_home || ""; $("#sImgModel").value = s.image_model || "auto";
  $("#sLoras").value = (s.image_loras || []).map(l => `${l.name}:${l.strength}`).join("\n");
  api("/api/memory").then(r => $("#sMem").value = r.text || "").catch(() => {});
  setTab(tab || "ds"); $("#settings").classList.add("on"); loadHealth();
}
function setTab(t) { $$(".tab").forEach(x => x.classList.toggle("on", x.dataset.tab === t)); $$(".pane").forEach(x => x.classList.toggle("on", x.dataset.pane === t)); if (t === "health") loadHealth(); if (t === "skills") loadSkills(); if (t === "gen") loadFv(); }
async function loadFv() {
  const box = $("#fvBox"); box.innerHTML = `<div class="h"><i class="spin"></i>يفحص…</div>`;
  try {
    const f = (await api("/api/health")).freevideo;
    const row = (ok, name, note) => `<div class="h"><span class="${ok ? "ok" : "bad"}">${icon(ok ? "check" : "x", "sm")}</span>${name}<span class="s">${esc(note || "")}</span></div>`;
    box.innerHTML = [
      row(f.installed, "مثبت", f.installed ? f.home : (f.launcher ? "افتح FreeVideo وكمّل التثبيت" : "شغّل install-freevideo.bat")),
      row(f.ready, "شغال وجاهز", f.ready ? `الإصدار ${f.version || ""} · ${f.url}` : (f.running ? (f.problem || "مو جاهز") : "مطفي — يشتغل تلقائيًا وقت التوليد")),
    ].join("");
  } catch (e) { box.textContent = e.message; }
}
$("#fvStart").onclick = async () => {
  try { const r = await api("/api/freevideo/start", {}); if (r.ok) { toast("يشغّل FreeVideo… إذا ظهرت نافذته اضغط Launch"); setTimeout(loadFv, 8000); } else toast(r.error, true); }
  catch (e) { toast(e.message, true); }
};
$("#sFvStopRow").onclick = () => { fvStop = !fvStop; $("#sFvStop").classList.toggle("on", fvStop); };
async function loadSkills() {
  const box = $("#skList"); box.innerHTML = `<div class="sk"><i class="spin"></i></div>`;
  try {
    const list = await api("/api/skills");
    box.innerHTML = "";
    for (const s of list) {
      const d = document.createElement("div"); d.className = "sk";
      d.innerHTML = `<div class="sw${s.enabled ? " on" : ""}"></div><div class="t"><b>${esc(s.name)}</b><span title="${esc(s.description)}">${esc(s.description)}</span></div><span class="tag">${s.builtin ? "مدمجة" : "مثبتة"}</span>`;
      d.querySelector(".sw").onclick = async e => { const on = !e.target.classList.contains("on"); e.target.classList.toggle("on", on); await api("/api/skills/toggle", {name: s.name, on}); };
      if (!s.builtin) d.appendChild(iconBtn("trash", "حذف", async () => { await api("/api/skills/remove", {name: s.name}); loadSkills(); }));
      box.appendChild(d);
    }
  } catch (e) { box.textContent = e.message; }
}
$("#skInstall").onclick = async () => {
  const url = $("#skUrl").value.trim(); if (!url) return;
  const b = $("#skInstall"); b.disabled = true; b.textContent = "يثبت…";
  try { const r = await api("/api/skills/install", {url}); toast("تثبتت: " + r.installed.join("، ")); $("#skUrl").value = ""; loadSkills(); }
  catch (e) { toast(e.message, true); }
  b.disabled = false; b.textContent = "تثبيت";
};
$$(".tab").forEach(t => t.onclick = () => setTab(t.dataset.tab));
$("#sWarmRow").onclick = () => { warm = !warm; $("#sWarm").classList.toggle("on", warm); };
$$("[data-close]").forEach(b => b.onclick = () => b.closest(".modal").classList.remove("on"));
$("#openSettings").onclick = () => S && openSettings();
$("#openWs").onclick = () => api("/api/open_folder", {which: "workspace"}).catch(e => toast(e.message, true));
$$("[data-open]").forEach(b => b.onclick = () => api("/api/open_folder", {which: b.dataset.open}).catch(() => {}));
$("#sKeyTest").onclick = async () => {
  const h = $("#sKeyHelp"); h.textContent = "يختبر…";
  try { const r = await api("/api/check_key", {key: $("#sKey").value.trim()}); h.innerHTML = r.ok ? `<span style="color:var(--ok)">✓ المفتاح شغال — الرصيد: ${esc(r.msg)}</span>` : `<span style="color:var(--bad)">✗ ${esc(r.msg)}</span>`; }
  catch (e) { h.textContent = e.message; }
};
$("#saveSettings").onclick = async () => {
  const body = {deepseek_model: $("#sDsModel").value, deepseek_effort: $("#sEffort").value, executor_model: $("#sExec").value.trim(),
    free_model: $("#sFree").value.trim(), num_ctx: +$("#sCtx").value, max_steps: +$("#sSteps").value, keep_executor_warm: warm,
    workspace: $("#sWs").value.trim(), freevideo_home: $("#sFvHome").value.trim(), image_model: $("#sImgModel").value,
    stop_freevideo_on_exit: fvStop,
    image_loras: $("#sLoras").value.split("\n").map(x => x.trim()).filter(Boolean).map(x => { const m = x.match(/^(.*?)(?::(-?[\d.]+))?$/); return {name: m[1].trim(), strength: m[2] ? +m[2] : 1}; })};
  if ($("#sKey").value.trim()) body.deepseek_key = $("#sKey").value.trim();
  try {
    await api("/api/settings", body);
    await api("/api/memory", {text: $("#sMem").value});
    $("#settings").classList.remove("on"); toast("انحفظت الإعدادات"); pollState();
  } catch (e) { toast(e.message, true); }
};
$("#resetAlways").onclick = async () => { await api("/api/reset_always", {}); toast("انلغت موافقات «دايم»"); };
async function loadHealth() {
  const box = $("#health"); box.innerHTML = `<div class="h"><i class="spin"></i>يفحص…</div>`;
  try {
    const h = await api("/api/health");
    const row = (ok, name, note) => `<div class="h"><span class="${ok ? "ok" : "bad"}">${icon(ok ? "check" : "x", "sm")}</span>${name}<span class="s">${esc(note || "")}</span></div>`;
    box.innerHTML = [
      row(h.ollama, "Ollama", h.ollama ? "الإصدار " + h.ollama_version : "مو شغال"),
      ...Object.entries(h.models).map(([k, ok]) => row(ok, S.agents[k].short + " — " + S.agents[k].model, ok ? "منزّل" : "ينزل تلقائيًا أول استخدام")),
      row(h.deepseek_key, "مفتاح DeepSeek", h.deepseek_key ? "موجود" : "ناقص"),
      row(h.ffmpeg, "ffmpeg", h.ffmpeg ? "" : "شغّل install.bat"),
      row(h.ytdlp, "yt-dlp (تحميل من المواقع)", h.ytdlp ? "" : "شغّل install.bat"),
      row(h.extras, "Whisper + إزالة الخلفية + الصوت", h.extras ? "" : "شغّل install-extras.bat"),
      row(h.realesrgan, "Real-ESRGAN (تكبير الصور)", h.realesrgan ? "" : "شغّل install-extras.bat"),
      row(h.freevideo.installed, "FreeVideo (توليد الصور والفيديو)", h.freevideo.installed ? (h.freevideo.ready ? "شغال" : "مثبت — يشتغل وقت التوليد") : "شغّل install-freevideo.bat"),
      row(h.nvidia, "كرت NVIDIA", h.nvidia ? "" : "nvidia-smi مو موجود"),
      row(h.pc_control, "التحكم بالجهاز", h.pc_control ? "" : "ويندوز بس"),
    ].join("");
    $("#aboutKv").innerHTML = `الإصدار ${esc(S.version)} · موافقات «دايم» الحالية: ${esc((S.always || []).join("، ") || "لا شي")}`;
  } catch (e) { box.innerHTML = `<div class="h">${esc(e.message)}</div>`; }
}

// ================= misc UI =================
$("#newChat").onclick = newChat;
$("#q").oninput = renderConvs;
$("#toggleSide").onclick = () => { if (innerWidth <= 900) $("#app").classList.toggle("mobile-open"); else $("#app").classList.toggle("collapsed"); };
$("#scroll").addEventListener("scroll", () => {
  const s = $("#scroll"); stickBottom = s.scrollHeight - s.scrollTop - s.clientHeight < 80;
  $("#jump").classList.toggle("on", !stickBottom && !!cur && cur.messages.length > 0);
});
$("#jump").onclick = () => { stickBottom = true; scrollBottom(); $("#jump").classList.remove("on"); };
document.addEventListener("click", e => {
  if (!e.target.closest("#menu")) closeMenu();
  const z = e.target.closest("[data-zoom]");
  if (z) { const lb = $("#lightbox"); lb.querySelector("img").src = z.dataset.zoom; lb.classList.add("on"); }
  const c = e.target.closest("[data-copy]");
  if (c) copyText(c.closest(".code").querySelector("pre").innerText);
});
$("#lightbox").onclick = () => $("#lightbox").classList.remove("on");
document.addEventListener("keydown", e => {
  if (e.ctrlKey && e.key.toLowerCase() === "n") { e.preventDefault(); newChat(); }
  else if (e.ctrlKey && e.key.toLowerCase() === "k") { e.preventDefault(); $("#q").focus(); }
  else if (e.ctrlKey && e.key === ",") { e.preventDefault(); S && openSettings(); }
  else if (e.key === "Escape") {
    if ($("#lightbox").classList.contains("on")) $("#lightbox").classList.remove("on");
    else if ($(".modal.on")) $(".modal.on").classList.remove("on");
    else if (live && !live.done) stop();
  }
});
addEventListener("pagehide", () => { try { navigator.sendBeacon("/api/bye", ""); } catch (e) {} });

// ================= boot =================
(async function boot() {
  hydrateIcons();
  await pollState();
  setInterval(pollState, 2500);
  pollStats(); setInterval(pollStats, 3000);
  await loadConvs();
  const deep = new URLSearchParams(location.search).get("c");
  if (deep && convs.some(c => c.id === deep)) await openConv(deep);
  else if (S && S.run) await openConv(S.run.conv);
  else { const last = store.get("last", null); if (last && convs.some(c => c.id === last)) await openConv(last); else renderThread(); }
  const st = new URLSearchParams(location.search).get("settings");
  if (st && S) openSettings(st);
  updateSend(); inp.focus();
})();
