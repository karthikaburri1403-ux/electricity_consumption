import os

from flask import Blueprint, jsonify, request
from sqlalchemy import text

from db import engine
from utils import error

validation_bp = Blueprint("validation", __name__, url_prefix="/validation")


def env_number(name, default):
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return float(default)


def read_settings():
    """Returns (max_gap_days, meter_max, None) or (None, None, message)."""
    raw = request.args.get("max_gap_days")
    try:
        gap = float(raw) if raw is not None else env_number("MAX_GAP_DAYS", 45)
    except ValueError:
        return None, None, "max_gap_days must be a number"
    if gap <= 0:
        return None, None, "max_gap_days must be positive"
    return gap, env_number("METER_MAX_KWH", 100000), None


def validate_readings(rows, max_gap_days, meter_max):
    """List the problems found in one meter's readings (oldest first)."""
    if len(rows) < 2:
        return [{"type": "insufficient_data", "date": None,
                 "detail": f"{len(rows)} reading(s); at least 2 are needed"}]

    issues = []
    for prev, cur in zip(rows, rows[1:]):
        old, new = float(prev["cumulative_kwh"]), float(cur["cumulative_kwh"])
        days = (cur["reading_date"] - prev["reading_date"]).days
        when = cur["reading_date"].isoformat()

        if new < old:
            kind = "possible_rollover" if old >= 0.9 * meter_max else "possible_reset"
            issues.append({"type": kind, "date": when,
                           "detail": f"value fell from {old} to {new} kWh; "
                                     "period excluded from consumption"})
        elif new == old:
            issues.append({"type": "no_consumption", "date": when,
                           "detail": f"value unchanged at {new} kWh"})
        if days > max_gap_days:
            issues.append({"type": "long_gap", "date": when,
                           "detail": f"{days} days since the previous reading "
                                     f"(limit {max_gap_days:g})"})
    return issues


def report_for(conn, meter_id, meter_code, max_gap, meter_max):
    rows = conn.execute(
        text("SELECT reading_date, cumulative_kwh FROM meter_readings "
             "WHERE meter_id = :m ORDER BY reading_date"),
        {"m": meter_id},
    ).mappings().all()
    issues = validate_readings(rows, max_gap, meter_max)
    return {"meter_id": meter_id, "meter_code": meter_code,
            "readings_checked": len(rows),
            "status": "ok" if not issues else "issues found",
            "issues": issues}


@validation_bp.get("/<int:meter_id>")
def meter_validation(meter_id):
    max_gap, meter_max, problem = read_settings()
    if problem:
        return error(problem, 400)
    with engine.connect() as conn:
        code = conn.execute(
            text("SELECT meter_code FROM meters WHERE meter_id = :m"), {"m": meter_id}
        ).scalar()
        if code is None:
            return error("meter not found", 404)
        return jsonify(report_for(conn, meter_id, code, max_gap, meter_max))


@validation_bp.get("")
def all_validation():
    max_gap, meter_max, problem = read_settings()
    if problem:
        return error(problem, 400)
    with engine.connect() as conn:
        meters = conn.execute(
            text("SELECT meter_id, meter_code FROM meters ORDER BY meter_id")
        ).mappings().all()
        reports = [report_for(conn, m["meter_id"], m["meter_code"], max_gap, meter_max)
                   for m in meters]
    return jsonify(meters_checked=len(reports),
                   meters_with_issues=sum(1 for r in reports if r["issues"]),
                   reports=reports)