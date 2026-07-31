"""Parses every committed fixture and asserts real values come out (Plan 02 DoD:
'parsing each fixture is itself a test'). These fixtures are reused by every later plan."""

from components.parsers.html_parser import HtmlParser
from components.parsers.json_parser import JsonParser
from components.parsers.pdf_parser import PdfParser
from components.parsers.xml_parser import XmlParser
from core.models import Selector, SelectorKind
from tests.helpers import fixture_response


def css(query: str) -> Selector:
    """Shorthand for a CSS selector."""
    return Selector(SelectorKind.CSS, query)


def xpath(query: str) -> Selector:
    """Shorthand for an XPath selector."""
    return Selector(SelectorKind.XPATH, query)


def jsonpath(query: str) -> Selector:
    """Shorthand for a JSONPath selector."""
    return Selector(SelectorKind.JSONPATH, query)


def regex(query: str) -> Selector:
    """Shorthand for a regex selector."""
    return Selector(SelectorKind.REGEX, query)


class TestHtmlFixture:
    """The saved product page parses and yields the expected fields."""

    def setup_method(self):
        """Parses the HTML fixture once per test."""
        self.doc = HtmlParser().parse(fixture_response("sample_product.html", "text/html"))

    def test_title_via_css(self):
        assert self.doc.select(css("h1#product-title span")) == ["Aurora X2 Wireless Headphones"]

    def test_price_via_xpath(self):
        assert self.doc.select(xpath("//span[@class='price']/text()")) == ["₹4,999.00"]

    def test_sku_via_xpath_attribute(self):
        assert self.doc.select(xpath("//main[@id='product-page']/@data-sku")) == ["B0AURX2HDX"]

    def test_discount_via_regex_on_text(self):
        assert self.doc.select(regex(r"(\d+)% off")) == ["23"]

    def test_highlights_via_css_list(self):
        highlights = self.doc.select(css("ul.highlights li"))
        assert len(highlights) == 3
        assert "60-hour battery life" in str(highlights[1])


class TestJsonFixture:
    """The saved API response parses and yields the expected fields."""

    def setup_method(self):
        """Parses the JSON fixture once per test."""
        response = fixture_response("sample_api_response.json", "application/json")
        self.doc = JsonParser().parse(response)

    def test_name_stays_a_string(self):
        assert self.doc.select(jsonpath("$.product.name")) == ["Aurora X2 Wireless Headphones"]

    def test_number_rendered_as_json_text(self):
        assert self.doc.select(jsonpath("$.product.price.value")) == ["4999.0"]

    def test_object_match_returns_mapping(self):
        matches = self.doc.select(jsonpath("$.product.rating"))
        assert matches == [{"score": 4.4, "count": 1284}]

    def test_related_names_via_wildcard(self):
        names = self.doc.select(jsonpath("$.related[*].name"))
        assert names == ["Aurora X1 Wireless Headphones", "Nimbus Pods Mini"]

    def test_pagination_cursor_present(self):
        assert self.doc.select(jsonpath("$.pagination.cursor")) == ["eyJvZmZzZXQiOiAyMH0"]


class TestXmlFixture:
    """The saved RSS feed parses and yields the expected fields."""

    def setup_method(self):
        """Parses the XML fixture once per test."""
        self.doc = XmlParser().parse(fixture_response("sample_feed.xml", "application/rss+xml"))

    def test_item_titles(self):
        titles = self.doc.select(xpath("//item/title/text()"))
        assert titles == ["Aurora X2 Wireless Headphones", "Nimbus Pods Mini"]

    def test_price_currency_attribute(self):
        assert self.doc.select(xpath("//item[1]/price/@currency")) == ["INR"]

    def test_guids_via_regex(self):
        """Each ID appears twice in the feed text (guid + link URL), so dedupe first."""
        matches = self.doc.select(regex(r"B0[A-Z0-9]{8}"))
        assert sorted(set(matches)) == ["B0AURX2HDX", "B0NIMBUSPD"]


class TestPdfFixture:
    """The generated order-report PDF parses and yields the expected text."""

    def setup_method(self):
        """Parses the PDF fixture once per test."""
        self.doc = PdfParser().parse(fixture_response("sample_report.pdf", "application/pdf"))

    def test_has_two_pages(self):
        assert len(self.doc.pages) == 2

    def test_order_id_via_regex(self):
        assert self.doc.select(regex(r"Order ID: (\S+)")) == ["SV-2026-018342"]

    def test_total_via_regex(self):
        assert self.doc.select(regex(r"Total: INR ([\d.]+)")) == ["5898.82"]

    def test_positional_blocks_retained(self):
        """Block coordinates survive extraction — later layout selectors depend on this."""
        first_block = self.doc.pages[0].blocks[0]
        assert first_block.text
        assert first_block.x1 > first_block.x0
        assert first_block.y1 > first_block.y0
