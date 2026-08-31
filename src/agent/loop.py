"""The trading loop: what the agent decides, and what it is structurally prevented from deciding.

**The model never expresses a price.** It emits a `CondorRequest` — underlying, expiry, short
delta, wing width, contracts, and a written rationale. `submit_condor` solves the strikes, prices
the structure and computes the net limit itself. That removes sign inversion from the model's reach
rather than catching it downstream, which matters because `limit_price` on a multi-leg order is a
NET price where negative means credit, and inverting it does not raise.

Two decisions carry registered thresholds and both are here rather than in a prompt:

**The ladder** is declared data. Monday opens two tranches, Tuesday offers one conditional, and
Wednesday and Thursday open nothing. The Wednesday redeploy and a Monday leg into Sep 1 were both
cut on gamma — net structure gamma is 0.0822 at 1 DTE against 0.0438 at 2, a 1.88x gap — and
nothing expires after the Thursday close, because equity is scored there and a later expiry is
marked rather than settled.

**The Tuesday gate** is two conditions read on the morning, not decided in advance. Measured EV per
contract is −$38 to −$47 unconditional, +$21 to +$34 conditioned on calm entry IV at a mid fill, and
+$1 to +$14 at touch-ish fills. The sign lives on the fill and the regime, so the entry waits for
both to be known. If either fails the book runs at two tranches and the remaining budget goes
unrisked, which is the correct outcome rather than a shortfall.

State is never trusted from disk. Every wake re-reads positions and account from the broker and
reconciles, so the process can die at any point and restart correct.
"""

from __future__ import annotations

import dataclasses
import datetime

from ..options.condor import (
    BookState,
    CondorPlan,
    CondorRequest,
    Veto,
    build_plan,
    validate,
)

# Registered thresholds. See .claude/private/2026-08-30-spy-condor-ladder-plan.md §4.
FILL_FLOOR = -0.05
"""Monday's 4-leg fill must clear at mid − 0.05 or better."""

IV_CEILING = 0.16
"""Live IV at Tuesday 09:35 must be at or below this."""

SCORED_CLOSE = datetime.date(2026, 9, 3)
"""Equity is measured at this close. Nothing may expire after it."""

LAST_ENTRY = datetime.date(2026, 9, 2)
"""Guardrail #8. With the ladder fully placed by Tuesday this never binds, but it stays as a
backstop against an entry that could not expire inside the window."""


@dataclasses.dataclass(frozen=True)
class TrancheSpec:
    """One entry in the ladder. Declared, not derived — it is a registered decision."""

    session: datetime.date
    expiry: datetime.date
    fraction: float
    conditional: bool = False
    note: str = ""

    @property
    def dte(self) -> int:
        return (self.expiry - self.session).days


LADDER: tuple[TrancheSpec, ...] = (
    TrancheSpec(
        session=datetime.date(2026, 8, 31),
        expiry=datetime.date(2026, 9, 2),
        fraction=1 / 3,
        note="tranche 1, 2 DTE, committed",
    ),
    TrancheSpec(
        session=datetime.date(2026, 8, 31),
        expiry=datetime.date(2026, 9, 3),
        fraction=1 / 3,
        note="tranche 2, 3 DTE, committed",
    ),
    TrancheSpec(
        session=datetime.date(2026, 9, 1),
        expiry=datetime.date(2026, 9, 3),
        fraction=1 / 3,
        conditional=True,
        note="tranche 3, 2 DTE, gated on Monday's fill and Tuesday's IV",
    ),
)


def tranches_for(session: datetime.date) -> list[TrancheSpec]:
    """The tranches this session may open. Empty is a valid and common answer."""
    return [t for t in LADDER if t.session == session]


def tuesday_gate(fill_vs_mid: float | None, live_iv: float | None) -> tuple[bool, str]:
    """Both registered conditions, evaluated together.

    Returns `(open, why_not)`. Every failing condition is named, not just the first — a caller who
    fixes one and retries should not discover the second on the next attempt.

    A missing input closes the gate. Absence is not permission: no fill means the probe never
    resolved, and entering on an unmeasured fill is the thing the gate exists to prevent.
    """
    reasons = []
    if fill_vs_mid is None:
        reasons.append("no Monday fill recorded — the probe did not resolve")
    elif fill_vs_mid < FILL_FLOOR:
        reasons.append(
            f"Monday's fill came in {fill_vs_mid:+.3f} against mid, below the {FILL_FLOOR:+.2f} "
            f"floor; EV at touch-ish fills is +$1 to +$14 per contract"
        )
    if live_iv is None:
        reasons.append("no live IV")
    elif live_iv > IV_CEILING:
        reasons.append(
            f"IV {live_iv:.3f} over the {IV_CEILING:.2f} ceiling; EV is negative unconditional "
            f"and positive only in a calm regime"
        )
    return (not reasons), "; ".join(reasons)


def _is_option(row: dict) -> bool:
    return "option" in str(row.get("asset_class", "")).lower()


def _spread_key(symbol: str) -> str:
    """Group legs into the structure they belong to: underlying root plus expiry.

    Four legs is one condor. Counting legs instead would trip the position cap after a single
    entry and refuse everything afterwards.
    """
    import re

    m = re.match(r"^([A-Z]{1,6})(\d{6})", symbol or "")
    return f"{m.group(1)}{m.group(2)}" if m else (symbol or "")


def book_state(
    account: dict,
    positions: list[dict],
    high_water: float,
    open_defined_risk: float,
) -> BookState:
    """Build the validator's view of the world from raw broker payloads.

    Raw dicts, not `src.models.Position` — that model discards `asset_class`, and without it an
    equity holding would be counted as part of the options book.
    """
    equity = float(account.get("equity") or 0.0)
    opts = [p for p in positions or [] if _is_option(p)]
    spreads = {_spread_key(p.get("symbol", "")) for p in opts}
    return BookState(
        account_number=str(account.get("account_number") or ""),
        equity=equity,
        # A peak below spot would make drawdown read negative, so the running peak includes now.
        high_water=max(float(high_water or 0.0), equity),
        cash=float(account.get("cash") or 0.0),
        open_positions=len(spreads),
        open_defined_risk=float(open_defined_risk or 0.0),
        breaches=0,
    )


@dataclasses.dataclass(frozen=True)
class Step:
    """One scheduled action in a session. `at` is local exchange time."""

    name: str
    at: datetime.time
    note: str = ""


@dataclasses.dataclass(frozen=True)
class SessionPlan:
    """What a given session does, in order.

    Two orderings here are not stylistic and are asserted in tests:

    **markwatch starts before anything is entered.** Quotes do not exist after the fact on this
    account, so a collector brought up after the first order leaves the mark-drift question
    unanswerable for the whole window -- and that question decides whether the scored equity number
    is a price we could actually have got.

    **The fill probe runs before any sized entry.** Registered in
    `docs/pending/condor-fill-realism.md`: one lot, one condor, and the result decides whether the
    book runs 4-leg or falls back to paired verticals. Sizing into an unmeasured fill is what the
    probe exists to prevent.
    """

    session: datetime.date
    steps: tuple[Step, ...]

    @classmethod
    def for_session(cls, day: datetime.date) -> SessionPlan:
        entering = bool(tranches_for(day))
        expiring = day in {t.expiry for t in LADDER}
        if not entering and not expiring:
            return cls(session=day, steps=())

        steps: list[Step] = [
            Step(
                "start_markwatch",
                datetime.time(9, 25),
                "before anything else: uncaptured quotes are unrecoverable",
            ),
            Step("observe", datetime.time(9, 30), "re-read the broker; local state is a cache"),
        ]
        if entering:
            steps.append(
                Step(
                    "solve_strikes",
                    datetime.time(9, 35),
                    "live spot and BS-inverted IV; this account serves no IV",
                )
            )
            if day == LADDER[0].session:
                steps.append(
                    Step(
                        "fill_probe",
                        datetime.time(9, 45),
                        "one lot; decides condors vs paired verticals",
                    )
                )
            if any(t.conditional for t in tranches_for(day)):
                steps.append(
                    Step(
                        "evaluate_gate",
                        datetime.time(9, 50),
                        "Monday's fill and today's IV against the registered thresholds",
                    )
                )
            steps.append(Step("enter_tranches", datetime.time(10, 0), "validate, then submit"))
        if expiring:
            steps.append(
                Step(
                    "pin_check",
                    datetime.time(15, 15),
                    "spot inside a wing means assignment; ITM settles T+1",
                )
            )
        steps.append(Step("monitor", datetime.time(16, 0), "spot only; the chain is not polled"))
        return cls(session=day, steps=tuple(steps))


@dataclasses.dataclass
class Decision:
    """One tranche, and what became of it. A skip is a result, not an absence."""

    spec: TrancheSpec
    plan: CondorPlan | None = None
    vetoes: list[str] = dataclasses.field(default_factory=list)
    skipped: bool = False
    reason: str = ""
    fill = None


class AgentLoop:
    """Orchestration. Holds no pricing logic and names no limit price.

    `client` is this repo's `AlpacaClient`; `recorder` is a markwatch `Recorder` when journalling.
    Both are injected so the loop is testable without a network.
    """

    def __init__(
        self,
        client,
        recorder=None,
        dry_run: bool = True,
        expected_account: str | None = None,
        collector_running: bool = False,
        limits=None,
        short_delta: float = 0.20,
        wing_width: float = 5.0,
        iv: float = 0.127,
        cash_floor: float = 35_000.0,
    ):
        from ..universe import CONDOR_LIMITS

        self.client = client
        self.recorder = recorder
        self.dry_run = dry_run
        self.expected_account = expected_account
        self.collector_running = collector_running
        self.limits = limits or CONDOR_LIMITS
        self.short_delta = short_delta
        self.wing_width = wing_width
        self.iv = iv
        self.cash_floor = cash_floor
        # Planning figure for sizing only. The real credit comes from the chain at build time.
        self.iv_credit_guess = 1.25

    def observe(self, high_water: float, open_defined_risk: float = 0.0) -> BookState:
        """Re-read the world. Never reads local state — the broker is the only source of truth."""
        acct = self.client.request("GET", self.client.trade_host, "/v2/account")
        pos = self.client.request("GET", self.client.trade_host, "/v2/positions")
        return book_state(acct, pos, high_water, open_defined_risk)

    def tick(
        self,
        session: datetime.date,
        high_water: float,
        fill_vs_mid: float | None = None,
        live_iv: float | None = None,
        open_defined_risk: float = 0.0,
        quotes: dict | None = None,
        spot: float | None = None,
        iv: float | None = None,
    ) -> list[Decision]:
        """One wake. Returns a Decision per tranche this session may open.

        Order of operations is deliberate. The collector check comes first, because markwatch has
        to be capturing before any order exists: there is no historical options quote endpoint on
        this account, so a fill placed before it starts can never be reconciled against the NBBO it
        crossed. Refusing is the only safe answer, and it refuses loudly.
        """
        specs = tranches_for(session)
        if not specs:
            return []

        if not self.dry_run and not self.collector_running:
            raise RuntimeError(
                "markwatch collector is not running. Quotes do not exist after the fact on this "
                "account, so an order placed now is unreconcilable forever. Start it first."
            )

        state = self.observe(high_water, open_defined_risk)

        # The account check comes before any plan is built, not after. Trading the rehearsal book
        # instead of the judged one is the only error here that produces no signal at all, and a
        # chain or quote problem must never be able to mask it by short-circuiting first.
        want = self.expected_account or state.account_number
        if state.account_number != want:
            v = Veto(
                rule="10_account",
                reason=(
                    f"credentials resolve to {state.account_number}, expected {want}. "
                    f"Trading the wrong book is silent and unrecoverable."
                ),
            )
            return [Decision(spec=s_, vetoes=[str(v)], reason=v.reason) for s_ in specs]

        spot = spot if spot is not None else self.client.stock_closes_latest(["SPY"])["SPY"]
        out: list[Decision] = []

        for spec in specs:
            if spec.conditional:
                ok, why = tuesday_gate(fill_vs_mid, live_iv)
                if not ok:
                    out.append(Decision(spec=spec, skipped=True, reason=why))
                    continue

            use_iv = iv if iv is not None else self.iv

            def _build(n, _spec=spec, _iv=use_iv):
                return build_plan(
                    CondorRequest(
                        underlying="SPY",
                        expiry=_spec.expiry,
                        short_delta=self.short_delta,
                        wing_width=self.wing_width,
                        contracts=n,
                        rationale=_spec.note,
                    ),
                    spot,
                    _iv,
                    quotes or {},
                    as_of=session,
                    grid=1.0,
                )

            # Price one contract first, then size off the credit the chain actually gives.
            # Sizing from an assumed credit is how a tranche ends up over its cap by rounding.
            probe = _build(1)
            if isinstance(probe, Veto):
                out.append(Decision(spec=spec, vetoes=[str(probe)], reason=probe.reason))
                continue

            built = _build(self._contracts(state, spec, probe.max_loss_per_contract))
            if isinstance(built, Veto):
                out.append(Decision(spec=spec, vetoes=[str(built)], reason=built.reason))
                continue

            vetoes = validate(
                built,
                state,
                self.limits,
                expected_account=self.expected_account or state.account_number,
                last_entry=LAST_ENTRY,
                max_expiry=SCORED_CLOSE,
                cash_floor=self.cash_floor,
                as_of=session,
            )
            out.append(Decision(spec=spec, plan=built, vetoes=[str(v) for v in vetoes]))

        return out

    def _contracts(self, state: BookState, spec: TrancheSpec, per_contract: float) -> int:
        """Contracts for this tranche, bounded by BOTH caps.

        The per-position cap alone is not enough. Three tranches at 6% each come to 18% against a
        16% book, so sizing on the position cap lets Monday consume the budget Tuesday's
        conditional tranche needs -- and the third is then refused on book risk after the first two
        are already on, which is the worst moment to find out.

        Each tranche gets its registered share of the book as well, and the smaller bound wins.
        Rounded down: one contract over the cap is refused outright by the validator.
        """
        if per_contract <= 0:
            return 1
        by_position = state.equity * self.limits.max_loss_per_position_pct
        by_book = state.equity * self.limits.max_total_defined_risk_pct * spec.fraction
        return max(1, int(min(by_position, by_book) // per_contract))
