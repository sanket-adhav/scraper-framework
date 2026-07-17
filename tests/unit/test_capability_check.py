"""Tests for the load-time capability check: format mismatches must fail at
config load with a clear message (plan2.md §5, Plan 02 DoD)."""

import pytest

from components.documents.html_document import HtmlDocument
from components.documents.json_document import JsonDocument
from core.config.capability_check import CapabilityError, check_spec_against_capabilities
from core.models import SelectorKind


class TestCapabilityCheck:
    """The pure check function that Plan 03's config loader will wire in."""

    def test_xpath_against_json_document_rejected(self):
        """DoD check: an XPath selector aimed at a JSON API fails with a clear message."""
        with pytest.raises(CapabilityError) as err:
            check_spec_against_capabilities(
                {"price": SelectorKind.XPATH},
                JsonDocument.capabilities,
                "JsonDocument",
            )
        message = str(err.value)
        assert "'price'" in message
        assert "'xpath'" in message
        assert "JsonDocument" in message
        assert "jsonpath" in message  # tells the user what IS allowed

    def test_jsonpath_against_html_document_rejected(self):
        """DoD check: a JSONPath selector aimed at an HTML page fails with a clear message."""
        with pytest.raises(CapabilityError) as err:
            check_spec_against_capabilities(
                {"title": SelectorKind.JSONPATH},
                HtmlDocument.capabilities,
                "HtmlDocument",
            )
        message = str(err.value)
        assert "'title'" in message
        assert "'jsonpath'" in message
        assert "HtmlDocument" in message

    def test_all_bad_fields_reported_at_once(self):
        """One load-time failure lists every bad field, not just the first."""
        with pytest.raises(CapabilityError) as err:
            check_spec_against_capabilities(
                {"a": SelectorKind.CSS, "b": SelectorKind.XPATH, "c": SelectorKind.JSONPATH},
                JsonDocument.capabilities,
                "JsonDocument",
            )
        assert "'a'" in str(err.value)
        assert "'b'" in str(err.value)
        assert "'c'" not in str(err.value)  # jsonpath IS supported — must not be flagged

    def test_matching_spec_passes_silently(self):
        """A spec whose kinds all fit the document's capabilities raises nothing."""
        check_spec_against_capabilities(
            {"title": SelectorKind.CSS, "price": SelectorKind.XPATH, "id": SelectorKind.REGEX},
            HtmlDocument.capabilities,
            "HtmlDocument",
        )
