"""All framework contracts — the ONLY core package plugins may import (plan2.md §8)."""

from core.contracts.document import Document, UnsupportedSelectorError
from core.contracts.extractor import ExtractionError, ExtractionSpec, Extractor
from core.contracts.fetcher import Fetcher, FetchError
from core.contracts.login_provider import AuthError, LoginProvider, Session, SessionContext
from core.contracts.middleware import Middleware, Next
from core.contracts.parser import ParseError, Parser
from core.contracts.repository import PersistError, Repository
from core.contracts.stage import Context, ErrorAction, Stage
from core.contracts.transformer import Transformer, TransformError
from core.contracts.validator import FieldFailure, ValidationError, ValidationResult, Validator

__all__ = [
    "AuthError",
    "Context",
    "Document",
    "ErrorAction",
    "ExtractionError",
    "ExtractionSpec",
    "Extractor",
    "FetchError",
    "Fetcher",
    "FieldFailure",
    "LoginProvider",
    "Middleware",
    "Next",
    "ParseError",
    "Parser",
    "PersistError",
    "Repository",
    "Session",
    "SessionContext",
    "Stage",
    "TransformError",
    "Transformer",
    "UnsupportedSelectorError",
    "ValidationError",
    "ValidationResult",
    "Validator",
]
