
"""Verify row counts across generated CSV, JSON, and SQLite exports."""

import json
import sqlite3
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CSV_DIR = ROOT / "data" / "generated"
JSON_DIR = ROOT / "data" / "json"
SQL_DIR = ROOT / "data" / "sql"

TABLES = [
    "products",
    "skus",
    "locations",
    "inventory_balances",
    "inventory_movements",
    "orders",
    "order_lines",
    "reservations",
    "shipments",
    "replenishment_rules",
]


def verify():
    errors = []
    db_path = SQL_DIR / "inventory_seed.sqlite"
    sql_path = SQL_DIR / "inventory_seed.sql"

    if not db_path.exists():
        errors.append(f"Missing SQLite database: {db_path}")
    if not sql_path.exists() or sql_path.stat().st_size == 0:
        errors.append(f"Missing or empty SQL script: {sql_path}")

    if errors:
        raise SystemExit("\n".join(errors))

    with sqlite3.connect(db_path) as connection:
        for table in TABLES:
            csv_path = CSV_DIR / f"{table}.csv"
            json_path = JSON_DIR / f"{table}.json"

            if not csv_path.exists() or not json_path.exists():
                errors.append(f"{table}: missing CSV or JSON file")
                continue

            csv_count = sum(1 for _ in csv_path.open(encoding="utf-8")) - 1
            with json_path.open(encoding="utf-8") as file:
                json_records = json.load(file)
            json_count = len(json_records)

            try:
                sql_count = connection.execute(
                    f'SELECT COUNT(*) FROM "{table}"'
                ).fetchone()[0]
            except sqlite3.Error as exc:
                errors.append(f"{table}: SQLite query failed: {exc}")
                continue

            print(
                f"{table}: CSV={csv_count:,}, "
                f"JSON={json_count:,}, SQLite={sql_count:,}"
            )

            if not (csv_count == json_count == sql_count):
                errors.append(
                    f"{table}: row-count mismatch "
                    f"(CSV={csv_count}, JSON={json_count}, SQLite={sql_count})"
                )

    if errors:
        raise SystemExit("\n".join(errors))

    print("\nPASS: all exported table row counts match.")


if __name__ == "__main__":
    verify()
