"""Render PNG mock cards in the style of Facebook, LinkedIn, X and Slack."""

from __future__ import annotations

import io
import os
import re
from urllib.parse import urlsplit

from PIL import Image, ImageDraw, ImageFont, ImageOps

_FONT_CANDIDATES = {
    False: ["arial.ttf", "DejaVuSans.ttf", "LiberationSans-Regular.ttf"],
    True: ["arialbd.ttf", "DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf"],
}


def _font(size: int, bold: bool = False):
    for name in _FONT_CANDIDATES[bold]:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size)
    except TypeError:
        return ImageFont.load_default()


def _wrap(draw, text: str, font, width: int, max_lines: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    cur = ""
    i = 0
    while i < len(words):
        trial = (cur + " " + words[i]).strip()
        if draw.textlength(trial, font=font) <= width or not cur:
            cur = trial
            i += 1
            if draw.textlength(cur, font=font) > width:  # single overlong word
                while cur and draw.textlength(cur, font=font) > width:
                    cur = cur[:-1]
        else:
            lines.append(cur)
            cur = ""
            if len(lines) == max_lines:
                break
    else:
        if cur:
            lines.append(cur)
    if len(lines) >= max_lines and (i < len(words) or cur):
        lines = lines[:max_lines]
        last = lines[-1]
        while last and draw.textlength(last + "...", font=font) > width:
            last = last[:-1]
        if i < len(words) or (cur and cur not in lines):
            lines[-1] = last.rstrip() + "..."
    return lines


def _text(draw, xy, text, font, fill, width, max_lines, line_h):
    x, y = xy
    for ln in _wrap(draw, text, font, width, max_lines):
        draw.text((x, y), ln, font=font, fill=fill)
        y += line_h
    return y


def _load(image_bytes: bytes | None):
    if not image_bytes:
        return None
    try:
        im = Image.open(io.BytesIO(image_bytes))
        im = ImageOps.exif_transpose(im)
        return im.convert("RGB")
    except Exception:
        return None


def _fit(im, size):
    if im is None:
        ph = Image.new("RGB", size, (221, 224, 228))
        d = ImageDraw.Draw(ph)
        f = _font(max(12, size[1] // 10))
        msg = "no image"
        d.text(((size[0] - d.textlength(msg, font=f)) / 2, size[1] / 2 - 8), msg, font=f, fill=(120, 126, 134))
        return ph
    return ImageOps.fit(im, size, Image.Resampling.LANCZOS, centering=(0.5, 0.5))


def _domain(url: str) -> str:
    return (urlsplit(url).hostname or url).lower()


def facebook(im, title, desc, url, site, W=600) -> Image.Image:
    ih = round(W / 1.91)
    canvas = Image.new("RGB", (W, ih + 110), (255, 255, 255))
    canvas.paste(_fit(im, (W, ih)), (0, 0))
    d = ImageDraw.Draw(canvas)
    d.rectangle([0, ih, W, ih + 110], fill=(240, 242, 245))
    d.text((12, ih + 10), (site or _domain(url)).upper(), font=_font(12), fill=(101, 103, 107))
    y = _text(d, (12, ih + 28), title, _font(17, True), (5, 5, 5), W - 24, 2, 21)
    _text(d, (12, y + 2), desc, _font(14), (101, 103, 107), W - 24, 1 if y > ih + 55 else 2, 18)
    d.rectangle([0, 0, W - 1, ih + 109], outline=(206, 208, 212))
    return canvas


def linkedin(im, title, desc, url, site, W=600) -> Image.Image:
    ih = round(W / 1.91)
    canvas = Image.new("RGB", (W, ih + 78), (255, 255, 255))
    canvas.paste(_fit(im, (W, ih)), (0, 0))
    d = ImageDraw.Draw(canvas)
    y = _text(d, (14, ih + 10), title, _font(16, True), (0, 0, 0), W - 28, 2, 20)
    d.text((14, y + 4), _domain(url), font=_font(13), fill=(102, 102, 102))
    d.rectangle([0, 0, W - 1, ih + 77], outline=(224, 223, 220))
    return canvas


def x_card(im, title, desc, url, site, card="summary_large_image", W=600) -> Image.Image:
    large = card != "summary"
    if large:
        ih = W // 2
        canvas = Image.new("RGB", (W, ih), (255, 255, 255))
        canvas.paste(_fit(im, (W, ih)), (0, 0))
        d = ImageDraw.Draw(canvas)
        label = _domain(url) + " - " + title
        f = _font(13)
        text = _wrap(d, label, f, W - 44, 1)[0] if label else ""
        tw = d.textlength(text, font=f)
        d.rounded_rectangle([10, ih - 34, 10 + tw + 20, ih - 10], radius=6, fill=(0, 0, 0))
        d.text((20, ih - 30), text, font=f, fill=(255, 255, 255))
        canvas = _round(canvas, 16)
    else:
        sq = 130
        canvas = Image.new("RGB", (W, sq), (255, 255, 255))
        canvas.paste(_fit(im, (sq, sq)), (0, 0))
        d = ImageDraw.Draw(canvas)
        d.text((sq + 14, 12), _domain(url), font=_font(13), fill=(83, 100, 113))
        y = _text(d, (sq + 14, 32), title, _font(15, True), (15, 20, 25), W - sq - 28, 1, 19)
        _text(d, (sq + 14, y + 2), desc, _font(14), (83, 100, 113), W - sq - 28, 2, 18)
        canvas = _round(canvas, 16, outline=(207, 217, 222))
    return canvas


def _round(im, radius, outline=None):
    im = im.convert("RGBA")
    mask = Image.new("L", im.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, im.size[0] - 1, im.size[1] - 1], radius=radius, fill=255)
    out = Image.new("RGBA", im.size, (255, 255, 255, 255))
    out.paste(im, (0, 0), mask)
    if outline:
        ImageDraw.Draw(out).rounded_rectangle([0, 0, im.size[0] - 1, im.size[1] - 1], radius=radius, outline=outline)
    return out.convert("RGB")


def slack(im, title, desc, url, site, W=600) -> Image.Image:
    pad = 14
    iw = 360
    ih = 200
    canvas = Image.new("RGB", (W, 40 + 22 + 60 + 20 + ih + 20), (255, 255, 255))
    d = ImageDraw.Draw(canvas)
    d.rectangle([pad, 12, pad + 3, canvas.size[1] - 12], fill=(221, 221, 221))
    x = pad + 16
    d.text((x, 12), site or _domain(url), font=_font(13, True), fill=(29, 28, 29))
    y = _text(d, (x, 32), title, _font(15, True), (18, 100, 163), W - x - pad, 2, 19)
    y = _text(d, (x, y + 2), desc, _font(14), (29, 28, 29), W - x - pad, 3, 18)
    if im is not None:
        w, h = im.size
        s = min(iw / w, ih / h, 1.0) if w and h else 1
        thumb = im.resize((max(1, int(w * s)), max(1, int(h * s))), Image.Resampling.LANCZOS)
        canvas = canvas.crop((0, 0, W, y + 10 + thumb.size[1] + 14)) if y + 10 + thumb.size[1] + 14 < canvas.size[1] else canvas
        if canvas.size[1] < y + 10 + thumb.size[1] + 14:
            grown = Image.new("RGB", (W, y + 10 + thumb.size[1] + 14), (255, 255, 255))
            grown.paste(canvas, (0, 0))
            canvas = grown
        d = ImageDraw.Draw(canvas)
        d.rectangle([pad, 12, pad + 3, canvas.size[1] - 12], fill=(221, 221, 221))
        canvas.paste(thumb, (x, y + 10))
    else:
        canvas = canvas.crop((0, 0, W, y + 14))
    return canvas


def slugify(url: str) -> str:
    s = urlsplit(url)
    raw = (s.netloc + s.path + (("?" + s.query) if s.query else "")).strip("/")
    return re.sub(r"[^A-Za-z0-9._-]+", "_", raw)[:80] or "page"


def render_previews(result: dict, outdir: str) -> dict:
    """Write facebook/linkedin/x/slack PNGs plus a combined sheet. Returns {name: path}."""
    res = result.get("resolved") or {}
    if not result.get("tags"):
        return {}
    imgs = result.get("images", {})
    x_img = imgs.get("twitter:image") or imgs.get("og:image") or {}
    og_img = imgs.get("og:image") or imgs.get("twitter:image") or {}
    og_bytes = og_img.get("_data")
    x_bytes = x_img.get("_data")
    url = result.get("final_url") or result["url"]
    title = res.get("title") or "(no title)"
    desc = res.get("description") or ""
    site = res.get("site_name") or ""
    card = result["tags"].get("twitter:card") or "summary"
    og_im, x_im = _load(og_bytes), _load(x_bytes)
    cards = {
        "facebook": facebook(og_im, title, desc, url, site),
        "linkedin": linkedin(og_im, title, desc, url, site),
        "x": x_card(x_im, res.get("x_title") or title, res.get("x_description") or desc, url, site, card),
        "slack": slack(og_im, title, desc, url, site),
    }
    d = os.path.join(outdir, slugify(result["url"]))
    os.makedirs(d, exist_ok=True)
    paths = {}
    for name, im in cards.items():
        p = os.path.join(d, name + ".png")
        im.save(p)
        paths[name] = p
    gap = 16
    W = max(i.size[0] for i in cards.values()) + 2 * gap
    H = sum(i.size[1] + gap for i in cards.values()) + gap
    sheet = Image.new("RGB", (W, H), (236, 238, 241))
    y = gap
    for im in cards.values():
        sheet.paste(im, (gap, y))
        y += im.size[1] + gap
    p = os.path.join(d, "preview.png")
    sheet.save(p)
    paths["sheet"] = p
    return paths
