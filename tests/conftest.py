import http.server
import io
import sys
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class Site:
    """A tiny local HTTP site: routes maps path -> (content-type, str|bytes)."""

    def __init__(self):
        self.routes = {}
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), self._make_handler())
        self.base = "http://127.0.0.1:%d" % self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def _make_handler(self):
        site = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                self._serve(True)

            def do_HEAD(self):
                self._serve(False)

            def _serve(self, with_body):
                item = site.routes.get(self.path)
                if item is None:
                    self.send_response(404)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                ctype, data = item
                if isinstance(data, str):
                    data = data.replace("{base}", site.base).encode()
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                if with_body:
                    self.wfile.write(data)

        return Handler

    def add(self, path, ctype, data):
        self.routes[path] = (ctype, data)

    def close(self):
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def site():
    s = Site()
    yield s
    s.close()


@pytest.fixture
def png_bytes():
    from PIL import Image

    def make(w, h, color=(20, 90, 200)):
        buf = io.BytesIO()
        Image.new("RGB", (w, h), color).save(buf, "PNG")
        return buf.getvalue()

    return make
