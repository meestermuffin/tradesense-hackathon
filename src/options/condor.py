"""`submit_condor` — the only path from a model's decision to a live order.

**The model never expresses a price.** It asks for an underlying, an expiry, a short delta and a
width; this module solves the strikes, prices the structure, and computes the net limit itself.
That removes sign inversion from the model's reach rather than catching it downstream, which
matters because `limit_price` on a multi-leg order is a NET price where negative means credit, and
inverting it does not raise — it places a real order at the wrong price.

Every guardrail lives here, inside the tool, enforced by schema and process boundary rather than by
prompt instruction. A veto returns a structured reason the model can read and respond to, which is
better trace material than a silent rejection.

The rules and where they came from:

  1  net credit sign          the worst failure mode this API offers
  2  credit >= floor          below it the risk/reward does not justify the trade
  3  short strike in band     delta, cross-checked against expected move -- see `structure.py`
  4  per-position cap         registered in CONDOR_LIMITS
  5  book cap                 registered in CONDOR_LIMITS
  6  expiry on or before      equity is scored EOD Thu 3 Sep; later expiries are marked, not settled
  7  cash floor               assignment handling
  8  entry deadline           no new risk that cannot expire inside the window
  9  kill switch              mark-to-market drawdown OR breach count
 10  account assertion        trading the wrong book is the only silent error here
 11  limits registered        refuses to run against unregistered limits
"""

from __future__ import annotations

import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..models import Quote
from .structure import strike_at_delta, verify_delta_em_consistency

CONTRACT_MULTIPLIER = 100


class Veto(BaseModel):
    """A refusal, with the rule that fired. Structured so the journal and the model both read it."""

    model_config = ConfigDict(frozen=True)
    rule: str
    reason: str

    def __str__(self) -> str:
        return f"[{self.rule}] {self.reason}"


class BookState(BaseModel):
    """What the validator needs to know about the world. Read from the broker, never from cache."""

    model_config = ConfigDict(frozen=True)
    account_number: str
    equity: float = Field(gt=0)
    high_water: float = Field(gt=0)
    cash: float = Field(ge=0)
    open_positions: int = Field(ge=0)
    open_defined_risk: float = Field(ge=0)
    breaches: int = Field(0, ge=0)


class CondorRequest(BaseModel):
    """What the model is allowed to ask for. Note what is absent: any price."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    underlying: str
    expiry: datetime.date
    short_delta: float = Field(gt=0.05, lt=0.45)
    wing_width: float = Field(gt=0)
    contracts: int = Field(gt=0)
    rationale: str = Field(min_length=1)
    """Why this trade. Recorded in the journal; a request without one is refused by the schema."""


class CondorPlan(BaseModel):
    """A priced, resolved structure. Constructing one asserts the sign convention."""

    model_config = ConfigDict(frozen=True)
    underlying: str
    expiry: datetime.date
    dte: int
    short_put: float
    long_put: float
    short_call: float
    long_call: float
    credit: float = Field(gt=0)
    credit_at_touch: float
    """What the structure collects if every leg fills at the far side.

    The mid-based credit CANNOT see spread width -- widening a book symmetrically leaves the
    midpoint untouched -- so a floor checked against mid says nothing about execution. This is the
    number that does, and it is the pessimistic bound: shorts sold at bid, longs bought at ask.
    Measured fills clear between the two, better than touch but not reliably at mid.
    """
    wing_width: float = Field(gt=0)
    contracts: int = Field(gt=0)
    limit_price: float
    spot: float
    iv: float
    short_put_delta: float
    short_call_delta: float
    requested_delta: float = Field(gt=0, lt=1)
    """What was asked for. Kept so the delta/expected-move cross-check has its target."""

    @model_validator(mode="after")
    def _sign_and_shape(self) -> CondorPlan:
        if self.limit_price >= 0:
            raise ValueError(
                f"limit_price {self.limit_price:+.2f} is not a credit. On a multi-leg order this "
                f"is a NET price and negative means credit; a positive number here pays to open a "
                f"structure meant to collect."
            )
        if abs(self.limit_price) != round(self.credit, 4):
            raise ValueError(f"limit {self.limit_price} does not match credit {self.credit}")
        if not (self.long_put < self.short_put < self.short_call < self.long_call):
            raise ValueError(
                f"strikes are not a condor: {self.long_put}/{self.short_put}/"
                f"{self.short_call}/{self.long_call}"
            )
        if self.credit >= self.wing_width:
            raise ValueError(
                f"credit {self.credit:.2f} >= width {self.wing_width:g}: max loss would be "
                f"negative, which means a quote is stale or crossed, not that this is free money"
            )
        return self

    @property
    def max_loss_per_contract(self) -> float:
        return (self.wing_width - self.credit) * CONTRACT_MULTIPLIER

    @property
    def defined_risk(self) -> float:
        return self.max_loss_per_contract * self.contracts

    @property
    def credit_pct_of_width(self) -> float:
        return self.credit / self.wing_width

    @property
    def touch_pct_of_width(self) -> float:
        return self.credit_at_touch / self.wing_width

    @property
    def spread_cost(self) -> float:
        """What crossing all four legs costs, as a share of the mid credit."""
        return (self.credit - self.credit_at_touch) / self.credit if self.credit else 1.0


def build_plan(req: CondorRequest, spot: float, iv: float, quotes, as_of=None, rate=0.04, grid=1.0):
    """Resolve a request into a priced plan, or return a Veto explaining why not.

    `quotes` maps strike -> (put Quote, call Quote). The credit is taken from quote midpoints; the
    strikes are solved from delta.
    """
    as_of = as_of or datetime.date.today()
    dte = (req.expiry - as_of).days
    if dte <= 0:
        return Veto(rule="expiry", reason=f"{req.expiry} is not in the future")

    sp = strike_at_delta(spot, iv, dte, req.short_delta, "P", rate, grid)
    sc = strike_at_delta(spot, iv, dte, req.short_delta, "C", rate, grid)
    lp, lc = sp - req.wing_width, sc + req.wing_width

    missing = [k for k in (lp, sp, sc, lc) if k not in quotes]
    if missing:
        return Veto(rule="chain", reason=f"no quote for strikes {missing}")

    def mid(strike, side):
        q: Quote = quotes[strike][0 if side == "P" else 1]
        return None if not q.two_sided else q.mid

    legs = {"sp": mid(sp, "P"), "lp": mid(lp, "P"), "sc": mid(sc, "C"), "lc": mid(lc, "C")}
    if any(v is None for v in legs.values()):
        bad = [k for k, v in legs.items() if v is None]
        return Veto(rule="quote_quality", reason=f"no two-sided quote on {bad}")

    credit = round((legs["sp"] - legs["lp"]) + (legs["sc"] - legs["lc"]), 2)
    if credit <= 0:
        return Veto(rule="structure", reason=f"structure does not credit at mid ({credit:+.2f})")

    # Pessimistic: sell the shorts at bid, buy the longs at ask.
    touch = round(
        (quotes[sp][0].bid - quotes[lp][0].ask) + (quotes[sc][1].bid - quotes[lc][1].ask), 2
    )

    from .iv import greeks

    T = dte / 365.0
    try:
        return CondorPlan(
            underlying=req.underlying,
            expiry=req.expiry,
            dte=dte,
            short_put=sp,
            long_put=lp,
            short_call=sc,
            long_call=lc,
            credit=credit,
            credit_at_touch=touch,
            wing_width=req.wing_width,
            contracts=req.contracts,
            limit_price=-credit,
            spot=spot,
            iv=iv,
            short_put_delta=abs(greeks(spot, sp, T, rate, iv, "P")["delta"]),
            short_call_delta=abs(greeks(spot, sc, T, rate, iv, "C")["delta"]),
            requested_delta=req.short_delta,
        )
    except ValueError as e:
        return Veto(rule="structure", reason=str(e).split("\n")[-1].strip() or str(e))


def validate(
    plan: CondorPlan,
    state: BookState,
    limits,
    *,
    expected_account: str,
    credit_floor=0.18,
    touch_floor=0.15,
    max_crossing_cost=0.25,
    delta_band=(0.18, 0.22),
    last_entry: datetime.date,
    max_expiry: datetime.date,
    cash_floor: float,
    as_of=None,
) -> list[Veto]:
    """Every rule, applied. An empty list means the order may go."""
    as_of = as_of or datetime.date.today()
    v: list[Veto] = []

    if limits.kill_switch_breaches is None:
        v.append(Veto(rule="11_limits", reason="limits carry no breach switch; use CONDOR_LIMITS"))

    if state.account_number != expected_account:
        v.append(
            Veto(
                rule="10_account",
                reason=(
                    f"credentials resolve to {state.account_number}, expected {expected_account}. "
                    f"Trading the wrong book is silent and unrecoverable."
                ),
            )
        )

    drawdown = (state.high_water - state.equity) / state.high_water if state.high_water else 0.0
    if drawdown > limits.kill_switch_drawdown_pct:
        v.append(
            Veto(
                rule="09_kill_switch",
                reason=(
                    f"mark-to-market drawdown {drawdown:.1%} over "
                    f"{limits.kill_switch_drawdown_pct:.0%}"
                ),
            )
        )
    if limits.kill_switch_breaches and state.breaches >= limits.kill_switch_breaches:
        v.append(
            Veto(
                rule="09_kill_switch",
                reason=(f"{state.breaches} breaches, halt at {limits.kill_switch_breaches}"),
            )
        )

    if as_of > last_entry:
        v.append(
            Veto(rule="08_deadline", reason=f"{as_of} is past the entry deadline {last_entry}")
        )

    if state.cash - plan.defined_risk < cash_floor:
        v.append(
            Veto(
                rule="07_cash",
                reason=(
                    f"${state.cash - plan.defined_risk:,.0f} unencumbered after this trade, "
                    f"floor ${cash_floor:,.0f}"
                ),
            )
        )

    if plan.expiry > max_expiry:
        v.append(
            Veto(
                rule="06_expiry",
                reason=(
                    f"expiry {plan.expiry} after {max_expiry}: equity is scored at that "
                    f"close, so a later "
                    f"expiry is marked rather than settled"
                ),
            )
        )

    if state.open_positions >= limits.max_open_positions:
        v.append(
            Veto(
                rule="05_book",
                reason=(f"{state.open_positions} open, cap {limits.max_open_positions}"),
            )
        )
    total = state.open_defined_risk + plan.defined_risk
    if total > state.equity * limits.max_total_defined_risk_pct:
        v.append(
            Veto(
                rule="05_book",
                reason=(
                    f"book risk ${total:,.0f} over {limits.max_total_defined_risk_pct:.0%} of "
                    f"${state.equity:,.0f}"
                ),
            )
        )

    if plan.defined_risk > state.equity * limits.max_loss_per_position_pct:
        v.append(
            Veto(
                rule="04_position",
                reason=(
                    f"${plan.defined_risk:,.0f} over the per-position cap "
                    f"{limits.max_loss_per_position_pct:.0%} of ${state.equity:,.0f}"
                ),
            )
        )

    lo, hi = delta_band
    for name, d in (("put", plan.short_put_delta), ("call", plan.short_call_delta)):
        if not (lo <= d <= hi):
            v.append(
                Veto(
                    rule="03_delta",
                    reason=(f"short {name} delta {d:.3f} outside [{lo:.2f}, {hi:.2f}]"),
                )
            )
    ok, actual, want = verify_delta_em_consistency(
        plan.spot, plan.iv, plan.dte, plan.requested_delta, "P"
    )
    if not ok:
        v.append(
            Veto(
                rule="03_delta",
                reason=(
                    f"strike sits {actual:.2f}xEM where its delta implies {want:.2f}x — "
                    f"the day-count "
                    f"used for expected move and for Black-Scholes have drifted apart"
                ),
            )
        )

    if plan.credit_pct_of_width < credit_floor:
        v.append(
            Veto(
                rule="02_credit",
                reason=(
                    f"credit {plan.credit_pct_of_width:.1%} of width, floor {credit_floor:.0%}"
                ),
            )
        )
    if plan.spread_cost > max_crossing_cost:
        v.append(
            Veto(
                rule="02_credit",
                reason=(
                    f"crossing all four legs gives up {plan.spread_cost:.0%} of the mid credit, "
                    f"cap {max_crossing_cost:.0%}. Measured SPY round trip is ~8% of credit, so "
                    f"this book is several times wider than what we priced against."
                ),
            )
        )
    if plan.touch_pct_of_width < touch_floor:
        v.append(
            Veto(
                rule="02_credit",
                reason=(
                    f"at the touch this collects {plan.touch_pct_of_width:.1%} of width, floor "
                    f"{touch_floor:.0%}. The mid-based floor above cannot see spread width — "
                    f"widening a book symmetrically leaves its midpoint untouched."
                ),
            )
        )

    if plan.limit_price >= 0:
        v.append(Veto(rule="01_sign", reason="limit price is not a credit"))

    return sorted(v, key=lambda x: x.rule)
