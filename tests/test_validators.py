
import pandas as pd

from src.validators import (
    check_primary_keys,
    check_foreign_keys,
    validate_inventory_reconciliation,
    validate_reservation_availability,
    validate_blocked_stock_fulfillment,
    validate_premature_transfers,
)


def test_duplicate_primary_key_is_detected():
    df = pd.DataFrame({"sku_id": ["SKU-000001", "SKU-000001"]})

    issues = check_primary_keys(df, "sku_id", "SKU")

    assert any(
        issue["issue_type"] == "DUPLICATE_PRIMARY_KEY"
        for issue in issues
    )


def test_invalid_foreign_key_is_detected():
    child = pd.DataFrame({"product_id": ["PRD-999999"]})
    parent = pd.DataFrame({"product_id": ["PRD-000001"]})

    issues = check_foreign_keys(
        child, "product_id", parent, "product_id", "SKU"
    )

    assert any(
        issue["issue_type"] == "INVALID_FOREIGN_KEY"
        for issue in issues
    )


def test_balance_mismatch_is_detected():
    reconciliation = pd.DataFrame([{
        "sku_id": "SKU-000001",
        "location_id": "LOC-000001",
        "on_hand": 100,
        "calculated_on_hand": 90,
        "reconciles": False,
    }])

    issues = validate_inventory_reconciliation(reconciliation)

    assert issues[0]["issue_type"] == "BALANCE_RECONCILIATION_MISMATCH"


def test_reservation_exceeding_available_stock_is_detected():
    reservations = pd.DataFrame([{
        "sku_id": "SKU-000001",
        "location_id": "LOC-000001",
        "quantity": 95,
        "status": "ACTIVE",
    }])

    inventory = pd.DataFrame([{
        "sku_id": "SKU-000001",
        "location_id": "LOC-000001",
        "calculated_on_hand": 100,
        "blocked": 10,
        "safety_stock": 10,
    }])

    issues = validate_reservation_availability(reservations, inventory)

    assert any(
        i["issue_type"] == "RESERVATION_EXCEEDS_AVAILABLE"
        for i in issues
    )


def test_blocked_stock_fulfillment_is_detected():
    allocations = pd.DataFrame([{
        "allocation_id": "ALLOC-000001",
        "sku_id": "SKU-000001",
        "location_id": "LOC-000001",
        "quantity": 2,
    }])

    balances = pd.DataFrame([{
        "sku_id": "SKU-000001",
        "location_id": "LOC-000001",
        "blocked": 5,
    }])

    issues = validate_blocked_stock_fulfillment(allocations, balances)

    assert any(
        i["issue_type"] == "BLOCKED_STOCK_FULFILLMENT"
        for i in issues
    )


def test_premature_transfer_is_detected():
    transfers = pd.DataFrame([{
        "transfer_id": "TRF-000001",
        "source_counted": True,
        "destination_counted": True,
        "received": False,
    }])

    issues = validate_premature_transfers(transfers)

    assert any(
        i["issue_type"] == "TRANSFER_COUNTED_AT_BOTH_ENDS"
        for i in issues
    )
