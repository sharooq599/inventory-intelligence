
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


def validate_reservation_availability(
    reservations,
    inventory,
    as_of="2026-10-28T12:00:00Z",
):
    """Flag active reservations exceeding policy-available inventory.

    For backward compatibility, expires_at is optional. When supplied,
    expired reservations are excluded. Inventory availability deducts
    blocked stock, safety stock, and channel buffer when those columns
    are available.
    """
    issues = []

    required_reservation_columns = {
        "sku_id",
        "location_id",
        "quantity",
        "status",
    }
    missing = required_reservation_columns - set(reservations.columns)

    if missing:
        raise ValueError(
            f"Reservations missing columns: {sorted(missing)}"
        )

    required_inventory_columns = {
        "sku_id",
        "location_id",
        "calculated_on_hand",
    }
    missing = required_inventory_columns - set(inventory.columns)

    if missing:
        raise ValueError(
            f"Inventory missing columns: {sorted(missing)}"
        )

    reservation_data = reservations.copy()

    reservation_data["quantity"] = pd.to_numeric(
        reservation_data["quantity"],
        errors="raise",
    )

    if (
        reservation_data["quantity"].isna().any()
        or (reservation_data["quantity"] < 0).any()
    ):
        raise ValueError(
            "Reservation quantities must be non-negative."
        )

    active_mask = reservation_data["status"].eq("ACTIVE")

    # Older tests or input datasets may omit expires_at.
    # If it exists, only reservations that have not expired are active.
    if "expires_at" in reservation_data.columns:
        reservation_data["expires_at"] = pd.to_datetime(
            reservation_data["expires_at"],
            utc=True,
            errors="coerce",
        )
        timestamp = pd.to_datetime(as_of, utc=True)

        active_mask &= reservation_data["expires_at"].gt(timestamp)

    active = reservation_data.loc[active_mask].copy()

    totals = (
        active.groupby(
            ["sku_id", "location_id"],
            as_index=False,
        )["quantity"]
        .sum()
        .rename(columns={"quantity": "reserved_quantity"})
    )

    if totals.empty:
        return issues

    joined = totals.merge(
        inventory,
        on=["sku_id", "location_id"],
        how="left",
        validate="one_to_one",
    )

    for _, row in joined.iterrows():
        record_id = f"{row['sku_id']}|{row['location_id']}"

        if pd.isna(row["calculated_on_hand"]):
            issues.append({
                "issue_type": "RESERVATION_UNKNOWN_INVENTORY",
                "entity": "Reservation",
                "record_id": record_id,
                "details": "No matching inventory balance",
            })
            continue

        on_hand = pd.to_numeric(
            pd.Series([row["calculated_on_hand"]]),
            errors="coerce",
        ).iloc[0]

        if pd.isna(on_hand) or on_hand < 0:
            issues.append({
                "issue_type": "INVALID_INVENTORY_BALANCE",
                "entity": "InventoryBalance",
                "record_id": record_id,
                "details": f"Invalid calculated_on_hand={row['calculated_on_hand']}",
            })
            continue

        blocked = (
            pd.to_numeric(
                pd.Series([row["blocked"]]), errors="coerce"
            ).iloc[0]
            if "blocked" in joined.columns
            else 0
        )
        safety_stock = (
            pd.to_numeric(
                pd.Series([row["safety_stock"]]), errors="coerce"
            ).iloc[0]
            if "safety_stock" in joined.columns
            else 0
        )
        channel_buffer = (
            pd.to_numeric(
                pd.Series([row["channel_buffer"]]), errors="coerce"
            ).iloc[0]
            if "channel_buffer" in joined.columns
            else 0
        )

        deductions = [blocked, safety_stock, channel_buffer]
        if any(pd.isna(value) or value < 0 for value in deductions):
            issues.append({
                "issue_type": "INVALID_INVENTORY_POLICY_QUANTITY",
                "entity": "InventoryBalance",
                "record_id": record_id,
                "details": (
                    "Blocked stock, safety stock, and channel buffer "
                    "must be non-negative numeric values"
                ),
            })
            continue

        available = max(
            0,
            on_hand - blocked - safety_stock - channel_buffer,
        )

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
    """Flag allocations that exceed eligible, unblocked stock.

    If on_hand is provided, eligible stock is on_hand minus blocked.
    For older/minimal inputs without on_hand, a positive allocation
    against a balance with blocked stock is conservatively flagged.
    """
    required_allocation_columns = {
        "allocation_id",
        "sku_id",
        "location_id",
        "quantity",
    }
    missing = required_allocation_columns - set(allocations.columns)

    if missing:
        raise ValueError(
            f"Allocations missing columns: {sorted(missing)}"
        )

    required_balance_columns = {
        "sku_id",
        "location_id",
        "blocked",
    }
    missing = required_balance_columns - set(balances.columns)

    if missing:
        raise ValueError(
            f"Balances missing columns: {sorted(missing)}"
        )

    balance_columns = ["sku_id", "location_id", "blocked"]
    has_on_hand = "on_hand" in balances.columns

    if has_on_hand:
        balance_columns.append("on_hand")

    joined = allocations.merge(
        balances[balance_columns],
        on=["sku_id", "location_id"],
        how="left",
        validate="many_to_one",
        indicator=True,
    )

    issues = []

    for _, row in joined.iterrows():
        allocation_id = str(row["allocation_id"])

        if row["_merge"] == "left_only":
            issues.append({
                "issue_type": "ALLOCATION_UNKNOWN_INVENTORY",
                "entity": "Allocation",
                "record_id": allocation_id,
                "details": "No matching inventory balance",
            })
            continue

        blocked = pd.to_numeric(
            pd.Series([row["blocked"]]), errors="coerce"
        ).iloc[0]
        quantity = pd.to_numeric(
            pd.Series([row["quantity"]]), errors="coerce"
        ).iloc[0]

        if (
            pd.isna(blocked)
            or pd.isna(quantity)
            or blocked < 0
            or quantity < 0
        ):
            issues.append({
                "issue_type": "INVALID_ALLOCATION_QUANTITY",
                "entity": "Allocation",
                "record_id": allocation_id,
                "details": (
                    "Blocked and allocation quantities must be "
                    "valid non-negative numbers"
                ),
            })
            continue

        if has_on_hand:
            on_hand = pd.to_numeric(
                pd.Series([row["on_hand"]]), errors="coerce"
            ).iloc[0]

            if pd.isna(on_hand) or on_hand < 0:
                issues.append({
                    "issue_type": "INVALID_ALLOCATION_QUANTITY",
                    "entity": "Allocation",
                    "record_id": allocation_id,
                    "details": "On-hand quantity must be non-negative",
                })
                continue

            if blocked > on_hand:
                issues.append({
                    "issue_type": "INVALID_BLOCKED_BALANCE",
                    "entity": "InventoryBalance",
                    "record_id": (
                        f"{row['sku_id']}|{row['location_id']}"
                    ),
                    "details": (
                        f"Blocked={blocked} exceeds on_hand={on_hand}"
                    ),
                })
                continue

            eligible_stock = on_hand - blocked

            if quantity > eligible_stock:
                issues.append({
                    "issue_type": "BLOCKED_STOCK_FULFILLMENT",
                    "entity": "Allocation",
                    "record_id": allocation_id,
                    "details": (
                        f"Allocation={quantity}; "
                        f"eligible stock={eligible_stock}; "
                        f"on_hand={on_hand}; blocked={blocked}"
                    ),
                })
        elif blocked > 0 and quantity > 0:
            # Without on_hand, we cannot determine the exact eligible
            # quantity, so flag this as a conservative potential issue.
            issues.append({
                "issue_type": "BLOCKED_STOCK_FULFILLMENT",
                "entity": "Allocation",
                "record_id": allocation_id,
                "details": (
                    f"Allocation={quantity} against inventory with "
                    f"blocked={blocked}; on_hand was not provided"
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
        issues,
        columns=columns,
    ).to_csv(path, index=False)


