"""Typed shapes for everything that crosses a boundary.

Two kinds of model live here and they have opposite settings, deliberately.

**Wire models** parse what Alpaca sends. They ignore unknown fields, because the API returns far
more than this book reads and a new field upstream must not break a cycle. What they do *not* do is
tolerate a missing one. That is the point of them: an absent key on an otherwise-200 response is
this project's most-repeated failure -- `greeks` and `impliedVolatility` are simply not there on an
account without an OPRA agreement, and a plain dict answers `.get("greeks")` with None and lets the
run continue on a number that was never served. These raise instead.

They also absorb the string-typed numerics. Alpaca sends `strike_price`, `equity` and
`filled_avg_price` as strings; every call site used to wrap them in `float()` and one that forgot
would compare a string to a number and silently take the wrong branch.

**Domain models** are frozen and forbid unknown fields, because a typo in a keyword argument is a
bug, and a spread whose credit exceeds its width is not a windfall -- it is a bad quote, and the
invariant belongs on the type rather than in whichever call site remembers to check.
"""

from __future__ import annotations

import datetime
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

CONTRACT_MULTIPLIER = 100

# ---------------------------------------------------------------- wire models


class Wire(BaseModel):
    """Parsed from an Alpaca response. Unknown fields ignored, missing required fields raise."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")


class Quote(Wire):
    """Latest NBBO for one contract.

    There is no historical equivalent -- Alpaca serves no options quote history, so a spread not
    captured at submission is unreconstructable forever. See docs/measurement-log.md
    """

    bid: float = Field(alias="bp")
    ask: float = Field(alias="ap")
    bid_size: float = Field(0, alias="bs")
    ask_size: float = Field(0, alias="as")
    timestamp: str | None = Field(None, alias="t")

    @property
    def two_sided(self) -> bool:
        """A crossed or one-sided quote is data to refuse, not to raise on."""
        return self.bid > 0 and self.ask > 0 and self.ask >= self.bid

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2

    @property
    def spread_pct(self) -> float | None:
        return None if not self.two_sided or self.mid <= 0 else (self.ask - self.bid) / self.mid


class OptionContract(Wire):
    """Contract metadata. Served by the TRADING host -- a data key there returns 401."""

    symbol: str
    expiration_date: datetime.date
    strike_price: float
    type: Literal["call", "put"] | None = None


class Account(Wire):
    account_number: str
    equity: float
    last_equity: float | None = None
    cash: float | None = None
    position_market_value: float | None = None
    status: str | None = None
    options_approved_level: int | None = None


class Clock(Wire):
    is_open: bool
    next_open: str | None = None
    next_close: str | None = None


# OCC option symbol: root, then YYMMDD, then C/P, then an 8-digit strike.
_OCC = re.compile(r"^([A-Z]{1,6})(\d{6})([CP])(\d{8})$")


class Position(Wire):
    symbol: str
    qty: float = 0

    @property
    def underlying(self) -> str:
        """The name this position is on.

        `symbol` on an options position is the OCC contract, not the underlying. Comparing it
        directly against a candidate's underlying is a comparison that can never be true, which is
        how a one-position-per-name cap silently stops capping anything.
        """
        m = _OCC.match(self.symbol)
        return m.group(1) if m else self.symbol


class OrderLeg(Wire):
    symbol: str
    side: str | None = None
    status: str | None = None
    filled_avg_price: float | None = None


class Order(Wire):
    id: str | None = None
    status: str | None = None
    filled_at: str | None = None
    filled_avg_price: float | None = None
    legs: list[OrderLeg] = Field(default_factory=list)

    @property
    def settled(self) -> bool:
        return self.status in ("filled", "canceled", "rejected", "expired")


# -------------------------------------------------------------- domain models


class Domain(BaseModel):
    """Ours, not the API's. Frozen, and a stray keyword is an error rather than a silent no-op."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class Template(Domain):
    """What the model emits: a structure and its parameters, not contracts.

    Resolving this to strikes is `selection.select_vertical`. Keeping the model's surface at this
    level is what keeps stale chains, missing strikes and contract multipliers out of it, and what
    makes the decision backtestable.

    The defaults were previously spread across `template.get(...)` calls at each use site, which is
    how two call sites disagree about what a default is.
    """

    structure: Literal["put_credit", "call_credit"]
    target_delta: float = Field(gt=0, lt=1)
    width: float = Field(gt=0)
    max_width: float | None = Field(None, gt=0)
    dte_min: int = Field(5, ge=0)
    dte_max: int = Field(9, ge=0)
    max_spread_pct: float = Field(0.08, gt=0, lt=1)
    delta_tolerance: float = Field(0.15, gt=0, lt=1)

    @model_validator(mode="after")
    def _coherent(self) -> Template:
        if self.dte_max < self.dte_min:
            raise ValueError(f"dte_max {self.dte_max} below dte_min {self.dte_min}")
        if self.max_width is not None and self.max_width < self.width:
            raise ValueError(f"max_width {self.max_width} below width {self.width}")
        return self

    @property
    def cp(self) -> Literal["P", "C"]:
        return "P" if self.structure == "put_credit" else "C"

    @property
    def width_cap(self) -> float:
        return self.max_width if self.max_width is not None else self.width * 2


class StrikeCandidate(Domain):
    """One strike that passed quote quality and IV inversion.

    `delta` is computed, never read -- greeks are OPRA-gated and absent from the response.
    """

    strike: float
    symbol: str
    mid: float
    iv: float
    delta: float
    quote: Quote


class Spread(Domain):
    """A resolved vertical. Constructing one asserts the structure is sane."""

    underlying: str
    structure: Literal["put_credit", "call_credit"]
    expiry: datetime.date
    dte: int
    short: StrikeCandidate
    long: StrikeCandidate
    width: float = Field(gt=0)
    spot: float = Field(gt=0)
    credit_mid: float
    credit_touch: float
    max_loss: float
    short_delta: float

    @model_validator(mode="after")
    def _priced_sanely(self) -> Spread:
        if self.credit_mid <= 0:
            raise ValueError(f"{self.underlying}: structure does not credit at mid")
        if self.credit_mid >= self.width:
            # Credit above width implies negative max loss, i.e. risk-free money. It never is.
            # It means a quote is stale, crossed, or one side has not traded.
            raise ValueError(
                f"{self.underlying}: credit {self.credit_mid:.2f} >= width {self.width:g} — "
                f"the quotes are not trustworthy, this is not an arbitrage"
            )
        return self


class Rejection(Domain):
    """Why no spread was produced. A first-class result, not an error."""

    reason: str


SelectionResult = Spread | Rejection


class RankRow(Domain):
    """One name's standing in the IV-percentile ranking."""

    symbol: str
    eligible: bool
    day: str | None = None
    iv: float | None = None
    percentile: float | None = None
    obs: int = 0
    reason: str | None = None


class LiveIVReading(Domain):
    """Today's IV, inverted from a quote midpoint.

    `seam` is not a comment. The trailing history is inverted from last-trade closes and this is
    inverted from a quote mid; measured on 2026-08-26 those definitions disagree by 46-94% of a
    typical daily IV move. Carrying the seam on every reading is what makes that error measurable
    later rather than assumed away now.
    """

    iv: float
    strike: float
    expiry: datetime.date
    spot: float
    legs: int
    source: str
    seam: str


class RiskLimits(Domain):
    """Per-position and portfolio caps. See `risk_profile` for what they do *not* cover.

    A book gets its own named instance rather than an edit to someone else's. Two competing
    sources of truth for a limit is the failure this validates against.
    """

    max_open_positions: int = Field(gt=0)
    max_loss_per_position_pct: float = Field(gt=0, lt=1)
    max_total_defined_risk_pct: float = Field(gt=0, lt=1)
    kill_switch_drawdown_pct: float = Field(gt=0, lt=1)
    kill_switch_breaches: int | None = Field(None, gt=0)
    """Breaches that halt opening.

    A drawdown switch keyed on *realized* loss cannot fire in a book that closes nothing: with
    every position held to expiry there is no realized loss until the first expiry, so the counter
    reads zero through the half of the window it is supposed to govern. Breach count fires while
    positions are still open, and does not depend on how the paper engine marks a multi-leg book.
    """

    @model_validator(mode="after")
    def _position_cap_fits_the_book(self) -> RiskLimits:
        if self.max_loss_per_position_pct > self.max_total_defined_risk_pct:
            raise ValueError(
                f"per-position cap {self.max_loss_per_position_pct:.1%} exceeds the book cap "
                f"{self.max_total_defined_risk_pct:.1%} — one position could breach the book"
            )
        return self


class PortfolioState(Domain):
    equity: float
    last_equity: float
    open_count: int


class Exposure(Domain):
    """Net greeks for one position, signed for a short-premium structure."""

    delta: float
    gamma: float
    vega: float
    theta: float


class BookPosition(Domain):
    """A held position as the risk profile sees it."""

    exposure: Exposure
    max_loss: float
    spot: float


class SideQuote(Domain):
    bid: float
    ask: float


class NetQuote(Domain):
    """The two legs priced as one, captured either side of submission."""

    mid: float
    touch: float
    short: SideQuote
    long: SideQuote


class BookProfile(Domain):
    """What the book is exposed to, as opposed to how much it may lose per position."""

    positions: int
    effective_bets: float
    net_delta: float
    net_gamma: float
    net_vega: float
    net_theta: float
    defined_risk: float
    defined_risk_pct: float | None = None
    correlated_worst_case_pct: float | None = None


class StressResult(Domain):
    """A first-order shock. Crude on purpose, and labelled so at the point of use."""

    scenario: str
    delta_pnl: float
    vega_pnl: float
    first_order_pnl: float
    floor_from_defined_risk: float
    pct_of_equity: float | None = None
    note: str


class FillRecord(Domain):
    """One order, with the NBBO either side of submission.

    Written to JSONL and treated as evidence, which is why it is a declared schema rather than a
    dict assembled at the call site: the quotes in it cannot be re-fetched at any later date.
    """

    ok: bool
    filled: bool = False
    error: str | None = None
    order_id: str | None = None
    status: str | None = None
    underlying: str | None = None
    structure: str | None = None
    expiry: datetime.date | None = None
    contracts: int | None = None
    closing: bool = False
    limit: float | None = None
    submitted_at: str | None = None
    filled_at: str | None = None
    fill: float | None = None
    nbbo_pre: NetQuote | None = None
    nbbo_post: NetQuote | None = None
    legs: list[OrderLeg] = Field(default_factory=list)
    vs_mid: float | None = None
    vs_touch: float | None = None


class CondorLegFill(Domain):
    """One leg of a filled condor, with the NBBO it crossed."""

    symbol: str
    side: str
    signed_qty: int
    fill_price: float | None = None
    bid: float | None = None
    ask: float | None = None


class CondorFill(Domain):
    """A submitted condor and what happened to it.

    `FillRecord` cannot carry this: its `NetQuote` has a `short` and a `long`, which is a vertical.
    A condor crosses four legs and the per-leg prices are the thing worth keeping -- the fill probe
    exists to find out whether all four clear at one limit, and an aggregate would hide the answer.
    """

    ok: bool
    filled: bool = False
    error: str | None = None
    order_id: str | None = None
    status: str | None = None
    underlying: str
    expiry: datetime.date
    contracts: int
    limit_price: float
    credit_at_mid: float
    submitted_at: str
    filled_at: str | None = None
    fill: float | None = None
    legs: list[CondorLegFill] = Field(default_factory=list)
    vetoes: list[str] = Field(default_factory=list)

    @property
    def vs_mid(self) -> float | None:
        """Positive is price improvement: we collected more than the mid.

        `fill` comes back as a net price, negative for a credit, so it is compared on magnitude.
        """
        return None if self.fill is None else round(abs(self.fill) - self.credit_at_mid, 4)
