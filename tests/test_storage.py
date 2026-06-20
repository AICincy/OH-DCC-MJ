from pathlib import Path

from ohcanna.models import VapeProduct
from ohcanna.storage import (
    latest_path,
    read_snapshot,
    snapshot_path,
    update_latest,
    write_snapshot,
)


def _sample_product() -> VapeProduct:
    return VapeProduct(
        source="bloom",
        location="akron",
        category="vape",
        product_id="1",
        product_url="https://example/",
        name="Test",
        brand="Klutch",
        product_format="distillate cart",
        strain_type="hybrid",
        thc_percent=80.0,
        sale_price=24.85,
        msrp=35.50,
        discount_percent=30,
        scraped_at="2026-06-20T14:23:17Z",
        cart_size_grams=1.0,
        secondary_cannabinoids=["CBN"],
        terpenes=["Myrcene"],
    )


def test_snapshot_round_trip(tmp_path: Path):
    p = write_snapshot("bloom", "akron", "vape", [_sample_product()],
                       date="2026-06-20", data_root=tmp_path)
    assert p == snapshot_path("bloom", "akron", "vape", date="2026-06-20",
                              data_root=tmp_path)
    records = read_snapshot(p)
    assert records[0]["brand"] == "Klutch"
    assert records[0]["cart_size_grams"] == 1.0


def test_update_latest_overwrites(tmp_path: Path):
    update_latest("bloom", "vape", [_sample_product()], data_root=tmp_path)
    p = latest_path("bloom", "vape", data_root=tmp_path)
    assert p.exists()
    update_latest("bloom", "vape", [], data_root=tmp_path)
    assert read_snapshot(p) == []
