import http.server
import io
import json
import threading

import pytest
from PIL import Image

from og_card_check.analyze import check_url, error_count
from og_card_check.cli import main
from og_card_check.fetch import Fetcher
from og_card_check.parser import parse_html
from og_card_check.preview import render_previews


def png(w, h, color=(200, 30, 30)):
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color).save(buf, "PNG")
    return buf.getvalue()


GOOD = """<html><head><title>Good page</title>
<meta property="og:title" content="Good page">
<meta property="og:description" content="A fine description.">
<meta property="og:image" content="{base}/big.png">
<meta property="og:image:alt" content="alt">
<meta property="og:url" content="{base}/good">
<meta property="og:type" content="website">
<meta property="og:site_name" content="Site">
<meta name="twitter:card" content="summary_large_image">
<link rel="canonical" href="{base}/good">
<link rel="icon" href="/fav.png">
<link rel="apple-touch-icon" href="/touch.png">
</head><body>x</body></html>"""

BAD = """<html><head><title>{longtitle}</title>
<meta property="og:title" content="{longtitle}">
<meta property="og:image" content="/small.png">
<meta property="og:url" content="{base}/other">
<link rel="canonical" href="{base}/bad">
</head></html>"""

NOIMG = """<html><head><title>Only title</title><meta name="description" content="meta desc"></head></html>"""

ROUTES = {}


class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        self._serve(True)

    def do_HEAD(self):
        self._serve(False)

    def _serve(self, body):
        base = "http://127.0.0.1:%d" % self.server.server_address[1]
        item = ROUTES.get(self.path)
        if item is None:
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        ctype, data = item
        if isinstance(data, str):
            data = data.replace("{base}", base).encode()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if body:
            self.wfile.write(data)


@pytest.fixture(scope="module")
def base():
    ROUTES.update({
        "/good": ("text/html; charset=utf-8", GOOD),
        "/bad": ("text/html", BAD.replace("{longtitle}", "T" * 90)),
        "/noimg": ("text/html", NOIMG),
        "/big.png": ("image/png", png(1200, 630)),
        "/small.png": ("image/png", png(300, 300)),
        "/fav.png": ("image/png", png(32, 32)),
        "/touch.png": ("image/png", png(180, 180)),
        "/text": ("text/plain", "hello"),
    })
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield "http://127.0.0.1:%d" % srv.server_address[1]
    srv.shutdown()


def fetcher():
    return Fetcher(delay=0, timeout=5)


def codes(r, level=None):
    return {f["code"] for f in r["findings"] if level is None or f["level"] == level}


def test_parse_html():
    p = parse_html('<title> A  b </title><meta property="og:title" content="X">'
                   '<link rel="shortcut icon" href="/i.ico"><link rel="canonical" href="/c">')
    assert p["title"] == "A b"
    assert p["meta"]["og:title"] == "X"
    assert p["icon"] == "/i.ico" and p["canonical"] == "/c"


def test_good_page_has_no_errors_or_warnings(base):
    r = check_url(base + "/good", fetcher())
    assert r["status"] == 200
    assert not codes(r, "error") and not codes(r, "warn"), r["findings"]
    img = r["images"]["og:image"]
    assert (img["width"], img["height"]) == (1200, 630)
    assert img["ratio"] == pytest.approx(1.905, abs=0.01)
    assert r["images"]["favicon"]["status"] == 200
    assert r["images"]["apple-touch-icon"]["status"] == 200


def test_bad_page_findings(base):
    r = check_url(base + "/bad", fetcher())
    c = codes(r)
    assert {"relative-image", "url-mismatch", "title-long", "image-small",
            "missing-tag"} <= c
    assert r["images"]["og:image"]["url"] == base + "/small.png"
    # favicon default /favicon.ico does not exist here
    assert "icon-unreachable" in c


def test_fallbacks(base):
    r = check_url(base + "/noimg", fetcher())
    fb = " ".join(r["resolved"]["fallbacks"])
    assert "<title>" in fb and "meta description" in fb
    assert "og:image" in codes(r, "error") or any("og:image" in f["message"] for f in r["findings"])
    assert error_count([r]) >= 1


def test_http_404_and_not_html(base):
    assert "http-status" in codes(check_url(base + "/nope", fetcher()), "error")
    assert "not-html" in codes(check_url(base + "/text", fetcher()), "error")


def test_connection_refused():
    r = check_url("http://127.0.0.1:9/x", fetcher())
    assert "fetch-failed" in codes(r, "error")


def test_previews_written(base, tmp_path):
    r = check_url(base + "/good", fetcher())
    paths = render_previews(r, str(tmp_path))
    assert set(paths) == {"facebook", "linkedin", "x", "slack", "sheet"}
    for p in paths.values():
        with Image.open(p) as im:
            assert im.size[0] >= 300
    with Image.open(paths["x"]) as im:
        assert im.size == (600, 300)  # 2:1 large card


def test_cli_exit_codes_and_reports(base, tmp_path, capsys):
    md, js = tmp_path / "r.md", tmp_path / "r.json"
    rc = main([base + "/good", "--delay", "0", "-o", str(tmp_path / "out"),
               "--markdown", str(md), "--json", str(js)])
    assert rc == 0
    assert "og-card-check report" in md.read_text(encoding="utf-8")
    data = json.loads(js.read_text(encoding="utf-8"))
    assert data[0]["url"] == base + "/good"
    rc = main([base + "/good", base + "/noimg", "--delay", "0", "--no-preview"])
    assert rc == 1
    capsys.readouterr()


def test_strict_makes_warnings_fail(base):
    assert main([base + "/bad", "--delay", "0", "--no-preview"]) == 0
    assert main([base + "/bad", "--delay", "0", "--no-preview", "--strict"]) == 1
