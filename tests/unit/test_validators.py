"""Validator tests: each of the five, with per-field failure detail assertions."""

from components.validators.business_rule import BusinessRuleValidator
from components.validators.duplicate_detector import DuplicateDetectorValidator
from components.validators.required_field import RequiredFieldValidator
from components.validators.schema_validator import SchemaValidator
from components.validators.type_validator import TypeValidator
from tests.contract.base_suites import ValidatorContractSuite
from tests.helpers import make_record


class TestRequiredFieldContract(ValidatorContractSuite):
    """Contract conformance for the required-field validator."""

    def make_component(self):
        return RequiredFieldValidator(fields=["title"])

    def make_record(self):
        return make_record()


class TestRequiredField:
    def test_missing_and_empty_fields_reported_per_field(self):
        validator = RequiredFieldValidator(fields=["title", "price", "sku"])
        result = validator.validate(make_record({"title": "", "price": 4999.0}))
        assert not result.valid
        assert {f.field for f in result.failures} == {"title", "sku"}
        assert all("required" in f.message for f in result.failures)

    def test_all_present_passes(self):
        result = RequiredFieldValidator(fields=["title"]).validate(make_record())
        assert result.valid and result.failures == ()


class TestTypeValidator:
    def test_wrong_types_reported_with_expected_and_actual(self):
        validator = TypeValidator(types={"title": "str", "price": "float", "count": "int"})
        result = validator.validate(make_record({"title": 42, "price": "cheap", "count": 3}))
        by_field = {f.field: f.message for f in result.failures}
        assert by_field == {
            "title": "expected str, got int",
            "price": "expected float, got str",
        }

    def test_int_is_acceptable_float_and_none_is_skipped(self):
        validator = TypeValidator(types={"price": "float", "title": "str"})
        result = validator.validate(make_record({"price": 4999, "title": None}))
        assert result.valid

    def test_bool_is_not_a_number(self):
        result = TypeValidator(types={"count": "int"}).validate(make_record({"count": True}))
        assert not result.valid
        assert result.failures[0].message == "expected int, got bool"


class TestSchemaValidator:
    SCHEMAS = {"1": {"title": "str", "price": "float"}}

    def test_validates_against_the_declared_version(self):
        result = SchemaValidator(self.SCHEMAS).validate(make_record({"title": 1, "price": 2.0}))
        assert not result.valid
        assert result.failures[0].field == "title"

    def test_unknown_schema_version_fails_loudly(self):
        result = SchemaValidator(self.SCHEMAS).validate(make_record(schema_version="99"))
        assert not result.valid
        assert result.failures[0].field == "schema_version"
        assert "'99'" in result.failures[0].message


class TestBusinessRule:
    def test_broken_rules_reported_with_values(self):
        validator = BusinessRuleValidator(
            rules=[
                {"field": "price", "op": ">", "value": 0},
                {"field": "rating", "op": "<=", "value": 5},
            ]
        )
        result = validator.validate(make_record({"price": -1, "rating": 9.9}))
        by_field = {f.field: f.message for f in result.failures}
        assert "price > 0" in by_field["price"] and "-1" in by_field["price"]
        assert "rating <= 5" in by_field["rating"]

    def test_in_rule_and_none_skip(self):
        validator = BusinessRuleValidator(
            rules=[{"field": "currency", "op": "in", "value": ["INR", "USD"]}]
        )
        assert validator.validate(make_record({"currency": "INR"})).valid
        assert validator.validate(make_record({"currency": None})).valid
        assert not validator.validate(make_record({"currency": "XXX"})).valid


class TestDuplicateDetector:
    def test_first_sight_passes_repeat_fails(self):
        validator = DuplicateDetectorValidator(key_fields=["sku"])
        first = validator.validate(make_record({"sku": "B0X", "price": 1.0}))
        repeat = validator.validate(make_record({"sku": "B0X", "price": 2.0}))  # same key
        other = validator.validate(make_record({"sku": "B0Y"}))
        assert first.valid and other.valid
        assert not repeat.valid
        assert repeat.failures[0].field == "sku"
        assert "duplicate" in repeat.failures[0].message
