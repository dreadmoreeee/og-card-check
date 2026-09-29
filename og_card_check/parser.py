"""Extract Open Graph, Twitter card, canonical and icon tags from HTML."""

from __future__ import annotations

from html.parser import HTMLParser


class _Collector(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.meta: list[tuple[str, str]] = []  # (key, content), key lowercased
        self.links: list[dict] = []
        self.title = ""
        self._in_title = False
        self._in_head_done = False

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "meta":
            key = a.get("property") or a.get("name")
            if key and "content" in a:
                self.meta.append((key.strip().lower(), a["content"].strip()))
            elif key:
                self.meta.append((key.strip().lower(), ""))
        elif tag == "link" and a.get("rel"):
            self.links.append({"rel": a["rel"].lower().split(), "href": a.get("href", "").strip(),
                               "sizes": a.get("sizes", ""), "type": a.get("type", "")})
        elif tag == "title" and not self.title:
            self._in_title = True
        elif tag == "body":
            self._in_head_done = True

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data


def parse_html(html: str) -> dict:
    """Return a dict with keys: meta (first value per key), all_meta, title, canonical, icons."""
    c = _Collector()
    try:
        c.feed(html)
        c.close()
    except Exception:
        pass
    meta: dict[str, str] = {}
    for k, v in c.meta:
        meta.setdefault(k, v)
    canonical = ""
    icon = ""
    apple = ""
    for link in c.links:
        rel = link["rel"]
        if "canonical" in rel and not canonical:
            canonical = link["href"]
        if "apple-touch-icon" in rel or "apple-touch-icon-precomposed" in rel:
            apple = apple or link["href"]
        elif "icon" in rel and not icon:
            icon = link["href"]
    return {
        "meta": meta,
        "title": " ".join(c.title.split()),
        "canonical": canonical,
        "icon": icon,
        "apple_touch_icon": apple,
    }
