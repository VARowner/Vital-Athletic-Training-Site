#!/usr/bin/env python3
"""Make an exact, self-contained static copy of the live vitalathletic.com site (hosted on Weebly).

Runs in GitHub Actions (see .github/workflows/site.yml) because that is where internet access is.
Output goes to ./site, which GitHub Pages serves as-is:

  site/<page>.html             every page, at its original URL, so old links keep working
  site/uploads/...             images and files from www.vitalathletic.com
  site/_ext/<host>/<path>      CSS, JS, fonts and images from Weebly's CDNs (editmysite.com, ...)

Every reference to those hosts (in HTML attributes, inline styles and CSS url(...)) is rewritten to the
local copy, so the site keeps working after the Weebly account is cancelled. Google Fonts and Google
Maps stay external on purpose.

Edits on top of the copy (kept small and listed here so they are easy to undo):
  - the blog is removed: nav/footer links dropped, /blog.html redirects to the home page
  - the "Website Design by My Personal Trainer Website" credit link is removed
  - files in ./static are copied into ./site, and pages with a form load /assets/forms.js, which sends
    submissions to Formspree instead of Weebly (see static/assets/forms.js)

`python3 scripts/mirror.py --finalize-only` re-applies the last two steps to an existing ./site without
re-downloading anything (use it after editing ./static).
"""
from __future__ import annotations

import hashlib
import re
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ORIGIN = "https://www.vitalathletic.com"
OWN_HOSTS = {"www.vitalathletic.com", "vitalathletic.com"}
# Hosts whose files are copied locally. Matched as a suffix, so "editmysite.com" covers cdn2.editmysite.com.
COPY_HOST_SUFFIXES = ("vitalathletic.com", "editmysite.com", "weebly.com", "weeblycloud.com", "weeblysite.com")

PAGES = [
    "/",
    "/about.html",
    "/personal-training.html",
    "/online-coaching.html",
    "/nutrition-coaching.html",
    "/gym-design--consulting.html",
    "/metabolic-assessments.html",
    "/contact.html",
    "/offer.html",
    "/privacy-policy.html",
    "/terms-and-conditions.html",
]
REDIRECT_TO_HOME = ["/blog.html"]

OUT = Path("site")
UA = "Mozilla/5.0 (compatible; vitalathletic-site-mirror/1.0)"

# url(...) in CSS and inline styles; src/href/srcset/data-* attributes in HTML.
CSS_URL = re.compile(r"url\(\s*(?!&quot;)(['\"]?)([^'\")]+)\1\s*\)", re.I)
# Inline styles written by Weebly quote URLs with HTML entities: url(&quot;/uploads/...&quot;)
CSS_URL_ENTITY = re.compile(r"url\(\s*&quot;(.*?)&quot;\s*\)", re.I)
CSS_IMPORT = re.compile(r"@import\s+(['\"])([^'\"]+)\1", re.I)
ATTR_URL = re.compile(
    r"""(\s(?:src|href|data-src|data-original|poster)\s*=\s*)(["'])([^"']*)\2""", re.I
)
SRCSET = re.compile(r"""(\ssrcset\s*=\s*)(["'])([^"']*)\2""", re.I)
ABS_IN_TEXT = re.compile(r"""(?:https?:)?//(?:[a-z0-9-]+\.)*(?:%s)/[^\s"'<>()\\]*""" % "|".join(
    re.escape(s) for s in COPY_HOST_SUFFIXES), re.I)

fetched: dict[str, str | None] = {}  # absolute url -> local site path ("/x/y") or None if failed
failures: list[str] = []


def should_copy(host: str) -> bool:
    host = host.lower()
    return any(host == s or host.endswith("." + s) for s in COPY_HOST_SUFFIXES)


def absolutize(ref: str, base: str) -> str | None:
    ref = ref.strip()
    if not ref or ref.startswith(("data:", "mailto:", "tel:", "javascript:", "#", "about:", "blob:")):
        return None
    return urllib.parse.urljoin(base, ref)


def local_path_for(url: str) -> str:
    """Site-root path a copied file is saved under. Query strings are folded into the name only when
    they matter (two different files differing by query)."""
    p = urllib.parse.urlsplit(url)
    host = p.hostname or ""
    path = urllib.parse.unquote(p.path) or "/"
    if path.endswith("/"):
        path += "index.html"
    if host in OWN_HOSTS:
        local = path
    else:
        local = f"/_ext/{host}{path}"
    if p.query and not re.search(r"\.(css|js|png|jpe?g|gif|svg|webp|ico|woff2?|ttf|eot|otf)$", local, re.I):
        stem, dot, ext = local.rpartition(".")
        h = hashlib.sha1(p.query.encode()).hexdigest()[:8]
        local = f"{stem}-{h}.{ext}" if dot else f"{local}-{h}"
    # Keep names safe for GitHub Pages.
    return re.sub(r"[^A-Za-z0-9._/~-]", "_", local)


def http_get(url: str) -> tuple[bytes, str]:
    last = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read(), r.headers.get_content_type()
        except (urllib.error.URLError, TimeoutError) as e:
            last = e
            time.sleep(1 + attempt)
    raise RuntimeError(f"{url}: {last}")


def write(local: str, data: bytes) -> None:
    dest = OUT / local.lstrip("/")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)


def copy_asset(url: str) -> str | None:
    """Download an asset (recursing into CSS) and return its local path, or None."""
    url = url.split("#", 1)[0]
    parts = urllib.parse.urlsplit(url)
    if (parts.hostname or "") in OWN_HOSTS and (
        parts.path in ("", "/") or parts.path in PAGES or parts.path in REDIRECT_TO_HOME or parts.path.endswith(".html")
    ):
        return parts.path or "/"  # one of our pages: link to it, never download it as a file
    if url in fetched:
        return fetched[url]
    if re.search(r"\.(php|aspx?)$", parts.path, re.I):
        return None  # a server endpoint (e.g. Weebly's form handler), not a file; forms are handled separately
    host = urllib.parse.urlsplit(url).hostname or ""
    if not should_copy(host):
        fetched[url] = None
        return None
    local = local_path_for(url)
    fetched[url] = local  # set before recursing so CSS cycles terminate
    try:
        data, ctype = http_get(url)
    except Exception as e:  # noqa: BLE001 - record and keep going
        failures.append(str(e))
        fetched[url] = None
        return None
    if ctype == "text/css" or local.lower().endswith(".css"):
        data = rewrite_css(data.decode("utf-8", "replace"), url).encode("utf-8")
    write(local, data)
    return local


def rewrite_ref(ref: str, base: str) -> str:
    absu = absolutize(ref, base)
    if not absu:
        return ref
    parts = urllib.parse.urlsplit(absu)
    host = parts.hostname or ""
    if host in OWN_HOSTS and (parts.path in PAGES or parts.path in REDIRECT_TO_HOME or parts.path.endswith(".html")):
        # A link to one of our own pages: keep it root-relative (same URLs on the new host).
        return parts.path + (f"#{parts.fragment}" if parts.fragment else "")
    if not should_copy(host):
        return ref
    local = copy_asset(absu)
    return local if local else ref


def rewrite_css(css: str, base: str) -> str:
    css = CSS_IMPORT.sub(lambda m: f"@import {m.group(1)}{rewrite_ref(m.group(2), base)}{m.group(1)}", css)
    return CSS_URL.sub(lambda m: f"url({m.group(1)}{rewrite_ref(m.group(2), base)}{m.group(1)})", css)


def rewrite_html(html: str, base: str) -> str:
    def attr(m: re.Match[str]) -> str:
        return f"{m.group(1)}{m.group(2)}{rewrite_ref(m.group(3), base)}{m.group(2)}"

    def srcset(m: re.Match[str]) -> str:
        items = []
        for part in m.group(3).split(","):
            bits = part.strip().split()
            if bits:
                bits[0] = rewrite_ref(bits[0], base)
                items.append(" ".join(bits))
        return f"{m.group(1)}{m.group(2)}{', '.join(items)}{m.group(2)}"

    html = ATTR_URL.sub(attr, html)
    html = SRCSET.sub(srcset, html)
    # Inline styles and <style> blocks.
    html = CSS_URL_ENTITY.sub(lambda m: f"url(&quot;{rewrite_ref(m.group(1), base)}&quot;)", html)
    html = CSS_URL.sub(lambda m: f"url({m.group(1)}{rewrite_ref(m.group(2), base)}{m.group(1)})", html)
    # Any remaining absolute references to the copied hosts (e.g. inside inline scripts / JSON).
    html = ABS_IN_TEXT.sub(lambda m: copy_asset(absolutize(m.group(0), base) or "") or m.group(0), html)
    return apply_site_edits(html)


def apply_site_edits(html: str) -> str:
    # Remove the blog from menus and footer.
    html = re.sub(r"<li[^>]*>\s*<a[^>]*href=[\"'][^\"']*blog\.html[\"'][^>]*>.*?</a>\s*(?:<div[^>]*>.*?</div>\s*)?</li>",
                  "", html, flags=re.I | re.S)
    html = re.sub(r"<a[^>]*href=[\"'][^\"']*blog\.html[\"'][^>]*>.*?</a>", "", html, flags=re.I | re.S)
    # Remove the template vendor's credit link.
    html = re.sub(r"<a[^>]*mypersonaltrainerwebsite\.com[^>]*>.*?</a>", "", html, flags=re.I | re.S)
    html = re.sub(r"Website Design by\s*", "", html, flags=re.I)
    return html


REDIRECT_HTML = """<!doctype html><html><head><meta charset="utf-8"><title>Vital Athletic</title>
<link rel="canonical" href="/"><meta http-equiv="refresh" content="0; url=/"></head>
<body><a href="/">Continue to Vital Athletic</a></body></html>
"""


FORMS_TAG = '<script src="/assets/forms.js" defer></script>'


def finalize() -> None:
    """Copy ./static into ./site and wire up the forms. Safe to run repeatedly."""
    static = Path("static")
    if static.is_dir():
        shutil.copytree(static, OUT, dirs_exist_ok=True)
    for page in OUT.glob("*.html"):
        html = page.read_text("utf-8")
        # Weebly's map widget is served by weebly.com; use a plain Google Maps embed at the same spot.
        html, n = re.subn(
            r"""src=(["'])(?:https?:)?//www\.weebly\.com/weebly/apps/generateMap\.php\?[^"']*?long=(-?[\d.]+)&(?:amp;)?lat=(-?[\d.]+)[^"']*\1""",
            lambda m: f'src="https://maps.google.com/maps?q={m.group(3)},{m.group(2)}&z=15&output=embed" loading="lazy"',
            html,
        )
        if n:
            page.write_text(html, "utf-8")
            print(f"map replaced: {page}")
        html2 = re.sub(r'action="(?:https?:)?//www\.weebly\.com/weebly/apps/formSubmit\.php"', 'action="#"', html)
        if html2 != html:
            html = html2
            page.write_text(html, "utf-8")
        if re.search(r'<form[^>]+id="form-', html) and FORMS_TAG not in html:
            html = re.sub(r"</body>", FORMS_TAG + "\n</body>", html, count=1, flags=re.I)
            page.write_text(html, "utf-8")
            print(f"forms wired: {page}")


def main() -> int:
    if "--finalize-only" in sys.argv:
        finalize()
        return 0
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir()
    for page in PAGES:
        url = urllib.parse.urljoin(ORIGIN, page)
        print(f"page {page}", flush=True)
        data, _ = http_get(url)
        html = rewrite_html(data.decode("utf-8", "replace"), url)
        write("/index.html" if page == "/" else page, html.encode("utf-8"))
    for page in REDIRECT_TO_HOME:
        write(page, REDIRECT_HTML.encode())
    # GitHub Pages serves 404.html for unknown paths; send people home rather than to a blank error.
    write("/404.html", REDIRECT_HTML.encode())
    (OUT / ".nojekyll").write_text("")  # serve folders starting with "_" (like _ext) as-is
    finalize()

    copied = sum(1 for v in fetched.values() if v)
    print(f"\ncopied {copied} assets; {len(failures)} failures")
    for f in failures:
        print("  FAILED", f)
    # Anything still pointing at the old host after rewriting?
    leftovers = []
    for f in OUT.rglob("*"):
        if f.suffix.lower() in {".html", ".css"}:
            for m in ABS_IN_TEXT.finditer(f.read_text("utf-8", "replace")):
                leftovers.append(f"{f}: {m.group(0)[:120]}")
    print(f"{len(leftovers)} remaining references to the old host")
    for line in leftovers[:50]:
        print("  LEFT", line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
