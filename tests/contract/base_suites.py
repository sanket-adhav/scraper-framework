"""Reusable contract-conformance suites (plan2.md §11).

Every implementation of a contract — built-in or plugin-contributed — must pass
the suite for that contract. An implementation opts in by subclassing the suite
and overriding `make_component` (plus the `make_*` input hooks where relevant):

    class TestHttpFetcherContract(FetcherContractSuite):
        def make_component(self) -> Fetcher:
            return HttpFetcher(...)

The base `make_component` skips, so these suites are collected and runnable
before any implementation exists (Plan 01 state). Suites grow assertions as the
contracts earn them in Plans 02+; they never shrink.
"""

from __future__ import annotations

from typing import Any, NoReturn

import pytest

from core.contracts import (
    Document,
    ErrorAction,
    Extractor,
    Fetcher,
    LoginProvider,
    Middleware,
    Parser,
    Repository,
    Stage,
    Transformer,
    UnsupportedSelectorError,
    Validator,
)
from core.models import Record, Response, ScrapeRequest, Selector, SelectorKind


def _skip_no_impl() -> NoReturn:
    pytest.skip("contract-suite skeleton: no implementation registered yet (Plans 02+)")


class FetcherContractSuite:
    def make_component(self) -> Fetcher:
        _skip_no_impl()

    def make_request(self) -> ScrapeRequest:
        return ScrapeRequest(url="file:///fixture")

    def test_satisfies_protocol(self):
        assert isinstance(self.make_component(), Fetcher)

    async def test_fetch_returns_response(self):
        response = await self.make_component().fetch(self.make_request())
        assert isinstance(response, Response)


class ParserContractSuite:
    def make_component(self) -> Parser:
        _skip_no_impl()

    def make_response(self) -> Response:
        _skip_no_impl()

    def test_satisfies_protocol(self):
        assert isinstance(self.make_component(), Parser)

    def test_declares_content_types(self):
        parser = self.make_component()
        assert isinstance(parser.content_types, frozenset)
        assert parser.content_types, "a parser must declare at least one content type"

    def test_declares_document_type(self):
        """Every parser must say which Document class it produces (ADR 0001) —
        the load-time capability check depends on this declaration."""
        parser = self.make_component()
        assert isinstance(parser.document_type, type)
        assert isinstance(parser.document_type.capabilities, frozenset)

    def test_parse_returns_document(self):
        doc = self.make_component().parse(self.make_response())
        assert isinstance(doc, Document)

    def test_parse_output_matches_declared_type(self):
        """The document a parser returns must be an instance of its declared document_type."""
        parser = self.make_component()
        assert isinstance(parser.parse(self.make_response()), parser.document_type)


class DocumentContractSuite:
    def make_component(self) -> Document:
        _skip_no_impl()

    def test_satisfies_protocol(self):
        assert isinstance(self.make_component(), Document)

    def test_declares_capabilities(self):
        doc = self.make_component()
        assert isinstance(doc.capabilities, frozenset)
        assert doc.capabilities, "a document must declare at least one selector kind"

    def test_undeclared_kind_raises(self):
        doc = self.make_component()
        for kind in set(SelectorKind) - doc.capabilities:
            with pytest.raises(UnsupportedSelectorError):
                doc.select(Selector(kind=kind, query="anything"))

    def test_text_projection_is_str(self):
        assert isinstance(self.make_component().text(), str)

    def test_raw_returns_original_bytes(self):
        assert isinstance(self.make_component().raw(), bytes)

    def test_select_returns_plain_values_only(self):
        """Results are list[str | Mapping] — parser-native nodes must never leak out."""
        doc = self.make_component()
        for kind in doc.capabilities:
            for value in doc.select(self.make_selector(kind)):
                assert isinstance(value, str | dict), (
                    f"select() leaked a non-plain value for {kind}: {type(value)!r}"
                )

    def make_selector(self, kind: SelectorKind) -> Selector:
        _skip_no_impl()


class ExtractorContractSuite:
    def make_component(self) -> Extractor:
        _skip_no_impl()

    def test_satisfies_protocol(self):
        assert isinstance(self.make_component(), Extractor)


class ValidatorContractSuite:
    def make_component(self) -> Validator:
        _skip_no_impl()

    def make_record(self) -> Record:
        _skip_no_impl()

    def test_satisfies_protocol(self):
        assert isinstance(self.make_component(), Validator)

    def test_reports_per_field_failures(self):
        result = self.make_component().validate(self.make_record())
        for failure in result.failures:
            assert failure.field
            assert failure.message


class TransformerContractSuite:
    def make_component(self) -> Transformer:
        _skip_no_impl()

    def make_record(self) -> Record:
        _skip_no_impl()

    def test_satisfies_protocol(self):
        assert isinstance(self.make_component(), Transformer)

    def test_returns_record(self):
        assert isinstance(self.make_component().transform(self.make_record()), Record)


class RepositoryContractSuite:
    def make_component(self) -> Repository:
        _skip_no_impl()

    def make_record(self) -> Record:
        _skip_no_impl()

    def test_satisfies_protocol(self):
        assert isinstance(self.make_component(), Repository)

    async def test_save_accepts_record(self):
        await self.make_component().save(self.make_record())


class MiddlewareContractSuite:
    def make_component(self) -> Middleware:
        _skip_no_impl()

    def test_satisfies_protocol(self):
        assert isinstance(self.make_component(), Middleware)

    async def test_passes_through_to_next(self):
        """Default expectation: middleware calls next and returns its response.
        Suites for short-circuiting middleware (cache, block detection) override this."""
        seen: list[ScrapeRequest] = []
        canned = Response(status=200)

        async def next_(request: ScrapeRequest) -> Response:
            seen.append(request)
            return canned

        request = ScrapeRequest(url="file:///fixture")
        response = await self.make_component()(request, next_)
        assert seen, "middleware never called next"
        assert isinstance(response, Response)


class StageContractSuite:
    def make_component(self) -> Stage:
        _skip_no_impl()

    def make_error(self) -> Any:
        _skip_no_impl()

    def make_context(self) -> Any:
        _skip_no_impl()

    def test_satisfies_protocol(self):
        assert isinstance(self.make_component(), Stage)

    def test_has_name(self):
        assert self.make_component().name

    def test_on_error_returns_error_action(self):
        action = self.make_component().on_error(self.make_context(), self.make_error())
        assert isinstance(action, ErrorAction)


class LoginProviderContractSuite:
    def make_component(self) -> LoginProvider:
        _skip_no_impl()

    def test_satisfies_protocol(self):
        assert isinstance(self.make_component(), LoginProvider)
