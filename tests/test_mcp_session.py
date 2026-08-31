"""Capability isolation across two MCP instances.

The plan asked for a read instance carrying market data that could not place an order. Probing the
server on 2026-08-31 showed that is not achievable: `ALPACA_TOOLSETS` has six valid names —
account, trading, watchlists, assets, news, locates — and **none of them carries option quotes**.
Those appear only in the unrestricted 72-tool configuration, which also carries
`place_option_order`.

So the split is inverted from the plan, and ends up stronger:

- The **agent's** instance gets `account,assets,news`. It has no ordering tool at all, and the
  absence is structural rather than instructed.
- Option chains and quotes come from this repo's own client, which is the tested path anyway — it
  carries the 40-symbol batch limit, the retry policy and pydantic validation at the boundary.
- The **write** instance gets `trading`, reachable only through `submit_condor`.

Unknown toolset names are silently accepted and yield nothing but the five always-on documentation
tools, so a typo in this config disarms the agent with no error. That is what `AGENT_TOOLSETS` and
`WRITE_TOOLSETS` being constants, and this test asserting their contents, is for.
"""

import pytest

from src.agent.mcp import (
    AGENT_TOOLSETS,
    VALID_TOOLSETS,
    WRITE_TOOLSETS,
    server_env,
)


def test_the_agent_instance_has_no_ordering_toolset():
    """The isolation claim, as a property of the config rather than of a prompt."""
    assert "trading" not in AGENT_TOOLSETS


def test_the_write_instance_carries_trading():
    assert "trading" in WRITE_TOOLSETS


def test_both_configs_name_only_real_toolsets():
    """Unknown names are accepted silently and load nothing. A typo would disarm the agent."""
    for ts in AGENT_TOOLSETS + WRITE_TOOLSETS:
        assert ts in VALID_TOOLSETS, f"{ts!r} is not a real toolset"


def test_the_valid_set_is_what_the_server_actually_defines():
    """Probed from the installed package, 2026-08-31."""
    assert VALID_TOOLSETS == frozenset(
        {"account", "trading", "watchlists", "assets", "news", "locates"}
    )


def test_the_two_instances_do_not_overlap():
    assert not (set(AGENT_TOOLSETS) & set(WRITE_TOOLSETS))


# ---- environment construction


def test_env_maps_our_credential_names_to_the_ones_the_server_reads():
    """We store ALPACA_KEY_ID; the server reads ALPACA_API_KEY and never loads a .env."""
    env = server_env(["account"], key="abc", secret="xyz")
    assert env["ALPACA_API_KEY"] == "abc"
    assert env["ALPACA_SECRET_KEY"] == "xyz"


def test_env_sets_the_toolsets_as_a_comma_list():
    env = server_env(["account", "assets"], key="k", secret="s")
    assert env["ALPACA_TOOLSETS"] == "account,assets"


def test_env_defaults_to_paper():
    """A live-trading default would be the worst possible failure mode here."""
    assert server_env(["account"], key="k", secret="s")["ALPACA_PAPER_TRADE"] == "True"


def test_live_must_be_asked_for_explicitly():
    env = server_env(["account"], key="k", secret="s", paper=False)
    assert env["ALPACA_PAPER_TRADE"] == "False"


def test_env_refuses_an_unknown_toolset():
    """Silent acceptance by the server is exactly why this must raise here."""
    with pytest.raises(ValueError, match="market_data"):
        server_env(["market_data"], key="k", secret="s")


def test_env_refuses_empty_toolsets():
    """Empty means unset, which loads all 72 tools including ordering."""
    with pytest.raises(ValueError):
        server_env([], key="k", secret="s")
