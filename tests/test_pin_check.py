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


# ---- overlapping structures at one expiry


# The real 3 Sep book: tranche 2 at 753/758P 772/777C, tranche 3 at 750/755P 768/773C.
# Same expiry, so proximity cannot tell the two structures apart.
OVERLAPPING = [
    (750.0, "P", 13),
    (753.0, "P", 13),
    (755.0, "P", -13),
    (758.0, "P", -13),
    (768.0, "C", -13),
    (772.0, "C", -13),
    (773.0, "C", 13),
    (777.0, "C", 13),
]


def test_a_short_is_not_covered_by_another_structures_wing():
    """The bug that made the live check report `watch` while a short sat unprotected.

    At SPY 773.85 the 772 call is in the money. Its own wing is 777, which is not. That is
    assignment without the offset -- severity 2. `_wing_for` instead took 773, the nearest long
    above, which belongs to the other structure, concluded the short was past its wing, and
    downgraded to `watch`.

    Understating risk in exactly the circumstance the check exists to flag.
    """
    sev, msg = assess(773.85, OVERLAPPING)
    assert sev == 2, msg
    assert "IN THE MONEY" in msg


def test_each_long_can_only_cover_one_short():
    """773 protects 768 or 772, not both. Reusing it prices protection we do not own."""
    sev, msg = assess(773.85, OVERLAPPING)
    assert msg.count("fully defined") <= 1, msg


def test_a_genuinely_covered_short_still_reads_as_defined():
    """Past its own wing, the loss is the one we priced. Do not escalate that."""
    sev, msg = assess(779.0, OVERLAPPING)  # through 777, both spreads fully in the money
    assert sev == 1, msg
    assert "fully defined" in msg


def test_a_single_structure_is_unaffected():
    """The pairing must not change behaviour on a book holding one condor."""
    sev, _ = assess(765.0, CONDOR)
    assert sev == 0
    assert assess(758.0, CONDOR)[0] == 2
