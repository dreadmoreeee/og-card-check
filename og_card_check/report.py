"""Markdown and JSON reports."""

from __future__ import annotations

import json

ORDER = {"error": 0, "warn": 1, "info": 2}
ICON = {"error": "ERROR", "warn": "WARN", "info": "INFO"}


def _public(result: dict) -> dict:
    out = dict(result)
    out["images"] = {k: {kk: vv for kk, vv in v.items() if not kk.startswith("_")}
                     for k, v in result.get("images", {}).items()}
    return out


def to_json(results: list[dict]) -> str:
    return json.dumps([_public(r) for r in results], indent=2, ensure_ascii=True)


def _cell(s) -> str:
    return str(s).replace("|", "\\|").replace("\n", " ")


def to_markdown(results: list[dict]) -> str:
    lines = ["# og-card-check report", ""]
    for r in results:
        errs = sum(1 for f in r["findings"] if f["level"] == "error")
        warns = sum(1 for f in r["findings"] if f["level"] == "warn")
        lines += ["## %s" % r["url"], "",
                  "HTTP %s, %d error(s), %d warning(s)" % (r["status"], errs, warns), ""]
        tags = r.get("tags") or {}
        if tags:
            lines += ["| Tag | Value |", "|---|---|"]
            for k, v in tags.items():
                lines.append("| %s | %s |" % (k, _cell(v) if v else "(missing)"))
            lines.append("")
        imgs = r.get("images") or {}
        if imgs:
            lines += ["| Image | Status | Type | Size | Bytes |", "|---|---|---|---|---|"]
            for k, v in imgs.items():
                dim = "%sx%s" % (v["width"], v["height"]) if v.get("width") else "-"
                lines.append("| %s | %s | %s | %s | %s |" % (
                    k, v.get("status", "-"), v.get("content_type") or "-", dim, v.get("bytes") or "-"))
            lines.append("")
        fb = (r.get("resolved") or {}).get("fallbacks") or []
        if fb:
            lines += ["Fallbacks:", ""] + ["- %s" % x for x in fb] + [""]
        if r["findings"]:
            lines += ["Findings:", ""]
            for f in sorted(r["findings"], key=lambda f: ORDER[f["level"]]):
                lines.append("- **%s** `%s`: %s" % (ICON[f["level"]], f["code"], f["message"]))
            lines.append("")
        else:
            lines += ["No findings.", ""]
        if r.get("previews"):
            lines += ["Preview: `%s`" % r["previews"].get("sheet", ""), ""]
    return "\n".join(lines)


def to_text(results: list[dict]) -> str:
    out = []
    for r in results:
        out.append("%s  [HTTP %s]" % (r["url"], r["status"]))
        for f in sorted(r["findings"], key=lambda f: ORDER[f["level"]]):
            out.append("  %-5s %s" % (ICON[f["level"]], f["message"]))
        for x in (r.get("resolved") or {}).get("fallbacks", []):
            out.append("  FALLBACK %s" % x)
        for k, v in r.get("images", {}).items():
            dim = "%sx%s" % (v["width"], v["height"]) if v.get("width") else "?"
            out.append("  image %-16s HTTP %s %s %s %s bytes" % (
                k, v.get("status"), v.get("content_type") or "-", dim, v.get("bytes")))
        if r.get("previews"):
            out.append("  preview: %s" % r["previews"]["sheet"])
        out.append("")
    return "\n".join(out)
