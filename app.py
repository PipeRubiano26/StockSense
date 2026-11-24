"""
StockSense — aplicación Flask.

Ejecución:  python app.py      (o)   flask --app app run
Reinicio de datos:  flask --app app init-db --reset
"""
import logging
import os
from datetime import date

import click
from flask import Flask, jsonify, render_template, request

from config import Config
from database import db
from database.models import Alert, Sale
from database.seed import reset_database, seed_database
from routes.health import POD_NAME
from services.prediction_service import PredictionService

logger = logging.getLogger("stocksense")


def create_app(config_class=Config):
    if not logging.getLogger().handlers:  # p. ej. bajo Gunicorn en Kubernetes
        logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    app = Flask(__name__)
    app.config.from_object(config_class)
    db.init_app(app)

    # El modelo se CARGA una vez al iniciar (no se entrena aquí)
    service = PredictionService(app.config["MODEL_PATH"], app.config["MODEL_METADATA_PATH"],
                                horizon=app.config["FORECAST_HORIZON_DAYS"],
                                coverage_days=app.config["COVERAGE_DAYS"])
    app.extensions["prediction_service"] = service
    if service.available:
        logger.info("Modelo cargado: versión %s", service.metadata.get("model_version"))
    else:
        logger.warning(service.load_error)

    from routes.alerts import alerts_bp
    from routes.dashboard import dashboard_bp
    from routes.health import health_bp
    from routes.predictions import predictions_bp
    from routes.products import products_bp
    from routes.sales import sales_bp
    from routes.scenarios import scenarios_bp
    from routes.suppliers import suppliers_bp
    for blueprint in (dashboard_bp, products_bp, sales_bp, suppliers_bp, predictions_bp, scenarios_bp,
                      alerts_bp, health_bp):
        app.register_blueprint(blueprint)

    with app.app_context():
        db.create_all()
        if app.config.get("SEED_ON_STARTUP"):
            _seed_and_refresh(service)

    _register_template_helpers(app)
    _register_error_handlers(app)
    _register_commands(app)
    return app


def _seed_and_refresh(service):
    from services.alert_service import refresh_alerts
    if seed_database():
        logger.info("Datos iniciales cargados")
        refresh_alerts(service)


def _register_template_helpers(app):
    @app.template_filter("money")
    def money(value):
        return "$ " + f"{value or 0:,.0f}".replace(",", ".")

    @app.template_filter("number")
    def number(value, decimals=0):
        text = f"{value or 0:,.{decimals}f}"
        return text.replace(",", "X").replace(".", ",").replace("X", ".")

    @app.context_processor
    def inject_globals():
        # Si el historial lleva días sin ventas, el modelo ve ceros y predice demanda baja
        last_sale = db.session.query(db.func.max(Sale.sale_date)).scalar()
        stale_days = (date.today() - last_sale.date()).days - 1 if last_sale else None
        return {
            "history_last_sale": last_sale,
            "history_stale_days": stale_days if stale_days and stale_days >= 2 else None,
            "active_alert_count": Alert.query.filter_by(status="activa").count(),
            "model_service": app.extensions["prediction_service"],
            # En Kubernetes se muestra qué réplica (pod) atendió la página
            "pod_name": POD_NAME if os.environ.get("KUBERNETES_SERVICE_HOST") else None,
        }


def _wants_json():
    return request.path.startswith("/api") or "/api/" in request.path or request.is_json


def _register_error_handlers(app):
    @app.errorhandler(404)
    def not_found(error):
        if _wants_json():
            return jsonify({"error": "Recurso no encontrado"}), 404
        return render_template("error.html", code=404, message="La página o el registro no existe."), 404

    @app.errorhandler(405)
    def method_not_allowed(error):
        if _wants_json():
            return jsonify({"error": "Método no permitido"}), 405
        return render_template("error.html", code=405, message="Método no permitido."), 405

    @app.errorhandler(500)
    def server_error(error):
        db.session.rollback()
        if _wants_json():
            return jsonify({"error": "Error interno del servidor"}), 500
        return render_template("error.html", code=500, message="Ocurrió un error inesperado."), 500


def _register_commands(app):
    @app.cli.command("init-db")
    @click.option("--reset", is_flag=True, help="Elimina todos los datos y vuelve a cargar los iniciales.")
    def init_db(reset):
        """Crea las tablas y carga los datos iniciales (solo si la base está vacía)."""
        if reset:
            reset_database()
            click.echo("Base de datos reiniciada.")
        service = app.extensions["prediction_service"]
        from services.alert_service import refresh_alerts
        if seed_database():
            refresh_alerts(service)
            click.echo("Datos iniciales cargados (20 productos, 5 proveedores, 12 meses de ventas).")
        else:
            click.echo("La base de datos ya tenía datos; no se duplicaron.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    create_app().run(debug=False, port=5000)
