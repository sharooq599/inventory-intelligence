# Data Dictionary

All data is synthetic and generated locally using a deterministic random seed.

## Products
| Column | Meaning |
|---|---|
| product_id | Unique product identifier |
| product_name | Generated product name |
| category | Product category |
| status | Product status |

## SKUs
| Column | Meaning |
|---|---|
| sku_id | Unique stock-keeping-unit identifier |
| product_id | Parent product reference |
| sku_name | Generated SKU name |
| unit | Unit of measure |
| safety_stock | Quantity protected as safety stock |
| channel_buffer | Quantity withheld for channel policy |
| status | SKU status |

## Locations
| Column | Meaning |
|---|---|
| location_id | Unique inventory location |
| location_name | Generated location name |
| location_type | Warehouse, store, or online fulfillment |
| parent_location_id | Optional parent location |
| status | Location status |

## Inventory Balances
| Column | Meaning |
|---|---|
| balance_id | Unique SKU/location balance identifier |
| sku_id | SKU reference |
| location_id | Location reference |
| opening_on_hand | Starting physical quantity |
| recorded_on_hand | Recorded ending quantity |
| on_hand | Reported on-hand quantity |
| reserved | Quantity reserved |
| blocked | Quantity blocked from fulfillment |
| safety_stock | Safety-stock policy quantity |
| channel_buffer | Channel-protected quantity |
| as_of | Balance snapshot timestamp |

## Inventory Movements
| Column | Meaning |
|---|---|
| movement_id | Unique movement identifier |
| sku_id | Affected SKU |
| location_id | Affected location |
| movement_type | Receipt, sale, return, transfer, or adjustment |
| quantity | Positive movement magnitude |
| event_time | Movement event timestamp |
| reference_id | Related business reference, when available |
| transfer_id | Transfer-pair identifier, when applicable |
| status | Movement status |

Movement sign convention: RECEIPT, RETURN, TRANSFER_IN, and positive ADJUSTMENT increase stock; SALE and TRANSFER_OUT decrease stock. The current implementation treats ADJUSTMENT as positive.

## Orders
| Column | Meaning |
|---|---|
| order_id | Unique order identifier |
| channel | Sales channel |
| order_time | Order timestamp |
| status | Order lifecycle state |

## Order Lines
| Column | Meaning |
|---|---|
| order_line_id | Unique order-line identifier |
| order_id | Parent order |
| sku_id | Requested SKU |
| quantity | Requested quantity |
| fulfillment_location_id | Intended fulfillment location |

## Reservations
| Column | Meaning |
|---|---|
| reservation_id | Unique reservation identifier |
| order_line_id | Related order line |
| sku_id | Reserved SKU |
| location_id | Reserving location |
| quantity | Reserved quantity |
| created_at | Creation timestamp |
| expires_at | Expiration timestamp |
| status | Active, expired, released, or fulfilled |

## Shipments
| Column | Meaning |
|---|---|
| shipment_id | Unique shipment identifier |
| order_id | Related order |
| location_id | Shipping location |
| status | Shipment lifecycle state |
| created_at | Creation timestamp |

## Replenishment Rules
| Column | Meaning |
|---|---|
| rule_id | Unique rule identifier |
| sku_id | SKU governed by the rule |
| reorder_point | Stock threshold for replenishment |
| reorder_quantity | Suggested replenishment quantity |
| allow_inbound_atp | Whether eligible inbound stock can count toward ATP |
| effective_date | Rule start date |

## Derived inventory concepts

- On-hand: opening stock plus signed posted movement quantities.
- Available-to-promise (ATP): on-hand less applicable reservations, blocked stock, safety stock, and channel buffers, subject to the inventory engine's eligibility rules.
- Reconciliation mismatch: difference between ledger-derived stock and recorded stock.
- Ground truth: labels and fixture details stored separately from baseline model inputs.

## Notes and limitations

This dictionary describes the implemented dataset. Confirm column names against the generated CSV headers before extending the schema. The SQLite export currently infers column types from CSV values and does not enforce relational foreign-key constraints.
