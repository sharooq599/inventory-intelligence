
"""Export generated inventory CSV tables to JSON and SQLite SQL seed data."""

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


def export_json():
    """Export each CSV table as a JSON array of records."""
    JSON_DIR.mkdir(parents=True, exist_ok=True)

    for table in TABLES:
        csv_path = CSV_DIR / f"{table}.csv"
        if not csv_path.exists():
            raise FileNotFoundError(f"Missing required input: {csv_path}")

        frame = pd.read_csv(csv_path)
        records = json.loads(frame.to_json(orient="records", date_format="iso"))

        output_path = JSON_DIR / f"{table}.json"
        output_path.write_text(
            json.dumps(records, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"JSON: {output_path.relative_to(ROOT)} ({len(records)} rows)")


def export_sqlite():
    """Load CSV tables into a portable SQLite database."""
    SQL_DIR.mkdir(parents=True, exist_ok=True)
    db_path = SQL_DIR / "inventory_seed.sqlite"

    if db_path.exists():
        db_path.unlink()

    with sqlite3.connect(db_path) as connection:
        for table in TABLES:
            csv_path = CSV_DIR / f"{table}.csv"
            if not csv_path.exists():
                raise FileNotFoundError(f"Missing required input: {csv_path}")

            frame = pd.read_csv(csv_path)
            frame.to_sql(table, connection, if_exists="replace", index=False)
            print(f"SQLite: {table} ({len(frame)} rows)")

        # Add useful indexes for common inventory joins and lookups.
        connection.executescript("""
            CREATE INDEX idx_skus_product_id
                ON skus(product_id);
            CREATE INDEX idx_balances_sku_location
                ON inventory_balances(sku_id, location_id);
            CREATE INDEX idx_movements_sku_location
                ON inventory_movements(sku_id, location_id);
            CREATE INDEX idx_order_lines_order_id
                ON order_lines(order_id);
            CREATE INDEX idx_reservations_order_line
                ON reservations(order_line_id);
        """)

    # Also produce a portable SQL script with INSERT statements.
    # The SQLite database remains the primary, directly executable seed artifact.
    sql_path = SQL_DIR / "inventory_seed.sql"
    with sqlite3.connect(db_path) as connection:
        with sql_path.open("w", encoding="utf-8") as output:
            output.write("-- Generated from data/generated CSV files.\n")
            output.write("-- Import into SQLite; schema types are inferred from CSV data.\n")
            for table in TABLES:
                output.write(f"\n-- Table: {table}\n")
                query = f'SELECT * FROM "{table}"'
                cursor = connection.execute(query)
                columns = [description[0] for description in cursor.description]
                output.write(
                    f'CREATE TABLE IF NOT EXISTS "{table}" ('
                    + ", ".join(f'"{col}" TEXT' for col in columns)
                    + ");\n"
                )
                quoted_columns = ", ".join(f'"{col}"' for col in columns)
                placeholders = ", ".join("?" for _ in columns)
                rows = cursor.fetchall()
                for row in rows:
                    # SQLite's quote() safely escapes strings and preserves NULL.
                    values = []
                    for value in row:
                        if value is None:
                            values.append("NULL")
                        elif isinstance(value, (int, float)):
                            values.append(str(value))
                        else:
                            escaped = str(value).replace("'", "''")
                            values.append("'" + escaped + "'")
                    output.write(
                        f'INSERT INTO "{table}" ({quoted_columns}) '
                        f"VALUES ({', '.join(values)});\n"
                    )

    print(f"\nSQLite database: {db_path.relative_to(ROOT)}")
    print(f"SQL script:      {sql_path.relative_to(ROOT)}")


def main():
    export_json()
    export_sqlite()
    print("\nAll exports completed.")


if __name__ == "__main__":
    main()
