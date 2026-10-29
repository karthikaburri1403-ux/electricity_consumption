from flask import Blueprint, jsonify, request
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from db import engine
from utils import error

meters_bp = Blueprint("meters", __name__, url_prefix="/meters")


def validate_meter(data):
    """Returns (clean_values, None) or (None, error_message)."""
    code = str(data.get("meter_code", "")).strip()
    if not code or len(code) > 20:
        return None, "meter_code is required (max 20 characters)"

    try:
        consumer_id = int(data.get("consumer_id"))
    except (ValueError, TypeError):
        return None, "consumer_id is required and must be an integer"

    return {"code": code, "consumer_id": consumer_id}, None


def consumer_exists(conn, consumer_id):
    return conn.execute(
        text("SELECT 1 FROM consumers WHERE consumer_id = :id"),
        {"id": consumer_id},
    ).first() is not None


# ---------- CREATE ----------
@meters_bp.post("")
def create_meter():
    data = request.get_json(silent=True) or {}
    clean, problem = validate_meter(data)
    if problem:
        return error(problem, 400)

    try:
        with engine.begin() as conn:
            if not consumer_exists(conn, clean["consumer_id"]):
                return error("consumer_id does not exist", 400)
            result = conn.execute(
                text("INSERT INTO meters (consumer_id, meter_code) "
                     "VALUES (:consumer_id, :code)"),
                clean,
            )
            new_id = result.lastrowid
    except IntegrityError:
        return error("meter_code already exists", 409)

    return jsonify(message="meter created", meter_id=new_id), 201
# ---------- READ (all) ----------
@meters_bp.get("")
def list_meters():
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT m.meter_id, m.meter_code, m.consumer_id, c.consumer_code "
                 "FROM meters m "
                 "JOIN consumers c ON c.consumer_id = m.consumer_id "
                 "ORDER BY m.meter_id")
        ).mappings().all()
    return jsonify([dict(r) for r in rows])
# ---------- READ (one) ----------
@meters_bp.get("/<int:meter_id>")
def get_meter(meter_id):
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT m.meter_id, m.meter_code, m.consumer_id, c.consumer_code "
                 "FROM meters m "
                 "JOIN consumers c ON c.consumer_id = m.consumer_id "
                 "WHERE m.meter_id = :id"),
            {"id": meter_id},
        ).mappings().first()
    if row is None:
        return error("meter not found", 404)
    return jsonify(dict(row))
# ---------- UPDATE ----------
@meters_bp.put("/<int:meter_id>")
def update_meter(meter_id):
    data = request.get_json(silent=True) or {}
    clean, problem = validate_meter(data)
    if problem:
        return error(problem, 400)

    try:
        with engine.begin() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM meters WHERE meter_id = :id"),
                {"id": meter_id},
            ).first()
            if exists is None:
                return error("meter not found", 404)
            if not consumer_exists(conn, clean["consumer_id"]):
                return error("consumer_id does not exist", 400)

            conn.execute(
                text("UPDATE meters SET meter_code = :code, consumer_id = :consumer_id "
                     "WHERE meter_id = :id"),
                {**clean, "id": meter_id},
            )
    except IntegrityError:
        return error("meter_code already exists", 409)

    return jsonify(message="meter updated")
# ---------- DELETE ----------
@meters_bp.delete("/<int:meter_id>")
def delete_meter(meter_id):
    try:
        with engine.begin() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM meters WHERE meter_id = :id"),
                {"id": meter_id},
            ).first()
            if exists is None:
                return error("meter not found", 404)
            conn.execute(text("DELETE FROM meters WHERE meter_id = :id"),
                         {"id": meter_id})
    except IntegrityError:
        return error("meter has readings; delete the readings first", 409)

    return jsonify(message="meter deleted")