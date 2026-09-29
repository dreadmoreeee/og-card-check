"""Analyze a page: tags, fallbacks, image checks, findings."""

from __future__ import annotations

import io
from urllib.parse import urljoin, urlsplit, urlunsplit

from .fetch import Fetcher, Response
from .parser import parse_html

TITLE_MAX = 60          # og:title is usually cut around here in feeds
TWITTER_TITLE_MAX = 70
DESC_MAX = 160
OG_DESC_MAX = 200
MIN_W, MIN_H = 1200, 630
HARD_MIN = 200          # Facebook rejects images smaller than this
WARN_BYTES = 5 * 1024 * 1024
ERR_BYTES = 8 * 1024 * 1024
IMAGE_TYPES = {"image/png", "image/jpeg", "image/jpg", "image/gif", "image/webp",
               "image/x-icon", "image/vnd.microsoft.icon", "image/svg+xml", "image/avif"}

OG_KEYS = ["og:title", "og:description", "og:image", "og:image:width", "og:image:height",
           "og:image:alt", "og:url", "og:type", "og:site_name"]
TW_KEYS = ["twitter:card", "twitter:title", "twitter:description", "twitter:image"]


def _f(level, code, msg):
    return {"level": level, "code": code, "message": msg}


def _is_abs(u: str) -> bool:
    return u.lower().startswith(("http://", "https://"))


def _norm(u: str) -> str:
    s = urlsplit(u.strip())
    path = s.path.rstrip("/") or "/"
    return urlunsplit((s.scheme.lower(), s.netloc.lower(), path, s.query, ""))


def check_image(fetcher: Fetcher, url: str, full: bool = True) -> dict:
    """Fetch an image and report status, type, bytes and pixel size."""
    info = {"url": url, "status": 0, "content_type": "", "bytes": None,
            "width": None, "height": None, "ratio": None, "error": ""}
    if full:
        r = fetcher.get(url)
    else:
        r = fetcher.head(url)
        if r.status in (403, 405, 501) or (r.ok and not r.content_type):
            r = fetcher.get(url)
    info["status"] = r.status
    info["content_type"] = r.content_type
    info["error"] = r.error
    info["bytes"] = len(r.body) if r.body else r.content_length
    if r.content_length is not None and (not r.body or r.content_length > len(r.body)):
        info["bytes"] = r.content_length
    if r.ok and r.body:
        if r.content_type == "image/svg+xml":
            return info
        try:
            from PIL import Image
            with Image.open(io.BytesIO(r.body)) as im:
                info["width"], info["height"] = im.size
                info["ratio"] = round(im.size[0] / im.size[1], 3) if im.size[1] else None
                info["_data"] = r.body
        except Exception as e:
            info["error"] = info["error"] or "cannot decode image: %s" % type(e).__name__
    return info


def _check_social_image(fetcher, url, label, findings, card_type=""):
    img = check_image(fetcher, url)
    if img["error"] and not img["status"]:
        findings.append(_f("error", "image-unreachable", "%s not reachable (%s)" % (label, img["error"])))
        return img
    if img["status"] >= 400 or img["status"] == 0:
        findings.append(_f("error", "image-unreachable", "%s returned HTTP %s" % (label, img["status"])))
        return img
    ct = img["content_type"]
    if ct and not ct.startswith("image/"):
        findings.append(_f("error", "image-not-image", "%s content-type is %s, not an image" % (label, ct)))
        return img
    if img["error"]:
        findings.append(_f("error", "image-invalid", "%s: %s" % (label, img["error"])))
        return img
    b = img["bytes"] or 0
    if b > ERR_BYTES:
        findings.append(_f("error", "image-too-big", "%s is %.1f MB (limit ~8 MB)" % (label, b / 1048576)))
    elif b > WARN_BYTES:
        findings.append(_f("warn", "image-large", "%s is %.1f MB (above ~5 MB)" % (label, b / 1048576)))
    w, h = img["width"], img["height"]
    if w and h:
        if w < HARD_MIN or h < HARD_MIN:
            findings.append(_f("error", "image-tiny", "%s is %dx%d, below the 200x200 minimum" % (label, w, h)))
        elif w < MIN_W or h < MIN_H:
            findings.append(_f("warn", "image-small", "%s is %dx%d; %dx%d or larger is recommended" % (label, w, h, MIN_W, MIN_H)))
        ratio = w / h
        if not (1.85 <= ratio <= 1.97 or 1.97 < ratio <= 2.03):
            findings.append(_f("warn", "image-ratio", "%s aspect ratio is %.2f:1; about 1.91:1 (or 2:1 for X summary_large_image) is best" % (label, ratio)))
    return img


def _check_icon(fetcher, url, label, findings, required=False):
    img = check_image(fetcher, url, full=False)
    if img["status"] and img["status"] < 400 and not img["error"]:
        return img
    lvl = "warn"
    findings.append(_f(lvl, "icon-unreachable", "%s not reachable at %s (%s)" % (
        label, url, img["error"] or "HTTP %s" % img["status"])))
    return img


def resolve(tags: dict, page: dict) -> dict:
    """Values a platform would show, applying the usual fallbacks."""
    m = page["meta"]
    fb = []
    title = m.get("og:title", "")
    if not title:
        title = m.get("twitter:title", "") or page["title"]
        if title:
            fb.append("og:title missing: platforms fall back to %s" % (
                "twitter:title" if m.get("twitter:title") else "<title>"))
    desc = m.get("og:description", "")
    if not desc:
        desc = m.get("twitter:description", "") or m.get("description", "")
        if desc:
            fb.append("og:description missing: platforms fall back to %s" % (
                "twitter:description" if m.get("twitter:description") else "meta description"))
    image = m.get("og:image", "") or m.get("og:image:url", "")
    if not image and m.get("twitter:image"):
        image = m["twitter:image"]
        fb.append("og:image missing: falling back to twitter:image")
    x_title = m.get("twitter:title") or title
    if not m.get("twitter:title") and title:
        fb.append("twitter:title missing: X falls back to og:title" if m.get("og:title") else "twitter:title missing: X falls back to <title>")
    x_desc = m.get("twitter:description") or desc
    if not m.get("twitter:description") and desc:
        fb.append("twitter:description missing: X falls back to og:description")
    x_image = m.get("twitter:image") or image
    if not m.get("twitter:image") and image:
        fb.append("twitter:image missing: X falls back to og:image")
    return {"title": title, "description": desc, "image": image, "x_title": x_title,
            "x_description": x_desc, "x_image": x_image,
            "site_name": m.get("og:site_name", ""), "fallbacks": fb}


def analyze_html(fetcher: Fetcher, page_url: str, html: str, check_images: bool = True) -> dict:
    page = parse_html(html)
    m = page["meta"]
    findings: list[dict] = []
    tags = {k: m.get(k, "") for k in OG_KEYS + TW_KEYS}
    tags["title"] = page["title"]
    tags["description"] = m.get("description", "")
    tags["canonical"] = page["canonical"]
    tags["icon"] = page["icon"]
    tags["apple-touch-icon"] = page["apple_touch_icon"]
    res = resolve(tags, page)

    required = {"og:title": "error", "og:image": "error", "og:description": "warn",
                "og:url": "warn", "og:type": "warn", "og:site_name": "info"}
    for k, lvl in required.items():
        if k not in m:
            if k == "og:title" and res["title"]:
                lvl = "warn"
            if k == "og:image" and res["image"]:
                lvl = "warn"
            findings.append(_f(lvl, "missing-tag", "%s is missing" % k))
        elif not m[k]:
            findings.append(_f("error" if lvl == "error" else "warn", "empty-tag", "%s is empty" % k))
    for k in ("og:image:width", "og:image:height", "og:image:alt"):
        if k not in m and m.get("og:image"):
            findings.append(_f("info", "missing-tag", "%s is missing (recommended)" % k))
    if "twitter:card" not in m:
        findings.append(_f("warn", "missing-tag", "twitter:card is missing; X shows a small summary at best"))
    elif m["twitter:card"] not in ("summary", "summary_large_image", "app", "player"):
        findings.append(_f("warn", "bad-twitter-card", "twitter:card=%r is not a known card type" % m["twitter:card"]))
    if not page["canonical"]:
        findings.append(_f("warn", "missing-canonical", "no <link rel=canonical>"))

    # lengths
    if len(res["title"]) > TITLE_MAX:
        findings.append(_f("warn", "title-long", "title is %d chars; likely truncated above ~%d" % (len(res["title"]), TITLE_MAX)))
    if len(res["x_title"]) > TWITTER_TITLE_MAX:
        findings.append(_f("warn", "twitter-title-long", "twitter title is %d chars; X truncates around %d" % (len(res["x_title"]), TWITTER_TITLE_MAX)))
    if len(res["description"]) > OG_DESC_MAX:
        findings.append(_f("warn", "description-long", "description is %d chars; likely truncated above ~%d" % (len(res["description"]), OG_DESC_MAX)))
    elif len(res["description"]) > DESC_MAX:
        findings.append(_f("info", "description-long", "description is %d chars; some platforms cut at ~%d" % (len(res["description"]), DESC_MAX)))

    # og:url vs canonical
    ogu, can = m.get("og:url", ""), page["canonical"]
    if ogu and not _is_abs(ogu):
        findings.append(_f("warn", "relative-url", "og:url is not absolute: %s" % ogu))
    if can and not _is_abs(can):
        findings.append(_f("warn", "relative-url", "canonical is not absolute: %s" % can))
    if ogu and can and _norm(urljoin(page_url, ogu)) != _norm(urljoin(page_url, can)):
        findings.append(_f("warn", "url-mismatch", "og:url (%s) differs from canonical (%s)" % (ogu, can)))

    # images
    images: dict[str, dict] = {}
    for key, label in (("og:image", "og:image"), ("twitter:image", "twitter:image")):
        raw = m.get(key, "")
        if not raw:
            continue
        if not _is_abs(raw):
            findings.append(_f("warn", "relative-image", "%s is a relative URL (%s); use an absolute URL" % (label, raw)))
        absu = urljoin(page_url, raw)
        if key == "twitter:image" and absu == images.get("og:image", {}).get("url"):
            images[key] = images["og:image"]
            continue
        if check_images:
            images[key] = _check_social_image(fetcher, absu, label, findings, m.get("twitter:card", ""))
        else:
            images[key] = {"url": absu}
    if not res["image"]:
        pass
    elif not m.get("og:image") and res["image"] and "twitter:image" not in images:
        images["og:image"] = {"url": urljoin(page_url, res["image"])}
    og = images.get("og:image")
    if og and og.get("width"):
        for dim, key in (("width", "og:image:width"), ("height", "og:image:height")):
            declared = m.get(key)
            if declared and declared.isdigit() and int(declared) != og[dim]:
                findings.append(_f("warn", "declared-size", "%s=%s but the file is %s px" % (key, declared, og[dim])))

    # icons
    if check_images:
        ico = urljoin(page_url, page["icon"]) if page["icon"] else urljoin(page_url, "/favicon.ico")
        images["favicon"] = _check_icon(fetcher, ico, "favicon", findings)
        if page["apple_touch_icon"]:
            images["apple-touch-icon"] = _check_icon(fetcher, urljoin(page_url, page["apple_touch_icon"]), "apple-touch-icon", findings)
        else:
            findings.append(_f("info", "missing-apple-touch-icon", "no apple-touch-icon declared"))

    return {"tags": tags, "resolved": res, "findings": findings, "images": images}


def check_url(url: str, fetcher: Fetcher | None = None, check_images: bool = True) -> dict:
    """Fetch and analyze one URL. Returns a JSON-friendly dict (plus private _data bytes)."""
    fetcher = fetcher or Fetcher()
    r: Response = fetcher.get(url)
    result = {"url": url, "final_url": r.final_url, "status": r.status, "content_type": r.content_type,
              "tags": {}, "resolved": {}, "findings": [], "images": {}}
    if r.error and not r.body:
        result["findings"].append(_f("error", "fetch-failed", "could not fetch page: %s" % r.error))
        return result
    if r.status >= 400 or r.status == 0:
        result["findings"].append(_f("error", "http-status", "page returned HTTP %s" % r.status))
        return result
    if r.content_type and "html" not in r.content_type:
        result["findings"].append(_f("error", "not-html", "content-type is %s, not HTML" % r.content_type))
        return result
    cs = r.headers.get("_charset") or "utf-8"
    try:
        html = r.body.decode(cs, errors="replace")
    except LookupError:
        html = r.body.decode("utf-8", errors="replace")
    if r.final_url != url:
        result["findings"].append(_f("info", "redirect", "redirected to %s" % r.final_url))
    result.update(analyze_html(fetcher, r.final_url or url, html, check_images))
    result["findings"] = result["findings"] if not r.error else result["findings"] + [_f("warn", "truncated", r.error)]
    return result


def error_count(results: list[dict]) -> int:
    return sum(1 for r in results for f in r["findings"] if f["level"] == "error")
