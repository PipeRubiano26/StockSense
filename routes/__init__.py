"""Funciones compartidas por las rutas."""
from flask import abort, current_app, jsonify

from database import db
from services.alert_service import refresh_alerts
from services.prediction_service import ModelNotAvailableError
from services.validators import ValidationError


def get_prediction_service():
    return current_app.extensions["prediction_service"]


def get_or_404(model, object_id):
    instance = db.session.get(model, object_id)
    if instance is None:
        abort(404)
    return instance


def refresh_product_alerts(*products):
    """Recalcula las alertas después de un cambio de inventario."""
    refresh_alerts(get_prediction_service(), [product for product in products if product is not None])


def json_error(error):
    """Respuesta JSON uniforme para errores de validación o de modelo."""
    if isinstance(error, ValidationError):
        return jsonify({"error": "Datos inválidos", "fields": error.errors}), 400
    if isinstance(error, ModelNotAvailableError):
        return jsonify({"error": str(error)}), 503
    raise error
