"""The traded universe — single source of truth.

Decided 2026-08-26 on measured IV-series quality against criteria registered before any data was
seen. Full derivation: docs/probes/2026-08-26-universe-quality-RESULTS.md

Excluded and why, so neither gets re-added by accident:
  AVGO  17.2% missing days (CONDITIONAL) and reports 2 Sep, inside the judged window
  NFLX  21.2% missing days (CONDITIONAL) and the only name the estimator diagnostic called ambiguous
"""
UNIVERSE = ["SPY", "TSLA", "NVDA", "MSFT", "AAPL", "META", "AMZN", "INTC", "GOOGL", "AMD", "MU"]

EXCLUDED = {
    "AVGO": "coverage CONDITIONAL (17.2% missing); earnings 2026-09-02, inside the window",
    "NFLX": "coverage CONDITIONAL (21.2% missing); estimator diagnostic ambiguous",
}

# 20% total defined risk / 2% per position = 10 concurrent positions, one per name.
# The live risk_config value of 0 and the column default of 5 are both inherited from the
# shelved equity strategy and were never derived for this book.
MAX_OPEN_POSITIONS = 10
MAX_LOSS_PER_POSITION_PCT = 0.02
MAX_TOTAL_DEFINED_RISK_PCT = 0.20
KILL_SWITCH_DRAWDOWN_PCT = 0.05
