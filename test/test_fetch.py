import asyncio

import httpx
import pytest

from web_scraper_mcp import fetch as fetch_mod
from web_scraper_mcp.fetch import FetchError, fetch_page


class _StreamCtx:
    """Async context manager yielded by FakeClient.stream()."""

    def __init__(self, response=None, error=None):
        self._response = response
        self._error = error

    async def __aenter__(self):
        if self._error is not None:
            raise self._error
        return self._response

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakeClient:
    """Stand-in for httpx.AsyncClient that never touches the network."""

    def __init__(self, response=None, stream_error=None):
        self._response = response
        self._stream_error = stream_error

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def stream(self, method, url):
        return _StreamCtx(self._response, self._stream_error)


class FakeResponse:
    """Stand-in for httpx.Response with the bits fetch.py uses."""

    def __init__(
        self,
        url="https://example.com/page",
        status_code=200,
        reason_phrase="OK",
        encoding="utf-8",
        chunks=("body",),
    ):
        self.url = httpx.URL(url)
        self.status_code = status_code
        self.reason_phrase = reason_phrase
        self.encoding = encoding
        self._chunks = [chunk.encode(encoding) for chunk in chunks]

    async def aiter_bytes(self):
        for chunk in self._chunks:
            yield chunk


@pytest.fixture
def fake_httpx(monkeypatch):
    """Replace the network client and disable SSRF DNS resolution."""

    async def _no_ssrf_check(host):
        return None

    def _install(response=None, stream_error=None):
        client = FakeClient(response, stream_error)
        monkeypatch.setattr(
            fetch_mod.httpx, "AsyncClient", lambda **kwargs: client
        )
        monkeypatch.setattr(fetch_mod, "_check_ssrf", _no_ssrf_check)
        return client

    return _install


def test_fetch_success(fake_httpx):
    fake_httpx(
        FakeResponse(
            url="https://example.com/final",
            status_code=200,
            chunks=("<h1>Hello</h1>",),
        )
    )

    result = asyncio.run(fetch_page("https://example.com/start"))

    assert result.url == "https://example.com/final"
    assert result.status_code == 200
    assert result.content == "<h1>Hello</h1>"


def test_fetch_streams_body_across_chunks(fake_httpx):
    fake_httpx(FakeResponse(chunks=("<h1>", "Hello", "</h1>")))

    result = asyncio.run(fetch_page("https://example.com/page"))

    assert result.content == "<h1>Hello</h1>"


def test_empty_url_rejected():
    with pytest.raises(FetchError, match="non-empty"):
        asyncio.run(fetch_page(""))


def test_url_without_host_rejected():
    with pytest.raises(FetchError, match="no host"):
        asyncio.run(fetch_page("http://"))


def test_unsupported_scheme_rejected():
    with pytest.raises(FetchError, match="Unsupported URL scheme"):
        asyncio.run(fetch_page("ftp://example.com/file"))


def test_loopback_ip_rejected():
    with pytest.raises(FetchError, match="Refusing to fetch"):
        asyncio.run(fetch_page("http://127.0.0.1/"))


def test_private_ip_rejected():
    with pytest.raises(FetchError, match="Refusing to fetch"):
        asyncio.run(fetch_page("http://192.168.1.1/"))


def test_response_size_limit(fake_httpx):
    fake_httpx(FakeResponse(chunks=("x" * 100,)))

    with pytest.raises(FetchError, match="exceeds"):
        asyncio.run(fetch_page("https://example.com/page", max_bytes=50))


def test_timeout_converted_to_fetch_error(fake_httpx):
    fake_httpx(stream_error=httpx.TimeoutException("timed out"))

    with pytest.raises(FetchError, match="timed out"):
        asyncio.run(fetch_page("https://example.com/page"))


def test_connect_error_converted_to_fetch_error(fake_httpx):
    fake_httpx(stream_error=httpx.ConnectError("connection refused"))

    with pytest.raises(FetchError, match="Could not connect"):
        asyncio.run(fetch_page("https://example.com/page"))


def test_http_error_status_converted(fake_httpx):
    fake_httpx(FakeResponse(status_code=500, reason_phrase="Internal Server Error"))

    with pytest.raises(FetchError, match="HTTP error 500"):
        asyncio.run(fetch_page("https://example.com/page"))
