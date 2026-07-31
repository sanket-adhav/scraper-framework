"""Shared safety limits that every parser applies before touching a response body.

Kept in one place so no parser author can forget them (plan2.md §13):
size limit, empty-body rejection, and XML entity-expansion protection.
"""

from __future__ import annotations

from core.contracts.parser import ParseError
from core.models.response import Response

DEFAULT_MAX_BODY_BYTES = 50 * 1024 * 1024  # 50 MB — generous for pages, small enough to stop bombs


class OversizedBodyError(ParseError):
    """The response body is bigger than the allowed size limit."""


class EmptyBodyError(ParseError):
    """The response body is empty, so there is nothing to parse."""


class EntityProtectionError(ParseError):
    """The XML declares its own entities (billion-laughs attack vector) — never allowed."""


def checked_body(response: Response, max_bytes: int = DEFAULT_MAX_BODY_BYTES) -> bytes:
    """Returns the response body after checking it is not empty and not oversized."""
    body = response.body
    if not body:
        raise EmptyBodyError("response body is empty — nothing to parse")
    if len(body) > max_bytes:
        raise OversizedBodyError(
            f"response body is {len(body)} bytes, over the {max_bytes}-byte limit"
        )
    return body


def reject_xml_entity_declarations(body: bytes) -> None:
    """Rejects XML that declares custom entities — this is how billion-laughs bombs work.

    A plain substring scan is deliberate: it can rarely false-positive on
    '<!ENTITY' inside CDATA, but it can never miss a real declaration.
    """
    if b"<!ENTITY" in body:
        raise EntityProtectionError(
            "XML entity declarations are not allowed (entity-expansion protection)"
        )
