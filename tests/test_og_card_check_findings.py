import json

from og_card_check import analyze
from og_card_check.analyze import check_url
from og_card_check.cli import main
from og_card_check.fetch import Fetcher

PAGE = """<html><head><title>T</title>
<meta property="og:title" content="T">
<meta property="og:description" content="D">
<meta property="og:image" content="{img}">
<meta property="og:url" content="{og_url}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="S">
{extra}
<link rel="canonical" href="{canonical}">
<link rel="icon" href="/fav.png">
<link rel="apple-touch-icon" href="/touch.png">
</head><body>x</body></html>"""


def fetcher():
    return Fetcher(delay=0, timeout=5)


def codes(r, level=None):
    return {f["code"] for f in r["findings"] if level is None or f["level"] == level}


def build(site, png_bytes, img="{base}/img.png", og_url="{base}/p", canonical="{base}/p",
          extra="", image=None, icons=True):
    site.add("/p", "text/html", PAGE.format(img=img, og_url=og_url, canonical=canonical, extra=extra))
    if image is not None:
        site.add("/img.png", "image/png", image)
    if icons:
        site.add("/fav.png", "image/png", png_bytes(32, 32))
        site.add("/touch.png", "image/png", png_bytes(180, 180))
    return site.base + "/p"


def test_square_image_gets_ratio_warning(site, png_bytes):
    url = build(site, png_bytes, image=png_bytes(1200, 1200))
    r = check_url(url, fetcher())
    assert "image-ratio" in codes(r, "warn")
    assert "image-small" not in codes(r)
    assert r["images"]["og:image"]["ratio"] == 1.0


def test_small_image_warns_but_is_not_tiny(site, png_bytes):
    url = build(site, png_bytes, image=png_bytes(600, 315))
    r = check_url(url, fetcher())
    assert "image-small" in codes(r, "warn")
    assert "image-tiny" not in codes(r)
    assert "image-ratio" not in codes(r)


def test_tiny_image_is_error(site, png_bytes):
    url = build(site, png_bytes, image=png_bytes(150, 100))
    assert "image-tiny" in codes(check_url(url, fetcher()), "error")


def test_file_size_thresholds(site, png_bytes, monkeypatch):
    data = png_bytes(1200, 630)
    url = build(site, png_bytes, image=data)
    monkeypatch.setattr(analyze, "WARN_BYTES", len(data) - 1)
    monkeypatch.setattr(analyze, "ERR_BYTES", len(data) + 1000)
    r = check_url(url, fetcher())
    assert "image-large" in codes(r, "warn") and "image-too-big" not in codes(r)
    monkeypatch.setattr(analyze, "ERR_BYTES", len(data) - 1)
    r = check_url(url, fetcher())
    assert "image-too-big" in codes(r, "error") and "image-large" not in codes(r)


def test_file_size_padded_response(site, png_bytes, monkeypatch):
    # PNG decoders ignore trailing bytes, so padding grows the file cheaply.
    data = png_bytes(1200, 630) + b"\x00" * 300000
    url = build(site, png_bytes, image=data)
    monkeypatch.setattr(analyze, "WARN_BYTES", 200000)
    r = check_url(url, fetcher())
    assert "image-large" in codes(r, "warn")
    assert r["images"]["og:image"]["bytes"] == len(data)


def test_relative_image_url_finding(site, png_bytes):
    url = build(site, png_bytes, img="/img.png", image=png_bytes(1200, 630))
    r = check_url(url, fetcher())
    assert "relative-image" in codes(r, "warn")
    assert r["images"]["og:image"]["url"] == site.base + "/img.png"
    assert r["images"]["og:image"]["status"] == 200


def test_og_url_canonical_mismatch(site, png_bytes):
    url = build(site, png_bytes, og_url="{base}/a", canonical="{base}/b", image=png_bytes(1200, 630))
    assert "url-mismatch" in codes(check_url(url, fetcher()), "warn")


def test_og_url_canonical_match_ignores_trailing_slash(site, png_bytes):
    url = build(site, png_bytes, og_url="{base}/a/", canonical="{base}/a", image=png_bytes(1200, 630))
    assert "url-mismatch" not in codes(check_url(url, fetcher()))


def test_unreachable_og_image_is_error(site, png_bytes):
    url = build(site, png_bytes, img="{base}/missing.png")
    r = check_url(url, fetcher())
    assert "image-unreachable" in codes(r, "error")
    assert r["images"]["og:image"]["status"] == 404


def test_og_image_not_an_image(site, png_bytes):
    url = build(site, png_bytes)
    site.add("/img.png", "text/html", "<html></html>")
    assert "image-not-image" in codes(check_url(url, fetcher()), "error")


def test_icons_reachable(site, png_bytes):
    url = build(site, png_bytes, image=png_bytes(1200, 630))
    r = check_url(url, fetcher())
    assert "icon-unreachable" not in codes(r)
    assert r["images"]["favicon"]["status"] == 200
    assert r["images"]["apple-touch-icon"]["status"] == 200


def test_icons_unreachable_warn(site, png_bytes):
    url = build(site, png_bytes, image=png_bytes(1200, 630), icons=False)
    r = check_url(url, fetcher())
    msgs = [f["message"] for f in r["findings"] if f["code"] == "icon-unreachable"]
    assert len(msgs) == 2
    assert any("favicon" in m for m in msgs) and any("apple-touch-icon" in m for m in msgs)
    assert "icon-unreachable" not in codes(r, "error")


def test_twitter_summary_large_image_accepts_2_to_1(site, png_bytes):
    extra = '<meta name="twitter:card" content="summary_large_image">'
    url = build(site, png_bytes, extra=extra, image=png_bytes(1200, 600))
    r = check_url(url, fetcher())
    assert r["images"]["og:image"]["ratio"] == 2.0
    assert "image-ratio" not in codes(r)
    assert r["tags"]["twitter:card"] == "summary_large_image"


def test_twitter_image_checked_separately(site, png_bytes):
    extra = ('<meta name="twitter:card" content="summary_large_image">'
             '<meta name="twitter:image" content="{base}/tw.png">')
    url = build(site, png_bytes, extra=extra, image=png_bytes(1200, 630))
    site.add("/tw.png", "image/png", png_bytes(800, 800))
    r = check_url(url, fetcher())
    assert r["images"]["twitter:image"]["width"] == 800
    assert "image-ratio" in codes(r, "warn")


def test_json_report_structure(site, png_bytes, tmp_path):
    url = build(site, png_bytes, image=png_bytes(1200, 630))
    js = tmp_path / "r.json"
    rc = main([url, site.base + "/nope", "--delay", "0", "--no-preview", "--json", str(js)])
    assert rc == 1
    data = json.loads(js.read_text(encoding="utf-8"))
    assert isinstance(data, list) and len(data) == 2
    good, bad = data
    for key in ("url", "final_url", "status", "content_type", "tags", "resolved",
                "findings", "images"):
        assert key in good
    assert good["status"] == 200 and good["url"] == url
    assert good["tags"]["og:image"] == site.base + "/img.png"
    assert set(good["resolved"]) >= {"title", "description", "image", "fallbacks"}
    for f in good["findings"]:
        assert set(f) == {"level", "code", "message"}
        assert f["level"] in ("error", "warn", "info")
    img = good["images"]["og:image"]
    assert {"url", "status", "content_type", "bytes", "width", "height", "ratio"} <= set(img)
    assert not any(k.startswith("_") for k in img)
    assert bad["status"] == 404
    assert bad["findings"][0]["code"] == "http-status"


def test_json_to_stdout(site, png_bytes, capsys):
    url = build(site, png_bytes, image=png_bytes(1200, 630))
    main([url, "--delay", "0", "--no-preview", "--json", "-"])
    out = capsys.readouterr().out
    assert json.loads(out[out.index("["):])[0]["url"] == url
