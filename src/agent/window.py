"""Refusing to act on a wake-up that arrived late.

launchd does not skip a missed job -- it runs it when the machine next wakes. For a job whose whole
meaning is the moment it fires, that is worse than not running: a 10:00 entry placed at 14:00 is a
different trade, priced off a different book, and nothing in the order says it was late.

So every scheduled entry point states the window it is valid in, and refuses outside it. The
refusal is the correct outcome and is recorded as one.
"""

import datetime

# A market-order window is minutes wide, not hours. Ten is enough to absorb a slow start and a
# retry; past that, the quotes the decision was made against have moved.
DEFAULT_GRACE_MINUTES = 10


def within(
    target: datetime.time,
    now: datetime.datetime | None = None,
    grace_minutes: int = DEFAULT_GRACE_MINUTES,
) -> tuple[bool, str]:
    """Is `now` inside [target, target + grace]? Returns (ok, the reason either way).

    Early is refused as well as late. A job that fires before its target is a misconfigured plist,
    and placing anyway would hide the misconfiguration behind a fill.
    """
    now = now or datetime.datetime.now()
    t = datetime.datetime.combine(now.date(), target)
    delta = (now - t).total_seconds() / 60.0
    if delta < 0:
        return False, f"{now:%H:%M:%S} is {-delta:.0f} min BEFORE the {target:%H:%M} window"
    if delta > grace_minutes:
        return False, (
            f"{now:%H:%M:%S} is {delta:.0f} min past the {target:%H:%M} window "
            f"(grace {grace_minutes} min). A late wake is not a trading signal."
        )
    return True, f"{now:%H:%M:%S}, {delta:.0f} min into the {target:%H:%M} window"


def parse(hhmm: str) -> datetime.time:
    h, m = hhmm.split(":")
    return datetime.time(int(h), int(m))
