"""Pin-risk classification on an expiry day.

The dangerous zone is narrow and easy to get backwards: a short in the money whose wing is NOT
in the money gets assigned without the offset. Past the wing, the loss is the defined one we
already priced. These tests pin which is which.
"""

import datetime as dt

from scripts.pin_check import assess, structures


class P:
    def __init__(self, symbol, qty):
        self.symbol, self.qty = symbol, qty


CONDOR = [  # 754/759 put spread, 771/776 call spread
    (754.0, "P", 13),
    (759.0, "P", -13),
    (771.0, "C", -13),
    (776.0, "C", 13),
]


def test_spot_between_the_shorts_is_clear():
    sev, msg = assess(765.0, CONDOR)
    assert sev == 0, msg


def test_a_short_put_in_the_money_needs_a_human():
    """758 is through the 759 short and short of the 754 wing — assignment is not offset."""
    sev, msg = assess(758.0, CONDOR)
    assert sev == 2
    assert "IN THE MONEY" in msg


def test_a_short_call_in_the_money_needs_a_human():
    sev, msg = assess(772.0, CONDOR)
    assert sev == 2 and "IN THE MONEY" in msg


def test_past_the_wing_is_the_defined_loss_not_an_emergency():
    """Beyond the long strike both legs are ITM and the spread is worth its width.

    That is the defined loss we already priced, not an emergency.
    """
    sev, msg = assess(750.0, CONDOR)
    assert sev == 1, msg
    assert "fully defined" in msg


def test_approaching_a_short_trips_the_guard_before_it_is_breached():
    sev, msg = assess(769.5, CONDOR)  # 1.5 from the 771 call
    assert sev == 2
    assert "inside the" in msg


def test_the_guard_width_is_configurable():
    assert assess(769.5, CONDOR, warn=1.0)[0] == 0
    assert assess(769.5, CONDOR, warn=3.0)[0] == 2


def test_legs_are_grouped_by_expiry_not_by_order():
    """Assignment does not care which ticket a leg arrived on."""
    got = structures(
        [
            P("SPY260902P00759000", -13),
            P("SPY260902P00754000", 13),
            P("SPY260903C00768000", -13),
        ]
    )
    assert set(got) == {dt.date(2026, 9, 2), dt.date(2026, 9, 3)}
    assert len(got[dt.date(2026, 9, 2)]) == 2


def test_non_option_symbols_are_ignored():
    assert structures([P("SPY", 100)]) == {}


def test_no_shorts_is_not_a_risk():
    assert assess(765.0, [(754.0, "P", 13)])[0] == 0
