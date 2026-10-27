# Data Schema and Relationships

## Entity relationships

- Product 1-to-many SKU
- SKU 1-to-many InventoryBalance
- Location 1-to-many InventoryBalance
- SKU 1-to-many InventoryMovement
- Location 1-to-many InventoryMovement
- Location may reference a parent Location
- Order 1-to-many OrderLine
- SKU 1-to-many OrderLine
- Location 1-to-many OrderLine through fulfillment_location_id
- OrderLine 1-to-many Reservation
- Order 1-to-many Shipment
- SKU 1-to-1 ReplenishmentRule in the generated baseline

## Inventory balance grain

InventoryBalance represents one SKU at one location. The generated baseline contains 5,000 SKUs and 100 locations, yielding 500,000 balance records.

## Movement ledger

Each movement has a unique movement_id, SKU, location, type, quantity, event timestamp, and status. Transfer movements include a transfer identifier linking the source and destination movements.

The baseline generator writes completed transfer pairs. This is a simplifying assumption: it does not model a complete asynchronous dispatch-to-receipt workflow.

## Inventory calculations

Ledger-derived on-hand:

opening_on_hand + signed sum of eligible posted movements

ATP follows the inventory engine policy and deducts applicable reservations, blocked stock, safety stock, and channel buffers. Inbound stock is only eligible under the engine's inbound policy.

## Integrity requirements

- Primary identifiers are unique and non-empty.
- Foreign-key references resolve to existing records, except explicitly nullable fields such as parent_location_id.
- Quantities must be valid and positive where required.
- Lifecycle timestamps and states must be consistent.
- Transfer pairs must agree on SKU and quantity and use different locations.
- Recorded inventory must reconcile with the movement ledger in the clean baseline.

## Storage and exports

- data/generated: baseline CSV inputs and source manifest.
- data/json: JSON array exports of each table.
- data/sql/inventory_seed.sqlite: local SQLite database.
- data/sql/inventory_seed.sql: generated SQL seed script.
- data/ground_truth: anomaly labels and fixture details.

The current SQLite exporter creates tables from CSV-inferred values; it does not declare or enforce all primary-key, foreign-key, enum, and check constraints in the database schema.
