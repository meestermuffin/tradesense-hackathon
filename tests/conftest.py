"""Fakes, so the suite runs on a fresh clone with no credentials and no network.

That is not only convenience. A test that needs a live account can only be run by the one person
holding the keys, which means in practice it is not run.
"""

import datetime

import pytest

from src.models import Order, Quote, StrikeCandidate, Template


def q(bid, ask):
    return Quote(bp=bid, ap=ask)


@pytest.fixture
def template():
    return Template(structure="put_credit", target_delta=0.25, width=5.0, max_width=25.0)


class FakeClient:
    """Answers the three calls `select_vertical` and `execution.place` make.

    `chain` is {strike: (symbol, bid, ask)}. Contracts are generated from it, so a test cannot
    accidentally describe a strike that has a quote but no contract.
    """

    def __init__(self, chain, expiry, order_status="filled", fill=None):
        self.chain, self.expiry = chain, expiry
        self.order_status, self.fill = order_status, fill
        self.submitted = []

    def option_contracts(self, underlying, **kw):
        """Honours the filters the real endpoint applies server-side.

        A fake that accepts `exp_lte` and then ignores it will pass a test that fails live -- and
        this endpoint's filters are exactly where this project has been bitten, since omitting an
        expiry bound silently defaults it to next weekend.
        """
        from src.models import OptionContract

        iso = self.expiry.isoformat()
        if kw.get("expiration_date") and kw["expiration_date"] != iso:
            return []
        if kw.get("exp_gte") and iso < kw["exp_gte"]:
            return []
        if kw.get("exp_lte") and iso > kw["exp_lte"]:
            return []
        lo, hi = kw.get("strike_gte"), kw.get("strike_lte")
        return [
            OptionContract(
                symbol=sym,
                expiration_date=self.expiry,
                strike_price=k,
                type="put" if kw.get("type_") in (None, "put") else "call",
            )
            for k, (sym, _, _) in sorted(self.chain.items())
            if (lo is None or k >= lo) and (hi is None or k <= hi)
        ]

    def option_quotes_latest(self, symbols):
        want = set(symbols)
        return {sym: q(bid, ask) for _, (sym, bid, ask) in self.chain.items() if sym in want}

    def submit_mleg(self, legs, qty, limit_price, tif="day"):
        self.submitted.append(dict(legs=legs, qty=qty, limit_price=limit_price))
        return Order(
            id="test-order",
            status=self.order_status,
            filled_avg_price=self.fill,
            filled_at="2026-08-26T14:00:00Z" if self.order_status == "filled" else None,
            legs=[],
        )

    def get_order(self, order_id):
        return Order(id=order_id, status=self.order_status, filled_avg_price=self.fill)

    def cancel_order(self, order_id):
        return True


@pytest.fixture
def put_chain():
    """A realistic put chain around spot 100, wide enough to hold a 5-wide vertical."""
    expiry = datetime.date.today() + datetime.timedelta(days=7)
    strikes = {}
    for k in range(80, 121, 5):
        mid = max(0.05, 6.0 - 0.28 * (100 - k))
        strikes[float(k)] = (f"XYZ{k:03d}P", round(mid - 0.05, 2), round(mid + 0.05, 2))
    return FakeClient(strikes, expiry)


def candidate(strike, symbol, mid, delta):
    return StrikeCandidate(
        strike=strike,
        symbol=symbol,
        mid=mid,
        iv=0.3,
        delta=delta,
        quote=q(mid - 0.05, mid + 0.05),
    )
