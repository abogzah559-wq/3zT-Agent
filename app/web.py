"""Web access without API keys: search (DuckDuckGo HTML, Bing fallback) and page reading."""
import base64
import gzip
import html
import re
import urllib.parse
import urllib.request
import zlib
from html.parser import HTMLParser

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/130.0 Safari/537.36 Edg/130.0")


def _fetch(url, data=None, timeout=20, max_bytes=6 << 20):
    req = urllib.request.Request(url, data=data, headers={
        "User-Agent": UA, "Accept-Language": "ar,en;q=0.8", "Accept-Encoding": "gzip, deflate",
        "Accept": "text/html,application/xhtml+xml,application/json,text/plain;q=0.9,*/*;q=0.5"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read(max_bytes)
        enc = (r.headers.get("Content-Encoding") or "").lower()
        if enc == "gzip":
            raw = gzip.decompress(raw)
        elif enc == "deflate":
            raw = zlib.decompress(raw, -zlib.MAX_WBITS)
        ctype = r.headers.get("Content-Type") or ""
        charset = r.headers.get_content_charset() or "utf-8"
        return raw, ctype, charset, r.geturl()


def _clean(s):
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", s)).split())


def _bing_url(url):
    """Bing wraps results in /ck/a?...&u=a1<base64url>; return the real address."""
    if "bing.com/ck/a" not in url:
        return url
    try:
        u = urllib.parse.parse_qs(urllib.parse.urlparse(url).query).get("u", [""])[0]
        if u.startswith("a1"):
            b = u[2:]
            return base64.urlsafe_b64decode(b + "=" * (-len(b) % 4)).decode("utf-8", "replace")
    except Exception:
        pass
    return url


def _ddg(page, count):
    out = []
    blocks = re.findall(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>(.*?)(?=<a[^>]+class="result__a"|$)',
                        page, re.S)
    for href, title, rest in blocks:
        m = re.search(r'class="result__snippet"[^>]*>(.*?)</a>', rest, re.S)
        out.append((href, title, m.group(1) if m else ""))
    if not out:     # lite layout
        for href, title in re.findall(r"<a[^>]+href=\"([^\"]+)\"[^>]+class=['\"]result-link['\"][^>]*>(.*?)</a>", page, re.S):
            out.append((href, title, ""))
        snips = re.findall(r"class=['\"]result-snippet['\"][^>]*>(.*?)</td>", page, re.S)
        out = [(h, t, snips[i] if i < len(snips) else "") for i, (h, t, _) in enumerate(out)]
    res = []
    for href, title, snip in out:
        url = html.unescape(href)
        if "uddg=" in url:
            url = urllib.parse.unquote(urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["uddg"][0])
        if url.startswith("//"):
            url = "https:" + url
        if "duckduckgo.com/y.js" in url or not url.startswith("http"):      # ads
            continue
        res.append({"title": _clean(title), "url": url, "snippet": _clean(snip)})
        if len(res) >= count:
            break
    return res


def _words(text):
    return {w for w in re.findall(r"[\w\u0600-\u06FF]{3,}", text.lower())}


def _relevant(results, query):
    """Drop results that share no word with the query (spam a search engine sometimes serves to bots)."""
    q = _words(query)
    if not q:
        return results
    keep = [r for r in results if q & _words(r["title"] + " " + r["snippet"] + " " + r["url"])]
    return keep


def search(query, count=8):
    results, err = [], None
    ascii_q = all(ord(c) < 128 for c in query)
    for url, data in (("https://html.duckduckgo.com/html/", {"q": query, "kl": "wt-wt"}),
                      ("https://lite.duckduckgo.com/lite/", {"q": query, "kl": "wt-wt"})):
        try:
            raw, _, cs, _ = _fetch(url, urllib.parse.urlencode(data).encode())
            results = _relevant(_ddg(raw.decode(cs, errors="replace"), count), query)
        except Exception as e:
            err = e
        if results:
            break
    if not results:
        try:
            q = {"q": query, "count": count}
            if ascii_q:
                q.update(setlang="en", mkt="en-US")
            raw, _, cs, _ = _fetch("https://www.bing.com/search?" + urllib.parse.urlencode(q))
            page = raw.decode(cs, errors="replace")
            for li in re.findall(r'<li class="b_algo".*?</li>', page, re.S):
                a = re.search(r'<h2[^>]*>\s*<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', li, re.S)
                if not a:
                    continue
                p = re.search(r"<p[^>]*>(.*?)</p>", li, re.S)
                results.append({"title": _clean(a.group(2)), "url": _bing_url(html.unescape(a.group(1))),
                                "snippet": _clean(p.group(1)) if p else ""})
                if len(results) >= count:
                    break
            results = _relevant(results, query)
        except Exception as e:
            err = e
    if not results:
        if err:
            return f"خطأ: البحث ما اشتغل ({err}). جرّب fetch_url على موقع رسمي مباشرة."
        return "ما لقيت نتائج مفيدة. جرّب كلمات ثانية أو fetch_url على موقع رسمي مباشرة."
    return "\n\n".join(f"[{i}] {r['title']}\n{r['url']}\n{r['snippet']}" for i, r in enumerate(results, 1))


class _Text(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "head", "template", "iframe"}
    BLOCK = {"p", "div", "section", "article", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6",
             "header", "footer", "pre", "blockquote", "table", "ul", "ol"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.skip, self.title, self._in_title = [], 0, "", False

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip += 1
        if tag == "title":
            self._in_title = True
        if tag in self.BLOCK:
            self.out.append("\n")
        if tag == "li":
            self.out.append("• ")
        if tag in ("h1", "h2", "h3"):
            self.out.append("## ")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.skip:
            self.skip -= 1
        if tag == "title":
            self._in_title = False
        if tag in self.BLOCK:
            self.out.append("\n")

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        if not self.skip:
            self.out.append(data)


def read_page(url, max_chars=40_000):
    if not re.match(r"^https?://", url):
        url = "https://" + url
    raw, ctype, cs, final = _fetch(url)
    if "pdf" in ctype:
        return f"{final}\n(هذا ملف PDF — نزّله بأداة download واقرأه بـ read_file)"
    text = raw.decode(cs, errors="replace")
    if "html" in ctype or text.lstrip()[:15].lower().startswith(("<!doctype", "<html")):
        p = _Text()
        p.feed(text)
        body = "".join(p.out)
        body = re.sub(r"[ \t\r\f\v]+", " ", body)
        body = re.sub(r"\n\s*\n+", "\n\n", body).strip()
        text = (f"# {p.title.strip()}\n" if p.title.strip() else "") + body
    if len(text) > max_chars:
        text = text[:max_chars] + f"\n...(انقطع، الصفحة {len(text):,} حرف)"
    return f"{final}\n\n{text}"
