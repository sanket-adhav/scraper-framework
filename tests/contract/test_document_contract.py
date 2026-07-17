"""Runs the shared Document contract suite against all five document types.

Every document type is built from a real fixture through its real parser, so
these tests also prove parser → document wiring works for each format.
"""

from components.parsers.html_parser import HtmlParser
from components.parsers.json_parser import JsonParser
from components.parsers.pdf_parser import PdfParser
from components.parsers.text_parser import TextParser
from components.parsers.xml_parser import XmlParser
from core.models import Response, Selector, SelectorKind
from tests.contract.base_suites import DocumentContractSuite
from tests.helpers import fixture_response


class TestHtmlDocumentContract(DocumentContractSuite):
    """Contract conformance for HtmlDocument (CSS, XPath, regex, text)."""

    def make_component(self):
        return HtmlParser().parse(fixture_response("sample_product.html", "text/html"))

    def make_selector(self, kind: SelectorKind) -> Selector:
        return {
            SelectorKind.CSS: Selector(SelectorKind.CSS, "h1#product-title span"),
            SelectorKind.XPATH: Selector(SelectorKind.XPATH, "//span[@class='price']/text()"),
            SelectorKind.REGEX: Selector(SelectorKind.REGEX, r"(\d+)% off"),
            SelectorKind.TEXT: Selector(SelectorKind.TEXT, ""),
        }[kind]


class TestXmlDocumentContract(DocumentContractSuite):
    """Contract conformance for XmlDocument (XPath, regex, text)."""

    def make_component(self):
        return XmlParser().parse(fixture_response("sample_feed.xml", "application/rss+xml"))

    def make_selector(self, kind: SelectorKind) -> Selector:
        return {
            SelectorKind.XPATH: Selector(SelectorKind.XPATH, "//item/title/text()"),
            SelectorKind.REGEX: Selector(SelectorKind.REGEX, r"B0[A-Z0-9]{8}"),
            SelectorKind.TEXT: Selector(SelectorKind.TEXT, ""),
        }[kind]


class TestJsonDocumentContract(DocumentContractSuite):
    """Contract conformance for JsonDocument (JSONPath, regex, text)."""

    def make_component(self):
        return JsonParser().parse(fixture_response("sample_api_response.json", "application/json"))

    def make_selector(self, kind: SelectorKind) -> Selector:
        return {
            SelectorKind.JSONPATH: Selector(SelectorKind.JSONPATH, "$.product.name"),
            SelectorKind.REGEX: Selector(SelectorKind.REGEX, r'"id": "([^"]+)"'),
            SelectorKind.TEXT: Selector(SelectorKind.TEXT, ""),
        }[kind]


class TestPdfDocumentContract(DocumentContractSuite):
    """Contract conformance for PdfDocument (text, regex)."""

    def make_component(self):
        return PdfParser().parse(fixture_response("sample_report.pdf", "application/pdf"))

    def make_selector(self, kind: SelectorKind) -> Selector:
        return {
            SelectorKind.REGEX: Selector(SelectorKind.REGEX, r"Order ID: (\S+)"),
            SelectorKind.TEXT: Selector(SelectorKind.TEXT, ""),
        }[kind]


class TestTextDocumentContract(DocumentContractSuite):
    """Contract conformance for TextDocument (text, regex)."""

    def make_component(self):
        response = Response(status=200, body=b"order SV-1 total 42.00\n", content_type="text/plain")
        return TextParser().parse(response)

    def make_selector(self, kind: SelectorKind) -> Selector:
        return {
            SelectorKind.REGEX: Selector(SelectorKind.REGEX, r"total (\d+\.\d{2})"),
            SelectorKind.TEXT: Selector(SelectorKind.TEXT, ""),
        }[kind]
