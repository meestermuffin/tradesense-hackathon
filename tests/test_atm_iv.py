"""Implied vol for the expiry actually being traded.

The agent shipped with `iv = 0.127` as a constructor default — a constant read off 25 August data.
Every strike was solved against it. That is fine on a day the tape happens to agree and wrong on
any other: at 0.20 the 20-delta strike sits 3 points closer than it should, at 0.28 it is 7, and in
both cases the true delta is well outside the 18–22 band the guardrail exists to enforce.

**30-day IV is the wrong tenor here.** `src/options/live_iv.py` inverts at ~30 DTE to match how the
committed series was built, which is right for that series and wrong for a 2-day condor. Term
structure is real, and short-dated vol is what these strikes are priced against.

So: invert from the ATM contract of the expiry being traded, calls and puts averaged.
"""

import datetime as dt

import pytest

from src.options.atm import atm_iv, nearest_strike
from src.options.iv import price


class FakeClient:
    """Prices its own chain at a known vol, so inversion has a right answer to recover."""

    def __init__(
        self,
        spot=769.0,
        iv=0.1734,
        expiry=dt.date(2026, 9, 2),
        as_of=dt.date(2026, 8, 31),
        strikes=None,
    ):
        self.spot, self.iv, self.expiry, self.as_of = spot, iv, expiry, as_of
        self.strikes = strikes or [float(k) for k in range(int(spot) - 10, int(spot) + 11)]

    def option_contracts(self, underlying, **kw):
        from src.models import OptionContract

        out = []
        for k in self.strikes:
            for t in ("put", "call"):
                out.append(
                    OptionContract(
                        symbol=f"{underlying}{self.expiry:%y%m%d}{t[0].upper()}{int(k * 1000):08d}",
                        expiration_date=self.expiry,
                        strike_price=k,
                        type=t,
                    )
                )
        return out


def quotes_for(c: FakeClient, drop=(), one_sided=()):
    T = (c.expiry - c.as_of).days / 365.0
    out = {}
    for x in c.option_contracts("SPY"):
        if x.symbol in drop:
            continue
        cp = "C" if x.type == "call" else "P"
        p = price(c.spot, x.strike_price, T, 0.04, c.iv, cp)
        bid = None if x.symbol in one_sided else max(0.01, p * 0.995)
        out[x.symbol] = {"bid": bid, "ask": p * 1.005 + 0.01}
    return out


def test_it_recovers_the_vol_the_chain_was_priced_at():
    c = FakeClient(iv=0.1734)
    got = atm_iv(c, "SPY", c.expiry, c.spot, quotes_for(c), as_of=c.as_of)
    assert got == pytest.approx(0.1734, abs=0.005)


@pytest.mark.parametrize("iv", [0.08, 0.127, 0.20, 0.35])
def test_it_recovers_across_the_range_that_matters(iv):
    c = FakeClient(iv=iv)
    assert atm_iv(c, "SPY", c.expiry, c.spot, quotes_for(c), as_of=c.as_of) == pytest.approx(
        iv, abs=0.01
    )


def test_it_uses_the_expiry_being_traded_not_a_fixed_tenor():
    """Term structure is real: a 2-day condor must not be priced off 30-day vol."""
    near = FakeClient(iv=0.20, expiry=dt.date(2026, 9, 2))
    far = FakeClient(iv=0.13, expiry=dt.date(2026, 9, 30))
    a = atm_iv(near, "SPY", near.expiry, near.spot, quotes_for(near), as_of=near.as_of)
    b = atm_iv(far, "SPY", far.expiry, far.spot, quotes_for(far), as_of=far.as_of)
    assert a == pytest.approx(0.20, abs=0.01)
    assert b == pytest.approx(0.13, abs=0.01)
    assert a > b, "each expiry gets its own vol"


def test_nearest_strike_picks_the_atm_one():
    assert nearest_strike([760.0, 765.0, 770.0], 769.0) == 770.0
    assert nearest_strike([760.0, 765.0, 770.0], 766.0) == 765.0


def test_a_one_sided_atm_quote_falls_through_to_the_next_strike():
    """A missing side is a real market state near expiry, not an error."""
    c = FakeClient(iv=0.15)
    atm = nearest_strike(c.strikes, c.spot)
    dead = [x.symbol for x in c.option_contracts("SPY") if x.strike_price == atm]
    got = atm_iv(c, "SPY", c.expiry, c.spot, quotes_for(c, one_sided=dead), as_of=c.as_of)
    assert got is not None and got == pytest.approx(0.15, abs=0.02)


def test_it_returns_none_rather_than_guessing_when_nothing_inverts():
    c = FakeClient()
    assert atm_iv(c, "SPY", c.expiry, c.spot, {}, as_of=c.as_of) is None


def test_calls_and_puts_are_averaged():
    """Put-call parity should make them agree; averaging absorbs quote noise on either side."""
    c = FakeClient(iv=0.18)
    got = atm_iv(c, "SPY", c.expiry, c.spot, quotes_for(c), as_of=c.as_of)
    assert got == pytest.approx(0.18, abs=0.01)


def test_a_zero_dte_expiry_does_not_divide_by_zero():
    c = FakeClient(expiry=dt.date(2026, 8, 31), as_of=dt.date(2026, 8, 31))
    got = atm_iv(c, "SPY", c.expiry, c.spot, quotes_for(c), as_of=c.as_of)
    assert got is None or got > 0
