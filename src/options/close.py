"""Closing a condor. The sign convention inverts, and nothing else guards it.

Issue #33. `CondorPlan` refuses to construct with a non-credit limit, so an opening order cannot
reach the wire with the wrong sign -- the invariant lives on the type rather than in a check.
There was no counterpart on the way out because there was no way out: nothing in the condor path
closed a position, and the only close-leg builder in the repo belongs to the shelved vertical path.

Closing inverts the convention. Opening a condor takes a credit, so its net limit is negative.
Closing pays a debit, so its net limit is positive. The API raises nothing either way; a
credit-signed close is a real order at a price nobody intended.

So the exit invariant lives here, on the type, for the same reason the entry one does: the first
person to close a condor on this account will be doing it by hand, under time pressure, on a day
that matters.
"""

from __future__ import annotations

import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

CONTRACT_MULTIPLIER = 100

MAX_CROSS = 0.25
"""How far over the touch a close may reach.

Crossing the touch is deliberate -- an unmarketable close rests while the position expires, which
on an expiry day is the same as not having sent it. But a limit far above the touch is a
fat-fingered price rather than a cross, and it is the other half of the sign bug: both put a
number on the wire that nobody meant.
"""


class CondorClose(BaseModel):
    """An order to close a condor. Note the sign: `limit_price` is a **debit** and is positive.

    The mirror of `CondorPlan`, which asserts the opposite. Constructing one of these proves the
    sign, so a caller that holds a `CondorClose` is holding something that cannot be an accidental
    credit order.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    underlying: str
    expiry: datetime.date
    contracts: int = Field(gt=0)
    limit_price: float
    """NET price, POSITIVE for a debit. Opening was negative. This is the inversion."""
    debit_at_touch: float
    rationale: str = Field(min_length=1)

    @model_validator(mode="after")
    def _the_sign_is_a_debit(self) -> CondorClose:
        if self.limit_price <= 0:
            raise ValueError(
                f"limit_price {self.limit_price:+.2f} is not a debit. Closing a credit structure "
                f"PAYS: on a multi-leg order this is a NET price, and a negative number here is "
                f"the opening convention copied onto an exit. It does not raise at the API."
            )
        if self.limit_price < self.debit_at_touch:
            raise ValueError(
                f"limit {self.limit_price:.2f} is below the touch {self.debit_at_touch:.2f}, so "
                f"it is not marketable. An unfilled close on an expiry day is the same as not "
                f"having sent one."
            )
        if self.limit_price > self.debit_at_touch + MAX_CROSS:
            raise ValueError(
                f"limit {self.limit_price:.2f} is {self.limit_price - self.debit_at_touch:.2f} "
                f"over the touch {self.debit_at_touch:.2f}, past the {MAX_CROSS:.2f} cap. That is "
                f"a fat-fingered price, not a cross."
            )
        return self

    @property
    def cost(self) -> float:
        """What this pays, in dollars, if it fills at the limit."""
        return self.limit_price * CONTRACT_MULTIPLIER * self.contracts


def build_close_legs(held: list[tuple[str, int]]) -> list[dict]:
    """Legs that flatten what is held: sell the longs, buy back the shorts.

    `held` is (symbol, signed_qty) as the broker reports it. The direction comes from the sign of
    the position, which is unambiguous here -- unlike a fill, where the trade direction and the
    position sign disagree precisely on a closing order.
    """
    out = []
    for symbol, qty in held:
        if qty == 0:
            raise ValueError(f"{symbol} is not held; a close cannot flatten a flat leg")
        long = qty > 0
        out.append(
            {
                "symbol": symbol,
                "ratio_qty": "1",  # the structure, not the size. `qty` carries the count.
                "side": "sell" if long else "buy",
                "position_intent": "sell_to_close" if long else "buy_to_close",
            }
        )
    return out


def price_close(held: list[tuple[str, int]], quotes: dict) -> tuple[float, float]:
    """`(net_at_mid, net_at_touch)` as **debits** -- positive means we pay.

    At the touch we sell the longs into the bid and buy the shorts at the ask, which is what
    crossing actually costs. A leg without a two-sided quote refuses rather than being skipped: a
    net summed over whichever legs happened to quote is a different number, not an approximate one.
    """
    mid = touch = 0.0
    for symbol, qty in held:
        q = quotes.get(symbol) or {}
        bid, ask = q.get("bid"), q.get("ask")
        if bid is None or ask is None:
            raise ValueError(f"no two-sided quote for {symbol}; refusing to price a partial close")
        long = qty > 0
        m = (bid + ask) / 2.0
        # Selling takes in (negative debit), buying pays out (positive debit).
        mid += -m if long else m
        touch += -bid if long else ask
    return round(mid, 4), round(touch, 4)
