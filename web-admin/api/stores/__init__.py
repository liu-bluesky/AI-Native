"""Compatibility exports for MCP store bridge."""

import stores.mcp_bridge as _impl
from stores.mcp_bridge import *  # noqa: F401,F403
globals().update({name: getattr(_impl, name) for name in dir(_impl) if not name.startswith("__")})
