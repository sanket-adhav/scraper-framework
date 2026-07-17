"""Collects every contract suite in skeleton form (all tests skip — no implementations yet).

This file proves the suites are importable and runnable (Plan 01 DoD). From
Plan 02 on, real implementations get their own test modules subclassing the
same suites, and this file stays as-is.
"""

from tests.contract.base_suites import (
    DocumentContractSuite,
    ExtractorContractSuite,
    FetcherContractSuite,
    LoginProviderContractSuite,
    MiddlewareContractSuite,
    ParserContractSuite,
    RepositoryContractSuite,
    StageContractSuite,
    TransformerContractSuite,
    ValidatorContractSuite,
)


class TestFetcherSuiteSkeleton(FetcherContractSuite): ...


class TestParserSuiteSkeleton(ParserContractSuite): ...


class TestDocumentSuiteSkeleton(DocumentContractSuite): ...


class TestExtractorSuiteSkeleton(ExtractorContractSuite): ...


class TestValidatorSuiteSkeleton(ValidatorContractSuite): ...


class TestTransformerSuiteSkeleton(TransformerContractSuite): ...


class TestRepositorySuiteSkeleton(RepositoryContractSuite): ...


class TestMiddlewareSuiteSkeleton(MiddlewareContractSuite): ...


class TestStageSuiteSkeleton(StageContractSuite): ...


class TestLoginProviderSuiteSkeleton(LoginProviderContractSuite): ...
