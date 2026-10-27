
"""Create concrete, reproducible anomaly fixtures and separate ground truth."""

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "data" / "generated"
OUTPUT = ROOT / "data" / "ground_truth"
FIXTURES = OUTPUT / "fixtures"


def read_csv(name):
    """Read a generated CSV file or raise a helpful error."""
    path = INPUT / name

    if not path.exists():
        raise FileNotFoundError(
            f"Missing {path}. Run src.generator first."
        )

    return pd.read_csv(path)


def write_fixture(case_id, records):
    """Write one reproducible anomaly scenario as JSON."""
    path = FIXTURES / f"{case_id.lower()}.json"

    with path.open("w", encoding="utf-8") as file:
        json.dump(records, file, indent=2, default=str)

    return str(path.relative_to(ROOT))


def create_anomaly_cases():
    """Create four anomaly fixtures and separate ground-truth files."""
    OUTPUT.mkdir(parents=True, exist_ok=True)
    FIXTURES.mkdir(parents=True, exist_ok=True)

    balances = read_csv("inventory_balances.csv")
    movements = read_csv("inventory_movements.csv")
    skus = read_csv("skus.csv")
    lines = read_csv("order_lines.csv")
    reservations = read_csv("reservations.csv")

    if balances.empty or skus.empty or lines.empty:
        raise ValueError(
            "Balances, SKUs, and order lines must not be empty."
        )

    # ANOM-001: recorded stock differs from ledger-derived stock.
    balance = balances.iloc[0].copy()
    sku_id = str(balance["sku_id"])
    location_id = str(balance["location_id"])

    related_movements = movements.loc[
        (movements["sku_id"] == sku_id)
        & (movements["location_id"] == location_id)
    ].copy()

    recorded = int(balance["recorded_on_hand"])
    balance["recorded_on_hand"] = recorded + 1
    balance["on_hand"] = recorded + 1

    case_001 = {
        "case_id": "ANOM-001",
        "issue_type": "BALANCE_RECONCILIATION_MISMATCH",
        "balances": [balance.to_dict()],
        "movements": related_movements.to_dict(orient="records"),
        "expected_detection": True,
        "expected_decision": (
            "Investigate ledger and balance discrepancy"
        ),
    }

    # ANOM-002: active reservation exceeds stock after policy deductions.
    sku_matches = skus.loc[skus["sku_id"] == sku_id]

    if sku_matches.empty:
        raise ValueError(f"Could not find SKU policy for {sku_id}.")

    sku = sku_matches.iloc[0]

    policy_available = max(
        0,
        int(balance["recorded_on_hand"])
        - int(balance["blocked"])
        - int(sku["safety_stock"])
        - int(sku["channel_buffer"]),
    )

    reservation_quantity = policy_available + 10

    existing = reservations.loc[
        (reservations["sku_id"] == sku_id)
        & (reservations["location_id"] == location_id)
    ]

    reservation_id = f"ANOM-RES-{sku_id}-{location_id}"

    case_002 = {
        "case_id": "ANOM-002",
        "issue_type": "RESERVATION_EXCEEDS_AVAILABLE",
        "inventory": [{
            "sku_id": sku_id,
            "location_id": location_id,
            "calculated_on_hand": int(balance["recorded_on_hand"]),
            "blocked": int(balance["blocked"]),
            "safety_stock": int(sku["safety_stock"]),
            "channel_buffer": int(sku["channel_buffer"]),
        }],
        "reservations": [{
            "reservation_id": reservation_id,
            "sku_id": sku_id,
            "location_id": location_id,
            "quantity": reservation_quantity,
            "status": "ACTIVE",
            "expires_at": "2026-12-31T23:59:59Z",
        }],
        "policy_available_before_test_reservation": policy_available,
        "existing_reservation_count_for_pair": int(len(existing)),
        "expected_detection": True,
        "expected_decision": (
            "Reject or partially allocate reservation"
        ),
    }

    # ANOM-003: allocation exceeds eligible stock because some stock is blocked.
    line = lines.iloc[0]
    case_003_sku = str(line["sku_id"])
    case_003_location = str(line["fulfillment_location_id"])

    case_003_balance = balances.loc[
        (balances["sku_id"] == case_003_sku)
        & (balances["location_id"] == case_003_location)
    ]

    if case_003_balance.empty:
        raise ValueError(
            "Could not find inventory for the selected order line."
        )

    blocked_balance = case_003_balance.iloc[0].copy()

    on_hand = int(blocked_balance["recorded_on_hand"])
    blocked = max(1, int(blocked_balance["blocked"]))

    # Keep blocked stock within the recorded on-hand quantity.
    if on_hand < 1:
        on_hand = 1
        blocked_balance["recorded_on_hand"] = on_hand
        blocked_balance["on_hand"] = on_hand

    blocked = min(blocked, on_hand)
    blocked_balance["blocked"] = blocked

    eligible_stock = max(0, on_hand - blocked)

    # This deliberately exceeds eligible stock by one unit.
    allocation_quantity = eligible_stock + 1

    case_003 = {
        "case_id": "ANOM-003",
        "issue_type": "BLOCKED_STOCK_FULFILLMENT",
        "balances": [blocked_balance.to_dict()],
        "allocations": [{
            "allocation_id": "ANOM-ALLOC-0001",
            "order_line_id": str(line["order_line_id"]),
            "sku_id": case_003_sku,
            "location_id": case_003_location,
            "quantity": allocation_quantity,
        }],
        "eligible_stock_before_allocation": eligible_stock,
        "blocked_quantity": blocked,
        "expected_detection": True,
        "expected_decision": (
            "Reject allocation and select eligible stock"
        ),
    }

    # ANOM-004: destination counts stock before receiving the transfer.
    transfer_id = "ANOM-TRANSFER-0001"

    case_004 = {
        "case_id": "ANOM-004",
        "issue_type": "TRANSFER_COUNTED_AT_BOTH_ENDS",
        "transfers": [{
            "transfer_id": transfer_id,
            "source_location_id": location_id,
            "destination_location_id": str(
                balances.iloc[-1]["location_id"]
            ),
            "sku_id": sku_id,
            "quantity": 5,
            "source_counted": True,
            "destination_counted": True,
            "received": False,
        }],
        "expected_detection": True,
        "expected_decision": (
            "Keep stock in transit until destination receipt"
        ),
    }

    cases = []

    for case in (case_001, case_002, case_003, case_004):
        fixture_path = write_fixture(case["case_id"], case)

        descriptions = {
            "ANOM-001": (
                "Recorded balance differs from movement-derived balance."
            ),
            "ANOM-002": (
                "Active reservation exceeds policy-available stock."
            ),
            "ANOM-003": (
                "An order allocation exceeds eligible stock because "
                "inventory is blocked."
            ),
            "ANOM-004": (
                "Destination counts stock before transfer receipt."
            ),
        }

        cases.append({
            "case_id": case["case_id"],
            "issue_type": case["issue_type"],
            "description": descriptions[case["case_id"]],
            "fixture": fixture_path,
            "expected_detection": case["expected_detection"],
            "expected_decision": case["expected_decision"],
        })

    with (OUTPUT / "ground_truth.json").open(
        "w", encoding="utf-8"
    ) as file:
        json.dump(cases, file, indent=2)

    pd.DataFrame(cases).to_csv(
        OUTPUT / "ground_truth.csv",
        index=False,
    )

    print(f"Created {len(cases)} concrete anomaly fixtures.")
    print(f"Ground truth: {OUTPUT}")
    print(f"Fixtures: {FIXTURES}")

    for case in cases:
        print(f"  {case['case_id']}: {case['fixture']}")


if __name__ == "__main__":
    create_anomaly_cases()
