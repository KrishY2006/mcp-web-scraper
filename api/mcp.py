import os
import sys
from pathlib import Path

from mcp.server.transport_security import TransportSecuritySettings

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from web_scraper_mcp.server import mcp

allowed_hosts = ["127.0.0.1:*", "localhost:*", "[::1]:*"]
for env_var in ("VERCEL_PROJECT_DOMAIN", "VERCEL_URL", "VERCEL_BRANCH_URL"):
    host = os.environ.get(env_var)
    if host:
        allowed_hosts.append(host)

mcp.settings.transport_security = TransportSecuritySettings(
    enable_dns_rebinding_protection=True,
    allowed_hosts=allowed_hosts,
)

app = mcp.streamable_http_app()
