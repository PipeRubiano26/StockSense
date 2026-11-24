"""
Pronóstico recursivo de demanda diaria con el modelo entrenado.

Para el día 1 se usan las ventas reales recientes. Para el día 2 en adelante,
las variables de historial (venta anterior, promedios 7 y 30 días) incluyen
las predicciones de los días anteriores. Cada día se predice con su propio
día de la semana, mes, precio y condición de promoción.

Se predicen varios productos a la vez (una llamada a predict() por día) para
que el cálculo sea rápido en el dashboard y en las alertas.
"""
import numpy as np
import pandas as pd

from ml.features import INPUT_FEATURES, calendar_values, lag_values_from_history


def _value_for_day(value, day):
    """Permite pasar un valor fijo o una lista con un valor por día."""
    if np.ndim(value) == 0:
        return value
    return value[day]


def recursive_forecast(model, series_list, start_date, horizon):
    """
    series_list: lista de diccionarios, uno por producto, con:
        history   -> ventas diarias pasadas (la más reciente al final)
        category  -> categoría del producto
        price     -> precio de lista (número o lista por día)
        promotion -> 0/1 (número o lista por día)
        discount  -> porcentaje de descuento (número o lista por día)

    Devuelve una matriz (productos x días) con unidades estimadas >= 0.
    """
    histories = [list(map(float, series["history"])) for series in series_list]
    predictions = np.zeros((len(series_list), horizon))
    dates = pd.date_range(pd.Timestamp(start_date), periods=horizon, freq="D")

    for day, date in enumerate(dates):
        calendar = calendar_values(date)
        rows = []
        for index, series in enumerate(series_list):
            rows.append({
                "price": float(_value_for_day(series["price"], day)),
                "discount_percentage": float(_value_for_day(series.get("discount", 0), day)),
                "promotion": int(_value_for_day(series.get("promotion", 0), day)),
                **lag_values_from_history(histories[index]),
                **calendar,
                "category": series["category"],
            })
        features = pd.DataFrame(rows, columns=INPUT_FEATURES)
        # Una regresión lineal puede devolver valores negativos: no existen ventas negativas
        day_prediction = np.clip(model.predict(features), 0, None)
        predictions[:, day] = day_prediction
        for index, value in enumerate(day_prediction):
            histories[index].append(float(value))

    return predictions


def build_feature_row(history, category, price, promotion, discount, date):
    """Una fila de variables de entrada (se usa para explicar la predicción)."""
    return pd.DataFrame([{
        "price": float(price),
        "discount_percentage": float(discount),
        "promotion": int(promotion),
        **lag_values_from_history(history),
        **calendar_values(date),
        "category": category,
    }], columns=INPUT_FEATURES)
