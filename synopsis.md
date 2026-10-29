# Synopsis: Electricity Consumption Analysis System (Project 18)

## Problem

Utilities record cumulative meter readings on different dates. Raw readings are hard to use: consumption has to be worked out from consecutive readings, meters get reset or replaced, and unusual usage is easy to miss. This project stores consumers, meters and readings, and turns them into reliable consumption figures.

## Objectives

1. Manage consumer and meter records.
2. Record dated meter readings with validation.
3. Calculate consumption from consecutive valid readings.
4. Summarize usage by month and by year.
5. Identify unusually high usage using a configurable threshold.

## Technology

| Part | Choice | Why |
|---|---|---|
| Backend | Python, Flask | Small, clear REST API |
| Database | MySQL | Relational data with foreign keys and constraints |
| Data access | SQLAlchemy (parameterized SQL) | Protects against SQL injection |
| Analysis | Pandas | Sorting, differences and grouping of time series |
| Version control | Git, GitHub | Team collaboration |

## Design

Three tables: `consumers`, `meters` and `meter_readings`. One consumer has many meters, and one meter has many readings (see `docs/er_diagram.png` and `docs/data_dictionary.md`).

The API has four groups of endpoints: `/consumers`, `/meters`, `/readings` (all full CRUD) and `/analysis` (consumption, summary, high-usage).

Consumption is calculated when requested and is not stored, so it can never disagree with the readings.

## Key business rules

- A new reading must be dated after the meter's latest reading and cannot be in the future.
- Readings cannot be negative, and a meter has one reading per date.
- A reading lower than the previous one is accepted but flagged as a possible meter reset. The affected period is excluded from totals, which prevents negative consumption.
- A period counts toward the month in which it starts.
- A period is "unusually high" when it exceeds the meter's average valid consumption multiplied by a factor. The factor defaults to 1.5 and can be changed in `.env` or per request.
- Deleting a consumer with meters, or a meter with readings, is refused (409), which protects history.

## Testing

The API was tested with PowerShell requests covering valid input, missing or wrong-typed fields, unknown records, duplicates, out-of-order dates and meter resets. Sample data covers normal usage (M001), a usage spike (M002) and a meter reset (M003).

## Limitations and future work

- No login or user roles.
- Readings are cumulative kWh only, with no tariffs or billing.
- The average used for high-usage detection includes the spike itself. A median would be more robust.
- A reset is detected only when the value drops, so a replaced meter that restarts above the old value would not be noticed.
- The API has no web front end. A dashboard with charts is a natural next step.