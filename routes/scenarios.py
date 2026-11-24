"""Simulador de escenarios."""
from flask import Blueprint, jsonify, render_template, request

from database.models import Product
from routes import get_or_404, get_prediction_service, json_error
from services import scenario_service
from services.prediction_service import ModelNotAvailableError
from services.validators import ValidationError

scenarios_bp = Blueprint("scenarios", __name__, url_prefix="/scenarios")


@scenarios_bp.get("/")
def index():
    return render_template("scenarios/index.html", products=Product.query.order_by(Product.name).all(),
                           selected_id=request.args.get("product_id", type=int),
                           defaults=scenario_service.DEFAULTS)


@scenarios_bp.post("/api/run")
def run():
    try:
        params = scenario_service.validate_parameters(request.get_json(silent=True) or request.form)
        product = get_or_404(Product, params["product_id"])
        return jsonify(scenario_service.run_scenarios(get_prediction_service(), product, params))
    except (ValidationError, ModelNotAvailableError) as error:
        return json_error(error)
