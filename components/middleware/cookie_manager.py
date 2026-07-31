"""Cookie-manager middleware (plan2.md §6, Plan 07).

Keeps a per-domain cookie jar: attaches stored cookies to each request and
harvests Set-Cookie from each response, so a site's session cookies persist
across requests within a run.
"""

from __future__ import annotations

import re
from dataclasses import replace
from urllib.parse import urlsplit

from core.contracts.middleware import Next
from core.models.response import Response
from core.models.scrape_request import ScrapeRequest


class CookieManagerMiddleware:
    """Middleware that remembers cookies per domain and replays them on later requests."""

    def __init__(self) -> None:
        """Starts with an empty per-domain cookie jar."""
        self._jars: dict[str, dict[str, str]] = {}

    async def __call__(self, request: ScrapeRequest, next: Next) -> Response:
        """Attaches known cookies, then stores any Set-Cookie the response returns."""
        domain = urlsplit(request.url).netloc
        jar = self._jars.setdefault(domain, {})
        tagged = replace(request, cookies={**jar, **dict(request.cookies)})
        response = await next(tagged)
        self._harvest(domain, response)
        return response

    def cookies_for(self, domain: str) -> dict[str, str]:
        """Returns the current cookie jar for a domain (for tests/inspection)."""
        return dict(self._jars.get(domain, {}))

    def _harvest(self, domain: str, response: Response) -> None:
        """Parses Set-Cookie header(s) from the response into the domain's jar."""
        raw = response.headers.get("set-cookie") or response.headers.get("Set-Cookie")
        if not raw:
            return
        jar = self._jars.setdefault(domain, {})
        for cookie in re.split(r",(?=[^ ;]+=)", raw):
            pair = cookie.split(";", 1)[0].strip()
            if "=" in pair:
                name, value = pair.split("=", 1)
                jar[name.strip()] = value.strip()
