from web_scraper_mcp.extract import ExtractionError, extract_structured


HTML = """
<html>
<head>
    <title>Test Page</title>
</head>
<body>
    <h1 id="title">Test Product</h1>
    <p class="description">This is a great product.</p>

    <a href="/products">Products</a>
    <img src="/images/product.jpg" alt="Product Image">

    <div class="item">Phone</div>
    <div class="item">Laptop</div>
</body>
</html>
"""


def test_plain_selector():
    result = extract_structured(
        HTML,
        {"title": "h1"},
        "https://example.com",
    )

    assert result["title"] == "Test Product"


def test_attribute_extraction():
    result = extract_structured(
        HTML,
        {
            "link": {
                "selector": "a",
                "attr": "href",
            }
        },
        "https://example.com",
    )

    assert result["link"] == "https://example.com/products"


def test_all_text():
    result = extract_structured(
        HTML,
        {
            "items": {
                "selector": ".item",
                "all": True,
            }
        },
        "https://example.com",
    )

    assert result["items"] == ["Phone", "Laptop"]


def test_all_attribute_extraction():
    result = extract_structured(
        HTML,
        {
            "images": {
                "selector": "img",
                "attr": "src",
                "all": True,
            }
        },
        "https://example.com",
    )

    assert result["images"] == ["https://example.com/images/product.jpg"]


def test_missing_selector_returns_none():
    result = extract_structured(
        HTML,
        {"missing": ".does-not-exist"},
        "https://example.com",
    )

    assert result["missing"] is None


def test_invalid_spec_raises_error():
    try:
        extract_structured(
            HTML,
            {"bad": {"attr": "href"}},
            "https://example.com",
        )
    except ExtractionError:
        pass
    else:
        raise AssertionError("Expected ExtractionError")