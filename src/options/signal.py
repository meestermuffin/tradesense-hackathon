"""Rank the universe by IV richness against each name's own history.

The measured result behind this: ranking on the per-name percentile carries rank IC +0.1753
(permutation p 0.0010), while ranking on the raw IV *level* carries -0.1055 — selling whatever
has the highest absolute IV is mildly harmful. The percentile is the signal; the level is not.
See docs/probes/2026-08-26-baseline-ic-RESULTS.md
"""

PCT_WINDOW, PCT_MIN_OBS = 126, 63


def percentile_rank(window, value):
    return 100.0 * sum(1 for v in window if v <= value) / len(window)


def rank_universe(series_by_symbol, as_of=None):
    """series_by_symbol: {symbol: [(day, iv)] chronological}. Returns rows sorted richest first.

    Trailing-only by construction: the window ends the session *before* the one being scored, so
    the value being ranked is never inside its own reference window.
    """
    out = []
    for sym, series in series_by_symbol.items():
        if not series:
            continue
        rows = [r for r in series if as_of is None or r[0] <= as_of]
        if len(rows) < PCT_MIN_OBS + 1:
            out.append(
                dict(
                    symbol=sym,
                    iv=None,
                    percentile=None,
                    obs=len(rows),
                    eligible=False,
                    reason="insufficient history",
                )
            )
            continue
        day, iv = rows[-1]
        window = [v for _, v in rows[-(PCT_WINDOW + 1) : -1]]
        if len(window) < PCT_MIN_OBS:
            out.append(
                dict(
                    symbol=sym,
                    iv=iv,
                    percentile=None,
                    obs=len(window),
                    eligible=False,
                    reason="window below minimum",
                )
            )
            continue
        out.append(
            dict(
                symbol=sym,
                day=day,
                iv=iv,
                percentile=percentile_rank(window, iv),
                obs=len(window),
                eligible=True,
                reason=None,
            )
        )
    ranked = [r for r in out if r["eligible"]]
    ranked.sort(key=lambda r: r["percentile"], reverse=True)
    return ranked + [r for r in out if not r["eligible"]]
