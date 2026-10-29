from flask import jsonify


def error(message, status):
    """Every error in the API has the same shape: {"error": "..."}"""
    return jsonify(error=message), status