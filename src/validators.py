
"""Data integrity and inventory exception validation."""

import pandas as pd


def check_primary_keys(df, key, entity_name):
    """Return duplicate or missing primary-key issues."""
    issues = []

    missing = df[key].isna() | df[key].astype(str).str.strip().eq("")

    for idx in df.index[missing]:
        issues.append({
            "issue_type": "MISSING_PRIMARY_KEY",
            "entity": entity_name,
            "record_id": str(idx),
            "details": f"Missing {key}",
        })

    duplicates = df[df[key].duplicated(keep=False) & ~missing]

    for _, row in duplicates.iterrows():
        issues.append({
            "issue_type": "DUPLICATE_PRIMARY_KEY",
            "entity": entity_name,
            "record_id": str(row[key]),
            "details": f"Duplicate {key}",
        })

    return issues


def check_foreign_keys(
    child,
    child_fk,
    parent,
    parent_pk,
    entity_name,
    nullable=False,
):
    """Validate foreign keys, allowing null only for optional references."""
    valid_ids = set(parent[parent_pk].dropna())
    issues = []

    for _, row in child.iterrows():
        value = row[child_fk]

        # Optional references, such as a root location's parent,
        # may be blank. All required references remain mandatory.
        if pd.isna(value):
            if nullable:
                continue

            issues.append({
                "issue_type": "INVALID_FOREIGN_KEY",
                "entity": entity_name,
                "record_id": str(row.get(child_fk, "")),
                "details": (
                    f"{child_fk} references missing {parent_pk}: {value}"
                ),
            })
            continue

        if value not in valid_ids:
            issues.append({
                "issue_type": "INVALID_FOREIGN_KEY",
                "entity": entity_name,
                "record_id": str(value),
                "details": (
                    f"{child_fk} references missing {parent_pk}: {value}"
                ),
            })

    return issues


def validate_inventory_reconciliation(reconciliation):
    """Find recorded balances that disagree with derived balances."""
    issues = []

    for _, row in reconciliation.iterrows():
        if not bool(row["reconciles"]):
            issues.append({
                "issue_type": "BALANCE_RECONCILIATION_MISMATCH",
                "entity": "InventoryBalance",
                "record_id": (
                    f"{row['sku_id']}|{row['location_id']}"
                ),
                "details": (
                    f"Recorded={row['on_hand']}; "
                    f"calculated={row['calculated_on_hand']}"
                ),
            })

    return issues


def validate_reservation_availability(reservations, inventory):
    """Flag active reservations that exceed policy-available stock."""
    issues = []

    active = reservations.loc[
        reservations["status"] == "ACTIVE"
    ]

    totals = (
        active.groupby(
            ["sku_id", "location_id"], as_index=False
        )["quantity"]
        .sum()
        .rename(columns={"quantity": "reserved_quantity"})
    )

    joined = totals.merge(
        inventory,
        on=["sku_id", "location_id"],
        how="left",
        validate="one_to_one",
    )

    for _, row in joined.iterrows():
        record_id = f"{row['sku_id']}|{row['location_id']}"

        if pd.isna(row.get("calculated_on_hand")):
            issues.append({
                "issue_type": "RESERVATION_UNKNOWN_INVENTORY",
                "entity": "Reservation",
                "record_id": record_id,
                "details": "No matching inventory balance",
            })
            continue

        available = (
            row["calculated_on_hand"]
            - row.get("blocked", 0)
            - row.get("safety_stock", 0)
            - row.get("channel_buffer", 0)
        )

        available = max(0, available)

        if row["reserved_quantity"] > available:
            issues.append({
                "issue_type": "RESERVATION_EXCEEDS_AVAILABLE",
                "entity": "Reservation",
                "record_id": record_id,
                "details": (
                    f"Reserved={row['reserved_quantity']}; "
                    f"available before reservation={available}"
                ),
            })

    return issues


def validate_blocked_stock_fulfillment(allocations, balances):
    """Flag allocations that attempt to use blocked inventory."""
    issues = []

    joined = allocations.merge(
        balances[["sku_id", "location_id", "blocked"]],
        on=["sku_id", "location_id"],
        how="left",
        validate="many_to_one",
    )

    for _, row in joined.iterrows():
        allocation_id = str(row["allocation_id"])

        if pd.isna(row["blocked"]):
            issues.append({
                "issue_type": "ALLOCATION_UNKNOWN_INVENTORY",
                "entity": "Allocation",
                "record_id": allocation_id,
                "details": "No matching inventory balance",
            })

        elif row["blocked"] > 0 and row["quantity"] > 0:
            issues.append({
                "issue_type": "BLOCKED_STOCK_FULFILLMENT",
                "entity": "Allocation",
                "record_id": allocation_id,
                "details": (
                    f"Allocation quantity={row['quantity']}; "
                    f"blocked quantity at location={row['blocked']}"
                ),
            })

    return issues


def validate_premature_transfers(transfers):
    """Detect destination counting before transfer receipt."""
    issues = []

    required = {
        "transfer_id",
        "source_counted",
        "destination_counted",
        "received",
    }
    missing = required - set(transfers.columns)

    if missing:
        raise ValueError(
            f"Transfer data missing columns: {sorted(missing)}"
        )

    for _, row in transfers.iterrows():
        if (
            bool(row["destination_counted"])
            and not bool(row["received"])
            and bool(row["source_counted"])
        ):
            issues.append({
                "issue_type": "TRANSFER_COUNTED_AT_BOTH_ENDS",
                "entity": "Transfer",
                "record_id": str(row["transfer_id"]),
                "details": (
                    "Destination counted before receipt while source "
                    "still counts the stock"
                ),
            })

    return issues


def write_issues(issues, path):
    """Save validation issues to CSV."""
    columns = ["issue_type", "entity", "record_id", "details"]

    pd.DataFrame(
        issues, columns=columns
    ).to_csv(path, index=False)
