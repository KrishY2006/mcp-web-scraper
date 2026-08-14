import os
import sys
from pathlib import Path

from mcp.server.transport_security import TransportSecuritySettings

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from web_scraper_mcp.server import mcp

allowed_hosts = ["127.0.0.1:*", "localhost:*", "[::1]:*"]
vercel_domain = os.environ.get("VERCEL_PROJECT_DOMAIN")
if vercel_domain:
    allowed_hosts.append(vercel_domain)

mcp.settings.transport_security = TransportSecuritySettings(
    enable_dns_rebinding_protection=True,
    allowed_hosts=allowed_hosts,
)

app = mcp.streamable_http_app()
