"""
Simulador de escenarios.

Cada escenario indica de dónde salen sus números:
  * "modelo": el resultado sale directamente de predict() con las variables del escenario.
  * "modelo + supuesto": se toma la predicción del modelo y se aplica una hipótesis
    manual del usuario (por ejemplo, +30 % de demanda). Ese efecto NO lo aprendió el modelo.
"""
from datetime import date, timedelta

import numpy as np

from services import inventory_service
from services.validators import FormValidator

DEFAULTS = {"discount": 20, "promotion_days": 7, "demand_increase": 30,
            "demand_decrease": 30, "supplier_delay": 5, "horizon": 60}


def validate_parameters(data):
    form = FormValidator(data)
    values = {
        "product_id": form.integer("product_id", "El producto", min_value=1),
        "discount": form.number("discount", "El descuento", required=False, min_value=1, max_value=90),
        "promotion_days": form.integer("promotion_days", "La duración de la promoción", required=False,
                                       min_value=1, max_value=90),
        "demand_increase": form.number("demand_increase", "El incremento de demanda", required=False,
                                       min_value=0, max_value=300),
        "demand_decrease": form.number("demand_decrease", "La reducción de demanda", required=False,
                                       min_value=0, max_value=95),
        "supplier_delay": form.integer("supplier_delay", "El retraso del proveedor", required=False,
                                       min_value=0, max_value=60),
        "horizon": form.integer("horizon", "El horizonte", required=False, min_value=14, max_value=90),
    }
    form.raise_if_errors()
    return {key: (DEFAULTS[key] if value is None and key in DEFAULTS else value) for key, value in values.items()}


def run_scenarios(prediction_service, product, params):
    today = date.today()
    horizon = params["horizon"]
    lead_time = product.supplier.delivery_days
    pending = inventory_service.pending_orders([product.id])

    base = prediction_service.forecast_products([product], horizon=horizon, today=today)[product.id]
    promo = prediction_service.forecast_products([product], horizon=horizon, today=today,
                                                 discount=params["discount"],
                                                 promotion_days=params["promotion_days"])[product.id]
    base_daily = base["daily"]
    increase, decrease = params["demand_increase"] / 100, params["demand_decrease"] / 100

    definitions = [
        {"key": "normal", "name": "Normal", "demand": base_daily, "lead_time": lead_time,
         "source": "modelo",
         "assumptions": [f"Precio actual ({product.price:,.0f} COP)", "Sin promoción",
                         f"Entrega del proveedor en {lead_time} días"]},
        {"key": "promotion", "name": f"Promoción {params['discount']:g} %", "demand": promo["daily"],
         "lead_time": lead_time, "source": "modelo",
         "assumptions": [f"Descuento del {params['discount']:g} % durante {params['promotion_days']} días",
                         "El descuento cambia las variables de entrada del modelo (promotion = 1, "
                         "discount_percentage); el aumento de demanda es el que aprendió el modelo",
                         f"Entrega del proveedor en {lead_time} días"]},
        {"key": "high_demand", "name": f"Alta demanda +{params['demand_increase']:g} %",
         "demand": base_daily * (1 + increase), "lead_time": lead_time, "source": "modelo + supuesto",
         "assumptions": [f"HIPÓTESIS MANUAL: la demanda del escenario normal se multiplica por {1 + increase:.2f}",
                         "Este incremento no proviene del modelo; representa un supuesto del usuario",
                         f"Entrega del proveedor en {lead_time} días"]},
        {"key": "low_demand", "name": f"Baja demanda −{params['demand_decrease']:g} %",
         "demand": base_daily * (1 - decrease), "lead_time": lead_time, "source": "modelo + supuesto",
         "assumptions": [f"HIPÓTESIS MANUAL: la demanda del escenario normal se multiplica por {1 - decrease:.2f}",
                         "Esta reducción no proviene del modelo; representa un supuesto del usuario",
                         f"Entrega del proveedor en {lead_time} días"]},
        {"key": "supplier_delay", "name": f"Retraso proveedor +{params['supplier_delay']} días",
         "demand": base_daily, "lead_time": lead_time + params["supplier_delay"], "source": "modelo",
         "assumptions": ["Demanda del escenario normal (modelo)",
                         f"Tiempo de entrega de {lead_time} + {params['supplier_delay']} = "
                         f"{lead_time + params['supplier_delay']} días (supuesto de retraso)"]},
    ]

    scenarios = []
    for definition in definitions:
        demand = np.asarray(definition.pop("demand"))
        analysis = prediction_service.analyze_stock(demand, product.current_stock, product.minimum_stock,
                                                    definition["lead_time"], pending, today)
        scenarios.append({**definition, "analysis": analysis,
                          "daily_demand": [round(float(value), 2) for value in demand]})

    return {
        "product": {"id": product.id, "name": product.name, "current_stock": product.current_stock,
                    "minimum_stock": product.minimum_stock, "supplier": product.supplier.name,
                    "lead_time": lead_time},
        "parameters": params,
        "dates": [(today + timedelta(days=i)).isoformat() for i in range(horizon)],
        "scenarios": scenarios,
        "warnings": sorted(set(base["warnings"] + promo["warnings"])),
    }
