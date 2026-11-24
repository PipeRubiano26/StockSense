"""
Servicio de predicción de demanda y agotamiento.

Responsabilidades:
  * Cargar el modelo entrenado (models/demand_model.joblib). NUNCA entrena.
  * Validar y preparar las variables de entrada.
  * Ejecutar predict() y evitar unidades negativas.
  * Estimar días hasta el agotamiento, riesgo y cantidad de reposición.
  * Explicar qué factores influyeron en la predicción (coeficientes lineales).
"""
import json
import math
import os
from datetime import date, timedelta

import joblib
import numpy as np
import pandas as pd

from ml.features import CATEGORICAL_FEATURES, INPUT_FEATURES
from ml.forecasting import build_feature_row, recursive_forecast
from services import inventory_service
from services.validators import FormValidator

HISTORY_WINDOW_DAYS = 60
TRAINED_DISCOUNT_RANGE = (10, 40)

FACTOR_LABELS = {
    "price": "Precio",
    "discount_percentage": "Porcentaje de descuento",
    "promotion": "Promoción activa",
    "previous_sales": "Ventas del día anterior",
    "average_sales_7d": "Promedio de ventas 7 días",
    "average_sales_30d": "Promedio de ventas 30 días",
    "discount_x_avg30": "Descuento × nivel de ventas",
    "weekend_x_avg30": "Fin de semana × nivel de ventas",
    "day_of_week": "Día de la semana",
    "month": "Mes",
    "category": "Categoría",
}
DAY_NAMES = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
RISK_ORDER = {"bajo": 0, "medio": 1, "alto": 2, "crítico": 3}


def _plain(value):
    """Convierte tipos de NumPy (np.int64, np.bool_...) a tipos nativos para poder enviarlos como JSON."""
    return value.item() if isinstance(value, np.generic) else value


class ModelNotAvailableError(Exception):
    """El archivo del modelo no existe o no se pudo cargar."""


class PredictionService:
    def __init__(self, model_path, metadata_path, horizon=90, coverage_days=14):
        self.model_path = model_path
        self.metadata_path = metadata_path
        self.horizon = horizon
        self.coverage_days = coverage_days
        self.model = None
        self.metadata = {}
        self.load_error = None
        self._load()

    # ------------------------------------------------------------ carga
    def _load(self):
        """Carga el Pipeline serializado. Si falla, la app sigue funcionando sin predicciones."""
        if not os.path.exists(self.model_path):
            self.load_error = (f"No se encontró el modelo en {self.model_path}. "
                               "Ejecute el notebook notebooks/StockSense_Model_Training.ipynb.")
            return
        try:
            model = joblib.load(self.model_path)
            if not hasattr(model, "predict"):
                raise TypeError("el archivo no contiene un modelo con método predict()")
            if os.path.exists(self.metadata_path):
                with open(self.metadata_path, encoding="utf-8") as file:
                    self.metadata = json.load(file)
            expected = self.metadata.get("input_features", INPUT_FEATURES)
            if list(expected) != INPUT_FEATURES:
                raise ValueError("las variables del modelo no coinciden con ml/features.py")
            self.model = model
        except Exception as error:  # el error se muestra en la interfaz
            self.load_error = f"No se pudo cargar el modelo: {error}"

    @property
    def available(self):
        return self.model is not None

    def _require_model(self):
        if not self.available:
            raise ModelNotAvailableError(self.load_error)

    @property
    def categories(self):
        return self.metadata.get("categories", [])

    # --------------------------------------------- predicción de un solo día
    def validate_features(self, data):
        """Valida un diccionario con las 9 variables de entrada y devuelve un DataFrame de una fila."""
        form = FormValidator(data)
        values = {
            "price": form.number("price", "price", min_value=0, exclusive_min=True),
            "discount_percentage": form.number("discount_percentage", "discount_percentage", min_value=0, max_value=100),
            "promotion": form.integer("promotion", "promotion", min_value=0, max_value=1),
            "previous_sales": form.number("previous_sales", "previous_sales", min_value=0),
            "average_sales_7d": form.number("average_sales_7d", "average_sales_7d", min_value=0),
            "average_sales_30d": form.number("average_sales_30d", "average_sales_30d", min_value=0),
            "day_of_week": form.integer("day_of_week", "day_of_week", min_value=0, max_value=6),
            "month": form.integer("month", "month", min_value=1, max_value=12),
            "category": (form.choice("category", "category", self.categories) if self.categories
                         else form.text("category", "category")),
        }
        if values["promotion"] == 0 and values["discount_percentage"]:
            form.errors["discount_percentage"] = "Sin promoción el descuento debe ser 0."
        form.raise_if_errors()
        return pd.DataFrame([values], columns=INPUT_FEATURES)

    def predict_units(self, data):
        """Predicción de unidades para un día a partir de variables explícitas."""
        self._require_model()
        features = self.validate_features(data)
        raw = float(self.model.predict(features)[0])
        return {
            "units_sold": round(max(raw, 0.0), 2),
            "raw_prediction": round(raw, 4),
            "clipped_to_zero": raw < 0,
            "features": {key: _plain(value) for key, value in features.iloc[0].items()},
            "model_version": self.metadata.get("model_version"),
        }

    # ------------------------------------------------ pronóstico de productos
    def forecast_products(self, products, horizon=None, discount=0.0, promotion_days=0, today=None):
        """
        Pronóstico recursivo diario para varios productos (ver ml/forecasting.py).
        `discount` y `promotion_days` modifican las VARIABLES DE ENTRADA del modelo.
        """
        self._require_model()
        horizon = horizon or self.horizon
        today = today or date.today()
        products = list(products)
        if not products:
            return {}
        promotion_days = max(0, min(int(promotion_days), horizon))
        promotion = np.array([1] * promotion_days + [0] * (horizon - promotion_days)) if discount > 0 else 0
        discount_by_day = np.array([discount] * promotion_days + [0.0] * (horizon - promotion_days)) \
            if discount > 0 else 0.0

        histories = inventory_service.daily_sales_history(products, today, HISTORY_WINDOW_DAYS)
        sold_today = inventory_service.sales_on_day(products, today)
        series_list = [{"history": histories[product.id], "category": product.category, "price": product.price,
                        "promotion": promotion, "discount": discount_by_day} for product in products]
        matrix = recursive_forecast(self.model, series_list, today, horizon)

        results = {}
        for index, product in enumerate(products):
            daily = matrix[index].copy()
            already_sold = sold_today.get(product.id, 0)
            # La demanda de hoy se reduce con lo que ya se vendió hoy
            daily[0] = max(daily[0] - already_sold, 0.0)
            history = histories[product.id]
            results[product.id] = {
                "daily": daily,
                "history": history,
                "sold_today": already_sold,
                "warnings": self._warnings(history, discount),
            }
        return results

    @staticmethod
    def _warnings(history, discount):
        warnings = []
        if len(history) < 7:
            warnings.append(f"El producto tiene solo {len(history)} día(s) de historial: la predicción es poco "
                            "confiable hasta acumular al menos 7 días de ventas.")
        elif len(history) < 30:
            warnings.append(f"Hay {len(history)} días de historial; el promedio de 30 días usa solo esos días.")
        if len(history) >= 7 and sum(history[-14:]) == 0:
            warnings.append("No hay ventas en los últimos 14 días: el modelo proyecta una demanda muy baja.")
        if discount and not TRAINED_DISCOUNT_RANGE[0] <= discount <= TRAINED_DISCOUNT_RANGE[1]:
            warnings.append(f"El descuento {discount:g} % está fuera del rango observado en el entrenamiento "
                            f"({TRAINED_DISCOUNT_RANGE[0]}–{TRAINED_DISCOUNT_RANGE[1]} %): es una extrapolación.")
        return warnings

    # ------------------------------------------------ análisis de agotamiento
    def analyze_stock(self, daily_demand, current_stock, minimum_stock, lead_time, pending_orders=(),
                      start_date=None):
        """
        A partir de la demanda diaria estimada (lista de días desde hoy) calcula:
        días hasta agotar, fecha, punto de reorden, riesgo y reposición recomendada.
        """
        start_date = start_date or date.today()
        demand = np.asarray(daily_demand, dtype=float)
        cumulative = np.cumsum(demand)
        lead_time = int(lead_time)

        days_to_stockout, stockout_date = None, None
        if current_stock <= 0:
            days_to_stockout, stockout_date = 0.0, start_date
        else:
            reached = np.nonzero(cumulative >= current_stock)[0]
            if len(reached):
                day = int(reached[0])
                sold_before = cumulative[day - 1] if day > 0 else 0.0
                days_to_stockout = round(float(day + (current_stock - sold_before) / demand[day]), 1)
                stockout_date = start_date + timedelta(days=day)

        pending_quantity = sum(order.quantity for order in pending_orders)
        in_time_orders = [order for order in pending_orders
                          if not order.is_delayed and stockout_date is not None
                          and order.expected_delivery <= stockout_date]
        demand_lead_time = float(demand[:lead_time].sum())
        reorder_point = math.ceil(demand_lead_time + minimum_stock)
        coverage_window = lead_time + self.coverage_days
        recommended = max(0, math.ceil(demand[:coverage_window].sum() + minimum_stock
                                       - current_stock - pending_quantity))
        risk, reason = self._risk(current_stock, minimum_stock, lead_time, days_to_stockout, in_time_orders)

        return {
            "current_stock": int(current_stock),
            "minimum_stock": int(minimum_stock),
            "lead_time_days": lead_time,
            "horizon_days": len(demand),
            "demand_today": round(float(demand[0]), 2),
            "demand_7d": round(float(demand[:7].sum()), 1),
            "demand_30d": round(float(demand[:30].sum()), 1),
            "demand_lead_time": round(demand_lead_time, 1),
            "average_daily_demand": round(float(demand[:30].mean()), 2),
            "days_to_stockout": days_to_stockout,
            "stockout_date": stockout_date.isoformat() if stockout_date else None,
            "stockout_beyond_horizon": stockout_date is None,
            "stockout_before_replenishment": bool(days_to_stockout is not None and days_to_stockout < lead_time
                                                  and not in_time_orders),
            "reorder_point": reorder_point,
            "needs_reorder": bool(current_stock + pending_quantity <= reorder_point),
            "pending_quantity": int(pending_quantity),
            "recommended_quantity": int(recommended),
            "coverage_days": self.coverage_days,
            "risk": risk,
            "risk_reason": reason,
            "stock_projection": [round(max(current_stock - value, 0.0), 1) for value in cumulative],
        }

    @staticmethod
    def _risk(current_stock, minimum_stock, lead_time, days_to_stockout, in_time_orders):
        if current_stock <= 0:
            return "crítico", "El producto no tiene existencias."
        if days_to_stockout is not None and days_to_stockout < lead_time:
            if in_time_orders:
                return "medio", (f"Se agotaría en {days_to_stockout:g} días, pero hay un pedido pendiente "
                                 "que llegaría antes.")
            level = "crítico" if days_to_stockout <= 2 else "alto"
            return level, (f"Se agotaría en {days_to_stockout:g} días, antes de que llegue un pedido hecho hoy "
                           f"(entrega en {lead_time} días).")
        if days_to_stockout is not None and days_to_stockout < lead_time + 7:
            return "medio", (f"Se agotaría en {days_to_stockout:g} días: hay poco margen sobre el tiempo de "
                             f"entrega ({lead_time} días).")
        if current_stock <= minimum_stock:
            return "medio", "El stock está por debajo del mínimo definido."
        return "bajo", "El inventario cubre la demanda estimada más allá del tiempo de entrega."

    # ----------------------------------------------- explicación del modelo
    def explain(self, history, category, price, promotion=0, discount=0.0, when=None):
        """
        Contribución de cada factor a la predicción del primer día.
        Como el modelo es lineal: predicción = intercepto + Σ coeficiente × valor transformado.
        Las numéricas se miden respecto al promedio del entrenamiento y las categóricas
        respecto a la categoría de referencia (lunes, enero, Abarrotes).
        """
        self._require_model()
        row = build_feature_row(history, category, price, promotion, discount, when or date.today())
        preprocess = self.model.named_steps["preprocess"]
        regressor = self.model.named_steps["regressor"]
        transformed = preprocess.transform(self.model.named_steps["interactions"].transform(row))
        transformed = transformed.toarray() if hasattr(transformed, "toarray") else np.asarray(transformed)
        contributions = transformed[0] * regressor.coef_

        grouped = {}
        for name, value in zip(preprocess.get_feature_names_out(), contributions):
            feature = name.split("__", 1)[1]
            for categorical in CATEGORICAL_FEATURES:
                if feature.startswith(categorical + "_"):
                    feature = categorical
            grouped[feature] = grouped.get(feature, 0.0) + float(value)

        values = {key: _plain(value) for key, value in row.iloc[0].items()}
        display_values = {**values, "day_of_week": DAY_NAMES[int(values["day_of_week"])],
                          "promotion": "sí" if values["promotion"] else "no"}
        factors = [{"feature": feature, "label": FACTOR_LABELS.get(feature, feature),
                    "value": display_values.get(feature), "contribution": round(contribution, 3)}
                   for feature, contribution in grouped.items()]
        factors.sort(key=lambda factor: abs(factor["contribution"]), reverse=True)
        raw = float(self.model.predict(row)[0])
        return {
            "intercept": round(float(regressor.intercept_), 3),
            "factors": factors,
            "raw_prediction": round(raw, 3),
            "inputs": {key: (round(value, 3) if isinstance(value, float) else value)
                       for key, value in values.items()},
        }

    # ---------------------------------------------------- uso desde la app
    def product_prediction(self, product, horizon=None):
        """Predicción completa de un producto: demanda, agotamiento, riesgo y factores."""
        today = date.today()
        forecast = self.forecast_products([product], horizon=horizon, today=today)[product.id]
        pending = inventory_service.pending_orders([product.id])
        analysis = self.analyze_stock(forecast["daily"], product.current_stock, product.minimum_stock,
                                      product.supplier.delivery_days, pending, today)
        explanation = self.explain(forecast["history"], product.category, product.price, when=today)
        return {
            "product": {"id": product.id, "name": product.name, "category": product.category,
                        "price": product.price, "supplier": product.supplier.name},
            "forecast": {
                "dates": [(today + timedelta(days=i)).isoformat() for i in range(len(forecast["daily"]))],
                "units": [round(float(value), 2) for value in forecast["daily"]],
                "method": "Pronóstico recursivo día a día con el modelo de regresión lineal "
                          "(cada día usa su día de la semana, mes y las predicciones previas).",
                "sold_today": forecast["sold_today"],
            },
            "analysis": analysis,
            "explanation": explanation,
            "warnings": forecast["warnings"],
            "pending_orders": [{"id": order.id, "quantity": order.quantity,
                                "expected_delivery": order.expected_delivery.isoformat(),
                                "delayed": order.is_delayed} for order in pending],
            "model": {"version": self.metadata.get("model_version"),
                      "trained_at": self.metadata.get("training_date"),
                      "test_metrics": self.metadata.get("metrics", {}).get("test")},
        }

    def analyze_products(self, products, horizon=60):
        """Pronóstico y análisis de varios productos con una sola pasada del modelo (dashboard y alertas)."""
        products = list(products)
        today = date.today()
        forecasts = self.forecast_products(products, horizon=horizon, today=today)
        pending = inventory_service.pending_orders([product.id for product in products])
        results = {}
        for product in products:
            orders = [order for order in pending if order.product_id == product.id]
            results[product.id] = self.analyze_stock(forecasts[product.id]["daily"], product.current_stock,
                                                     product.minimum_stock, product.supplier.delivery_days,
                                                     orders, today)
        return results
