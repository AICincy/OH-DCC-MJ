from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent.parent / "ohcanna" / "data" / "fixtures"
POC_SAMPLES = Path(__file__).parent.parent / "data" / "snapshots" / "2026-06-20"


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES


@pytest.fixture
def poc_vape_sample() -> Path:
    return POC_SAMPLES / "bloom_all_vape.json"


@pytest.fixture
def poc_vape_flagged_sample() -> Path:
    return POC_SAMPLES / "bloom_all_vape_flagged.json"
