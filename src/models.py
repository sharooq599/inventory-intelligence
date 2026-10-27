
"""Shared constants and ID helpers for Inventory Intelligence."""

from datetime import datetime, timezone

SEED = 20261022

MOVEMENT_TYPES = {
    "RECEIPT",
    "SALE",
    "RETURN",
    "TRANSFER_OUT",
    "TRANSFER_IN",
    "ADJUSTMENT",
}

LOCATION_TYPES = {"WAREHOUSE", "STORE", "ONLINE_FULFILLMENT"}
CHANNELS = {"STORE", "ONLINE", "MARKETPLACE"}
RESERVATION_STATES = {"ACTIVE", "EXPIRED", "RELEASED", "FULFILLED"}
ORDER_STATES = {"NEW", "ALLOCATED", "SHIPPED", "CANCELLED"}
SHIPMENT_STATES = {"PENDING", "IN_TRANSIT", "DELIVERED", "CANCELLED"}


def make_id(prefix: str, number: int, width: int = 6) -> str:
    """Create a deterministic, zero-padded ID."""
    if number < 1:
        raise ValueError("ID number must be positive")
    return f"{prefix}-{number:0{width}d}"


def make_order_id(number: int, year: int = 2026) -> str:
    return f"ORD-{year}-{number:06d}"


def make_movement_id(number: int, year: int = 2026) -> str:
    return f"MOV-{year}-{number:08d}"


def make_shipment_id(number: int, year: int = 2026) -> str:
    return f"SHP-{year}-{number:06d}"


def utc_now() -> str:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()
