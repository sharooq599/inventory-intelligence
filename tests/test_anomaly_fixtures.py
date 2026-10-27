
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
GROUND_TRUTH_DIR = ROOT / "data" / "ground_truth"
FIXTURES = GROUND_TRUTH_DIR / "fixtures"

EXPECTED_ISSUES = {
    "ANOM-001": "BALANCE_RECONCILIATION_MISMATCH",
    "ANOM-002": "RESERVATION_EXCEEDS_AVAILABLE",
    "ANOM-003": "BLOCKED_STOCK_FULFILLMENT",
    "ANOM-004": "TRANSFER_COUNTED_AT_BOTH_ENDS",
}


def load_fixture(case_id):
    """Load one generated anomaly fixture."""
    path = FIXTURES / f"{case_id.lower()}.json"
    assert path.exists(), f"Missing anomaly fixture: {path}"

    with path.open(encoding="utf-8") as file:
        return json.load(file)


def load_ground_truth():
    """Load the separate ground-truth metadata."""
    path = GROUND_TRUTH_DIR / "ground_truth.json"
    assert path.exists(), f"Missing ground truth: {path}"

    with path.open(encoding="utf-8") as file:
        return json.load(file)


def assert_ground_truth(case_id, fixture):
    """Ensure fixture metadata agrees with the ground-truth manifest."""
    cases = load_ground_truth()
    matching = [
        item for item in cases if item["case_id"] == case_id
    ]

    assert len(matching) == 1, (
        f"Expected exactly one ground-truth entry for {case_id}"
    )

    expected = matching[0]
    expected_issue = EXPECTED_ISSUES[case_id]

    assert expected["issue_type"] == expected_issue
    assert expected["expected_detection"] is True
    assert expected["expected_decision"].strip()
    assert fixture["case_id"] == case_id
    assert fixture["expected_detection"] is True
    assert fixture["expected_decision"] == expected["expected_decision"]

    return expected


def assert_issue_detected(issues, expected_issue):
    """Assert that a validator returns the expected issue type."""
    assert any(
        issue["issue_type"] == expected_issue
        for issue in issues
    ), (
        f"Expected {expected_issue}; detected issue types were "
        f"{[issue.get('issue_type') for issue in issues]}"
    )


def test_anom_001_balance_reconciliation_mismatch():
    case = load_fixture("ANOM-001")
    assert_ground_truth("ANOM-001", case)

    balance = pd.DataFrame(case["balances"])
    movements = pd.DataFrame(case["movements"])

    assert not balance.empty
    assert not movements.empty

    opening = float(balance.iloc[0]["opening_on_hand"])
    recorded = float(balance.iloc[0]["recorded_on_hand"])

    signs = {
        "RECEIPT": 1,
        "SALE": -1,
        "RETURN": 1,
        "TRANSFER_OUT": -1,
        "TRANSFER_IN": 1,
        "ADJUSTMENT": 1,
    }

    delta = 0.0

    for _, movement in movements.iterrows():
        if movement["status"] != "POSTED":
            continue

        movement_type = movement["movement_type"]
        assert movement_type in signs, (
            f"Unexpected movement type: {movement_type}"
        )

        delta += float(movement["quantity"]) * signs[movement_type]

    calculated = opening + delta

    reconciliation = pd.DataFrame([{
        "sku_id": balance.iloc[0]["sku_id"],
        "location_id": balance.iloc[0]["location_id"],
        "on_hand": recorded,
        "calculated_on_hand": calculated,
        "reconciles": recorded == calculated,
    }])

    issues = validate_inventory_reconciliation(reconciliation)

    assert recorded != calculated, (
        "ANOM-001 fixture must contain a real balance mismatch"
    )
    assert_issue_detected(
        issues, "BALANCE_RECONCILIATION_MISMATCH"
    )


def test_anom_002_reservation_exceeds_available():
    case = load_fixture("ANOM-002")
    assert_ground_truth("ANOM-002", case)

    reservations = pd.DataFrame(case["reservations"])
    inventory = pd.DataFrame(case["inventory"])

    assert not reservations.empty
    assert not inventory.empty

    issues = validate_reservation_availability(
        reservations,
        inventory,
    )

    assert_issue_detected(
        issues, "RESERVATION_EXCEEDS_AVAILABLE"
    )


def test_anom_003_blocked_stock_fulfillment():
    case = load_fixture("ANOM-003")
    assert_ground_truth("ANOM-003", case)

    allocations = pd.DataFrame(case["allocations"])
    balances = pd.DataFrame(case["balances"])

    assert not allocations.empty
    assert not balances.empty

    # Prefer the recorded inventory quantity when the fixture does not
    # already expose the validator's expected on_hand column.
    if "on_hand" not in balances.columns:
        assert "recorded_on_hand" in balances.columns, (
            "Fixture must provide on_hand or recorded_on_hand"
        )
        balances["on_hand"] = balances["recorded_on_hand"]

    assert (balances["blocked"] >= 0).all()
    assert (balances["on_hand"] >= 0).all()
    assert (balances["blocked"] <= balances["on_hand"]).all()

    allocation = allocations.iloc[0]
    matching_balance = balances.loc[
        (balances["sku_id"] == allocation["sku_id"])
        & (balances["location_id"] == allocation["location_id"])
    ]

    assert not matching_balance.empty

    eligible_stock = (
        float(matching_balance.iloc[0]["on_hand"])
        - float(matching_balance.iloc[0]["blocked"])
    )

    assert float(allocation["quantity"]) > eligible_stock, (
        "ANOM-003 allocation must exceed eligible unblocked stock"
    )

    issues = validate_blocked_stock_fulfillment(
        allocations,
        balances,
    )

    assert_issue_detected(
        issues, "BLOCKED_STOCK_FULFILLMENT"
    )


def test_anom_004_premature_transfer_counting():
    case = load_fixture("ANOM-004")
    assert_ground_truth("ANOM-004", case)

    transfers = pd.DataFrame(case["transfers"])

    assert not transfers.empty

    issues = validate_premature_transfers(transfers)

    assert_issue_detected(
        issues, "TRANSFER_COUNTED_AT_BOTH_ENDS"
    )
