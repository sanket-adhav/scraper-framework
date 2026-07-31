"""The full typed error taxonomy (plan2.md §10).

Every deliberate framework error lives here, rooted at ScraperError. Contract
files re-export their own error so `from core.contracts import FetchError`
keeps working. Transient errors are worth retrying; permanent ones are not.
"""

from __future__ import annotations


class ScraperError(Exception):
    """Root of every error the framework raises deliberately."""


class ConfigError(ScraperError):
    """The configuration is invalid — raised at load time, never mid-scrape."""


class FetchError(ScraperError):
    """Fetching a request failed."""

    def __init__(self, message: str, *, transient: bool = False, blocked: bool = False) -> None:
        """Stores the message, whether a retry could plausibly succeed, and
        whether the site blocked us (CAPTCHA / access denied) — plan2.md §12."""
        super().__init__(message)
        self.transient = transient
        self.blocked = blocked


class ParseError(ScraperError):
    """The response body could not be parsed into a Document."""


class ExtractionError(ScraperError):
    """Extraction failed — usually the spec no longer matches the page."""

    def __init__(self, message: str, *, field: str | None = None) -> None:
        """Stores the message and, when known, which spec field failed."""
        super().__init__(message)
        self.field = field


class ValidationError(ScraperError):
    """A record failed validation hard enough to stop the pipeline."""


class TransformError(ScraperError):
    """A transformation could not be applied to the record."""


class PersistError(ScraperError):
    """Saving a record failed."""

    def __init__(self, message: str, *, transient: bool = False) -> None:
        """Stores the message and whether a retry could plausibly succeed."""
        super().__init__(message)
        self.transient = transient


class PluginError(ScraperError):
    """A plugin failed to load or misbehaved; the plugin gets quarantined."""


class ParamError(ScraperError):
    """A runtime parameter is unknown, missing, or the wrong type — raised while
    resolving a job, before any scrape starts."""


class AuthError(ScraperError):
    """Login failed or a session could not be acquired/refreshed."""


class StageTimeoutError(ScraperError):
    """A pipeline stage ran longer than its configured time limit."""
