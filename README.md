# Inventory Intelligence

A reproducible synthetic inventory-data project built with Python. It generates inventory master data and transactions, calculates inventory availability, validates data integrity, and provides anomaly fixtures for testing.

## Project status

- Full-scale synthetic baseline generated using seed `20261022`.
- 5,000 SKUs across 100 locations.
- 1,000,000 inventory movements and 500,000 inventory balances.
- 50,000 orders, order lines, reservations, and shipments.
- Baseline dataset validation completed with `PASS`, zero reported issues, and zero inventory reconciliation mismatches.
- Automated test suite: 13 tests passed in the latest recorded full-suite run.
- Anomaly fixture tests: 4 passed in the latest recorded run.
- Export verification: CSV, JSON, and SQLite row counts match for all 10 tables.

These results reflect the runs completed during development. Re-run the commands in this README to verify the current checkout. Passing tests do not establish that every business rule or possible anomaly is covered.

## Technology

- Python
- pandas
- pytest
- SQLite
- CSV and JSON

## Project structure

```text
inventory-intelligence/
├── src/
│   ├── generator.py
│   ├── models.py
│   ├── inventory_engine.py
│   ├── validators.py
│   ├── lifecycle_validators.py
│   ├── anomaly_injector.py
│   ├── validate_dataset.py
│   └── export_data.py
├── tests/
├── docs/
│   ├── data_dictionary.md
│   ├── schema.md
│   └── prompt-history.md
├── data/
│   ├── generated/
│   ├── ground_truth/
│   ├── json/
│   └── sql/
├── reports/
├── requirements.txt
└── README.md
```

## Requirements

Use Python 3.10 or later. A compatible Python installation, pip, and sufficient free disk space are required. The full-scale CSV, JSON, SQL, and SQLite outputs can consume substantial disk space.

## Setup

Create and activate a virtual environment.

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## Generate the full-scale baseline

```powershell
python -m src.generator --seed 20261022 --skus 5000 --locations 100 --movements 1000000 --orders 50000 --batch-size 10000
```

The generator writes baseline CSV files to `data/generated/` and creates a source manifest containing dataset counts and checksums.

To generate a smaller development dataset, use smaller values for `--skus`, `--locations`, `--movements`, and `--orders`. Note that generation writes to the same output directory, so back up important outputs first.

## Validate the dataset

```powershell
python -m src.validate_dataset
```

Validation writes:

- `reports/validation_issues.csv`
- `reports/validation_summary.json`

The clean baseline is expected to have no reported validation issues and no inventory reconciliation mismatches.

## Generate anomaly fixtures

```powershell
python -m src.anomaly_injector
```

Fixtures and labels are written under `data/ground_truth/`. Ground-truth labels should remain separate from baseline model inputs. Review each fixture and verify that its anomaly is detected by the intended validation rule.

## Export JSON and SQL/SQLite

```powershell
python -m src.export_data
```

Outputs:

- `data/json/`: one JSON array file per table.
- `data/sql/inventory_seed.sqlite`: SQLite database.
- `data/sql/inventory_seed.sql`: SQL seed script.

The current export process infers table columns from CSV data. The SQLite schema does not enforce all relational and business constraints. Validate row counts after exporting.

## Run automated tests

```powershell
python -m pytest -q
```

Tests cover selected inventory calculations, validators, and anomaly fixtures. A passing test suite does not prove every possible business rule or every generated record is correct.

## Inventory calculation assumptions

- On-hand is calculated from opening stock and signed posted movements.
- Receipts, returns, and transfer-ins increase stock; sales and transfer-outs decrease stock.
- ATP deducts applicable reservations, blocked stock, safety stock, and channel buffers according to the implemented engine policy.
- The baseline uses completed transfer pairs. It does not model every real-world asynchronous dispatch and receipt event.
- Ground-truth fixtures are intentionally separate from the clean baseline.

Review `docs/data_dictionary.md` and `docs/schema.md` for entity descriptions and relationships.

## Known limitations

- Premature-transfer validation is limited by the lifecycle detail represented in the baseline.
- ATP is not yet validated exhaustively for every generated balance by the dataset validation command.
- The current adjustment movement sign convention treats adjustments as positive.
- The SQL exporter does not currently define and enforce all foreign keys, primary keys, enums, or check constraints.
- Synthetic records are for testing and are not representative of any real business or customer.
- Anomaly definitions must be checked against the exact technical assessment wording.

## AI-use disclosure

See `docs/prompt-history.md`. Complete it with the actual prompts submitted to all AI tools used during the project, and accurately document what was reviewed, changed, and verified by the candidate.

## Reproducibility

Use the same seed and CLI parameters to reproduce the same synthetic baseline, provided the code and relevant dependency behavior remain unchanged. Compare the manifest checksums to verify generated file identity.

## License and data

All generated records are synthetic. Add a license only if you intend to grant reuse rights for this repository.
