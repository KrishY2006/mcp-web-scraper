from mcp.server.fastmcp import FastMCP

mcp = FastMCP("web_scraper_mcp")


@mcp.tool()
def ping() -> str:
    """Check that the MCP server is working."""
    return "pong"


def main():
    mcp.run()


if __name__ == "__main__":
    main()