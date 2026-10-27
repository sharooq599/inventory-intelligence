
"""Reproducible synthetic inventory data generator.

Examples:
    python -m src.generator
    python -m src.generator --skus 500 --locations 20 --movements 10000 --orders 1000
    python -m src.generator --seed 20261022 --skus 5000 --locations 100 --movements 1000000 --orders 50000 --batch-size 10000
"""

import argparse
import hashlib
import json
import random
from pathlib import Path

import pandas as pd

from src.models import (
    SEED,
    make_id,
    make_order_id,
    make_movement_id,
    make_shipment_id,
)

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "generated"

MOVEMENT_COLUMNS = [
    "movement_id",
    "sku_id",
    "location_id",
    "movement_type",
    "quantity",
    "event_time",
    "reference_id",
    "transfer_id",
    "status",
]


def write_csv(rows, name, columns=None):
    """Write records to a CSV file."""
    path = OUTPUT / f"{name}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=columns).to_csv(path, index=False)


def file_checksum(path):
    """Return a SHA-256 checksum for reproducibility verification."""
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_master_data(skus_count, locations_count, rng):
    """Generate master data before dependent transaction records."""
    products = []
    skus = []
    locations = []
    rules = []

    categories = [
        "Electronics",
        "Home",
        "Fashion",
        "Grocery",
        "Sports",
    ]

    location_types = [
        "WAREHOUSE",
        "STORE",
        "ONLINE_FULFILLMENT",
    ]

    product_count = max(1, (skus_count + 2) // 3)

    for i in range(1, product_count + 1):
        products.append({
            "product_id": make_id("PRD", i),
            "product_name": f"Product {i:05d}",
            "category": categories[(i - 1) % len(categories)],
            "status": "ACTIVE",
        })

    for i in range(1, skus_count + 1):
        skus.append({
            "sku_id": make_id("SKU", i),
            "product_id": make_id(
                "PRD", rng.randint(1, product_count)
            ),
            "sku_name": f"SKU Item {i:06d}",
            "unit": "each",
            "safety_stock": rng.randint(2, 15),
            "channel_buffer": rng.randint(0, 5),
            "status": "ACTIVE",
        })

    for i in range(1, locations_count + 1):
        locations.append({
            "location_id": make_id("LOC", i),
            "location_name": f"Location {i:03d}",
            "location_type": location_types[(i - 1) % 3],
            "parent_location_id": (
                make_id("LOC", 1) if i > 3 else None
            ),
            "status": "ACTIVE",
        })

    for i in range(1, skus_count + 1):
        rules.append({
            "rule_id": make_id("RUL", i),
            "sku_id": make_id("SKU", i),
            "reorder_point": rng.randint(10, 30),
            "reorder_quantity": rng.randint(20, 100),
            "allow_inbound_atp": True,
            "effective_date": "2026-01-01",
        })

    return products, skus, locations, rules


def event_timestamp(rng):
    """Generate a deterministic UTC timestamp in the sample period."""
    day = rng.randint(1, 28)
    hour = rng.randint(0, 23)
    minute = rng.randint(0, 59)
    return f"2026-10-{day:02d}T{hour:02d}:{minute:02d}:00Z"


def generate_movements(
    skus,
    locations,
    movement_count,
    rng,
    batch_size,
):
    """Generate movements while maintaining the stock ledger.

    Transfer pairs are completed immediately in the baseline and share
    a transfer ID. Both events count toward the requested movement total.
    Opening and final recorded balances are exported separately.
    """
    sku_ids = [row["sku_id"] for row in skus]
    location_ids = [row["location_id"] for row in locations]

    safety_stock = {
        row["sku_id"]: row["safety_stock"] for row in skus
    }

    channel_buffer = {
        row["sku_id"]: row["channel_buffer"] for row in skus
    }

    opening = {}
    current = {}

    # Each SKU/location has a unique opening balance.
    for sku_id in sku_ids:
        for location_id in location_ids:
            key = (sku_id, location_id)
            quantity = rng.randint(40, 100)
            opening[key] = quantity
            current[key] = quantity

    balance_path = OUTPUT / "inventory_balances.csv"
    balance_path.parent.mkdir(parents=True, exist_ok=True)

    movement_path = OUTPUT / "inventory_movements.csv"

    movement_number = 0
    transfer_number = 0
    transfer_count = 0
    movement_buffer = []

    with movement_path.open(
        "w", encoding="utf-8", newline=""
    ) as movement_file:
        pd.DataFrame(columns=MOVEMENT_COLUMNS).to_csv(
            movement_file, index=False
        )

        while movement_number < movement_count:
            remaining = movement_count - movement_number

            # Ten percent of opportunities attempt a complete transfer.
            can_transfer = (
                len(location_ids) >= 2 and remaining >= 2
            )

            if can_transfer and rng.random() < 0.10:
                sku_id = rng.choice(sku_ids)
                source, destination = rng.sample(location_ids, 2)

                source_key = (sku_id, source)
                destination_key = (sku_id, destination)

                quantity = rng.randint(1, 5)

                # Never make a valid baseline transfer from insufficient
                # physical stock.
                if current[source_key] < quantity:
                    continue

                transfer_number += 1
                transfer_id = f"TRF-2026-{transfer_number:08d}"
                timestamp = event_timestamp(rng)

                movement_buffer.extend([
                    {
                        "movement_id": make_movement_id(
                            movement_number + 1
                        ),
                        "sku_id": sku_id,
                        "location_id": source,
                        "movement_type": "TRANSFER_OUT",
                        "quantity": quantity,
                        "event_time": timestamp,
                        "reference_id": transfer_id,
                        "transfer_id": transfer_id,
                        "status": "POSTED",
                    },
                    {
                        "movement_id": make_movement_id(
                            movement_number + 2
                        ),
                        "sku_id": sku_id,
                        "location_id": destination,
                        "movement_type": "TRANSFER_IN",
                        "quantity": quantity,
                        "event_time": timestamp,
                        "reference_id": transfer_id,
                        "transfer_id": transfer_id,
                        "status": "POSTED",
                    },
                ])

                current[source_key] -= quantity
                current[destination_key] += quantity

                movement_number += 2
                transfer_count += 1

            else:
                sku_id = rng.choice(sku_ids)
                location_id = rng.choice(location_ids)
                key = (sku_id, location_id)

                quantity = rng.randint(1, 5)

                movement_type = rng.choices(
                    [
                        "RECEIPT",
                        "SALE",
                        "RETURN",
                        "ADJUSTMENT",
                    ],
                    weights=[35, 40, 15, 10],
                    k=1,
                )[0]

                if (
                    movement_type == "SALE"
                    and current[key] < quantity
                ):
                    movement_type = "RECEIPT"

                # ADJUSTMENT means a positive stock correction here.
                # Damaged-stock write-offs will be modelled separately.
                if movement_type in {
                    "RECEIPT",
                    "RETURN",
                    "ADJUSTMENT",
                }:
                    current[key] += quantity
                else:
                    current[key] -= quantity

                movement_number += 1

                movement_buffer.append({
                    "movement_id": make_movement_id(
                        movement_number
                    ),
                    "sku_id": sku_id,
                    "location_id": location_id,
                    "movement_type": movement_type,
                    "quantity": quantity,
                    "event_time": event_timestamp(rng),
                    "reference_id": f"EVT-{movement_number:08d}",
                    "transfer_id": None,
                    "status": "POSTED",
                })

            if len(movement_buffer) >= batch_size:
                pd.DataFrame(
                    movement_buffer, columns=MOVEMENT_COLUMNS
                ).to_csv(
                    movement_file,
                    index=False,
                    header=False,
                )
                movement_buffer.clear()

        if movement_buffer:
            pd.DataFrame(
                movement_buffer, columns=MOVEMENT_COLUMNS
            ).to_csv(
                movement_file,
                index=False,
                header=False,
            )

    # Write balances in batches to limit peak memory usage.
    balance_columns = [
        "balance_id",
        "sku_id",
        "location_id",
        "opening_on_hand",
        "recorded_on_hand",
        "on_hand",
        "reserved",
        "blocked",
        "safety_stock",
        "channel_buffer",
        "as_of",
    ]

    with balance_path.open(
        "w", encoding="utf-8", newline=""
    ) as balance_file:
        pd.DataFrame(columns=balance_columns).to_csv(
            balance_file, index=False
        )

        balance_buffer = []

        for sku_id in sku_ids:
            for location_id in location_ids:
                key = (sku_id, location_id)
                final_quantity = current[key]

                balance_buffer.append({
                    "balance_id": f"BAL-{sku_id}-{location_id}",
                    "sku_id": sku_id,
                    "location_id": location_id,
                    "opening_on_hand": opening[key],
                    "recorded_on_hand": final_quantity,
                    "on_hand": final_quantity,
                    "reserved": 0,
                    "blocked": 0,
                    "safety_stock": safety_stock[sku_id],
                    "channel_buffer": channel_buffer[sku_id],
                    "as_of": "2026-10-29T00:00:00Z",
                })

                if len(balance_buffer) >= batch_size:
                    pd.DataFrame(
                        balance_buffer, columns=balance_columns
                    ).to_csv(
                        balance_file,
                        index=False,
                        header=False,
                    )
                    balance_buffer.clear()

        if balance_buffer:
            pd.DataFrame(
                balance_buffer, columns=balance_columns
            ).to_csv(
                balance_file,
                index=False,
                header=False,
            )

    return movement_number, transfer_count


def generate_orders(args, skus, locations, rng):
    """Generate orders with valid references and available-stock checks.

    Orders that cannot obtain a policy-compliant reservation remain NEW
    without a reservation. This avoids silently overselling in the baseline.
    """
    orders = []
    lines = []
    reservations = []
    shipments = []

    sku_ids = [row["sku_id"] for row in skus]
    location_ids = [row["location_id"] for row in locations]

    safety = {
        row["sku_id"]: row["safety_stock"] for row in skus
    }
    buffer = {
        row["sku_id"]: row["channel_buffer"] for row in skus
    }

    balances = pd.read_csv(
        OUTPUT / "inventory_balances.csv",
        usecols=[
            "sku_id",
            "location_id",
            "recorded_on_hand",
        ],
    )

    available = {
        (row.sku_id, row.location_id): max(
            0,
            int(row.recorded_on_hand)
            - safety[row.sku_id]
            - buffer[row.sku_id],
        )
        for row in balances.itertuples(index=False)
    }

    for i in range(1, args.orders + 1):
        order_id = make_order_id(i)
        line_id = f"LINE-{i:08d}-01"
        sku_id = rng.choice(sku_ids)
        requested_quantity = rng.randint(1, 3)
        timestamp_day = rng.randint(1, 28)
        timestamp = f"2026-10-{timestamp_day:02d}T10:00:00Z"

        # Search for a location with sufficient policy-available stock.
        location_id = None

        for candidate in rng.sample(
            location_ids, len(location_ids)
        ):
            if available[(sku_id, candidate)] >= requested_quantity:
                location_id = candidate
                break

        # If the sampled SKU has no suitable location, try another SKU.
        if location_id is None:
            candidates = list(sku_ids)
            rng.shuffle(candidates)

            for candidate_sku in candidates:
                for candidate_location in rng.sample(
                    location_ids, len(location_ids)
                ):
                    if (
                        available[(candidate_sku, candidate_location)]
                        >= requested_quantity
                    ):
                        sku_id = candidate_sku
                        location_id = candidate_location
                        break

                if location_id is not None:
                    break

        orders.append({
            "order_id": order_id,
            "channel": rng.choice(["ONLINE", "MARKETPLACE"]),
            "order_time": timestamp,
            "status": "NEW" if location_id is None else "ALLOCATED",
        })

        # Keep an order line even when stock is unavailable.
        if location_id is None:
            location_id = rng.choice(location_ids)
            lines.append({
                "order_line_id": line_id,
                "order_id": order_id,
                "sku_id": sku_id,
                "quantity": requested_quantity,
                "fulfillment_location_id": location_id,
            })
            continue

        lines.append({
            "order_line_id": line_id,
            "order_id": order_id,
            "sku_id": sku_id,
            "quantity": requested_quantity,
            "fulfillment_location_id": location_id,
        })

        reservation_id = f"RES-{order_id}-01"

        reservations.append({
            "reservation_id": reservation_id,
            "order_line_id": line_id,
            "sku_id": sku_id,
            "location_id": location_id,
            "quantity": requested_quantity,
            "created_at": timestamp,
            "expires_at": f"2026-10-{timestamp_day:02d}T12:00:00Z",
            "status": "ACTIVE",
        })

        # Reserve the quantity so later orders cannot reuse it.
        available[(sku_id, location_id)] -= requested_quantity

        shipments.append({
            "shipment_id": make_shipment_id(i),
            "order_id": order_id,
            "location_id": location_id,
            "status": "PENDING",
            "created_at": timestamp,
        })

    write_csv(orders, "orders")
    write_csv(lines, "order_lines")
    write_csv(reservations, "reservations")
    write_csv(shipments, "shipments")


def generate(args):
    """Run the complete reproducible data-generation workflow."""
    OUTPUT.mkdir(parents=True, exist_ok=True)

    rng = random.Random(args.seed)

    products, skus, locations, rules = build_master_data(
        args.skus, args.locations, rng
    )

    write_csv(products, "products")
    write_csv(skus, "skus")
    write_csv(locations, "locations")
    write_csv(rules, "replenishment_rules")

    movement_count, transfer_pairs = generate_movements(
        skus,
        locations,
        args.movements,
        rng,
        args.batch_size,
    )

    generate_orders(args, skus, locations, rng)

    files = sorted(
        path
        for path in OUTPUT.iterdir()
        if path.is_file() and path.name != "source_manifest.json"
    )

    checksums = {
        path.name: file_checksum(path) for path in files
    }

    manifest = {
        "seed": args.seed,
        "products": len(products),
        "skus": len(skus),
        "locations": len(locations),
        "movements": movement_count,
        "orders": args.orders,
        "transfer_pairs": transfer_pairs,
        "opening_balance_policy": (
            "Opening stock plus posted signed movement quantities"
        ),
        "baseline_reconciliation": (
            "Recorded balances derived from the generated movement ledger"
        ),
        "source": "Synthetic data generated locally",
        "checksums_sha256": checksums,
        "notes": [
            "Ground-truth fixtures are stored separately from baseline inputs.",
            "Four anomaly fixtures are generated by src.anomaly_injector.",
            "Run src.validate_dataset to validate the clean baseline.",
            "Transfer timing validation requires separate dispatch and receipt events.",
            "ATP is not exhaustively validated for every inventory balance.",
        ],
    }

    (OUTPUT / "source_manifest.json").write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )

    print(json.dumps({
        key: value
        for key, value in manifest.items()
        if key != "checksums_sha256"
    }, indent=2))


def main():
    """Parse CLI arguments and run the generator."""
    parser = argparse.ArgumentParser(
        description="Generate deterministic synthetic inventory data."
    )
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--skus", type=int, default=100)
    parser.add_argument("--locations", type=int, default=10)
    parser.add_argument("--movements", type=int, default=500)
    parser.add_argument("--orders", type=int, default=100)
    parser.add_argument("--batch-size", type=int, default=10000)

    args = parser.parse_args()

    if min(
        args.skus,
        args.locations,
        args.movements,
        args.orders,
        args.batch_size,
    ) < 1:
        parser.error("All scale values must be positive.")

    generate(args)


if __name__ == "__main__":
    main()
