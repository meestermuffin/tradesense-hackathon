"""The one data-access boundary.

Two implementations sit behind it. `FileFeatureSource` reads what is committed in `data/` and is
the path everyone who clones this repo is on. `AlpacaFeatureSource` reads the API and is how the
committed files get produced in the first place.

Nothing above this interface may know which one it has.
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
