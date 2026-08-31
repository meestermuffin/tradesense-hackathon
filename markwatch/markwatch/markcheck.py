"""Is the scored equity number a price you could actually get?

The hackathon scores broker equity at one instant. Broker equity contains a
*mark* for every open position. A mark is an estimate, not money. This module
measures the gap between that estimate and what the book would actually
liquidate for at the touch.

Three numbers per snapshot:

    broker    -- what the broker says the position is worth
    mid       -- value at the midpoint of the NBBO (a price nobody trades at)
    exec      -- value if you closed right now: sell longs at bid, buy back
                 shorts at ask

The diagnostic that matters:

    broker ~= mid   ->  the broker marks at mid, and the scored number
                        overstates by the full cost of crossing the spread on
                        every leg. On a 4-leg condor that is four crossings.
    broker ~= exec  ->  the mark is honest.

Discipline carried over from a previous project where a paper ledger read
+$22,737 and executable prices read -10.58% on the same trades:

  * A quote captured too far from the sample instant is `stale`, not a price.
    Negative ages (host clock behind the exchange) are stale too -- the guard
    fails closed rather than silently switching itself off.
  * Priceability is decided PER LEG, because it is directional: closing a long
    needs a bid, closing a short needs an ask. A zero bid on a long wing is a
    real, exactly-known value (worthless), not missing data.
  * Whatever still cannot be priced is reported as its own rate AND its broker
    mark is carried separately, so the headline gap is explicitly a LOWER
    BOUND rather than an average over the legs that happened to quote. The
    dropped legs are not random: a bid-less far-OTM wing is exactly what a
    mid-marking broker overstates most, so dropping it flatters the broker.
  * Coverage is measured by exposure as well as by leg count. Nine $10 wings
    and one $5,000 short is not 90% covered in any sense that matters.

MULTIPLIER: option contracts are per-share prices on 100 shares.
"""

from typing import Any, Dict, List, Optional

MULTIPLIER = 100

OK = "ok"
STALE = "stale"
UNQUOTABLE = "unquotable"

# A quote sampled more than this many seconds from the snapshot instant
# describes a different moment. Record it, do not price with it.
DEFAULT_FRESHNESS_S = 15.0

# Clock jitter allowance. Beyond this into the future the host clock is wrong
# and every freshness check it makes is meaningless.
CLOCK_SKEW_TOLERANCE_S = 2.0

# Below this share of legs (and of exposure) cleanly priced, no verdict.
DEFAULT_COVERAGE_FLOOR = 0.70


def _age_ok(age_s: Optional[float], freshness_s: float) -> bool:
    if age_s is None:
        return False
    if age_s > freshness_s:
        return False
    if age_s < -CLOCK_SKEW_TOLERANCE_S:
        return False          # host clock behind the exchange; fail closed
    return True


def classify_quote(
    bid: Optional[float],
    ask: Optional[float],
    age_s: Optional[float],
    freshness_s: float = DEFAULT_FRESHNESS_S,
) -> str:
    """Two-sided quote sanity, direction-agnostic.

    Used for reporting and for the fill path. Valuation uses `classify_leg`,
    which knows which side of the book the position actually needs.
    """
    if bid is None or ask is None:
        return UNQUOTABLE
    if bid <= 0 or ask <= 0:
        return UNQUOTABLE
    if ask < bid:
        return UNQUOTABLE
    return OK if _age_ok(age_s, freshness_s) else STALE


def classify_leg(
    signed_qty: int,
    bid: Optional[float],
    ask: Optional[float],
    age_s: Optional[float],
    freshness_s: float = DEFAULT_FRESHNESS_S,
) -> str:
    """Can THIS leg be valued at what it would liquidate for?

    Closing a long sells into the bid; closing a short buys at the ask. A leg
    only needs the side it would actually trade against. A zero bid on a long
    is a price (worthless), not a gap in the data -- treating it as missing is
    what biases the whole measurement.
    """
    if bid is not None and ask is not None and ask < bid:
        return UNQUOTABLE                      # crossed book, not a market
    needed = bid if signed_qty >= 0 else ask
    if needed is None or needed < 0:
        return UNQUOTABLE
    return OK if _age_ok(age_s, freshness_s) else STALE


def leg_values(signed_qty: int, bid: Optional[float], ask: Optional[float]) -> Dict[str, Any]:
    """Value of one leg three ways, signed from the account's perspective.

    Closing a long means selling into the bid. Closing a short means buying
    back at the ask. That asymmetry is the entire cost being measured, so it
    must not be collapsed into a single price.

    Mid is only defined with both sides; exec needs only the side that trades.
    """
    exec_px = bid if signed_qty >= 0 else ask
    if exec_px is None:
        raise ValueError("leg is not priceable on the side it would trade")
    mid = ((bid + ask) / 2.0) if (bid is not None and ask is not None) else None
    return {
        "mid_value": (signed_qty * mid * MULTIPLIER) if mid is not None else None,
        "exec_value": signed_qty * exec_px * MULTIPLIER,
        "spread": (ask - bid) if (bid is not None and ask is not None) else None,
        "mid_px": mid,
        "exec_px": exec_px,
    }


def _exposure(row: Dict[str, Any]) -> float:
    """Rough size of a leg, for weighting coverage. Broker mark preferred."""
    bm = row.get("broker_mark")
    if bm is not None:
        try:
            return abs(float(bm))
        except (TypeError, ValueError):
            pass
    bid, ask = row.get("bid"), row.get("ask")
    px = None
    if bid is not None and ask is not None:
        px = (bid + ask) / 2.0
    elif bid is not None:
        px = bid
    elif ask is not None:
        px = ask
    if px is None:
        return 0.0
    return abs(int(row.get("signed_qty", 0))) * px * MULTIPLIER


def evaluate_snapshot(
    rows: List[Dict[str, Any]],
    freshness_s: float = DEFAULT_FRESHNESS_S,
    coverage_floor: float = DEFAULT_COVERAGE_FLOOR,
) -> Dict[str, Any]:
    """Compare broker marks against executable value for one sampling pass.

    `rows` are leg dicts: symbol, signed_qty, broker_mark, bid, ask, quote_age_s.
    Returns a verdict dict. Never raises on bad quotes; classifies them.
    """
    total = len(rows)
    clean: List[Dict[str, Any]] = []
    stale: List[Dict[str, Any]] = []
    unquotable: List[Dict[str, Any]] = []

    for r in rows:
        r = dict(r)
        # A caller-supplied status is a two-sided verdict; re-derive per leg so
        # a long wing with a zero bid is still priced.
        status = classify_leg(int(r.get("signed_qty", 0)), r.get("bid"), r.get("ask"),
                              r.get("quote_age_s"), freshness_s)
        r["status"] = status
        if status == OK:
            clean.append(r)
        elif status == STALE:
            stale.append(r)
        else:
            unquotable.append(r)

    excluded = stale + unquotable
    exp_all = sum(_exposure(r) for r in rows)
    exp_clean = sum(_exposure(r) for r in clean)

    def _marks(items):
        s = 0.0
        for it in items:
            bm = it.get("broker_mark")
            if bm is not None:
                try:
                    s += float(bm)
                except (TypeError, ValueError):
                    pass
        return s

    leg_coverage = (len(clean) / total) if total else 0.0
    value_coverage = (exp_clean / exp_all) if exp_all > 0 else (1.0 if total == 0 else 0.0)

    result: Dict[str, Any] = {
        "legs_total": total,
        "legs_clean": len(clean),
        "legs_stale": len(stale),
        "legs_unquotable": len(unquotable),
        "unquotable_rate": (len(unquotable) / total) if total else 0.0,
        "unquotable_symbols": [r.get("symbol") for r in unquotable],
        "stale_symbols": [r.get("symbol") for r in stale],
        "coverage": leg_coverage,
        "value_coverage": value_coverage,
        # Broker mark sitting on legs we could not price. The headline gap
        # says nothing about this money.
        "broker_value_excluded": _marks(excluded),
        "verdict": None,
        "broker_value": None,
        "mid_value": None,
        "exec_value": None,
        "broker_minus_exec": None,
        "broker_minus_mid": None,
        "mid_minus_exec": None,
        "marks_at": None,
        "is_lower_bound": bool(excluded),
    }

    if total == 0:
        result["verdict"] = "no open legs"
        return result

    effective_coverage = min(leg_coverage, value_coverage)
    if effective_coverage < coverage_floor:
        result["verdict"] = (
            "insufficient coverage: %.0f%% of legs / %.0f%% of exposure priced, floor is %.0f%%"
            % (leg_coverage * 100, value_coverage * 100, coverage_floor * 100)
        )
        return result

    broker_v = 0.0
    mid_v = 0.0
    exec_v = 0.0
    have_broker = True
    mid_defined = True
    for r in clean:
        v = leg_values(int(r["signed_qty"]), r.get("bid"), r.get("ask"))
        exec_v += v["exec_value"]
        if v["mid_value"] is None:
            mid_defined = False
        else:
            mid_v += v["mid_value"]
        bm = r.get("broker_mark")
        if bm is None:
            have_broker = False
        else:
            broker_v += float(bm)

    result["exec_value"] = exec_v
    if mid_defined:
        result["mid_value"] = mid_v
        result["mid_minus_exec"] = mid_v - exec_v

    if not have_broker:
        result["verdict"] = "broker marks missing on at least one priced leg"
        return result

    result["broker_value"] = broker_v
    result["broker_minus_exec"] = broker_v - exec_v
    if mid_defined:
        result["broker_minus_mid"] = broker_v - mid_v

    if not mid_defined:
        result["marks_at"] = "indeterminate (one-sided book)"
    else:
        d_mid = abs(broker_v - mid_v)
        d_exec = abs(broker_v - exec_v)
        spread_cost = abs(mid_v - exec_v)
        if spread_cost < 1e-9:
            result["marks_at"] = "indeterminate (zero spread)"
        elif d_mid <= d_exec:
            result["marks_at"] = "mid"
        else:
            result["marks_at"] = "executable"

    bound = " (LOWER BOUND: %d of %d legs unpriced, %.2f of broker mark not measured)" % (
        len(excluded), total, result["broker_value_excluded"]) if excluded else ""
    result["verdict"] = (
        "broker marks at %s; scored equity is %+.2f vs liquidation%s"
        % (result["marks_at"], result["broker_minus_exec"], bound)
    )
    return result


def reconcile_fill(
    fill_price: Optional[float],
    side: str,
    bid: Optional[float],
    ask: Optional[float],
) -> Dict[str, Any]:
    """Where inside the NBBO did a fill actually land?

    `side` is the TRADE direction ("buy" / "sell"), not the resulting position.
    This distinction is the whole point: buying back a short to close is a BUY
    and pays the ask. Inferring direction from position sign scores every
    closing fill backwards and reports paid spread as price improvement --
    precisely the flattery this package exists to detect.

    0.0 = we crossed the full spread, 0.5 = mid, 1.0 = price improvement at the
    far touch. Normalised so a buy and a sell mean the same thing.
    """
    s = str(side).strip().lower()
    if s not in ("buy", "sell"):
        return {"position_in_spread": None, "vs_mid": None, "note": "unknown side: %r" % (side,)}
    if fill_price is None or bid is None or ask is None or ask <= bid:
        return {"position_in_spread": None, "vs_mid": None, "note": "unpriceable"}
    mid = (bid + ask) / 2.0
    width = ask - bid
    if s == "buy":
        pos = (ask - fill_price) / width      # paid the ask -> 0.0
        vs_mid = mid - fill_price             # positive = better than mid for us
    else:
        pos = (fill_price - bid) / width      # sold at the bid -> 0.0
        vs_mid = fill_price - mid
    return {"position_in_spread": pos, "vs_mid": vs_mid, "mid": mid, "width": width, "note": "ok"}


def side_for_close(signed_qty: int) -> str:
    """The trade that flattens a position: sell a long, buy back a short."""
    return "sell" if signed_qty >= 0 else "buy"


def format_report(result: Dict[str, Any]) -> str:
    lines = []
    lines.append("MARK QUALITY")
    lines.append("  legs            %d (priced %d / stale %d / unquotable %d)"
                 % (result["legs_total"], result["legs_clean"],
                    result["legs_stale"], result["legs_unquotable"]))
    lines.append("  coverage        %.0f%% of legs, %.0f%% of exposure"
                 % (result["coverage"] * 100, result.get("value_coverage", 0.0) * 100))
    if result["unquotable_symbols"]:
        lines.append("  unquotable      %.0f%%  %s"
                     % (result["unquotable_rate"] * 100,
                        ", ".join(str(s) for s in result["unquotable_symbols"])))
    if result.get("feed"):
        lines.append("  feed            %s%s" % (
            result["feed"],
            "   <- derived quotes, not true OPRA NBBO" if result["feed"] != "opra" else ""))
    if result["broker_value"] is not None:
        lines.append("  broker value    %12.2f" % result["broker_value"])
        if result["mid_value"] is not None:
            lines.append("  mid value       %12.2f" % result["mid_value"])
        lines.append("  exec value      %12.2f" % result["exec_value"])
        lines.append("  broker - exec   %12.2f   <- overstatement in the score"
                     % result["broker_minus_exec"])
        if result["broker_minus_mid"] is not None:
            lines.append("  broker - mid    %12.2f" % result["broker_minus_mid"])
        if result.get("broker_value_excluded"):
            lines.append("  NOT MEASURED    %12.2f   of broker mark on unpriced legs"
                         % result["broker_value_excluded"])
    lines.append("  verdict         %s" % result["verdict"])
    return "\n".join(lines)
