
"""Run dataset-wide integrity, lifecycle, and reconciliation checks."""

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "generated"
REPORTS = ROOT / "reports"

# Allow imports when this script is run directly from the project root.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.inventory_engine import reconcile_inventory
from src.validators import check_primary_keys, check_foreign_keys
from src.lifecycle_validators import (
    validate_order_lifecycle,
    validate_reservation_lifecycle,
    validate_shipment_lifecycle,
    validate_transfer_integrity,
)


def load(name):
    """Load a required generated CSV file."""
    path = DATA / f"{name}.csv"

    if not path.exists():
        raise FileNotFoundError(
            f"Required dataset file is missing: {path}"
        )

    return pd.read_csv(path)


def add_issue(issues, issue_type, entity, record_id, details):
    """Append a consistently structured validation issue."""
    issues.append({
        "issue_type": issue_type,
        "entity": entity,
        "record_id": str(record_id),
        "details": str(details),
    })


def validate_movement_fields(movements, issues):
    """Validate movement types, quantities, statuses, and timestamps."""
    allowed_movements = {
        "RECEIPT",
        "SALE",
        "RETURN",
        "TRANSFER_OUT",
        "TRANSFER_IN",
        "ADJUSTMENT",
    }
    allowed_statuses = {"POSTED", "PENDING", "CANCELLED"}

    invalid_type = (
        movements["movement_type"].isna()
        | ~movements["movement_type"].isin(allowed_movements)
    )

    for _, row in movements.loc[invalid_type].iterrows():
        add_issue(
            issues,
            "INVALID_MOVEMENT_TYPE",
            "InventoryMovement",
            row["movement_id"],
            f"Unknown or missing movement type: "
            f"{row['movement_type']}",
        )

    quantity = pd.to_numeric(
        movements["quantity"], errors="coerce"
    )
    invalid_quantity = quantity.isna() | (quantity < 0)

    for _, row in movements.loc[invalid_quantity].iterrows():
        add_issue(
            issues,
            "INVALID_MOVEMENT_QUANTITY",
            "InventoryMovement",
            row["movement_id"],
            "Movement quantity must be numeric, non-null, and non-negative.",
        )

    invalid_status = (
        movements["status"].isna()
        | ~movements["status"].isin(allowed_statuses)
    )

    for _, row in movements.loc[invalid_status].iterrows():
        add_issue(
            issues,
            "INVALID_MOVEMENT_STATUS",
            "InventoryMovement",
            row["movement_id"],
            f"Unknown or missing movement status: {row['status']}",
        )

    event_times = pd.to_datetime(
        movements["event_time"], utc=True, errors="coerce"
    )

    for index in movements.index[event_times.isna()]:
        add_issue(
            issues,
            "INVALID_MOVEMENT_TIMESTAMP",
            "InventoryMovement",
            movements.loc[index, "movement_id"],
            "Movement event_time is missing or invalid.",
        )


def validate_order_fields(orders, issues):
    """Validate order status values and timestamps."""
    allowed_statuses = {
        "NEW", "ALLOCATED", "SHIPPED", "CANCELLED"
    }
    allowed_channels = {"STORE", "ONLINE", "MARKETPLACE"}

    for _, row in orders.iterrows():
        if (
            pd.isna(row["status"])
            or row["status"] not in allowed_statuses
        ):
            add_issue(
                issues,
                "INVALID_ORDER_STATUS",
                "Order",
                row["order_id"],
                f"Unknown or missing order status: {row['status']}",
            )

        if (
            pd.isna(row["channel"])
            or row["channel"] not in allowed_channels
        ):
            add_issue(
                issues,
                "INVALID_ORDER_CHANNEL",
                "Order",
                row["order_id"],
                f"Unknown or missing order channel: {row['channel']}",
            )

    timestamps = pd.to_datetime(
        orders["order_time"], utc=True, errors="coerce"
    )

    for index in orders.index[timestamps.isna()]:
        add_issue(
            issues,
            "INVALID_ORDER_TIMESTAMP",
            "Order",
            orders.loc[index, "order_id"],
            "Order timestamp is missing or invalid.",
        )


def validate_location_hierarchy(locations, issues):
    """Validate location types and parent-location references."""
    allowed_types = {
        "WAREHOUSE", "STORE", "ONLINE_FULFILLMENT"
    }
    location_ids = set(locations["location_id"].dropna())

    for _, row in locations.iterrows():
        location_id = row["location_id"]
        location_type = row["location_type"]
        parent_id = row["parent_location_id"]

        if (
            pd.isna(location_type)
            or location_type not in allowed_types
        ):
            add_issue(
                issues,
                "INVALID_LOCATION_TYPE",
                "Location",
                location_id,
                f"Unknown or missing location type: {location_type}",
            )

        # Root locations may have no parent.
        if pd.notna(parent_id):
            if parent_id not in location_ids:
                add_issue(
                    issues,
                    "INVALID_PARENT_LOCATION",
                    "Location",
                    location_id,
                    f"Parent location {parent_id} does not exist.",
                )
            elif parent_id == location_id:
                add_issue(
                    issues,
                    "SELF_REFERENCING_LOCATION",
                    "Location",
                    location_id,
                    "A location cannot be its own parent.",
                )


def validate_line_quantities(lines, issues):
    """Require every order-line quantity to be a positive number."""
    quantity = pd.to_numeric(
        lines["quantity"], errors="coerce"
    )
    invalid = quantity.isna() | (quantity <= 0)

    for _, row in lines.loc[invalid].iterrows():
        add_issue(
            issues,
            "INVALID_ORDER_LINE_QUANTITY",
            "OrderLine",
            row["order_line_id"],
            "Order-line quantity must be positive and numeric.",
        )


def run_validation():
    """Load the baseline dataset, run checks, and write reports."""
    REPORTS.mkdir(parents=True, exist_ok=True)

    products = load("products")
    skus = load("skus")
    locations = load("locations")
    balances = load("inventory_balances")
    movements = load("inventory_movements")
    orders = load("orders")
    lines = load("order_lines")
    reservations = load("reservations")
    shipments = load("shipments")
    rules = load("replenishment_rules")

    issues = []

    # 1. Primary-key checks.
    primary_keys = {
        "products": (products, "product_id"),
        "skus": (skus, "sku_id"),
        "locations": (locations, "location_id"),
        "inventory_balances": (balances, "balance_id"),
        "inventory_movements": (movements, "movement_id"),
        "orders": (orders, "order_id"),
        "order_lines": (lines, "order_line_id"),
        "reservations": (reservations, "reservation_id"),
        "shipments": (shipments, "shipment_id"),
        "replenishment_rules": (rules, "rule_id"),
    }

    for entity, (df, key) in primary_keys.items():
        issues.extend(check_primary_keys(df, key, entity))

    # 2. Foreign-key checks.
    # The last value marks whether a missing relationship is allowed.
    foreign_keys = [
        (skus, "product_id", products, "product_id", "SKU"),
        (
            locations, "parent_location_id",
            locations, "location_id", "Location", True
        ),
        (
            balances, "sku_id", skus, "sku_id",
            "InventoryBalance"
        ),
        (
            balances, "location_id", locations, "location_id",
            "InventoryBalance"
        ),
        (
            movements, "sku_id", skus, "sku_id",
            "InventoryMovement"
        ),
        (
            movements, "location_id", locations, "location_id",
            "InventoryMovement"
        ),
        (
            lines, "order_id", orders, "order_id", "OrderLine"
        ),
        (
            lines, "sku_id", skus, "sku_id", "OrderLine"
        ),
        (
            lines, "fulfillment_location_id",
            locations, "location_id", "OrderLine"
        ),
        (
            reservations, "order_line_id", lines, "order_line_id",
            "Reservation"
        ),
        (
            reservations, "sku_id", skus, "sku_id", "Reservation"
        ),
        (
            reservations, "location_id", locations, "location_id",
            "Reservation"
        ),
        (
            shipments, "order_id", orders, "order_id", "Shipment"
        ),
        (
            shipments, "location_id", locations, "location_id",
            "Shipment"
        ),
        (
            rules, "sku_id", skus, "sku_id", "ReplenishmentRule"
        ),
    ]

    for relationship in foreign_keys:
        child, child_fk, parent, parent_pk, entity = relationship[:5]
        nullable = (
            relationship[5] if len(relationship) > 5 else False
        )

        issues.extend(
            check_foreign_keys(
                child,
                child_fk,
                parent,
                parent_pk,
                entity,
                nullable=nullable,
            )
        )

    # 3. Enum, quantity, timestamp, and hierarchy checks.
    validate_movement_fields(movements, issues)
    validate_order_fields(orders, issues)
    validate_location_hierarchy(locations, issues)
    validate_line_quantities(lines, issues)

    # 4. Order, reservation, shipment, and transfer lifecycles.
    issues.extend(
        validate_order_lifecycle(
            orders, lines, reservations, shipments
        )
    )
    issues.extend(
        validate_reservation_lifecycle(reservations, lines)
    )
    issues.extend(
        validate_shipment_lifecycle(shipments, orders)
    )
    issues.extend(
        validate_transfer_integrity(movements)
    )

    # 5. Baseline inventory reconciliation.
    mismatch_count = None

    try:
        reconciliation = reconcile_inventory(
            balances, movements
        )
        mismatch_count = int(
            (~reconciliation["reconciles"]).sum()
        )

        for _, row in reconciliation.loc[
            ~reconciliation["reconciles"]
        ].iterrows():
            add_issue(
                issues,
                "BALANCE_RECONCILIATION_MISMATCH",
                "InventoryBalance",
                f"{row['sku_id']}|{row['location_id']}",
                (
                    f"Recorded={row['recorded_on_hand']}; "
                    f"calculated={row['calculated_on_hand']}"
                ),
            )

    except (ValueError, KeyError) as exc:
        add_issue(
            issues,
            "RECONCILIATION_EXECUTION_ERROR",
            "InventoryBalance",
            "",
            str(exc),
        )

    # 6. Save detailed issues and a machine-readable summary.
    issue_columns = [
        "issue_type", "entity", "record_id", "details"
    ]
    issue_df = pd.DataFrame(
        issues, columns=issue_columns
    )
    issue_df.to_csv(
        REPORTS / "validation_issues.csv", index=False
    )

    summary = {
        "dataset": {
            name: int(len(df))
            for name, (df, _) in primary_keys.items()
        },
        "total_issues": int(len(issues)),
        "baseline_reconciliation_mismatches": mismatch_count,
        "issue_counts_by_type": (
            {
                str(key): int(value)
                for key, value in
                issue_df["issue_type"].value_counts().items()
            }
            if not issue_df.empty else {}
        ),
        "status": "PASS" if not issues else "FAIL",
        "checks": [
            "primary keys",
            "foreign keys (nullable parent location supported)",
            "movement enums, quantities, and timestamps",
            "order status, channel, and timestamps",
            "location hierarchy",
            "order-line quantities",
            "order lifecycle",
            "reservation lifecycle",
            "shipment lifecycle",
            "transfer-pair consistency",
            "inventory reconciliation",
        ],
        "limitations": [
            "Premature transfer counting requires separate transfer "
            "dispatch and receipt lifecycle data.",
            "This script does not yet validate every business rule "
            "or calculate ATP for every inventory row.",
        ],
    }

    summary_path = REPORTS / "validation_summary.json"
    with summary_path.open("w", encoding="utf-8") as file:
        json.dump(summary, file, indent=2)

    print(json.dumps(summary, indent=2))
    print(f"\nDetailed issues: {REPORTS / 'validation_issues.csv'}")
    print(f"Summary: {summary_path}")

    if issues:
        raise SystemExit(1)


if __name__ == "__main__":
    run_validation()
