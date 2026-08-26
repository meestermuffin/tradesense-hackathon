"""The one data-access boundary.

Two implementations sit behind it. `FileFeatureSource` reads what is committed in `data/` and is
the path everyone who clones this repo is on. `AlpacaFeatureSource` reads the API and is how the
committed files get produced in the first place.

Nothing above this interface may know which one it has.

**Only `FileFeatureSource` implements this today.** The second implementation was meant to abstract
historical option quotes, and those do not exist -- Alpaca serves none and the project measured that
directly. So the live path uses `AlpacaClient` and bypasses this deliberately, rather than wrapping
a client in an interface that would abstract nothing.

What this boundary does earn: every measurement runs from committed data with no credentials, which
is what lets anyone reproduce the results on a fresh clone.
"""

from abc import ABC, abstractmethod


class FeatureSource(ABC):
    @abstractmethod
    def symbols(self):
        """Universe available from this source."""

    @abstractmethod
    def closes(self, symbol):
        """{'YYYY-MM-DD': close} for the underlying."""

    @abstractmethod
    def iv_series(self, symbol):
        """[(day, iv)] in chronological order, trailing-only by construction."""
