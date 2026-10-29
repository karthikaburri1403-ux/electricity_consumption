from flask import Flask, jsonify
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from db import engine
from routes.consumers import consumers_bp
from routes.meters import meters_bp
from utils import error
from routes.readings import readings_bp
from routes.analysis import analysis_bp
from routes.validation import validation_bp
from routes.charts import charts_bp

def create_app():
    app = Flask(__name__)
    app.register_blueprint(consumers_bp)
    app.register_blueprint(meters_bp)
    app.register_blueprint(readings_bp)
    app.register_blueprint(analysis_bp)
    app.register_blueprint(validation_bp)
    app.register_blueprint(charts_bp)

    @app.get("/health")
    def health():
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return jsonify(status="ok", database="connected")
        except SQLAlchemyError:
            return error("database unreachable", 503)

    @app.errorhandler(404)
    def not_found(e):
        return error("route not found", 404)

    @app.errorhandler(405)
    def wrong_method(e):
        return error("method not allowed for this route", 405)

    @app.errorhandler(SQLAlchemyError)
    def database_error(e):
        app.logger.exception("Database error")
        return error("a database error occurred", 500)

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True)