import math
from datetime import date, datetime

from flask import Blueprint, jsonify, request
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from db import engine
from utils import error

readings_bp = Blueprint("readings", __name__, url_prefix="/readings")


def validate_reading(data):
    """Returns (clean_values, None) or (None, error_message)."""
    try:
        meter_id = int(data.get("meter_id"))
    except (ValueError, TypeError):
        return None, "meter_id is required and must be an integer"

    try:
        reading_date = datetime.strptime(str(data.get("reading_date")), "%Y-%m-%d").date()
    except ValueError:
        return None, "reading_date is required in YYYY-MM-DD format"

    try:
        kwh = float(data.get("cumulative_kwh"))
    except (ValueError, TypeError):
        return None, "cumulative_kwh is required and must be a number"

    if not math.isfinite(kwh) or kwh < 0:
        return None, "cumulative_kwh must be a non-negative number"
    if reading_date > date.today():
        return None, "reading_date cannot be in the future"

    return {"meter_id": meter_id, "date": reading_date, "kwh": kwh}, None


# ---------- CREATE ----------
@readings_bp.post("")
def create_reading():
    data = request.get_json(silent=True) or {}
    clean, problem = validate_reading(data)
    if problem:
        return error(problem, 400)

    try:
        with engine.begin() as conn:
            meter = conn.execute(
                text("SELECT 1 FROM meters WHERE meter_id = :m"),
                {"m": clean["meter_id"]},
            ).first()
            if meter is None:
                return error("meter not found", 404)

            latest = conn.execute(
                text("SELECT reading_date, cumulative_kwh FROM meter_readings "
                     "WHERE meter_id = :m ORDER BY reading_date DESC LIMIT 1"),
                {"m": clean["meter_id"]},
            ).mappings().first()

            if latest and clean["date"] <= latest["reading_date"]:
                return error(
                    f"reading_date must be after the latest reading ({latest['reading_date']})",
                    409,
                )

            result = conn.execute(
                text("INSERT INTO meter_readings (meter_id, reading_date, cumulative_kwh) "
                     "VALUES (:m, :d, :k)"),
                {"m": clean["meter_id"], "d": clean["date"], "k": clean["kwh"]},
            )
            new_id = result.lastrowid
    except IntegrityError:
        return error("a reading for this meter and date already exists", 409)

    response = {"message": "reading recorded", "reading_id": new_id}
    if latest and clean["kwh"] < float(latest["cumulative_kwh"]):
        response["warning"] = ("value is lower than the previous reading; "
                               "possible meter reset or rollover")
    return jsonify(response), 201


# ---------- READ (all, optional ?meter_id=1) ----------
@readings_bp.get("")
def list_readings():
    meter_id = request.args.get("meter_id", type=int)

    sql = ("SELECT r.reading_id, r.meter_id, m.meter_code, "
           "r.reading_date, r.cumulative_kwh "
           "FROM meter_readings r "
           "JOIN meters m ON m.meter_id = r.meter_id ")
    params = {}
    if meter_id is not None:
        sql += "WHERE r.meter_id = :m "
        params["m"] = meter_id
    sql += "ORDER BY r.meter_id, r.reading_date"

    with engine.connect() as conn:
        rows = conn.execute(text(sql), params).mappings().all()

    return jsonify([
        {**dict(r),
         "reading_date": r["reading_date"].isoformat(),
         "cumulative_kwh": float(r["cumulative_kwh"])}
        for r in rows
    ])


# ---------- READ (one) ----------
@readings_bp.get("/<int:reading_id>")
def get_reading(reading_id):
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT r.reading_id, r.meter_id, m.meter_code, "
                 "r.reading_date, r.cumulative_kwh "
                 "FROM meter_readings r "
                 "JOIN meters m ON m.meter_id = r.meter_id "
                 "WHERE r.reading_id = :id"),
            {"id": reading_id},
        ).mappings().first()
    if row is None:
        return error("reading not found", 404)
    return jsonify({**dict(row),
                    "reading_date": row["reading_date"].isoformat(),
                    "cumulative_kwh": float(row["cumulative_kwh"])})


# ---------- UPDATE ----------
@readings_bp.put("/<int:reading_id>")
def update_reading(reading_id):
    data = request.get_json(silent=True) or {}
    clean, problem = validate_reading(data)
    if problem:
        return error(problem, 400)

    try:
        with engine.begin() as conn:
            current = conn.execute(
                text("SELECT meter_id, reading_date FROM meter_readings "
                     "WHERE reading_id = :id"),
                {"id": reading_id},
            ).mappings().first()
            if current is None:
                return error("reading not found", 404)
            if current["meter_id"] != clean["meter_id"]:
                return error("a reading cannot be moved to another meter", 400)

            # The new date must stay between the readings before and after it.
            prev_date = conn.execute(
                text("SELECT MAX(reading_date) FROM meter_readings "
                     "WHERE meter_id = :m AND reading_date < :old"),
                {"m": clean["meter_id"], "old": current["reading_date"]},
            ).scalar()
            next_date = conn.execute(
                text("SELECT MIN(reading_date) FROM meter_readings "
                     "WHERE meter_id = :m AND reading_date > :old"),
                {"m": clean["meter_id"], "old": current["reading_date"]},
            ).scalar()
            if prev_date and clean["date"] <= prev_date:
                return error(f"reading_date must be after the previous reading ({prev_date})", 409)
            if next_date and clean["date"] >= next_date:
                return error(f"reading_date must be before the next reading ({next_date})", 409)

            conn.execute(
                text("UPDATE meter_readings SET reading_date = :d, cumulative_kwh = :k "
                     "WHERE reading_id = :id"),
                {"d": clean["date"], "k": clean["kwh"], "id": reading_id},
            )
    except IntegrityError:
        return error("a reading for this meter and date already exists", 409)

    return jsonify(message="reading updated")


# ---------- DELETE ----------
@readings_bp.delete("/<int:reading_id>")
def delete_reading(reading_id):
    with engine.begin() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM meter_readings WHERE reading_id = :id"),
            {"id": reading_id},
        ).first()
        if exists is None:
            return