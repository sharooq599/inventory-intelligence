

"""Inventory calculations, ATP, and reconciliation business logic."""

import pandas as pd


MOVEMENT_SIGN = {
    "RECEIPT": 1,
    "SALE": -1,
    "RETURN": 1,
    "TRANSFER_OUT": -1,
    "TRANSFER_IN": 1,
    "ADJUSTMENT": 1,
}

REQUIRED_BALANCE_COLUMNS = {
    "sku_id",
    "location_id",
    "reserved",
    "blocked",
}

REQUIRED_MOVEMENT_COLUMNS = {
    "sku_id",
    "location_id",
    "movement_type",
    "quantity",
    "status",
}


def _validate_columns(df, required, name):
    """Ensure a DataFrame contains all required columns."""
    missing = required - set(df.columns)
    if missing:
        raise ValueError(
            f"{name} is missing required columns: {sorted(missing)}"
        )


def _validate_unique_keys(balances):
    """Require one balance record per SKU and location."""
    keys = ["sku_id", "location_id"]

    if balances[keys].isna().any().any():
        raise ValueError("Inventory balance keys cannot be null.")

    if balances.duplicated(keys).any():
        raise ValueError(
            "Inventory balances must be unique per SKU and location."
        )


def _get_opening_stock(balances):
    """Return explicit opening stock, with legacy compatibility."""
    if "opening_on_hand" in balances.columns:
        column = "opening_on_hand"
    elif "on_hand" in balances.columns:
        # Backward compatibility for existing tests and starter CSVs.
        # New generated data should always provide opening_on_hand.
        column = "on_hand"
    else:
        raise ValueError(
            "Balances must contain opening_on_hand."
        )

    opening = pd.to_numeric(balances[column], errors="raise")

    if opening.isna().any():
        raise ValueError("Opening stock cannot be null.")

    if (opening < 0).any():
        raise ValueError("Opening stock cannot be negative.")

    return opening


def _signed_movements(movements):
    """Return posted movements with their signed quantities."""
    unknown = (
        set(movements["movement_type"].dropna().unique())
        - set(MOVEMENT_SIGN)
    )

    if unknown:
        raise ValueError(
            f"Unknown movement types: {sorted(unknown)}"
        )

    if movements["movement_type"].isna().any():
        raise ValueError("Movement type cannot be null.")

    quantity = pd.to_numeric(
        movements["quantity"], errors="raise"
    )

    if quantity.isna().any():
        raise ValueError("Movement quantities cannot be null.")

    if (quantity < 0).any():
        raise ValueError(
            "Movement quantities must be non-negative."
        )

    posted = movements.loc[
        movements["status"] == "POSTED"
    ].copy()

    posted["signed_quantity"] = (
        quantity.loc[posted.index]
        * posted["movement_type"].map(MOVEMENT_SIGN)
    )

    return posted


def calculate_inventory(balances, movements):
    """Calculate stock as opening balance plus posted movement deltas.

    `opening_on_hand` is the preferred source column. The legacy `on_hand`
    column is accepted when opening_on_hand is absent.

    This function derives stock; it never mutates its input DataFrames.
    """
    _validate_columns(
        balances,
        REQUIRED_BALANCE_COLUMNS,
        "balances",
    )
    _validate_columns(
        movements,
        REQUIRED_MOVEMENT_COLUMNS,
        "movements",
    )
    _validate_unique_keys(balances)

    result = balances.copy()
    opening = _get_opening_stock(result)

    posted = _signed_movements(movements)

    changes = (
        posted.groupby(
            ["sku_id", "location_id"],
            as_index=False,
        )["signed_quantity"]
        .sum()
        .rename(columns={"signed_quantity": "movement_delta"})
    )

    result = result.merge(
        changes,
        on=["sku_id", "location_id"],
        how="left",
        validate="one_to_one",
    )

    result["opening_on_hand"] = opening.to_numpy()

    result["movement_delta"] = pd.to_numeric(
        result["movement_delta"],
        errors="raise",
    ).fillna(0)

    result["calculated_on_hand"] = (
        result["opening_on_hand"] + result["movement_delta"]
    )

    return result


def calculate_atp(
    balances,
    movements,
    reservations,
    skus,
    as_of="2026-10-28T12:00:00Z",
    inbound=None,
):
    """Calculate available-to-promise stock by SKU and location.

    ATP = max(
        0,
        calculated_on_hand
        - active_reserved
        - blocked
        - safety_stock
        - channel_buffer
        + eligible_inbound
    )

    Reservations expire when expires_at <= as_of.

    Eligible inbound must explicitly be approved by policy and have an
    IN_TRANSIT or EXPECTED status. Inbound quantities are not added to
    destination on-hand stock until the corresponding receipt is posted.
    """
    _validate_columns(
        reservations,
        {
            "sku_id",
            "location_id",
            "quantity",
            "status",
            "expires_at",
        },
        "reservations",
    )

    _validate_columns(
        skus,
        {"sku_id", "safety_stock"},
        "skus",
    )

    if skus["sku_id"].duplicated().any():
        raise ValueError("SKU IDs must be unique in the SKU catalog.")

    timestamp = pd.to_datetime(as_of, utc=True)

    reservation_data = reservations.copy()
    reservation_data["expires_at"] = pd.to_datetime(
        reservation_data["expires_at"],
        utc=True,
        errors="raise",
    )

    reservation_data["quantity"] = pd.to_numeric(
        reservation_data["quantity"],
        errors="raise",
    )

    if reservation_data["quantity"].isna().any():
        raise ValueError("Reservation quantities cannot be null.")

    if (reservation_data["quantity"] < 0).any():
        raise ValueError("Reservation quantities cannot be negative.")

    active = reservation_data.loc[
        (reservation_data["status"] == "ACTIVE")
        & (reservation_data["expires_at"] > timestamp)
    ]

    reserved = (
        active.groupby(
            ["sku_id", "location_id"],
            as_index=False,
        )["quantity"]
        .sum()
        .rename(columns={"quantity": "calculated_reserved"})
    )

    result = calculate_inventory(balances, movements)

    result = result.merge(
        reserved,
        on=["sku_id", "location_id"],
        how="left",
        validate="one_to_one",
    )

    result["calculated_reserved"] = pd.to_numeric(
        result["calculated_reserved"],
        errors="raise",
    ).fillna(0)

    policy_columns = ["sku_id", "safety_stock"]

    if "channel_buffer" in skus.columns:
        policy_columns.append("channel_buffer")

    result = result.merge(
        skus[policy_columns],
        on="sku_id",
        how="left",
        validate="many_to_one",
        suffixes=("", "_sku"),
    )

    if result["safety_stock"].isna().any():
        raise ValueError(
            "Some inventory SKUs have no safety-stock policy."
        )

    if "blocked" not in result.columns:
        result["blocked"] = 0

    result["blocked"] = pd.to_numeric(
        result["blocked"], errors="raise"
    ).fillna(0)

    if "channel_buffer" not in result.columns:
        result["channel_buffer"] = 0

    result["channel_buffer"] = pd.to_numeric(
        result["channel_buffer"], errors="raise"
    ).fillna(0)

    result["eligible_inbound"] = 0

    if inbound is not None and not inbound.empty:
        _validate_columns(
            inbound,
            {
                "sku_id",
                "location_id",
                "quantity",
                "status",
                "eligible_for_atp",
            },
            "inbound",
        )

        inbound_data = inbound.copy()
        inbound_data["quantity"] = pd.to_numeric(
            inbound_data["quantity"],
            errors="raise",
        )

        if inbound_data["quantity"].isna().any():
            raise ValueError("Inbound quantities cannot be null.")

        if (inbound_data["quantity"] < 0).any():
            raise ValueError("Inbound quantities cannot be negative.")

        eligible = inbound_data.loc[
            inbound_data["eligible_for_atp"].eq(True)
            & inbound_data["status"].isin(
                {"IN_TRANSIT", "EXPECTED"}
            )
        ]

        inbound_totals = (
            eligible.groupby(
                ["sku_id", "location_id"],
                as_index=False,
            )["quantity"]
            .sum()
            .rename(columns={"quantity": "eligible_inbound"})
        )

        result = result.drop(
            columns=["eligible_inbound"]
        ).merge(
            inbound_totals,
            on=["sku_id", "location_id"],
            how="left",
            validate="one_to_one",
        )

        result["eligible_inbound"] = result[
            "eligible_inbound"
        ].fillna(0)

    result["atp"] = (
        result["calculated_on_hand"]
        - result["calculated_reserved"]
        - result["blocked"]
        - result["safety_stock"]
        - result["channel_buffer"]
        + result["eligible_inbound"]
    ).clip(lower=0)

    return result


def reconcile_inventory(balances, movements):
    """Compare recorded current stock against movement-derived stock.

    If `recorded_on_hand` is present, it is treated as the independently
    recorded current balance.

    Otherwise, the function retains compatibility with the original
    tests: it compares the derived balance with the `on_hand` baseline.
    """
    result = calculate_inventory(balances, movements)

    if "recorded_on_hand" in result.columns:
        recorded_column = "recorded_on_hand"
    elif "on_hand" in result.columns:
        recorded_column = "on_hand"
    else:
        raise ValueError(
            "Balances need recorded_on_hand or legacy on_hand."
        )

    recorded = pd.to_numeric(
        result[recorded_column], errors="raise"
    )

    if recorded.isna().any():
        raise ValueError("Recorded stock cannot be null.")

    result["recorded_on_hand"] = recorded

    result["reconciliation_difference"] = (
        result["calculated_on_hand"]
        - result["recorded_on_hand"]
    )

    result["reconciles"] = (
        result["reconciliation_difference"] == 0
    )

    return result
