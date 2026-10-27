
"""Validation for order, reservation, shipment, and transfer lifecycles."""

import pandas as pd

ORDER_STATES = {"NEW", "ALLOCATED", "SHIPPED", "CANCELLED"}
RESERVATION_STATES = {"ACTIVE", "EXPIRED", "RELEASED", "FULFILLED"}
SHIPMENT_STATES = {"PENDING", "IN_TRANSIT", "DELIVERED", "CANCELLED"}


def _issue(issue_type, entity, record_id, details):
    """Create a standardized validation issue."""
    return {
        "issue_type": issue_type,
        "entity": entity,
        "record_id": str(record_id),
        "details": details,
    }


def validate_order_lifecycle(orders, lines, reservations, shipments):
    """Check order states and consistency with related records efficiently."""
    issues = []

    # Build indexes once rather than scanning entire DataFrames per order.
    line_ids_by_order = (
        lines.groupby("order_id")["order_line_id"]
        .agg(set)
        .to_dict()
    )

    reserved_line_ids = set(reservations["order_line_id"].dropna())

    reserved_lines_by_order = {
        order_id: line_ids & reserved_line_ids
        for order_id, line_ids in line_ids_by_order.items()
    }

    shipment_order_ids = set(shipments["order_id"].dropna())

    for _, order in orders.iterrows():
        order_id = order["order_id"]
        status = order["status"]

        if status not in ORDER_STATES:
            issues.append(
                _issue(
                    "INVALID_ORDER_STATUS",
                    "Order",
                    order_id,
                    f"Unknown order status: {status}",
                )
            )
            continue

        order_line_ids = line_ids_by_order.get(order_id, set())
        has_lines = bool(order_line_ids)
        has_reservations = bool(
            reserved_lines_by_order.get(order_id, set())
        )
        has_shipments = order_id in shipment_order_ids

        if not has_lines:
            issues.append(
                _issue(
                    "ORDER_WITHOUT_LINES",
                    "Order",
                    order_id,
                    "Order has no order lines.",
                )
            )

        if status == "NEW" and (has_reservations or has_shipments):
            issues.append(
                _issue(
                    "NEW_ORDER_HAS_FULFILLMENT_RECORDS",
                    "Order",
                    order_id,
                    "NEW order unexpectedly has reservations or shipments.",
                )
            )

        if status in {"ALLOCATED", "SHIPPED"} and not has_reservations:
            issues.append(
                _issue(
                    "ALLOCATED_ORDER_WITHOUT_RESERVATION",
                    "Order",
                    order_id,
                    f"{status} order has no reservation.",
                )
            )

        if status == "SHIPPED" and not has_shipments:
            issues.append(
                _issue(
                    "SHIPPED_ORDER_WITHOUT_SHIPMENT",
                    "Order",
                    order_id,
                    "SHIPPED order has no shipment.",
                )
            )

    return issues


def validate_reservation_lifecycle(reservations, lines):
    """Validate reservation states, quantities, timestamps, and links."""
    issues = []
    valid_line_ids = set(lines["order_line_id"].dropna())

    for _, reservation in reservations.iterrows():
        reservation_id = reservation["reservation_id"]
        status = reservation["status"]

        if status not in RESERVATION_STATES:
            issues.append(
                _issue(
                    "INVALID_RESERVATION_STATUS",
                    "Reservation",
                    reservation_id,
                    f"Unknown reservation status: {status}",
                )
            )

        quantity = pd.to_numeric(
            pd.Series([reservation["quantity"]]),
            errors="coerce",
        ).iloc[0]

        if pd.isna(quantity) or quantity <= 0:
            issues.append(
                _issue(
                    "INVALID_RESERVATION_QUANTITY",
                    "Reservation",
                    reservation_id,
                    "Reservation quantity must be positive.",
                )
            )

        if reservation["order_line_id"] not in valid_line_ids:
            issues.append(
                _issue(
                    "RESERVATION_LINE_NOT_FOUND",
                    "Reservation",
                    reservation_id,
                    "Referenced order line does not exist.",
                )
            )

        created = pd.to_datetime(
            reservation["created_at"],
            utc=True,
            errors="coerce",
        )
        expires = pd.to_datetime(
            reservation["expires_at"],
            utc=True,
            errors="coerce",
        )

        if pd.isna(created) or pd.isna(expires):
            issues.append(
                _issue(
                    "INVALID_RESERVATION_TIMESTAMP",
                    "Reservation",
                    reservation_id,
                    "Creation or expiry timestamp is invalid.",
                )
            )
        elif expires <= created:
            issues.append(
                _issue(
                    "INVALID_RESERVATION_TIME_ORDER",
                    "Reservation",
                    reservation_id,
                    "Expiry must be later than creation.",
                )
            )

    return issues


def validate_shipment_lifecycle(shipments, orders):
    """Check shipment states and consistency with parent order status."""
    issues = []
    order_status = orders.set_index("order_id")["status"].to_dict()

    for _, shipment in shipments.iterrows():
        shipment_id = shipment["shipment_id"]
        status = shipment["status"]
        order_id = shipment["order_id"]

        if status not in SHIPMENT_STATES:
            issues.append(
                _issue(
                    "INVALID_SHIPMENT_STATUS",
                    "Shipment",
                    shipment_id,
                    f"Unknown shipment status: {status}",
                )
            )

        if order_id not in order_status:
            issues.append(
                _issue(
                    "SHIPMENT_ORDER_NOT_FOUND",
                    "Shipment",
                    shipment_id,
                    f"Order {order_id} does not exist.",
                )
            )
            continue

        if (
            status in {"IN_TRANSIT", "DELIVERED"}
            and order_status[order_id] != "SHIPPED"
        ):
            issues.append(
                _issue(
                    "SHIPMENT_ORDER_STATE_CONFLICT",
                    "Shipment",
                    shipment_id,
                    f"{status} shipment belongs to order state "
                    f"{order_status[order_id]}.",
                )
            )

        created = pd.to_datetime(
            shipment["created_at"],
            utc=True,
            errors="coerce",
        )

        if pd.isna(created):
            issues.append(
                _issue(
                    "INVALID_SHIPMENT_TIMESTAMP",
                    "Shipment",
                    shipment_id,
                    "Shipment creation timestamp is invalid.",
                )
            )

    return issues


def validate_transfer_integrity(movements):
    """Check transfer pairs for matching SKU, quantity, and locations.

    This validates transfer pairs in the posted movement ledger. It does
    not infer receipt timing from a movement ledger lacking separate
    dispatch/receipt lifecycle events.
    """
    issues = []

    required = {
        "movement_id",
        "sku_id",
        "location_id",
        "movement_type",
        "quantity",
        "transfer_id",
        "status",
    }

    missing = required - set(movements.columns)
    if missing:
        raise ValueError(
            f"Movement data missing columns: {sorted(missing)}"
        )

    transfers = movements.loc[
        movements["transfer_id"].notna()
        & movements["transfer_id"].astype(str).str.strip().ne("")
    ]

    for transfer_id, group in transfers.groupby("transfer_id"):
        posted = group.loc[group["status"] == "POSTED"]
        outs = posted.loc[posted["movement_type"] == "TRANSFER_OUT"]
        ins = posted.loc[posted["movement_type"] == "TRANSFER_IN"]

        if len(outs) != 1 or len(ins) != 1 or len(posted) != 2:
            issues.append(
                _issue(
                    "INVALID_TRANSFER_PAIR",
                    "Transfer",
                    transfer_id,
                    "A posted transfer must have exactly one outbound "
                    "and one inbound movement.",
                )
            )
            continue

        outbound = outs.iloc[0]
        inbound = ins.iloc[0]

        if outbound["sku_id"] != inbound["sku_id"]:
            issues.append(
                _issue(
                    "TRANSFER_SKU_MISMATCH",
                    "Transfer",
                    transfer_id,
                    "Outbound and inbound SKU IDs differ.",
                )
            )

        if float(outbound["quantity"]) != float(inbound["quantity"]):
            issues.append(
                _issue(
                    "TRANSFER_QUANTITY_MISMATCH",
                    "Transfer",
                    transfer_id,
                    "Outbound and inbound quantities differ.",
                )
            )

        if outbound["location_id"] == inbound["location_id"]:
            issues.append(
                _issue(
                    "TRANSFER_LOCATION_MISMATCH",
                    "Transfer",
                    transfer_id,
                    "Source and destination locations must differ.",
                )
            )

        if str(outbound["event_time"]) != str(inbound["event_time"]):
            issues.append(
                _issue(
                    "TRANSFER_TIMESTAMP_MISMATCH",
                    "Transfer",
                    transfer_id,
                    "Outbound and inbound event times differ.",
                )
            )

    return issues
