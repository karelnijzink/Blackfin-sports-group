from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def blast_media_csv() -> Path:
    return FIXTURES / "Blast_Media_Commission_Deals_Import.csv"
