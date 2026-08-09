"""MCP server for the mcp-web-scraper project (Milestone 3).

This module exposes the existing fetch layer (fetch.py) and extraction layer
(extract.py) as MCP tools:

    MCP tool  ->  fetch.py (URL -> HTML)  ->  extract.py (HTML -> data)

Only the MCP plumbing lives here; all scraping logic is delegated to the
other modules, which are reused as-is.
"""

from __future__ import annotations

from typing import Any, NoReturn

from mcp.server.fastmcp import FastMCP

from web_scraper_mcp.extract import (
    ExtractionError,
    extract_links,
    extract_readable_text,
    extract_structured,
    extract_tables,
)
from web_scraper_mcp.fetch import FetchError, FetchResult, fetch_page

mcp = FastMCP("web_scraper_mcp")


@mcp.tool()
def ping() -> str:
    """Check that the MCP server is working."""
    return "pong"


async def _fetch_page(url: str, timeout: float, max_bytes: int) -> FetchResult:
    """Fetch ``url``, converting a FetchError into a clean client error.

    Args:
        url: The absolute http:// or https:// URL to fetch.
        timeout: Request timeout in seconds.
        max_bytes: Maximum response size in bytes.

    Raises:
        ValueError: With a safe, human-readable message when the page cannot
            be fetched (invalid URL, SSRF block, timeout, HTTP error, ...).
    """
    try:
        return await fetch_page(url, max_bytes=max_bytes, timeout=timeout)
    except FetchError as exc:
        raise ValueError(f"Could not fetch '{url}': {exc}") from exc


def _extract_error(url: str, exc: Exception) -> NoReturn:
    """Raise a clean client error for a failed extraction step.

    Args:
        url: The URL that was being scraped.
        exc: The underlying ExtractionError.

    Raises:
        ValueError: With a safe, human-readable message.
    """
    raise ValueError(f"Could not extract data from '{url}': {exc}") from exc


@mcp.tool()
async def scrape_read(
    url: str,
    timeout_seconds: float = 10.0,
    max_bytes: int = 1_000_000,
    max_chars: int = 10_000,
) -> dict[str, Any]:
    """Fetch a webpage and return its readable text.

    Args:
        url: The absolute http:// or https:// URL to scrape.
        timeout_seconds: Timeout for the request, in seconds.
        max_bytes: Maximum response size to download, in bytes.
        max_chars: Maximum number of text characters to return.

    Returns:
        A dict with the final URL after redirects, the HTTP status code, and
        the readable text of the page.
    """
    page = await _fetch_page(url, timeout_seconds, max_bytes)
    try:
        text = extract_readable_text(page.content, max_chars=max_chars)
    except ExtractionError as exc:
        _extract_error(url, exc)
    return {
        "final_url": page.url,
        "status_code": page.status_code,
        "text": text,
    }


@mcp.tool()
async def scrape_extract(
    url: str,
    selectors: dict[str, Any],
    timeout_seconds: float = 10.0,
    max_bytes: int = 1_000_000,
) -> dict[str, Any]:
    """Fetch a webpage and extract structured fields from it.

    ``selectors`` maps output field names to CSS selectors.  Each value is
    either a plain selector string (first match, cleaned text) or an object
    describing how to extract the field::

        {
            "title": "h1",
            "price": ".price",
            "image": {"selector": "img.hero", "attr": "src"},
            "tags": {"selector": ".tag", "all": True},
        }

    Args:
        url: The absolute http:// or https:// URL to scrape.
        selectors: A dict of field names to CSS selectors or selector
            objects.
        timeout_seconds: Timeout for the request, in seconds.
        max_bytes: Maximum response size to download, in bytes.

    Returns:
        A dict with the final URL after redirects, the HTTP status code, and
        the extracted fields.
    """
    page = await _fetch_page(url, timeout_seconds, max_bytes)
    try:
        fields = extract_structured(page.content, selectors, page.url)
    except ExtractionError as exc:
        _extract_error(url, exc)
    return {
        "final_url": page.url,
        "status_code": page.status_code,
        "fields": fields,
    }


@mcp.tool()
async def scrape_links(
    url: str,
    timeout_seconds: float = 10.0,
    max_bytes: int = 1_000_000,
    max_links: int = 100,
) -> dict[str, Any]:
    """Fetch a webpage and return the links found on it.

    Links are resolved against the final page URL, so relative links become
    absolute HTTP/HTTPS URLs.

    Args:
        url: The absolute http:// or https:// URL to scrape.
        timeout_seconds: Timeout for the request, in seconds.
        max_bytes: Maximum response size to download, in bytes.
        max_links: Maximum number of unique links to return.

    Returns:
        A dict with the final URL, the HTTP status code, and a list of links.
        Each link has "url" and "text" keys.
    """
    page = await _fetch_page(url, timeout_seconds, max_bytes)
    try:
        links = extract_links(page.content, page.url, max_links=max_links)
    except ExtractionError as exc:
        _extract_error(url, exc)
    return {
        "final_url": page.url,
        "status_code": page.status_code,
        "links": links,
    }


@mcp.tool()
async def scrape_tables(
    url: str,
    timeout_seconds: float = 10.0,
    max_bytes: int = 1_000_000,
    max_tables: int = 10,
    max_rows: int = 100,
) -> dict[str, Any]:
    """Fetch a webpage and extract the HTML tables found on it.

    Args:
        url: The absolute http:// or https:// URL to scrape.
        timeout_seconds: Timeout for the request, in seconds.
        max_bytes: Maximum response size to download, in bytes.
        max_tables: Maximum number of tables to return.
        max_rows: Maximum number of data rows to return per table.

    Returns:
        A dict with the final URL, the HTTP status code, and a list of
        tables. Each table has "headers" and "rows" keys.
    """
    page = await _fetch_page(url, timeout_seconds, max_bytes)
    try:
        tables = extract_tables(
            page.content,
            max_tables=max_tables,
            max_rows=max_rows,
        )
    except ExtractionError as exc:
        _extract_error(url, exc)
    return {
        "final_url": page.url,
        "status_code": page.status_code,
        "tables": tables,
    }


def main():
    mcp.run()


if __name__ == "__main__":
    main()
