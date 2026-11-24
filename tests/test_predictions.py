"""
Pruebas del modelo y de las predicciones:
carga del modelo, ausencia de reentrenamiento, predict(), validación, cálculo
de agotamiento, integración Flask + SQLite + modelo y datos no vistos.
"""
import hashlib
import os
from datetime import date, datetime, timedelta

import numpy as np
import pytest
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.pipeline import Pipeline

from app import create_app
from config import Config, TestConfig
from services import inventory_service
from ml.features import INPUT_FEATURES
from ml.generate_dataset import generate_dataset
from services.prediction_service import ModelNotAvailableError, PredictionService
from services.validators import ValidationError
from tests.conftest import add_daily_sales, product_by_name

VALID_FEATURES = {"price": 4300, "discount_percentage": 0, "promotion": 0, "previous_sales": 50,
                  "average_sales_7d": 48, "average_sales_30d": 47, "day_of_week": 5, "month": 11,
                  "category": "Lácteos"}


def service_of(app):
    return app.extensions["prediction_service"]


# ------------------------------------------------------------ carga del modelo
def test_model_file_and_metadata_exist():
    assert os.path.exists(Config.MODEL_PATH)
    assert os.path.exists(Config.MODEL_METADATA_PATH)


def test_model_loads_as_pipeline_with_metadata(app):
    service = service_of(app)
    assert service.available and service.load_error is None
    assert isinstance(service.model, Pipeline)
    assert isinstance(service.model.named_steps["regressor"], LinearRegression)
    metadata = service.metadata
    assert metadata["input_features"] == INPUT_FEATURES
    for key in ("training_date", "model_version", "metrics", "dataset"):
        assert key in metadata
    assert metadata["dataset"]["total_records"] >= 30000
    assert {"MAE", "RMSE", "R2"} <= set(metadata["metrics"]["test"])


def test_flask_startup_does_not_train_the_model(monkeypatch):
    def forbidden_fit(*args, **kwargs):
        raise AssertionError("La aplicación intentó entrenar el modelo")

    with open(Config.MODEL_PATH, "rb") as file:
        digest_before = hashlib.sha256(file.read()).hexdigest()
    monkeypatch.setattr(LinearRegression, "fit", forbidden_fit)
    monkeypatch.setattr(Pipeline, "fit", forbidden_fit)

    app = create_app(TestConfig)          # si se entrenara, fallaría aquí
    result = service_of(app).predict_units(VALID_FEATURES)
    assert result["units_sold"] > 0
    with open(Config.MODEL_PATH, "rb") as file:
        assert hashlib.sha256(file.read()).hexdigest() == digest_before


def test_missing_model_is_reported_and_app_keeps_working(tmp_path):
    class NoModelConfig(TestConfig):
        MODEL_PATH = str(tmp_path / "no_existe.joblib")

    app = create_app(NoModelConfig)
    service = service_of(app)
    assert not service.available and "No se encontró el modelo" in service.load_error
    with pytest.raises(ModelNotAvailableError):
        service.predict_units(VALID_FEATURES)
    client = app.test_client()
    assert client.get("/products/").status_code == 200
    response = client.post("/predictions/api/predict", json=VALID_FEATURES)
    assert response.status_code == 503


# -------------------------------------------------------------- predict()
def test_predict_units_returns_structured_result(app):
    result = service_of(app).predict_units(VALID_FEATURES)
    assert set(result) >= {"units_sold", "raw_prediction", "clipped_to_zero", "features", "model_version"}
    assert result["units_sold"] >= 0 and not result["clipped_to_zero"]


def test_prediction_responds_to_inputs(app):
    service = service_of(app)
    base = service.predict_units(VALID_FEATURES)["units_sold"]
    higher_history = service.predict_units({**VALID_FEATURES, "average_sales_30d": 90, "average_sales_7d": 90})
    promotion = service.predict_units({**VALID_FEATURES, "promotion": 1, "discount_percentage": 30})
    assert higher_history["units_sold"] > base
    assert promotion["units_sold"] > base      # el modelo aprendió que el descuento aumenta la demanda


def test_negative_predictions_are_clipped_to_zero(app):
    service = service_of(app)

    class NegativeModel:
        def predict(self, features):
            return np.array([-4.2] * len(features))

    service_copy = PredictionService.__new__(PredictionService)
    service_copy.__dict__.update(service.__dict__, model=NegativeModel())
    result = service_copy.predict_units(VALID_FEATURES)
    assert result["units_sold"] == 0 and result["clipped_to_zero"]


@pytest.mark.parametrize("override, field", [
    ({"price": -1}, "price"), ({"day_of_week": 7}, "day_of_week"), ({"month": 13}, "month"),
    ({"category": "Ropa"}, "category"), ({"average_sales_7d": "abc"}, "average_sales_7d"),
    ({"promotion": 0, "discount_percentage": 20}, "discount_percentage"),
])
def test_invalid_prediction_inputs_are_rejected(app, override, field):
    with pytest.raises(ValidationError) as error:
        service_of(app).predict_units({**VALID_FEATURES, **override})
    assert field in error.value.errors


def test_explanation_adds_up_to_model_prediction(app):
    explanation = service_of(app).explain([40, 45, 50] * 10, "Snacks", 3000)
    total = explanation["intercept"] + sum(factor["contribution"] for factor in explanation["factors"])
    assert total == pytest.approx(explanation["raw_prediction"], abs=0.05)


# ------------------------------------------------------- cálculo de agotamiento
def test_days_to_stockout_with_known_demand(app):
    analysis = service_of(app).analyze_stock([10.0] * 30, current_stock=55, minimum_stock=10, lead_time=7,
                                              start_date=date(2026, 11, 25))
    assert analysis["days_to_stockout"] == 5.5
    assert analysis["stockout_date"] == "2026-11-30"
    assert analysis["risk"] == "alto" and analysis["stockout_before_replenishment"]
    assert analysis["reorder_point"] == 80                       # 7 días × 10 + mínimo 10
    assert analysis["recommended_quantity"] == 10 * (7 + 14) + 10 - 55


def test_stock_risk_levels(app):
    service = service_of(app)
    assert service.analyze_stock([5.0] * 30, 0, 5, 3)["risk"] == "crítico"
    assert service.analyze_stock([5.0] * 30, 40, 5, 3)["risk"] == "medio"      # 8 días < 3 + 7
    low = service.analyze_stock([1.0] * 60, 500, 5, 3)
    assert low["risk"] == "bajo" and low["days_to_stockout"] is None and low["stockout_beyond_horizon"]


# ---------------------------------------------- integración Flask + SQLite + modelo
def test_forecast_api_end_to_end(seeded_client, seeded_app):
    with seeded_app.app_context():
        product_id = product_by_name("Leche entera 1 L").id
    response = seeded_client.post("/predictions/api/forecast", json={"product_id": product_id, "horizon": 30})
    assert response.status_code == 200
    data = response.get_json()
    assert len(data["forecast"]["units"]) == 30 and min(data["forecast"]["units"]) >= 0
    assert data["analysis"]["current_stock"] > 0
    assert data["analysis"]["risk"] in ("bajo", "medio", "alto", "crítico")
    assert data["explanation"]["factors"]
    assert seeded_client.post("/predictions/api/forecast", json={"product_id": 99999}).status_code == 404


def test_forecast_uses_recent_sales_history(app):
    service = service_of(app)
    with app.app_context():
        product = product_by_name("Producto A")
        empty = service.forecast_products([product], horizon=14)[product.id]
        assert any("No hay ventas en los últimos 14 días" in warning for warning in empty["warnings"])
        add_daily_sales(product, [30] * 45)
        busy = service.forecast_products([product], horizon=14)[product.id]
        assert len(busy["history"]) >= 45 and busy["daily"][:7].mean() > empty["daily"][:7].mean() + 10


def test_new_product_without_history_gets_warning(app):
    with app.app_context():
        product = inventory_service.create_product({"name": "Nuevo", "category": "Bebidas", "price": 2500,
                                                    "current_stock": 30, "minimum_stock": 5, "supplier_id": 1})
        result = service_of(app).forecast_products([product], horizon=14)[product.id]
        assert result["history"] == []
        assert any("0 día(s) de historial" in warning for warning in result["warnings"])
        assert (result["daily"] >= 0).all()


def test_sale_registered_today_is_reflected_in_prediction(seeded_client, seeded_app):
    with seeded_app.app_context():
        product = product_by_name("Gaseosa cola 1.5 L")
        product_id, stock = product.id, product.current_stock
    before = seeded_client.post("/predictions/api/forecast", json={"product_id": product_id}).get_json()
    seeded_client.post("/sales/new", data={"product_id": product_id, "quantity": "10"})
    after = seeded_client.post("/predictions/api/forecast", json={"product_id": product_id}).get_json()
    assert after["analysis"]["current_stock"] == stock - 10
    assert after["forecast"]["sold_today"] == before["forecast"]["sold_today"] + 10
    expected_today = max(before["analysis"]["demand_today"] - 10, 0)
    assert after["analysis"]["demand_today"] == pytest.approx(expected_today, abs=0.05)


# -------------------------------------------------- datos no usados en el entrenamiento
@pytest.mark.parametrize("seed", [7, 123])
def test_model_generalizes_to_unseen_synthetic_data(app, seed):
    """Nueva muestra sintética: otra semilla, otros productos y fechas de 2026 (posteriores al entrenamiento)."""
    data = generate_dataset(seed=seed, n_products=12, n_days=240, start_date="2026-01-01")
    data = data[data["stockout"] == 0]
    predictions = np.clip(service_of(app).model.predict(data[INPUT_FEATURES]), 0, None)
    mae = mean_absolute_error(data["units_sold"], predictions)
    r2 = r2_score(data["units_sold"], predictions)
    baseline_r2 = r2_score(data["units_sold"], data["average_sales_7d"])
    assert r2 > 0.70 and r2 > baseline_r2
    assert mae / data["units_sold"].mean() < 0.40


def test_stale_history_warning(app, client):
    """Si el historial lleva días sin ventas, la interfaz advierte que hay que recargar los datos."""
    with app.app_context():
        product = product_by_name("Producto A")
        add_daily_sales(product, [3, 4, 5], end_day=datetime.now() - timedelta(days=6))
    page = client.get("/").get_data(as_text=True)
    assert "días recientes sin ventas" in page

    with app.app_context():
        add_daily_sales(product_by_name("Producto A"), [4])  # venta de ayer
    page = client.get("/").get_data(as_text=True)
    assert "días recientes sin ventas" not in page
