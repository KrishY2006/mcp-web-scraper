# MCP Web Scraper

## Purpose

MCP Web Scraper is an [MCP (Model Context Protocol)](https://modelcontextprotocol.io) server that safely fetches webpages over HTTP(S) and extracts useful, structured information from them.

It is built as a small pipeline with a clear separation of concerns:

```
MCP tool -> fetch.py (URL -> HTML) -> extract.py (HTML -> data)
```

- `fetch.py` handles all network I/O: it turns a URL into raw HTML text.
- `extract.py` is a pure, offline layer: it turns HTML text into structured data.
- `server.py` exposes both layers as MCP tools.

## Features

### MCP tools

The server currently implements the following MCP tools:

| Tool            | Purpose                                                            |
| --------------- | ------------------------------------------------------------------ |
| `ping`          | Health check; returns `"pong"`.                                    |
| `scrape_read`   | Fetch a page and return its clean, readable text.                  |
| `scrape_extract` | Fetch a page and extract structured fields using a selectors map.  |
| `scrape_links`  | Fetch a page and return the links found on it, with pagination.    |
| `scrape_tables` | Fetch a page and extract the HTML tables found on it.              |

#### scrape_links

- Resolves relative links against the final page URL, so all returned URLs are absolute.
- Removes duplicate URLs (each URL appears at most once).
- `same_domain` filtering: only keep links whose hostname matches the page's hostname.
- `limit`: maximum number of links to return.
- `offset`: number of links to skip before applying `limit`.
- `total`: the number of unique links before `offset`/`limit` are applied, so clients can paginate.
- Only `http`/`https` links are returned; `mailto:`, `javascript:`, `data:`, and fragment-only links are ignored.

#### scrape_extract

- Accepts a `selectors` map that turns output field names into CSS selectors.
- Plain CSS selector: returns the cleaned text of the first match.
- Attribute extraction: returns the value of a named attribute (for example `"attr": "src"`).
- `all: true`: returns a list of cleaned text values for every match (can be combined with `attr`).
- Relative `href`/`src` attribute values are resolved against the final page URL.
- Returns `null` for a selector that matches nothing.

### Fetch-layer security

- HTTP/HTTPS only; other schemes are rejected.
- SSRF protection: refuses to fetch loopback, private, and link-local addresses.
- Response-size limit: downloads are capped and aborted when the body grows too large.
- Timeout handling: every request step has a timeout.
- Redirect validation: redirect targets are re-checked for safety.
- HTTP error handling: 4xx/5xx responses become clean errors instead of raw output.

## Project Structure

```
mcp-web-scraper/
├── src/
│   └── web_scraper_mcp/
│       ├── __init__.py
│       ├── fetch.py       # URL -> HTML (network layer)
│       ├── extract.py     # HTML -> data (extraction layer)
│       └── server.py      # MCP tool definitions
├── test/
│   ├── test_fetch.py
│   ├── test_extract.py
│   ├── test_links.py
│   └── test_structured.py
├── pyproject.toml
└── .gitignore
```

## Requirements

- Python 3.10 or newer (see `requires-python` in `pyproject.toml`).
- The project's runtime dependencies, installed automatically from `pyproject.toml`:
  - `mcp[cli]>=1,<2` (MCP Python SDK v1, with the CLI extra)
  - `httpx`
  - `beautifulsoup4`
  - `lxml`

## Installation

Create and activate a virtual environment on Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

Install the project and its dependencies (editable install, so code changes apply immediately):

```powershell
python -m pip install -e .
```

If you use [uv](https://docs.astral.sh/uv/), the equivalent is:

```powershell
uv venv
uv pip install -e .
```

## Running the MCP Server

Start the server directly with the module command:

```powershell
python -m web_scraper_mcp.server
```

The server communicates over MCP **stdio**, so it is designed to be launched by an MCP client (like MCP Inspector) rather than used in a plain terminal.

## Running MCP Inspector

[MCP Inspector](https://modelcontextprotocol.io/docs/tools/inspector) launches the server and opens a browser interface where the tools can be tested:

```powershell
mcp dev src/web_scraper_mcp/server.py --with-editable .
```

`--with-editable .` installs the project (and its dependencies) into the temporary environment MCP Inspector uses. A browser window opens where each tool can be invoked and its response inspected.

## MCP Tools

### ping

- **Purpose:** verify the server is responding.
- **Parameters:** none.
- **Return:** the string `"pong"`.

Example input:

```json
{}
```

### scrape_read

- **Purpose:** fetch a webpage and return its readable text with script/style content removed.
- **Important parameters:**
  - `url` — absolute `http://` or `https://` URL.
  - `timeout_seconds` — request timeout (default `10.0`).
  - `max_bytes` — maximum response size in bytes (default `1_000_000`).
  - `max_chars` — maximum number of text characters to return (default `10_000`).
- **Return:** `{"final_url": "...", "status_code": 200, "text": "..."}`.

Example input:

```json
{
  "url": "https://example.com",
  "timeout_seconds": 10.0,
  "max_bytes": 1000000,
  "max_chars": 10000
}
```

### scrape_extract

- **Purpose:** fetch a webpage and extract named fields using CSS selectors.
- **Important parameters:**
  - `url` — absolute `http://` or `https://` URL.
  - `selectors` — a dict mapping field names to CSS selectors or selector objects.
  - `timeout_seconds` — request timeout (default `10.0`).
  - `max_bytes` — maximum response size in bytes (default `1_000_000`).
- **Return:** `{"final_url": "...", "status_code": 200, "fields": {...}}`. Each selector that matches nothing yields `null`.

Example input:

```json
{
  "url": "https://example.com",
  "selectors": {
    "title": "h1",
    "price": ".price",
    "image": {"selector": "img.hero", "attr": "src"},
    "tags": {"selector": ".tag", "all": true}
  }
}
```

### scrape_links

- **Purpose:** fetch a webpage and return the links found on it.
- **Important parameters:**
  - `url` — absolute `http://` or `https://` URL.
  - `same_domain` — only return links matching the page's hostname (default `false`).
  - `limit` — maximum number of links to return (default `100`).
  - `offset` — number of links to skip before applying `limit` (default `0`).
  - `timeout_seconds` — request timeout (default `10.0`).
  - `max_bytes` — maximum response size in bytes (default `1_000_000`).
- **Return:** `{"final_url": "...", "status_code": 200, "total": N, "links": [{"url": "...", "text": "..."}]}`.

Example input using `same_domain`, `limit`, and `offset`:

```json
{
  "url": "https://example.com",
  "same_domain": true,
  "limit": 10,
  "offset": 0
}
```

### scrape_tables

- **Purpose:** fetch a webpage and extract the HTML tables found on it.
- **Important parameters:**
  - `url` — absolute `http://` or `https://` URL.
  - `timeout_seconds` — request timeout (default `10.0`).
  - `max_bytes` — maximum response size in bytes (default `1_000_000`).
  - `max_tables` — maximum number of tables to return (default `10`).
  - `max_rows` — maximum number of data rows per table (default `100`).
- **Return:** `{"final_url": "...", "status_code": 200, "tables": [{"headers": [...], "rows": [[...]]}]}`.

Example input:

```json
{
  "url": "https://example.com",
  "max_tables": 5,
  "max_rows": 50
}
```

## Running Tests

The test suite uses [pytest](https://docs.pytest.org/). From the project root, run:

```powershell
pytest
```

The project currently has **42 tests** covering the fetch layer, extraction layer, structured extraction, and link pagination. All tests are offline and make no real network requests.

## Security Notes

- **SSRF protection:** before fetching, the server validates that the target is an absolute `http://` or `https://` URL, then resolves the host and refuses to connect to loopback, private, link-local, or otherwise non-global addresses. Redirect targets are re-checked the same way.
- **Response-size limit:** the response body is read as a stream and aborted as soon as it exceeds `max_bytes`, so an oversized or runaway response cannot exhaust memory.
- **Error handling:** invalid URLs, blocked addresses, timeouts, HTTP errors, and oversized bodies are converted into clean, human-readable client errors rather than crashing the server.

This project does **not** provide browser automation, JavaScript rendering, authentication, or crawling. It only fetches static HTML and extracts data from it.

## Development Notes

- **`fetch.py`** owns all networking: URL validation, SSRF checks, streaming downloads, and error conversion.
- **`extract.py`** owns all HTML processing: it is a pure, offline layer that never makes network requests.
- **`server.py`** owns the MCP plumbing: tool definitions, request/response shapes, and converting extraction/fetch errors into clean client-facing errors.

When changing behavior, keep these responsibilities in their respective files.
