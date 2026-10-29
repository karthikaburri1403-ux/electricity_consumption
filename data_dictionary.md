# Data Dictionary: Electricity Consumption Analysis System

Database: `electricity_db` (MySQL 8.0.16+)

## Relationships

- One **consumer** has many **meters** (`meters.consumer_id` → `consumers.consumer_id`).
- One **meter** has many **readings** (`meter_readings.meter_id` → `meters.meter_id`).
- Foreign keys use the default `RESTRICT` rule: a consumer with meters, or a meter with readings, cannot be deleted. The API reports this as 409 Conflict.

## Table: consumers

A customer who uses electricity.

| Column | Type | Key | Null | Description |
|---|---|---|---|---|
| `consumer_id` | INT, auto-increment | Primary key | No | Unique internal id |
| `consumer_code` | VARCHAR(20) | Unique | No | Business code, e.g. C001 |
| `consumer_type` | ENUM('Residential','Commercial','Industrial') | | No | Category of the consumer |
| `region` | VARCHAR(50) | | No | Region where the consumer is located |

## Table: meters

A physical meter that belongs to one consumer.

| Column | Type | Key | Null | Description |
|---|---|---|---|---|
| `meter_id` | INT, auto-increment | Primary key | No | Unique internal id |
| `consumer_id` | INT | Foreign key → `consumers.consumer_id` | No | Owner of the meter |
| `meter_code` | VARCHAR(20) | Unique | No | Business code, e.g. M001 |

## Table: meter_readings

A dated cumulative reading taken from a meter.

| Column | Type | Key | Null | Description |
|---|---|---|---|---|
| `reading_id` | INT, auto-increment | Primary key | No | Unique internal id |
| `meter_id` | INT | Foreign key → `meters.meter_id` | No | Meter the reading belongs to |
| `reading_date` | DATE | Part of unique pair | No | Date the reading was taken |
| `cumulative_kwh` | DECIMAL(12,2) | | No | Total kWh shown on the meter at that date |

Constraints:

- `uq_meter_date`: UNIQUE (`meter_id`, `reading_date`). A meter has at most one reading per date.
- `chk_kwh_nonnegative`: CHECK (`cumulative_kwh` >= 0). A reading cannot be negative.

## Business rules enforced by the API

These rules cannot be expressed in the schema, so `routes/readings.py` checks them.

| Rule | Result |
|---|---|
| `reading_date` cannot be in the future | 400 |
| `cumulative_kwh` must be a finite, non-negative number | 400 |
| The meter must exist | 404 |
| A new reading must be dated after the meter's latest reading | 409 |
| A value lower than the previous reading is accepted and flagged as a possible meter reset | 201 with a warning |
| An edited reading must stay between its neighbouring readings in date | 409 |

## Derived data (not stored)

Consumption, summaries and high-usage flags are calculated from the readings when requested.

| Concept | Rule |
|---|---|
| Consumption of a period | Later reading minus earlier reading |
| Meter reset | A negative difference. The period is marked `reset` and excluded from totals |
| Monthly/yearly total | Sum of valid periods, grouped by the month or year in which the period starts |
| High usage | A valid period above (average of the meter's valid periods × factor). The factor defaults to 1.5 and is set by `HIGH_USAGE_FACTOR` in `.env` or `?factor=` in the URL |