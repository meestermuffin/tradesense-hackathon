"""MCP server sessions, and the capability split between them.

**The plan's isolation design did not survive contact with the server.** It asked for a read
instance carrying market data that could not place an order. Probing `alpaca-mcp-server` v3.4.7 on
2026-08-31 showed that is not constructible:

| `ALPACA_TOOLSETS` | tools | ordering | option quotes |
|---|---|---|---|
| *(unset)* | 72 | yes | yes |
| `trading` | 20 | yes | no |
| `account,assets` | 19 | no | no |

There are six valid names — account, trading, watchlists, assets, news, locates — and **none of
them carries option quotes or chains.** Those exist only in the unrestricted configuration, which
also carries `place_option_order`. A market-data instance necessarily has ordering.

So the split is inverted, and lands somewhere better than the original:

- The **agent** gets `account,assets,news`: account state, the clock and calendar, tradable assets,
  news. **No ordering tool is loaded**, so the isolation is a property of the process rather than
  of an instruction in a prompt.
- Chains and quotes come from this repo's own `AlpacaClient`, which is the better path regardless:
  it carries the 40-symbol batch ceiling this endpoint needs, a retry policy, and pydantic
  validation at the boundary.
- The **write** instance gets `trading`, and is reachable only through `submit_condor`.

One sharp edge worth the constant: `_parse_toolsets` in the server does no validation. An unknown
name is accepted silently and loads nothing but the five always-on documentation tools — so a typo
here would disarm the agent with no error at all. `server_env` refuses instead.
"""

from __future__ import annotations

import os

VALID_TOOLSETS = frozenset({"account", "trading", "watchlists", "assets", "news", "locates"})
"""Read out of the installed package, 2026-08-31.

The server accepts any string here and warns on nothing.
"""

AGENT_TOOLSETS = ("account", "assets", "news")
"""What the model may reach directly. Deliberately excludes `trading`."""

WRITE_TOOLSETS = ("trading",)
"""Orders. Behind `submit_condor`, never handed to the model."""

SERVER_CMD = ("uvx", "--from", "alpaca-mcp-server", "alpaca-mcp-server", "--transport", "stdio")


def server_env(
    toolsets: list[str] | tuple[str, ...],
    key: str,
    secret: str,
    paper: bool = True,
    base: dict | None = None,
) -> dict:
    """Environment for one server instance.

    Raises on an unknown or empty toolset rather than letting the server accept it silently —
    empty means unset, which loads all 72 tools including ordering.
    """
    ts = list(toolsets)
    if not ts:
        raise ValueError(
            "no toolsets given; an empty ALPACA_TOOLSETS is treated as unset and loads "
            "all 72 tools, ordering included"
        )
    bad = [t for t in ts if t not in VALID_TOOLSETS]
    if bad:
        raise ValueError(
            f"unknown toolset(s) {bad}; the server accepts these silently and loads nothing. "
            f"Valid: {sorted(VALID_TOOLSETS)}"
        )
    env = dict(base if base is not None else os.environ)
    env["ALPACA_TOOLSETS"] = ",".join(ts)
    # The server reads ALPACA_API_KEY and never loads a .env; we store ALPACA_KEY_ID.
    env["ALPACA_API_KEY"] = key
    env["ALPACA_SECRET_KEY"] = secret
    env["ALPACA_PAPER_TRADE"] = "True" if paper else "False"
    return env
