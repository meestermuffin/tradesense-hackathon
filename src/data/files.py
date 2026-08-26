"""File-backed source: reads the CSV committed in data/. Standard library only."""

import csv
import gzip

from .source import FeatureSource


class FileFeatureSource(FeatureSource):
    def __init__(self, path):
        self.path = path
        self._rows = None

    def _load(self):
        if self._rows is None:
            op = gzip.open if self.path.endswith(".gz") else open
            with op(self.path, "rt", newline="") as fh:
                self._rows = list(csv.DictReader(fh))
        return self._rows

    def symbols(self):
        return sorted({r["symbol"] for r in self._load()})

    def closes(self, symbol):
        return {r["day"]: float(r["spot"]) for r in self._load() if r["symbol"] == symbol}

    def iv_series(self, symbol):
        return [
            (r["day"], float(r["iv"])) for r in self._load() if r["symbol"] == symbol and r["iv"]
        ]

    def rows(self, symbol=None):
        return [r for r in self._load() if symbol is None or r["symbol"] == symbol]
