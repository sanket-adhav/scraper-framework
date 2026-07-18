"""Transformer tests: edge-case tables for currency/date, plus the other four."""

import pytest

from components.transformers.currency_normalizer import CurrencyNormalizer
from components.transformers.date_normalizer import DateNormalizer
from components.transformers.enum_mapper import EnumMapper
from components.transformers.field_enricher import FieldEnricher
from components.transformers.text_cleaner import TextCleaner
from components.transformers.unit_converter import UnitConverter
from core.errors.exceptions import TransformError
from tests.contract.base_suites import TransformerContractSuite
from tests.helpers import make_record


class TestTextCleanerContract(TransformerContractSuite):
    """Contract conformance for the text cleaner."""

    def make_component(self):
        return TextCleaner()

    def make_record(self):
        return make_record()


class TestCurrencyNormalizer:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("₹4,999.00", 4999.0),
            ("Rs. 4999", 4999.0),
            ("rs 4,999", 4999.0),
            ("INR 4,999.50", 4999.5),
            ("$1,299.99", 1299.99),
            ("€49", 49.0),
            (4999.0, 4999.0),  # already numeric passes through
        ],
    )
    def test_variants_table(self, raw, expected):
        record = CurrencyNormalizer(fields=["price"]).transform(make_record({"price": raw}))
        assert record.data["price"] == expected

    def test_garbage_raises_typed_error(self):
        with pytest.raises(TransformError, match="'price'"):
            CurrencyNormalizer(fields=["price"]).transform(make_record({"price": "call us"}))

    def test_original_record_untouched(self):
        original = make_record({"price": "₹100"})
        CurrencyNormalizer(fields=["price"]).transform(original)
        assert original.data["price"] == "₹100"  # transformers are pure


class TestDateNormalizer:
    def test_explicit_formats_resolve_ambiguity_no_guessing(self):
        """03-07-2026: day-first config reads 3 July; month-first reads 7 March."""
        day_first = DateNormalizer(fields=["d"], input_formats=["%d-%m-%Y"])
        month_first = DateNormalizer(fields=["d"], input_formats=["%m-%d-%Y"])
        ambiguous = make_record({"d": "03-07-2026"})
        assert day_first.transform(ambiguous).data["d"] == "2026-07-03"
        assert month_first.transform(ambiguous).data["d"] == "2026-03-07"

    @pytest.mark.parametrize(
        ("raw", "formats", "expected"),
        [
            ("17 July 2026", ["%d %B %Y"], "2026-07-17"),
            ("2026/07/17", ["%Y/%m/%d"], "2026-07-17"),
            ("17-07-26", ["%d-%m-%Y", "%d-%m-%y"], "2026-07-17"),  # falls to second format
        ],
    )
    def test_formats_table(self, raw, formats, expected):
        record = DateNormalizer(fields=["d"], input_formats=formats).transform(
            make_record({"d": raw})
        )
        assert record.data["d"] == expected

    def test_unparseable_lists_the_formats_tried(self):
        normalizer = DateNormalizer(fields=["d"], input_formats=["%Y-%m-%d"])
        with pytest.raises(TransformError, match="matches none"):
            normalizer.transform(make_record({"d": "yesterday"}))

    def test_empty_formats_rejected_at_build(self):
        with pytest.raises(ValueError, match="no guessing"):
            DateNormalizer(fields=["d"], input_formats=[])


class TestTextCleaner:
    def test_collapses_and_trims(self):
        record = TextCleaner(fields=["title"]).transform(
            make_record({"title": "  Aurora   X2\n  Headphones "})
        )
        assert record.data["title"] == "Aurora X2 Headphones"

    def test_no_fields_means_every_string_field(self):
        record = TextCleaner().transform(make_record({"a": " x ", "b": 3}))
        assert record.data == {"a": "x", "b": 3}


class TestUnitConverter:
    def test_grams_to_kilograms(self):
        converter = UnitConverter(conversions=[{"field": "weight", "from": "g", "to": "kg"}])
        assert converter.transform(make_record({"weight": 248})).data["weight"] == 0.248

    def test_unsupported_pair_rejected_at_build(self):
        with pytest.raises(ValueError, match="unsupported conversion"):
            UnitConverter(conversions=[{"field": "x", "from": "furlong", "to": "m"}])


class TestEnumMapper:
    def test_maps_known_values_and_passes_unknown(self):
        mapper = EnumMapper(mappings={"stock": {"In stock": "in_stock"}})
        assert mapper.transform(make_record({"stock": "In stock"})).data["stock"] == "in_stock"
        assert mapper.transform(make_record({"stock": "odd"})).data["stock"] == "odd"


class TestFieldEnricher:
    def test_adds_constants_and_copies_without_overwriting(self):
        enricher = FieldEnricher(constants={"source": "shopverse"}, copy={"name": "title"})
        record = enricher.transform(make_record({"title": "X2", "source": "keep-me"}))
        assert record.data["source"] == "keep-me"  # never overwrites
        assert record.data["name"] == "X2"
