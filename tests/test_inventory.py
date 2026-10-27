
import pandas as pd

from src.inventory_engine import (
    calculate_inventory,
    calculate_atp,
    reconcile_inventory,
)


def test_inventory_movements():
    balances = pd.DataFrame([{
        "sku_id": "SKU-000001",
        "location_id": "LOC-000001",
        "on_hand": 100,
        "reserved": 0,
        "blocked": 0,
    }])

    movements = pd.DataFrame([
        {
            "sku_id": "SKU-000001",
            "location_id": "LOC-000001",
            "movement_type": "SALE",
            "quantity": 10,
            "status": "POSTED",
        },
        {
            "sku_id": "SKU-000001",
            "location_id": "LOC-000001",
            "movement_type": "RECEIPT",
            "quantity": 20,
            "status": "POSTED",
        },
    ])

    result = calculate_inventory(balances, movements)
    assert result.loc[0, "calculated_on_hand"] == 110


def test_atp_respects_reservations_and_safety_stock():
    balances = pd.DataFrame([{
        "sku_id": "SKU-000001",
        "location_id": "LOC-000001",
        "on_hand": 100,
        "reserved": 0,
        "blocked": 5,
    }])

    movements = pd.DataFrame(columns=[
        "sku_id", "location_id", "movement_type",
        "quantity", "status",
    ])

    reservations = pd.DataFrame([{
        "sku_id": "SKU-000001",
        "location_id": "LOC-000001",
        "quantity": 20,
        "status": "ACTIVE",
        "expires_at": "2026-10-29T00:00:00Z",
    }])

    skus = pd.DataFrame([{
        "sku_id": "SKU-000001",
        "safety_stock": 10,
    }])

    result = calculate_atp(
        balances, movements, reservations, skus,
        as_of="2026-10-28T12:00:00Z",
    )

    assert result.loc[0, "atp"] == 65


def test_reconciliation_detects_mismatch():
    balances = pd.DataFrame([{
        "sku_id": "SKU-000001",
        "location_id": "LOC-000001",
        "on_hand": 100,
        "reserved": 0,
        "blocked": 0,
    }])

    movements = pd.DataFrame([{
        "sku_id": "SKU-000001",
        "location_id": "LOC-000001",
        "movement_type": "SALE",
        "quantity": 10,
        "status": "POSTED",
    }])

    result = reconcile_inventory(balances, movements)

    assert result.loc[0, "calculated_on_hand"] == 90
    assert not result.loc[0, "reconciles"]
