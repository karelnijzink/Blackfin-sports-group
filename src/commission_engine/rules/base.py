"""The commission rule contract.

A rule is data plus one function: gross in, commission out, both Decimal.
Rules never round — 2dp is a rendering concern — and never touch I/O, so a
new client's logic is a small pure class that the rest of the engine can
treat as a black box.
"""

from decimal import Decimal
from typing import Protocol, runtime_checkable


@runtime_checkable
class CommissionRule(Protocol):
    def commission(self, gross: Decimal) -> Decimal:
        """Commission earned on a single deal's gross amount."""
        ...

    def describe(self) -> str:
        """One plain-language line for the report, e.g. 'flat 10% of gross'."""
        ...
