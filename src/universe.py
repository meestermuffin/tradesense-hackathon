"""The traded universe — single source of truth.

Decided 2026-08-26 on measured IV-series quality against criteria registered before any data was
seen. Full derivation: docs/measurement-log.md

Exclusions and their re-entry conditions are in EXCLUDED below, which is enforced rather than
described.
"""

from .models import RiskLimits

UNIVERSE = ["SPY", "TSLA", "NVDA", "MSFT", "AAPL", "META", "AMZN", "INTC", "GOOGL", "AMD", "MU"]

# Excluded names, and what would have to change for each to come back.
#
# Kept as data rather than prose because it is checked below — a comment cannot stop anyone adding
# a name back, and that is the only failure this is guarding against.
#
# Note the two are not equally settled. NFLX failed on two grounds that both still hold. AVGO failed
# on two grounds, one of which **expires with the judged window**: after 2026-09-04 its earnings
# reason is spent and only the coverage reading remains, which was CONDITIONAL rather than FAIL.
# AVGO is therefore a legitimate candidate for reconsideration after the window, on the same footing
# as NFLX, and that is a measurement question rather than a settled exclusion.
EXCLUDED = {
    "AVGO": {
        "durable": "coverage CONDITIONAL — 17.2% of sessions missing",
        "expires_2026_09_04": "reports 2026-09-02, inside the judged window",
    },
    "NFLX": {
        "durable": "coverage CONDITIONAL — 21.2% missing; and the only name the print-agreement "
        "diagnostic called ambiguous",
    },
}

_overlap = set(UNIVERSE) & set(EXCLUDED)
if _overlap:
    raise ValueError(
        f"{sorted(_overlap)} appears in both UNIVERSE and EXCLUDED. "
        f"Reasons: {[EXCLUDED[n] for n in sorted(_overlap)]}. "
        f"Re-admitting a name needs a measurement, not an edit — see "
        f"docs/measurement-log.md"
    )

# 20% total defined risk / 2% per position = 10 concurrent positions, one per name.
# The live risk_config value of 0 and the column default of 5 are both inherited from the
# shelved equity strategy and were never derived for this book.
#
# Validated on construction, so a limit edited to something incoherent (a negative cap, a
# percentage entered as 20 rather than 0.20) fails at import rather than at the first trade.
LIMITS = RiskLimits(
    max_open_positions=10,
    max_loss_per_position_pct=0.02,
    max_total_defined_risk_pct=0.20,
    kill_switch_drawdown_pct=0.05,
)

MAX_OPEN_POSITIONS = LIMITS.max_open_positions
MAX_LOSS_PER_POSITION_PCT = LIMITS.max_loss_per_position_pct
MAX_TOTAL_DEFINED_RISK_PCT = LIMITS.max_total_defined_risk_pct
KILL_SWITCH_DRAWDOWN_PCT = LIMITS.kill_switch_drawdown_pct
