import pandas as pd
import math
import os
from flask import Blueprint, jsonify
from sqlalchemy import text

from db import engine
from utils import error
from flask import Blueprint, jsonify, request
import numpy as np

analysis_bp = Blueprint("analysis", __name__, url_prefix="/analysis")


def calculate_consumption(rows):
    """Turn a meter's readings into consumption per period.

    A period runs from one reading to the next. If the value drops,
    the pair is a meter reset: it is marked 'reset' and not counted.
    """
    if len(rows) < 2:
        return []

    df = pd.DataFrame([dict(r) for r in rows])
    df["cumulative_kwh"] = df["cumulative_kwh"].astype(float)
    df["period_start"] = df["reading_date"].shift(1)
    df["consumption_kwh"] = df["cumulative_kwh"].diff()
    df = df.dropna(subset=["period_start"])

    periods = []
    for r in df.itertuples():
        is_reset = r.consumption_kwh < 0
        periods.append({
            "period_start": r.period_start.isoformat(),
            "period_end": r.reading_date.isoformat(),
            "consumption_kwh": None if is_reset else round(r.consumption_kwh, 2),
            "status": "reset" if is_reset else "valid",
        })
    return periods


@analysis_bp.get("/consumption/<int:meter_id>")
def meter_consumption(meter_id):
    with engine.connect() as conn:
        meter = conn.execute(
            text("SELECT 1 FROM meters WHERE meter_id = :m"), {"m": meter_id}
        ).first()
        if meter is None:
            return error("meter not found", 404)

        rows = conn.execute(
            text("SELECT reading_date, cumulative_kwh FROM meter_readings "
                 "WHERE meter_id = :m ORDER BY reading_date"),
            {"m": meter_id},
        ).mappings().all()

    return jsonify(meter_id=meter_id, periods=calculate_consumption(rows))
def summarize(periods, level):
    """Group consumption periods by month ('2026-01') or year ('2026')."""
    if not periods:
        return []

    df = pd.DataFrame(periods)
    cut = 7 if level == "monthly" else 4
    df["label"] = df["period_start"].str[:cut]

    valid = df[df["status"] == "valid"]
    totals = valid.groupby("label")["consumption_kwh"].agg(["sum", "count"])
    resets = df[df["status"] == "reset"].groupby("label").size()

    result = []
    for label in sorted(df["label"].unique()):
        has_valid = label in totals.index
        result.append({
            "period": label,
            "total_kwh": round(float(totals.loc[label, "sum"]), 2) if has_valid else 0.0,
            "valid_periods": int(totals.loc[label, "count"]) if has_valid else 0,
            "reset_periods": int(resets.get(label, 0)),
        })
    return result


@analysis_bp.get("/summary/<int:meter_id>")
def meter_summary(meter_id):
    level = request.args.get("level", "monthly")
    if level not in ("monthly", "yearly"):
        return error("level must be 'monthly' or 'yearly'", 400)

    with engine.connect() as conn:
        meter = conn.execute(
            text("SELECT 1 FROM meters WHERE meter_id = :m"), {"m": meter_id}
        ).first()
        if meter is None:
            return error("meter not found", 404)

        rows = conn.execute(
            text("SELECT reading_date, cumulative_kwh FROM meter_readings "
                 "WHERE meter_id = :m ORDER BY reading_date"),
            {"m": meter_id},
        ).mappings().all()

    periods = calculate_consumption(rows)
    return jsonify(meter_id=meter_id, level=level, summary=summarize(periods, level))
def default_factor():
    """Read the threshold factor from .env, falling back to 1.5."""
    try:
        return float(os.getenv("HIGH_USAGE_FACTOR", "1.5"))
    except ValueError:
        return 1.5


def find_high_usage(periods, factor):
    """Return (average, limit, flagged_periods) for one meter."""
    valid = [p for p in periods if p["status"] == "valid"]
    if not valid:
        return 0.0, 0.0, []

    average = sum(p["consumption_kwh"] for p in valid) / len(valid)
    limit = average * factor

    flagged = [
        {**p, "times_average": round(p["consumption_kwh"] / average, 2)}
        for p in valid
        if p["consumption_kwh"] > limit
    ]
    return round(average, 2), round(limit, 2), flagged


@analysis_bp.get("/high-usage/<int:meter_id>")
def high_usage(meter_id):
    raw = request.args.get("factor")
    if raw is None:
        factor = default_factor()
    else:
        try:
            factor = float(raw)
        except ValueError:
            return error("factor must be a number", 400)
    if not math.isfinite(factor) or factor <= 0:
        return error("factor must be a positive number", 400)

    with engine.connect() as conn:
        meter = conn.execute(
            text("SELECT 1 FROM meters WHERE meter_id = :m"), {"m": meter_id}
        ).first()
        if meter is None:
            return error("meter not found", 404)

        rows = conn.execute(
            text("SELECT reading_date, cumulative_kwh FROM meter_readings "
                 "WHERE meter_id = :m ORDER BY reading_date"),
            {"m": meter_id},
        ).mappings().all()

    periods = calculate_consumption(rows)
    average, limit, flagged = find_high_usage(periods, factor)
    return jsonify(meter_id=meter_id, factor=factor,
                   average_kwh=average, limit_kwh=limit, flagged=flagged)
def add_changes(periods):
    """Add change vs the previous period, using NumPy.

    A period right after a reset has no valid previous value,
    so its change is None.
    """
    values = np.array(
        [np.nan if p["status"] == "reset" else p["consumption_kwh"] for p in periods],
        dtype=float,
    )
    previous = np.concatenate(([np.nan], values[:-1]))
    change = values - previous
    with np.errstate(divide="ignore", invalid="ignore"):
        percent = change / previous * 100

    result = []
    for p, c, pc in zip(periods, change, percent):
        result.append({
            **p,
            "change_kwh": round(float(c), 2) if np.isfinite(c) else None,
            "change_pct": round(float(pc), 1) if np.isfinite(pc) else None,
        })
    return result


@analysis_bp.get("/change/<int:meter_id>")
def meter_change(meter_id):
    with engine.connect() as conn:
        meter = conn.execute(
            text("SELECT 1 FROM meters WHERE meter_id = :m"), {"m": meter_id}
        ).first()
        if meter is None:
            return error("meter not found", 404)
        rows = conn.execute(
            text("SELECT reading_date, cumulative_kwh FROM meter_readings "
                 "WHERE meter_id = :m ORDER BY reading_date"),
            {"m": meter_id},
        ).mappings().all()

    return jsonify(meter_id=meter_id, periods=add_changes(calculate_consumption(rows)))