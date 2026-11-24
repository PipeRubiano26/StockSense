"""Pruebas del simulador de escenarios y de la generación de alertas."""
from datetime import date, timedelta

import numpy as np
import pytest

from database import db
from database.models import Alert, PurchaseOrder
from services import alert_service, inventory_service
from tests.conftest import add_daily_sales, product_by_name


def run(client, product_id, **params):
    response = client.post("/scenarios/api/run", json={"product_id": product_id, **params})
    assert response.status_code == 200, response.get_json()
    return {scenario["key"]: scenario for scenario in response.get_json()["scenarios"]}


def test_scenarios_compare_model_and_assumptions(seeded_client, seeded_app):
    with seeded_app.app_context():
        product_id = product_by_name("Leche entera 1 L").id
    scenarios = run(seeded_client, product_id, discount=25, promotion_days=7, demand_increase=30,
                    demand_decrease=20, supplier_delay=5, horizon=30)
    assert set(scenarios) == {"normal", "promotion", "high_demand", "low_demand", "supplier_delay"}

    normal = np.array(scenarios["normal"]["daily_demand"])
    promotion = np.array(scenarios["promotion"]["daily_demand"])
    # La promoción cambia las variables del modelo: más demanda durante los 7 días de promoción
    assert promotion[:7].sum() > normal[:7].sum()
    assert scenarios["promotion"]["source"] == "modelo"
    # Alta/baja demanda son supuestos manuales explícitos sobre la predicción normal
    assert np.allclose(scenarios["high_demand"]["daily_demand"], normal * 1.3, atol=0.02)
    assert np.allclose(scenarios["low_demand"]["daily_demand"], normal * 0.8, atol=0.02)
    assert scenarios["high_demand"]["source"] == "modelo + supuesto"
    assert any("HIPÓTESIS" in text for text in scenarios["high_demand"]["assumptions"])
    # El retraso solo cambia el tiempo de entrega
    delay = scenarios["supplier_delay"]["analysis"]
    assert delay["lead_time_days"] == scenarios["normal"]["analysis"]["lead_time_days"] + 5
    assert delay["recommended_quantity"] >= scenarios["normal"]["analysis"]["recommended_quantity"]
    for scenario in scenarios.values():
        assert scenario["assumptions"]
        assert {"demand_7d", "days_to_stockout", "stockout_date", "risk", "recommended_quantity"} <= set(scenario["analysis"])


def test_higher_demand_means_earlier_stockout(seeded_client, seeded_app):
    with seeded_app.app_context():
        product_id = product_by_name("Agua mineral 600 ml").id
    scenarios = run(seeded_client, product_id, demand_increase=50, demand_decrease=50)
    normal_days = scenarios["normal"]["analysis"]["days_to_stockout"]
    assert scenarios["high_demand"]["analysis"]["days_to_stockout"] < normal_days
    assert scenarios["low_demand"]["analysis"]["days_to_stockout"] > normal_days


def test_scenario_unknown_product_returns_404(seeded_client):
    assert seeded_client.post("/scenarios/api/run", json={"product_id": 99999}).status_code == 404


def test_alerts_are_created_updated_and_resolved(app):
    service = app.extensions["prediction_service"]
    with app.app_context():
        product = product_by_name("Producto B")          # stock 5, mínimo 8, entrega 4 días
        add_daily_sales(product, [6] * 40)
        alert_service.refresh_alerts(service)
        active = {a.alert_type for a in Alert.query.filter_by(product_id=product.id, status="activa")}
        assert {"stock_bajo", "quiebre_antes_reposicion", "reposicion"} <= active

        alert_service.refresh_alerts(service)            # recalcular no duplica alertas
        assert Alert.query.filter_by(product_id=product.id, alert_type="stock_bajo", status="activa").count() == 1

        inventory_service.register_movement(product, {"movement_type": "entrada", "quantity": 900,
                                                      "description": "reposición"})
        alert_service.refresh_alerts(service)
        still_active = {a.alert_type for a in Alert.query.filter_by(product_id=product.id, status="activa")}
        assert not still_active & {"stock_bajo", "quiebre_antes_reposicion", "reposicion"}
        assert Alert.query.filter_by(product_id=product.id, status="resuelta").count() >= 3


def test_delayed_purchase_order_creates_supplier_alert(app):
    service = app.extensions["prediction_service"]
    with app.app_context():
        product = product_by_name("Producto A")
        db.session.add(PurchaseOrder(product=product, supplier=product.supplier, quantity=20,
                                     order_date=date.today() - timedelta(days=10),
                                     expected_delivery=date.today() - timedelta(days=2), status="pendiente"))
        db.session.commit()
        alert_service.refresh_alerts(service)
        alert = Alert.query.filter_by(product_id=product.id, alert_type="retraso_proveedor", status="activa").one()
        assert "2 días de retraso" in alert.message


@pytest.mark.parametrize("url", ["/", "/products/", "/sales/", "/suppliers/", "/predictions/", "/scenarios/", "/alerts/"])
def test_all_modules_render_with_seeded_data(seeded_client, url):
    response = seeded_client.get(url)
    assert response.status_code == 200 and "StockSense" in response.get_data(as_text=True)
