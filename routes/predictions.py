"""Predicciones: página del módulo y API JSON que ejecuta el modelo en vivo."""
from flask import Blueprint, jsonify, render_template, request

from database.models import Product
from routes import get_or_404, get_prediction_service, json_error
from services import inventory_service
from services.prediction_service import ModelNotAvailableError
from services.validators import FormValidator, ValidationError

predictions_bp = Blueprint("predictions", __name__, url_prefix="/predictions")


@predictions_bp.get("/")
def index():
    products = Product.query.order_by(Product.name).all()
    return render_template("predictions/index.html", products=products,
                           selected_id=request.args.get("product_id", type=int),
                           metadata=get_prediction_service().metadata)


@predictions_bp.get("/api/history/<int:product_id>")
def history(product_id):
    product = get_or_404(Product, product_id)
    days = max(7, min(request.args.get("days", 90, type=int), 365))
    # Termina ayer: el pronóstico empieza hoy (las ventas de hoy ya se descuentan de la demanda de hoy)
    return jsonify({"product_id": product.id,
                    **inventory_service.daily_sales_totals(days, product.id, include_today=False)})


@predictions_bp.post("/api/forecast")
def forecast():
    """Predicción completa de un producto (demanda, agotamiento, riesgo y factores)."""
    data = request.get_json(silent=True) or request.form
    try:
        form = FormValidator(data)
        product_id = form.integer("product_id", "El producto", min_value=1)
        horizon = form.integer("horizon", "El horizonte", required=False, min_value=14, max_value=90)
        form.raise_if_errors()
        product = get_or_404(Product, product_id)
        return jsonify(get_prediction_service().product_prediction(product, horizon=horizon))
    except (ValidationError, ModelNotAvailableError) as error:
        return json_error(error)


@predictions_bp.post("/api/predict")
def predict_single():
    """Predicción de un día a partir de las 9 variables de entrada (útil para pruebas y demostración)."""
    try:
        return jsonify(get_prediction_service().predict_units(request.get_json(silent=True) or {}))
    except (ValidationError, ModelNotAvailableError) as error:
        return json_error(error)


@predictions_bp.get("/api/model")
def model_info():
    service = get_prediction_service()
    return jsonify({"available": service.available, "error": service.load_error, "metadata": service.metadata})
