# og-card-check

Check how links to your pages look when shared. Fetches each URL with plain HTTP, reads the Open Graph and X (Twitter) card tags, checks the images, and draws PNG mock cards in the style of Facebook, LinkedIn, X and Slack. Exits non-zero when errors are found, so it works in CI.

## What it checks

- Open Graph: `og:title`, `og:description`, `og:image` (+ width, height, alt), `og:url`, `og:type`, `og:site_name`
- X cards: `twitter:card`, `twitter:title`, `twitter:description`, `twitter:image`
- `<link rel=canonical>`, favicon, apple-touch-icon
- Missing or empty tags, `og:url` vs canonical mismatch, relative image URLs, titles and descriptions that are too long
- Fallbacks: which value a platform uses when a tag is missing (for example `og:title` -> `<title>`, `twitter:image` -> `og:image`)
- Images: reachability, status, content-type, pixel size (1200x630 recommended), aspect ratio (about 1.91:1, or 2:1 for `summary_large_image`), file size (warns above ~5 MB, errors above ~8 MB). Favicon and apple-touch-icon are checked for reachability.

Severity: `ERROR` (missing/unreachable og:image, HTTP errors, tiny or oversized images), `WARN`, `INFO`. Only errors set the exit code; add `--strict` to fail on warnings too.

## Install

```
pip install .
```

Requires Python 3.10+ and Pillow.

## Usage

```
og-card-check https://example.com https://example.com/blog/post
python -m og_card_check https://example.com -o previews --markdown report.md --json report.json
```

Options: `-o/--output-dir` (default `og-card-output`), `--no-preview`, `--markdown FILE`, `--json FILE` (`-` for stdout), `--delay SECONDS` (default 1.0 between requests), `--timeout`, `--strict`.

Previews are written per URL to `<output-dir>/<slug>/{facebook,linkedin,x,slack,preview}.png`. The mock cards are approximations of each platform's layout, not pixel-exact copies.

The tool only sends GET and HEAD requests, with the User-Agent `og-card-check/1.0 (+https://github.com/dreadmoreeee/og-card-check)`.

## Measured result

Run against the author's own public sites (4 pages, 17 requests, 1 s apart). Full files: [examples/demo-output.txt](examples/demo-output.txt), [examples/demo-report.md](examples/demo-report.md). Sample preview: [examples/sample-preview.png](examples/sample-preview.png).

```
$ python -m og_card_check https://demarkstudio.ca https://demo.demarkstudio.ca https://demo.demarkstudio.ca/riverside-pub/site https://marvin.demarkstudio.ca
https://demarkstudio.ca  [HTTP 200]
  WARN  title is 82 chars; likely truncated above ~60
  WARN  twitter title is 82 chars; X truncates around 70
  image og:image         HTTP 200 image/png 1200x630 49255 bytes
  image apple-touch-icon HTTP 200 image/png ? 6088 bytes

https://demo.demarkstudio.ca  [HTTP 200]
  ERROR og:image is missing
  WARN  og:title is missing
  WARN  og:description is missing
  WARN  twitter:card is missing; X shows a small summary at best
  WARN  no <link rel=canonical>

https://demo.demarkstudio.ca/riverside-pub/site  [HTTP 200]
  ERROR og:image is missing
  WARN  og:title is missing
  WARN  og:description is missing
  WARN  twitter:card is missing; X shows a small summary at best

https://marvin.demarkstudio.ca  [HTTP 200]
  WARN  title is 68 chars; likely truncated above ~60
  INFO  description is 186 chars; some platforms cut at ~160
  image og:image         HTTP 200 image/png 1200x630 134943 bytes

4 page(s), 2 error(s), 15 warning(s)      (exit code 1)
```

(Trimmed: `og:url`/`og:type`/`og:site_name` lines and the fallback list are in the full output file.)

Honest reading: `demarkstudio.ca` and `marvin.demarkstudio.ca` have working 1200x630 cards; their only warnings are long titles. The `demo.demarkstudio.ca` pages have no Open Graph or X tags at all, so shared links would show only the page title and a meta description, with no image.

Tests:

```
$ python -m pytest -q -p no:cacheprovider --import-mode=importlib og-card-check
.........................                                                [100%]
25 passed in 11.53s
```

![Sample preview](examples/sample-preview.png)

## Tests

```
python -m pytest -q -p no:cacheprovider --import-mode=importlib
```

Tests use local HTTP servers on random free ports and need no internet.

Marvin Palencia, founder of [DeMark Studio](https://demarkstudio.ca), Miramichi, New Brunswick, Canada. Portfolio: [marvin.demarkstudio.ca](https://marvin.demarkstudio.ca)

MIT License.
