"""HubSpot API deal source — milestone 3. Interface only.

The adapter will read deals via a read-only private-app token and return the
same LoadResult shape as csv_source, so nothing downstream changes when the
source switches from export files to the live API. Nothing here ever writes
to HubSpot.
"""

from decimal import Decimal

from commission_engine.rules.base import CommissionRule

from .csv_source import DEFAULT_TOLERANCE, LoadResult


def load_hubspot_api(
    portal_id: str,
    rule: CommissionRule,
    *,
    tolerance: Decimal = DEFAULT_TOLERANCE,
    strict: bool = True,
) -> LoadResult:
    """Fetch deals from the HubSpot API (read-only). Milestone 3."""
    raise NotImplementedError(
        "HubSpot API ingest is milestone 3; use csv_source.load_hubspot_csv for now"
    )
