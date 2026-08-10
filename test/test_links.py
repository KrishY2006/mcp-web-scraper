import pytest

from web_scraper_mcp.extract import ExtractionError, extract_links


LINKS_HTML = """
<html>
<body>
    <a href="/products">Products</a>
    <a href="https://other.example.com/item">Other</a>
    <a href="https://example.com/docs">Docs</a>
    <a href="/products">Products duplicate</a>
    <a href="https://example.com:8443/alt">Alt port</a>
    <a href="mailto:info@example.com">Mail</a>
    <a href="#section">Anchor</a>
</body>
</html>
"""

BASE_URL = "https://example.com/shop/index.html"


def test_absolute_url_resolution():
    result = extract_links(LINKS_HTML, BASE_URL)

    urls = [link["url"] for link in result["links"]]
    assert urls[0] == "https://example.com/products"
    # A bare "#section" link resolves to the page itself.
    assert "https://example.com/shop/index.html" in urls


def test_deduplication():
    result = extract_links(LINKS_HTML, BASE_URL)

    urls = [link["url"] for link in result["links"]]
    assert len(urls) == len(set(urls))
    assert urls.count("https://example.com/products") == 1


def test_same_domain_excludes_external_domains():
    result = extract_links(LINKS_HTML, BASE_URL, same_domain=True)

    hosts = {link["url"].split("/")[2] for link in result["links"]}
    assert "other.example.com" not in hosts
    assert all(
        host in ("example.com", "example.com:8443") for host in hosts
    )


def test_same_domain_includes_external_domains_by_default():
    result = extract_links(LINKS_HTML, BASE_URL)

    urls = [link["url"] for link in result["links"]]
    assert any(url.startswith("https://other.example.com/") for url in urls)


def test_same_domain_ignores_port():
    result = extract_links(LINKS_HTML, BASE_URL, same_domain=True)

    urls = [link["url"] for link in result["links"]]
    assert "https://example.com:8443/alt" in urls


def test_same_domain_total():
    result = extract_links(LINKS_HTML, BASE_URL, same_domain=True)

    assert result["total"] == 4


def test_limit():
    result = extract_links(LINKS_HTML, BASE_URL, limit=2)

    assert result["total"] == 5
    assert len(result["links"]) == 2


def test_offset():
    result = extract_links(LINKS_HTML, BASE_URL, offset=2)

    assert result["total"] == 5
    assert len(result["links"]) == 3
    assert result["links"][0]["url"] == "https://example.com/docs"


def test_offset_and_limit_together():
    result = extract_links(LINKS_HTML, BASE_URL, limit=2, offset=1)

    assert result["total"] == 5
    assert len(result["links"]) == 2
    assert result["links"][0]["url"] == "https://other.example.com/item"


def test_offset_beyond_available_links():
    result = extract_links(LINKS_HTML, BASE_URL, offset=10)

    assert result["total"] == 5
    assert result["links"] == []


def test_total_is_before_pagination():
    result = extract_links(LINKS_HTML, BASE_URL, limit=1, offset=1)

    assert result["total"] == 5
    assert len(result["links"]) == 1


def test_negative_limit_rejected():
    with pytest.raises(ExtractionError, match="limit must not be negative"):
        extract_links(LINKS_HTML, BASE_URL, limit=-1)


def test_negative_offset_rejected():
    with pytest.raises(ExtractionError, match="offset must not be negative"):
        extract_links(LINKS_HTML, BASE_URL, offset=-1)
