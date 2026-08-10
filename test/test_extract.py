import pytest

from web_scraper_mcp.extract import (
    ExtractionError,
    extract_css,
    extract_links,
    extract_readable_text,
    extract_structured,
    extract_tables,
)


READABLE_HTML = """
<html>
<head>
    <title>Test Page</title>
</head>
<body>
    <h1>Heading</h1>
    <script>var secret = 1;</script>
    <style>.hidden { display: none; }</style>
    <p>Hello   world</p>
</body>
</html>
"""

CSS_HTML = """
<html>
<body>
    <h1 class="title" id="main">Widget</h1>
    <p class="intro">A great widget.</p>
    <p>No class here.</p>
</body>
</html>
"""

LINKS_HTML = """
<html>
<body>
    <a href="/products">Products</a>
    <a href="https://other.example.com/item">Other</a>
    <a href="#section">Anchor</a>
    <a href="mailto:info@example.com">Mail</a>
    <a href="/products">Products again</a>
</body>
</html>
"""

TABLE_HTML = """
<table>
  <tr><th>Name</th><th>Age</th></tr>
  <tr><td>Ada</td><td>36</td></tr>
  <tr><td>Bob</td><td>41</td></tr>
</table>
"""

CHROME_HTML = """
<html>
<body>
    <header>Site Header</header>
    <nav>
        <a href="/home">Home</a>
        <a href="/about">About</a>
    </nav>
    <main>
        <aside>Sidebar Ad</aside>
        <h1>Article Title</h1>
        <p>This is the article body.</p>
        <noscript>Please enable JavaScript.</noscript>
    </main>
    <footer>Site Footer</footer>
</body>
</html>
"""

STRUCTURED_HTML = """
<html>
<head><title>Structured Page</title></head>
<body>
    <h1>Structured Title</h1>
    <img class="hero" src="/images/hero.jpg" alt="Hero image">
    <a class="tag" href="/red">Red</a>
    <a class="tag" href="/blue">Blue</a>
</body>
</html>
"""


def test_readable_text_extraction():
    text = extract_readable_text(READABLE_HTML)

    assert "Test Page" in text
    assert "Heading" in text
    assert "secret" not in text
    assert ".hidden" not in text


def test_readable_text_preserves_internal_whitespace():
    text = extract_readable_text(READABLE_HTML)

    assert "Hello   world" in text


def test_readable_text_removes_chrome_elements():
    text = extract_readable_text(CHROME_HTML)

    assert "Site Header" not in text
    assert "Home" not in text
    assert "About" not in text
    assert "Sidebar Ad" not in text
    assert "Site Footer" not in text
    assert "Please enable JavaScript" not in text


def test_readable_text_preserves_main_content():
    text = extract_readable_text(CHROME_HTML)

    assert "Article Title" in text
    assert "This is the article body." in text


def test_css_selector_extraction():
    matches = extract_css(CSS_HTML, "h1")

    assert len(matches) == 1
    assert matches[0]["tag"] == "h1"
    assert matches[0]["text"] == "Widget"
    assert matches[0]["attrs"] == {"class": "title", "id": "main"}


def test_css_missing_selector_raises():
    with pytest.raises(ExtractionError, match="No elements matched"):
        extract_css(CSS_HTML, ".does-not-exist")


def test_link_extraction_resolves_relative_urls():
    result = extract_links(LINKS_HTML, "https://example.com/shop/index.html")

    assert result["total"] == 3
    assert result["links"] == [
        {"url": "https://example.com/products", "text": "Products"},
        {"url": "https://other.example.com/item", "text": "Other"},
        {"url": "https://example.com/shop/index.html", "text": "Anchor"},
    ]


def test_table_extraction():
    tables = extract_tables(TABLE_HTML)

    assert tables == [
        {"headers": ["Name", "Age"], "rows": [["Ada", "36"], ["Bob", "41"]]}
    ]


def test_structured_all_and_attr_combined():
    result = extract_structured(
        STRUCTURED_HTML,
        {
            "links": {
                "selector": "a.tag",
                "attr": "href",
                "all": True,
            }
        },
        "https://example.com",
    )

    assert result["links"] == [
        "https://example.com/red",
        "https://example.com/blue",
    ]


def test_structured_all_no_match_returns_empty_list():
    result = extract_structured(
        STRUCTURED_HTML,
        {"tags": {"selector": ".does-not-exist", "all": True}},
        "https://example.com",
    )

    assert result["tags"] == []


def test_structured_missing_attr_returns_none():
    result = extract_structured(
        STRUCTURED_HTML,
        {"data": {"selector": "img", "attr": "data-id"}},
        "https://example.com",
    )

    assert result["data"] is None


def test_structured_non_url_attr_is_not_resolved():
    result = extract_structured(
        STRUCTURED_HTML,
        {"alt": {"selector": "img", "attr": "alt"}},
        "https://example.com",
    )

    assert result["alt"] == "Hero image"


def test_structured_invalid_selectors_raises():
    with pytest.raises(ExtractionError, match="selectors must be a dict"):
        extract_structured(STRUCTURED_HTML, "not a dict", "https://example.com")


def test_structured_empty_html_raises():
    with pytest.raises(ExtractionError, match="HTML content is empty"):
        extract_structured("", {"title": "h1"}, "https://example.com")
