"""Fetch layer for the mcp-web-scraper project (Milestone 1).

This module safely fetches webpages over HTTP(S).  It validates the URL,
performs basic SSRF protection, enforces a response size limit, and returns
the fetched content together with useful metadata.

It does NOT parse HTML - that is left to later milestones.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
import urllib.parse
from dataclasses import dataclass

import httpx

#: User-Agent header that identifies this scraper.
USER_AGENT = "mcp-web-scraper/0.1"


class FetchError(Exception):
    """Raised when a URL cannot be fetched safely.

    The message is human-readable and safe to show to the user of the
    MCP server.
    """


@dataclass(frozen=True)
class FetchResult:
    """The successful outcome of fetching a webpage."""

    url: str  #: Final URL after following redirects.
    status_code: int  #: HTTP status code of the final response.
    content: str  #: The response body decoded as text.


def _validate_url(url: str) -> urllib.parse.SplitResult:
    """Validate that ``url`` is an absolute ``http://`` or ``https://`` URL.

    Returns the parsed URL so the caller does not need to parse it again.

    Raises:
        FetchError: If the URL is empty, malformed, or uses a scheme other
            than http or https.
    """
    if not isinstance(url, str) or not url.strip():
        raise FetchError("URL must be a non-empty string.")

    try:
        parts = urllib.parse.urlsplit(url.strip())
        _ = parts.port  # Raises ValueError for invalid port numbers.
    except ValueError as exc:
        raise FetchError(f"Malformed URL '{url}': {exc}") from exc

    if parts.scheme.lower() not in ("http", "https"):
        raise FetchError(
            f"Unsupported URL scheme '{parts.scheme or '(none)'}' in '{url}'. "
            "Only absolute http:// and https:// URLs are allowed."
        )

    if not parts.hostname:
        raise FetchError(
            f"Malformed URL '{url}': no host found. "
            "Only absolute http:// and https:// URLs are allowed."
        )

    return parts


def _is_blocked_address(
    ip: ipaddress.IPv4Address | ipaddress.IPv6Address,
) -> bool:
    """Return True if ``ip`` must never be fetched (SSRF protection).

    Blocks loopback, private, link-local, unspecified, reserved, multicast,
    and any other address that is not globally routable.
    """
    return (
        ip.is_loopback
        or ip.is_private
        or ip.is_link_local
        or ip.is_unspecified
        or ip.is_reserved
        or ip.is_multicast
        or not ip.is_global
    )


async def _resolve_host(
    host: str,
) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    """Resolve ``host`` to its IP addresses using async DNS.

    Raises:
        FetchError: If the hostname cannot be resolved.
    """
    loop = asyncio.get_running_loop()
    try:
        infos = await loop.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise FetchError(f"Could not resolve host '{host}': {exc}") from exc
    return [ipaddress.ip_address(info[4][0]) for info in infos]


async def _check_ssrf(host: str) -> None:
    """Refuse to fetch ``host`` if it points at a private network.

    If ``host`` is an IP literal it is checked directly.  Otherwise the
    hostname is resolved and every address it resolves to is checked.

    Raises:
        FetchError: If the host resolves to a blocked address.
    """
    try:
        ip = ipaddress.ip_address(host)
        addresses = [ip]
    except ValueError:
        addresses = await _resolve_host(host)

    for ip in addresses:
        if _is_blocked_address(ip):
            raise FetchError(
                f"Refusing to fetch '{host}': it resolves to {ip}, "
                "which is a loopback, private, or link-local address."
            )


async def _read_body(response: httpx.Response, max_bytes: int) -> str:
    """Read the response body, enforcing ``max_bytes`` while streaming.

    Raises:
        FetchError: If the body grows larger than ``max_bytes``.
    """
    chunks: list[bytes] = []
    total = 0
    async for chunk in response.aiter_bytes():
        total += len(chunk)
        if total > max_bytes:
            raise FetchError(f"Response body exceeds the {max_bytes} byte limit.")
        chunks.append(chunk)

    return b"".join(chunks).decode(response.encoding, errors="replace")


async def fetch_page(
    url: str,
    max_bytes: int = 1_000_000,
    timeout: float = 10.0,
) -> FetchResult:
    """Fetch a webpage over HTTP(S) and return its content.

    Args:
        url: An absolute ``http://`` or ``https://`` URL to fetch.
        max_bytes: Maximum number of bytes to download before giving up.
        timeout: Timeout in seconds for each step of the request.

    Returns:
        A FetchResult with the final URL, HTTP status code, and body text.

    Raises:
        FetchError: If the URL is invalid or unsafe, the request times out or
            fails, the server returns an HTTP error, or the body is too big.
    """
    if max_bytes <= 0:
        raise FetchError("max_bytes must be greater than zero.")
    if timeout <= 0:
        raise FetchError("timeout must be greater than zero.")

    parts = _validate_url(url)
    await _check_ssrf(parts.hostname)

    headers = {"User-Agent": USER_AGENT}
    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=httpx.Timeout(timeout),
            headers=headers,
            default_encoding="utf-8",
        ) as client:
            async with client.stream("GET", parts.geturl()) as response:
                # A redirect may have sent us somewhere we would refuse.
                if response.url.scheme not in ("http", "https"):
                    raise FetchError(
                        "Refusing to follow a redirect to an unsupported "
                        f"scheme '{response.url.scheme}'."
                    )
                await _check_ssrf(response.url.host)

                if response.status_code >= 400:
                    raise FetchError(
                        f"HTTP error {response.status_code} "
                        f"{response.reason_phrase} while fetching "
                        f"'{response.url}'."
                    )

                body = await _read_body(response, max_bytes)
    except FetchError:
        raise
    except httpx.TimeoutException as exc:
        raise FetchError(
            f"Request to '{url}' timed out after {timeout} seconds."
        ) from exc
    except httpx.ConnectError as exc:
        raise FetchError(f"Could not connect to '{url}': {exc}") from exc
    except httpx.UnsupportedProtocol as exc:
        raise FetchError(f"Unsupported protocol while fetching '{url}': {exc}") from exc
    except httpx.TooManyRedirects as exc:
        raise FetchError(f"Too many redirects while fetching '{url}'.") from exc
    except httpx.InvalidURL as exc:
        raise FetchError(f"Malformed URL '{url}': {exc}") from exc
    except httpx.StreamError as exc:
        raise FetchError(f"Failed to read response from '{url}': {exc}") from exc
    except httpx.HTTPError as exc:
        raise FetchError(f"Request to '{url}' failed: {exc}") from exc

    return FetchResult(
        url=str(response.url),
        status_code=response.status_code,
        content=body,
    )
