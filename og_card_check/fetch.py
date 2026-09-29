"""Polite HTTP fetching (GET/HEAD only) with a minimum delay between requests."""

from __future__ import annotations

import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field

USER_AGENT = "og-card-check/1.0 (+https://github.com/dreadmoreeee/og-card-check)"
MAX_BODY = 12 * 1024 * 1024


@dataclass
class Response:
    url: str
    final_url: str = ""
    status: int = 0
    content_type: str = ""
    content_length: int | None = None
    body: bytes = b""
    error: str = ""
    headers: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.error and 200 <= self.status < 400


class Fetcher:
    def __init__(self, delay: float = 1.0, timeout: float = 15.0, user_agent: str = USER_AGENT):
        self.delay = delay
        self.timeout = timeout
        self.user_agent = user_agent
        self._last = 0.0
        self.count = 0

    def _wait(self) -> None:
        gap = self.delay - (time.monotonic() - self._last)
        if gap > 0 and self._last:
            time.sleep(gap)
        self._last = time.monotonic()
        self.count += 1

    def request(self, url: str, method: str = "GET", max_body: int = MAX_BODY) -> Response:
        resp = Response(url=url, final_url=url)
        if not url.lower().startswith(("http://", "https://")):
            resp.error = "unsupported URL scheme"
            return resp
        self._wait()
        req = urllib.request.Request(url, method=method, headers={
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,image/*;q=0.8,*/*;q=0.5",
        })
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                self._fill(resp, r)
                if method == "GET":
                    resp.body = r.read(max_body + 1)
                    if len(resp.body) > max_body:
                        resp.body = resp.body[:max_body]
                        resp.error = "body larger than %d bytes (truncated)" % max_body
        except urllib.error.HTTPError as e:
            self._fill(resp, e)
        except Exception as e:  # network errors, timeouts, bad URLs
            resp.error = "%s: %s" % (type(e).__name__, e)
        finally:
            pass
        return resp

    @staticmethod
    def _fill(resp: Response, r) -> None:
        resp.status = getattr(r, "status", None) or r.getcode()
        resp.final_url = r.geturl()
        hdrs = r.headers
        resp.headers = {k.lower(): v for k, v in hdrs.items()}
        resp.content_type = (hdrs.get("Content-Type") or "").split(";")[0].strip().lower()
        cl = hdrs.get("Content-Length")
        resp.content_length = int(cl) if cl and cl.isdigit() else None
        cs = hdrs.get_content_charset() if hasattr(hdrs, "get_content_charset") else None
        resp.headers["_charset"] = cs or ""

    def get(self, url: str) -> Response:
        return self.request(url, "GET")

    def head(self, url: str) -> Response:
        return self.request(url, "HEAD")
