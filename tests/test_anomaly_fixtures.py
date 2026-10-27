
"""End-to-end checks for the four generated anomaly fixtures."""

import json
from pathlib import Path

import pandas as pd

from src.validators import (
    validate_inventory_reconciliation,
    validate_reservation_availability,
    validate_blocked_stock_fulfillment,
    validate_premature_transfers,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "data" / "ground_truth" / "fixtures"


def load_fixture(case_id):
    path = FIXTURES / f"{case_id.lower()}.json"
    assert path.exists(), f"Missing anomaly fixture: {path}"
    with path.open(encoding="utf-8") as file:
        return json.load(file)


def test_anom_001_balance_reconciliation_mismatch():
    case = load_fixture("ANOM-001")
    balance = pd.DataFrame(case["balances"])
    movements = pd.DataFrame(case["movements"])

    opening = float(balance.iloc[0]["opening_on_hand"])
    delta = 0

    signs = {
        "RECEIPT": 1,
        "SALE": -1,
        "RETURN": 1,
        "TRANSFER_OUT": -1,
        "TRANSFER_IN": 1,
        "ADJUSTMENT": 1,
    }

    for _, movement in movements.iterrows():
        if movement["status"] == "POSTED":
            delta += (
                float(movement["quantity"])
                * signs[movement["movement_type"]]
            )

    calculated = opening + delta
    recorded = float(balance.iloc[0]["recorded_on_hand"])

    validator_input = pd.DataFrame([{
        "sku_id": balance.iloc[0]["sku_id"],
        "location_id": balance.iloc[0]["location_id"],
        "on_hand": recorded,
        "calculated_on_hand": calculated,
        "reconciles": recorded == calculated,
    }])

    issues = validate_inventory_reconciliation(validator_input)

    assert recorded != calculated
    assert any(
        issue["issue_type"] == "BALANCE_RECONCILIATION_MISMATCH"
        for issue in issues
    )


def test_anom_002_reservation_exceeds_available():
    case = load_fixture("ANOM-002")

    reservations = pd.DataFrame(case["reservations"])
    inventory = pd.DataFrame(case["inventory"])

    issues = validate_reservation_availability(
        reservations, inventory
    )

    assert any(
        issue["issue_type"] == "RESERVATION_EXCEEDS_AVAILABLE"
        for issue in issues
    )


def test_anom_003_blocked_stock_fulfillment():
    case = load_fixture("ANOM-003")

    allocations = pd.DataFrame(case["allocations"])
    balances = pd.DataFrame(case["balances"])

    issues = validate_blocked_stock_fulfillment(
        allocations, balances
    )

    assert any(
        issue["issue_type"] == "BLOCKED_STOCK_FULFILLMENT"
        for issue in issues
    )


def test_anom_004_premature_transfer_counting():
    case = load_fixture("ANOM-004")
    transfers = pd.DataFrame(case["transfers"])

    issues = validate_premature_transfers(transfers)

    assert any(
        issue["issue_type"] == "TRANSFER_COUNTED_AT_BOTH_ENDS"
        for issue in issues
    )
