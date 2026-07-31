"""Block-detection tests: the fixture corpus of real-world block pages must be
classified correctly, and blocks must surface as typed, permanent, blocked errors."""

import pytest

from components.middleware.block_detection import BlockDetectionMiddleware, BlockKind
from core.errors.exceptions import FetchError
from core.models import Response, ScrapeRequest
from tests.helpers import fixture_response

REQ = ScrapeRequest(url="https://shop.example/item")


def serve(response: Response):
    """Wraps a canned response as a fake next() callable."""

    async def next_(request: ScrapeRequest) -> Response:
        return response

    return next_


class TestClassification:
    """classify() on the stored block-page fixtures — this corpus grows forever."""

    def test_real_content_is_content(self):
        bd = BlockDetectionMiddleware()
        response = fixture_response("sample_product.html", "text/html")
        assert bd.classify(response) is BlockKind.CONTENT

    def test_captcha_page_with_status_200(self):
        bd = BlockDetectionMiddleware()
        response = fixture_response("blocks/captcha_200.html", "text/html")
        assert response.status == 200
        assert bd.classify(response) is BlockKind.CAPTCHA

    def test_access_denied_page_with_status_200(self):
        bd = BlockDetectionMiddleware()
        response = fixture_response("blocks/access_denied_200.html", "text/html")
        assert bd.classify(response) is BlockKind.SOFT_BLOCK

    def test_403_is_hard_block(self):
        assert BlockDetectionMiddleware().classify(Response(status=403)) is BlockKind.HARD_BLOCK

    def test_custom_signatures_from_config(self):
        bd = BlockDetectionMiddleware(signatures={"soft_block": ["zugriff verweigert"]})
        response = Response(status=200, body=b"Zugriff verweigert!")
        assert bd.classify(response) is BlockKind.SOFT_BLOCK


class TestMiddlewareBehavior:
    async def test_blocked_response_raises_permanent_blocked_error(self):
        bd = BlockDetectionMiddleware()
        blocked = fixture_response("blocks/captcha_200.html", "text/html")
        with pytest.raises(FetchError) as err:
            await bd(REQ, serve(blocked))
        assert err.value.blocked is True
        assert err.value.transient is False  # retry middleware must never retry a block
        assert "captcha" in str(err.value)

    async def test_clean_response_passes_through(self):
        bd = BlockDetectionMiddleware()
        clean = fixture_response("sample_product.html", "text/html")
        assert (await bd(REQ, serve(clean))) is clean
