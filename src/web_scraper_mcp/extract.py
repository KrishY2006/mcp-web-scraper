"""Extraction layer for the mcp-web-scraper project (Milestone 2).

This module turns an HTML string into useful, structured data.  It is a
pure function of the HTML it is given: it never performs network requests,
never executes JavaScript, and never calls back into the fetch layer.

Architecture:

    fetch.py:    URL -> HTML
    extract.py:  HTML -> useful structured data

All public functions raise ``ExtractionError`` with a clear message when the
input cannot be extracted as requested.
"""

from __future__ import annotations

import urllib.parse
from typing import Any

from bs4 import BeautifulSoup
from bs4.element import Tag

#: Type aliases keep the public signatures readable.
ExtractedElement = dict[str, Any]  # tag + text + attrs from a CSS match.
ExtractedLink = dict[str, str]  # {"url": ..., "text": ...}
ExtractedTable = dict[str, Any]  # {"headers": [...], "rows": [[...], ...]}


class ExtractionError(Exception):
    """Raised when HTML cannot be extracted as requested.

    The message is human-readable and safe to show to the user of the
    MCP server.
    """


def _make_soup(html: str) -> BeautifulSoup:
    """Parse ``html`` into a BeautifulSoup tree using the lxml parser.

    Raises:
        ExtractionError: If ``html`` is not a string or is empty/blank, or if
            the parser cannot handle the input.
    """
    if not isinstance(html, str) or not html.strip():
        raise ExtractionError("HTML content is empty.")

    try:
        return BeautifulSoup(html, "lxml")
    except Exception as exc:  # Defensive: lxml may reject pathological input.
        raise ExtractionError(f"Could not parse the provided HTML: {exc}") from exc


def _clean_text(value: str) -> str:
    """Strip ``value`` and collapse runs of whitespace into single spaces."""
    return " ".join(value.split())


def _truncate(text: str, limit: int) -> str:
    """Return ``text`` capped at ``limit`` characters with a truncation marker."""
    marker = "... (truncated)"
    if len(text) <= limit:
        return text
    keep = max(0, limit - len(marker))
    return text[:keep] + marker


def _attrs_to_json(element: Tag) -> dict[str, str]:
    """Convert a tag's attributes into a flat, JSON-serializable dict.

    Attribute values are always returned as strings (a list of CSS classes,
    for example, is joined with spaces).
    """
    attrs: dict[str, str] = {}
    for name, value in element.attrs.items():
        if isinstance(value, list):
            value = " ".join(str(item) for item in value)
        attrs[name] = str(value)
    return attrs


def extract_readable_text(html: str, max_chars: int = 10_000) -> str:
    """Extract clean, readable text from an HTML string.

    Script and style blocks are removed, block boundaries become newlines,
    blank lines are dropped, and the result is capped at ``max_chars``.

    Args:
        html: The HTML to extract text from.
        max_chars: Maximum number of characters to return.

    Returns:
        The page's text as a plain string.

    Raises:
        ExtractionError: If ``html`` is empty or cannot be parsed.
    """
    if max_chars <= 0:
        raise ExtractionError("max_chars must be greater than zero.")

    soup = _make_soup(html)

    # Remove elements that contain code rather than readable content.
    for element in soup(["script", "style"]):
        element.decompose()

    # Use a newline separator, then drop blank lines.
    lines = (line.strip() for line in soup.get_text(separator="\n").splitlines())
    text = "\n".join(line for line in lines if line)

    return _truncate(text, max_chars)


def extract_css(
    html: str,
    selector: str,
    max_matches: int = 10,
    max_chars_per_match: int = 1_000,
) -> list[ExtractedElement]:
    """Extract elements matching a CSS selector.

    For every match the tag name, cleaned text content, and attributes are
    returned.

    Args:
        html: The HTML to search.
        selector: A CSS selector understood by BeautifulSoup.
        max_matches: Maximum number of matches to return.
        max_chars_per_match: Maximum characters of text per match.

    Returns:
        A list of dicts shaped like::

            {"tag": "h1", "text": "...", "attrs": {"id": "...", "class": "..."}}

    Raises:
        ExtractionError: If the selector is empty, nothing matches it, or any
            argument is invalid.
    """
    if not isinstance(selector, str) or not selector.strip():
        raise ExtractionError("CSS selector must be a non-empty string.")
    if max_matches <= 0:
        raise ExtractionError("max_matches must be greater than zero.")
    if max_chars_per_match <= 0:
        raise ExtractionError("max_chars_per_match must be greater than zero.")

    soup = _make_soup(html)

    elements = soup.select(selector)
    if not elements:
        raise ExtractionError(f"No elements matched CSS selector '{selector}'.")

    results: list[ExtractedElement] = []
    for element in elements[:max_matches]:
        results.append(
            {
                "tag": element.name,
                "text": _truncate(_clean_text(element.get_text(" ", strip=True)),
                                  max_chars_per_match),
                "attrs": _attrs_to_json(element),
            }
        )
    return results


def _normalize_url(url: str) -> str:
    """Normalize ``url`` for deduplication.

    Removes the fragment and lowercases the scheme and host so that
    equivalent URLs are treated as duplicates.
    """
    parts = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit(
        (parts.scheme.lower(), parts.netloc.lower(), parts.path, parts.query, "")
    )


def extract_links(
    html: str,
    base_url: str,
    max_links: int = 100,
) -> list[ExtractedLink]:
    """Extract links from anchor tags.

    Relative URLs are resolved against ``base_url``, fragments are dropped,
    and only absolute ``http``/``https`` URLs are kept.  Duplicate URLs are
    returned only once, in document order.

    Args:
        html: The HTML to search.
        base_url: The absolute ``http://`` or ``https://`` URL that relative
            links should be resolved against.
        max_links: Maximum number of unique links to return.

    Returns:
        A list of dicts shaped like ``{"url": "https://...", "text": "..."}``.

    Raises:
        ExtractionError: If ``base_url`` is invalid or any argument is out of
            range.
    """
    base_parts = urllib.parse.urlsplit(base_url)
    if (
        not base_parts.scheme.lower() in ("http", "https")
        or not base_parts.netloc
    ):
        raise ExtractionError(
            "base_url must be an absolute http:// or https:// URL."
        )
    if max_links <= 0:
        raise ExtractionError("max_links must be greater than zero.")

    soup = _make_soup(html)

    links: list[ExtractedLink] = []
    seen: set[str] = set()

    for anchor in soup.find_all("a"):
        href = anchor.get("href")
        if href is None:
            continue

        # Build an absolute URL, then drop any fragment (e.g. "#section").
        absolute = _normalize_url(urllib.parse.urljoin(base_url, str(href)))

        # Keep only web links; ignore javascript:, mailto:, data:, etc.
        scheme = urllib.parse.urlsplit(absolute).scheme
        if scheme not in ("http", "https"):
            continue

        if absolute in seen:
            continue
        seen.add(absolute)

        text = _clean_text(anchor.get_text(strip=True))
        links.append({"url": absolute, "text": text})

        if len(links) >= max_links:
            break

    return links


def extract_tables(
    html: str,
    max_tables: int = 10,
    max_rows: int = 100,
) -> list[ExtractedTable]:
    """Extract HTML tables into JSON-serializable Python data.

    If a table contains a row of ``<th>`` cells, that row becomes the table's
    ``headers``; every other row becomes a data row.  Cell whitespace is
    cleaned and blank lines removed.

    Args:
        html: The HTML to search.
        max_tables: Maximum number of tables to return.
        max_rows: Maximum number of data rows to return per table.

    Returns:
        A list of dicts shaped like::

            {"headers": ["Name", "Age"], "rows": [["Ada", "36"]]}

    Raises:
        ExtractionError: If the HTML contains no tables or any argument is
            invalid.
    """
    if max_tables <= 0:
        raise ExtractionError("max_tables must be greater than zero.")
    if max_rows <= 0:
        raise ExtractionError("max_rows must be greater than zero.")

    soup = _make_soup(html)

    tables = soup.find_all("table")
    if not tables:
        raise ExtractionError("No <table> elements found in the HTML.")

    result: list[ExtractedTable] = []
    for table in tables[:max_tables]:
        rows = table.find_all("tr")
        if not rows:
            continue

        # The first row that contains a <th> cell is treated as the header.
        header_index = next(
            (i for i, row in enumerate(rows) if row.find("th") is not None),
            -1,
        )

        if header_index != -1:
            header_row = rows[header_index]
            headers = [_clean_text(cell.get_text(strip=True))
                       for cell in header_row.find_all(["th", "td"])]
            data_rows = [row for i, row in enumerate(rows) if i != header_index]
        else:
            headers = []
            data_rows = rows

        rows_data: list[list[str]] = []
        for row in data_rows[:max_rows]:
            cells = [
                _clean_text(cell.get_text(strip=True))
                for cell in row.find_all(["th", "td"])
            ]
            rows_data.append(cells)

        result.append({"headers": headers, "rows": rows_data})

    return result
