"""Runs the shared Parser contract suite against all five parsers, plus the
hardening tests: oversized bodies, empty bodies, malformed input, entity bombs."""

import pytest

from components.parsers._hardening import (
    EmptyBodyError,
    EntityProtectionError,
    OversizedBodyError,
)
from components.parsers.html_parser import HtmlParser
from components.parsers.json_parser import JsonParser
from components.parsers.pdf_parser import PdfParser
from components.parsers.text_parser import TextParser
from components.parsers.xml_parser import XmlParser
from core.contracts.parser import ParseError
from core.models import Response
from tests.contract.base_suites import ParserContractSuite
from tests.helpers import fixture_response

ALL_PARSERS = [HtmlParser, XmlParser, JsonParser, PdfParser, TextParser]


def response_of(body: bytes, content_type: str = "text/plain") -> Response:
    """Wraps raw bytes as a fake Response for hardening tests."""
    return Response(status=200, body=body, content_type=content_type)


class TestHtmlParserContract(ParserContractSuite):
    """Contract conformance for HtmlParser."""

    def make_component(self):
        return HtmlParser()

    def make_response(self):
        return fixture_response("sample_product.html", "text/html")


class TestXmlParserContract(ParserContractSuite):
    """Contract conformance for XmlParser."""

    def make_component(self):
        return XmlParser()

    def make_response(self):
        return fixture_response("sample_feed.xml", "application/rss+xml")


class TestJsonParserContract(ParserContractSuite):
    """Contract conformance for JsonParser."""

    def make_component(self):
        return JsonParser()

    def make_response(self):
        return fixture_response("sample_api_response.json", "application/json")


class TestPdfParserContract(ParserContractSuite):
    """Contract conformance for PdfParser."""

    def make_component(self):
        return PdfParser()

    def make_response(self):
        return fixture_response("sample_report.pdf", "application/pdf")


class TestTextParserContract(ParserContractSuite):
    """Contract conformance for TextParser."""

    def make_component(self):
        return TextParser()

    def make_response(self):
        return response_of(b"hello scraper\n")


class TestHardening:
    """The shared safety limits every parser must enforce (plan2.md §13)."""

    @pytest.mark.parametrize("parser_cls", ALL_PARSERS, ids=lambda c: c.__name__)
    def test_empty_body_rejected_identically(self, parser_cls):
        """Every parser raises the same typed error on an empty body."""
        with pytest.raises(EmptyBodyError):
            parser_cls().parse(response_of(b""))

    @pytest.mark.parametrize("parser_cls", ALL_PARSERS, ids=lambda c: c.__name__)
    def test_configured_size_limit_enforced(self, parser_cls):
        """A body over the configured limit fails fast, before any parsing."""
        with pytest.raises(OversizedBodyError):
            parser_cls(max_body_bytes=1024).parse(response_of(b"x" * 1025))

    def test_500mb_body_fails_fast_on_default_limit(self):
        """DoD check: a 500 MB body is rejected by the default limit with a typed error."""
        with pytest.raises(OversizedBodyError):
            HtmlParser().parse(response_of(b"\0" * (500 * 1024 * 1024)))

    def test_billion_laughs_xml_rejected(self):
        """DoD check: an entity-expansion bomb is rejected before lxml ever sees it."""
        bomb = (
            b'<?xml version="1.0"?><!DOCTYPE lolz ['
            b'<!ENTITY lol "lol">'
            b'<!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">'
            b'<!ENTITY lol3 "&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;">'
            b"]><lolz>&lol3;</lolz>"
        )
        with pytest.raises(EntityProtectionError):
            XmlParser().parse(response_of(bomb, "application/xml"))

    @pytest.mark.parametrize(
        ("parser_cls", "garbage", "content_type"),
        [
            (XmlParser, b"<a><b></a>", "application/xml"),
            (JsonParser, b"{not json at all", "application/json"),
            (PdfParser, b"%PDF-this is not a real pdf", "application/pdf"),
        ],
        ids=["xml", "json", "pdf"],
    )
    def test_malformed_input_raises_typed_parse_error(self, parser_cls, garbage, content_type):
        """Malformed bodies raise ParseError — never a raw library exception.
        (HTML is exempt: HTML parsing is lenient by design, like browsers.)"""
        with pytest.raises(ParseError):
            parser_cls().parse(response_of(garbage, content_type))
