"""
Definición única de las variables del modelo de demanda.

Se usa tanto en el notebook de entrenamiento como en la aplicación Flask
para garantizar que las variables se calculen exactamente igual.
"""
import numpy as np
import pandas as pd

TARGET = "units_sold"

# Variables que recibe el Pipeline (entradas "crudas")
NUMERIC_FEATURES = [
    "price",
    "discount_percentage",
    "promotion",
    "previous_sales",
    "average_sales_7d",
    "average_sales_30d",
]
CATEGORICAL_FEATURES = ["day_of_week", "month", "category"]
INPUT_FEATURES = NUMERIC_FEATURES + CATEGORICAL_FEATURES

# Variables derivadas que crea el propio Pipeline (ver add_interaction_features)
INTERACTION_FEATURES = ["discount_x_avg30", "weekend_x_avg30"]

# Mínimo de días de historial para calcular el promedio de 30 días
MIN_HISTORY_DAYS = 30


def add_interaction_features(X):
    """
    Crea interacciones para que la regresión lineal capture efectos proporcionales:
    un 20 % de descuento no suma las mismas unidades a un producto que vende
    50 al día que a uno que vende 2. Se multiplica por el promedio de 30 días.

    Es una función de módulo (no lambda) para que Joblib pueda serializarla
    dentro del Pipeline.
    """
    X = X.copy()
    X["discount_x_avg30"] = X["discount_percentage"] / 100 * X["average_sales_30d"]
    X["weekend_x_avg30"] = (X["day_of_week"].astype(int) >= 5).astype(float) * X["average_sales_30d"]
    return X


def add_lag_features(df, group_column="product_id", date_column="date"):
    """
    Agrega ventas anteriores y promedios móviles por producto.

    Se usa shift(1): el valor del día t solo usa ventas de días anteriores a t,
    así se evita fuga de información del propio valor que se quiere predecir.
    """
    df = df.sort_values([group_column, date_column]).copy()
    past_sales = df.groupby(group_column)[TARGET].shift(1)
    grouped_past = past_sales.groupby(df[group_column])
    df["previous_sales"] = past_sales
    df["average_sales_7d"] = grouped_past.transform(lambda s: s.rolling(7, min_periods=7).mean())
    df["average_sales_30d"] = grouped_past.transform(lambda s: s.rolling(30, min_periods=30).mean())
    return df


def lag_values_from_history(daily_sales):
    """
    Calcula las variables de historial a partir de una lista de ventas diarias
    (la más reciente al final). Equivale a add_lag_features para un solo día.
    Si hay menos días de los necesarios, promedia los disponibles.
    """
    values = np.asarray(daily_sales, dtype=float)
    if len(values) == 0:
        return {"previous_sales": 0.0, "average_sales_7d": 0.0, "average_sales_30d": 0.0}
    return {
        "previous_sales": float(values[-1]),
        "average_sales_7d": float(values[-7:].mean()),
        "average_sales_30d": float(values[-30:].mean()),
    }


def calendar_values(date):
    """Día de la semana (0 = lunes) y mes de una fecha."""
    date = pd.Timestamp(date)
    return {"day_of_week": int(date.day_of_week), "month": int(date.month)}
