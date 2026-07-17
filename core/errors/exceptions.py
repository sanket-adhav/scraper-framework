"""Base of the framework error taxonomy.

Only the root lives here for now; each contract file defines its own error stub
next to its Protocol. The full §10 taxonomy (transient/permanent split, field
detail, policies) lands in Plan 03.
"""

from __future__ import annotations


class ScraperError(Exception):
    """Root of every error the framework raises deliberately."""
