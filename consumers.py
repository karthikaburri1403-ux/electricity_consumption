from flask import Blueprint, jsonify, request
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from db import engine
from utils import error

consumers_bp = Blueprint("consumers", __name__, url_prefix="/consumers")

VALID_TYPES = {"Residential", "Commercial", "Industrial"}


def validate_consumer(data):
    """Check the input. Returns (clean_values, None) or (None, error_message)."""
    code = str(data.get("consumer_code", "")).strip()
    ctype = data.get("consumer_type")
    region = str(data.get("region", "")).strip()

    if not code or len(code) > 20:
        return None, "consumer_code is required (max 20 characters)"
    if ctype not in VALID_TYPES:
        return None, f"consumer_type must be one of {sorted(VALID_TYPES)}"
    if not region or len(region) > 50:
        return None, "region is required (max 50 characters)"

    return {"code": code, "type": ctype, "region": region}, None


def find_consumer(conn, consumer_id):
    return conn.execute(
        text("SELECT consumer_id, consumer_code, consumer_type, region "
             "FROM consumers WHERE consumer_id = :id"),
        {"id": consumer_id},
    ).mappings().first()


# ---------- CREATE ----------
@consumers_bp.post("")
def create_consumer():
    data = request.get_json(silent=True) or {}
    clean, problem = validate_consumer(data)
    if problem:
        return error(problem, 400)

    try:
        with engine.begin() as conn:
            result = conn.execute(
                text("INSERT INTO consumers (consumer_code, consumer_type, region) "
                     "VALUES (:code, :type, :region)"),
                clean,
            )
            new_id = result.lastrowid
    except IntegrityError:
        return error("consumer_code already exists", 409)

    return jsonify(message="consumer created", consumer_id=new_id), 201


# ---------- READ (all) ----------
@consumers_bp.get("")
def list_consumers():
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT consumer_id, consumer_code, consumer_type, region "
                 "FROM consumers ORDER BY consumer_id")
        ).mappings().all()
    return jsonify([dict(r) for r in rows])


# ---------- READ (one) ----------
@consumers_bp.get("/<int:consumer_id>")
def get_consumer(consumer_id):
    with engine.connect() as conn:
        row = find_consumer(conn, consumer_id)
    if row is None:
        return error("consumer not found", 404)
    return jsonify(dict(row))


# ---------- UPDATE ----------
@consumers_bp.put("/<int:consumer_id>")
def update_consumer(consumer_id):
    data = request.get_json(silent=True) or {}
    clean, problem = validate_consumer(data)
    if problem:
        return error(problem, 400)

    try:
        with engine.begin() as conn:
            if find_consumer(conn, consumer_id) is None:
                return error("consumer not found", 404)
            conn.execute(
                text("UPDATE consumers SET consumer_code=:code, consumer_type=:type, "
                     "region=:region WHERE consumer_id=:id"),
                {**clean, "id": consumer_id},
            )
    except IntegrityError:
        return error("consumer_code already exists", 409)

    return jsonify(message="consumer updated")


# ---------- DELETE ----------
@consumers_bp.delete("/<int:consumer_id>")
def delete_consumer(consumer_id):
    try:
        with engine.begin() as conn:
            if find_consumer(conn, consumer_id) is None:
                return error("consumer not found", 404)
            conn.execute(text("DELETE FROM consumers WHERE consumer_id=:id"),
                         {"id": consumer_id})
    except IntegrityError:
        return error("consumer still has meters; delete the meters first", 409)

    return jsonify(message="consumer deleted")
