"""Runtime job resolution (plan2.md §runtime parameters).

Turns a caller's request — a plugin name plus a bag of runtime parameters — into
a fully rendered configuration the generic engine can execute. Nothing here
knows about SEBI, Amazon, titles, or dates: it validates parameters against the
plugin's own declared contract and substitutes them into the plugin's own
template. Business knowledge stays in plugins; the engine stays generic.
"""

from __future__ import annotations

from core.runtime.params import validate_params
from core.runtime.resolver import JobResolver, ResolvedRuntimeConfig
from core.runtime.template import render_template

__all__ = [
    "JobResolver",
    "ResolvedRuntimeConfig",
    "render_template",
    "validate_params",
]
