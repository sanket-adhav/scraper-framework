"""SpecDrivenExtractor tests — headlined by the Plan 05 DoD proof that the SAME
extractor class handles HTML and JSON specs identically."""

import pytest

from components.extractors.spec_driven import SpecDrivenExtractor
from components.parsers.html_parser import HtmlParser
from components.parsers.json_parser import JsonParser
from core.config.schema import ExtractConfigModel
from core.errors.exceptions import ExtractionError
from tests.contract.base_suites import ExtractorContractSuite
from tests.helpers import fixture_response

HTML_SPEC = ExtractConfigModel.model_validate(
    {
        "schema_version": "1",
        "spec": {
            "title": {"kind": "css", "query": "h1#product-title span"},
            "price": {
                "kind": "xpath",
                "query": "//span[@class='price']/text()",
                "cleanup": ["strip_currency", "to_float"],
            },
        },
    }
)

JSON_SPEC = ExtractConfigModel.model_validate(
    {
        "schema_version": "1",
        "spec": {
            "title": {"kind": "jsonpath", "query": "$.product.name"},
            "price": {
                "kind": "jsonpath",
                "query": "$.product.price.value",
                "cleanup": ["to_float"],
            },
        },
    }
)


class TestExtractorContract(ExtractorContractSuite):
    """Contract conformance for SpecDrivenExtractor."""

    def make_component(self):
        return SpecDrivenExtractor()


class TestSameExtractorBothFormats:
    """THE Plan 05 DoD test: one extractor class, two formats, identical output."""

    def test_html_and_json_specs_yield_identical_records(self):
        extractor = SpecDrivenExtractor()  # one instance for both formats
        html_doc = HtmlParser().parse(fixture_response("sample_product.html", "text/html"))
        json_doc = JsonParser().parse(
            fixture_response("sample_api_response.json", "application/json")
        )
        html_record = extractor.extract(html_doc, HTML_SPEC)
        json_record = extractor.extract(json_doc, JSON_SPEC)
        assert html_record.data == json_record.data  # same fields, same values
        assert html_record.data == {"title": "Aurora X2 Wireless Headphones", "price": 4999.0}


class TestFieldBehavior:
    def make_doc(self):
        """Parses the HTML fixture for field-level tests."""
        return HtmlParser().parse(fixture_response("sample_product.html", "text/html"))

    def spec_of(self, fields: dict) -> ExtractConfigModel:
        """Builds a spec from a plain field mapping."""
        return ExtractConfigModel.model_validate({"schema_version": "1", "spec": fields})

    def test_required_miss_raises_with_field_detail(self):
        spec = self.spec_of({"nope": {"kind": "css", "query": "#does-not-exist"}})
        with pytest.raises(ExtractionError) as err:
            SpecDrivenExtractor().extract(self.make_doc(), spec)
        assert err.value.field == "nope"
        assert "'nope'" in str(err.value)

    def test_optional_miss_is_none_and_counted(self):
        spec = self.spec_of(
            {"maybe": {"kind": "css", "query": "#does-not-exist", "required": False}}
        )
        extractor = SpecDrivenExtractor()
        record = extractor.extract(self.make_doc(), spec)
        assert record.data["maybe"] is None
        assert extractor.missing_optional["maybe"] == 1

    def test_against_url_field_uses_the_url_not_the_document(self):
        spec = self.spec_of(
            {"sku": {"kind": "regex", "query": r"/dp/([A-Z0-9]{10})", "against": "url"}}
        )
        record = SpecDrivenExtractor().extract(
            self.make_doc(), spec, source_url="https://shopverse.example.com/dp/B0AURX2HDX"
        )
        assert record.data["sku"] == "B0AURX2HDX"

    def test_unknown_cleanup_fails_clearly(self):
        spec = self.spec_of(
            {"title": {"kind": "css", "query": "h1#product-title span", "cleanup": ["sparkle"]}}
        )
        with pytest.raises(ExtractionError, match="unknown cleanup 'sparkle'"):
            SpecDrivenExtractor().extract(self.make_doc(), spec)

    def test_provenance_carries_plugin_url_and_schema_version(self):
        extractor = SpecDrivenExtractor(plugin_name="shopverse", plugin_version="1.2.0")
        spec = self.spec_of({"title": {"kind": "css", "query": "h1#product-title span"}})
        record = extractor.extract(self.make_doc(), spec, source_url="https://s.example/p/1")
        assert record.schema_version == "1"
        assert record.provenance.plugin_name == "shopverse"
        assert record.provenance.plugin_version == "1.2.0"
        assert record.provenance.source_url == "https://s.example/p/1"
        assert record.provenance.scraped_at.tzinfo is not None
