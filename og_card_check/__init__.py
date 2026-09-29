"""og-card-check: check how links to a page look when shared."""

__version__ = "1.0.0"
USER_AGENT = "og-card-check/1.0 (+https://github.com/dreadmoreeee/og-card-check)"

from .analyze import check_url  # noqa: E402

__all__ = ["check_url", "USER_AGENT", "__version__"]
