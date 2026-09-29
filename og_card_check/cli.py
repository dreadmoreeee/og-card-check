"""Command line interface."""

from __future__ import annotations

import argparse
import os
import sys

from . import __version__
from .analyze import check_url, error_count
from .fetch import Fetcher
from .preview import render_previews
from .report import to_json, to_markdown, to_text


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="og-card-check",
                                description="Check how links to a page look when shared.")
    p.add_argument("urls", nargs="+", help="page URLs to check")
    p.add_argument("-o", "--output-dir", default="og-card-output",
                   help="directory for PNG previews (default: og-card-output)")
    p.add_argument("--no-preview", action="store_true", help="skip PNG previews")
    p.add_argument("--markdown", metavar="FILE", help="write a Markdown report")
    p.add_argument("--json", metavar="FILE", help="write a JSON report ('-' for stdout)")
    p.add_argument("--delay", type=float, default=1.0, help="seconds between requests (default 1.0)")
    p.add_argument("--timeout", type=float, default=15.0, help="request timeout in seconds")
    p.add_argument("--strict", action="store_true", help="also exit non-zero on warnings")
    p.add_argument("--version", action="version", version="og-card-check " + __version__)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    fetcher = Fetcher(delay=max(args.delay, 0.0), timeout=args.timeout)
    results = []
    for url in args.urls:
        r = check_url(url, fetcher)
        if not args.no_preview:
            r["previews"] = render_previews(r, args.output_dir)
        results.append(r)
    if args.markdown:
        _write(args.markdown, to_markdown(results))
    if args.json == "-":
        sys.stdout.write(to_json(results) + "\n")
    else:
        if args.json:
            _write(args.json, to_json(results))
        sys.stdout.write(to_text(results) + "\n")
    errors = error_count(results)
    warns = sum(1 for r in results for f in r["findings"] if f["level"] == "warn")
    sys.stderr.write("%d page(s), %d error(s), %d warning(s)\n" % (len(results), errors, warns))
    if errors or (args.strict and warns):
        return 1
    return 0


def _write(path: str, text: str) -> None:
    d = os.path.dirname(os.path.abspath(path))
    os.makedirs(d, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


if __name__ == "__main__":
    sys.exit(main())
