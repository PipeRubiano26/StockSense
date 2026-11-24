"""
Generador reproducible del dataset sintético de entrenamiento.

Uso (desde la raíz del proyecto):
    python -m ml.generate_dataset            -> data/synthetic_sales.csv
    python -m ml.generate_dataset --seed 7   -> otra muestra (por ejemplo, para pruebas)
"""
import argparse
import os

import numpy as np
import pandas as pd

from ml.features import add_lag_features
from ml.simulation import (CATEGORIES, make_product_profile, simulate_demand,
                           simulate_inventory, simulate_prices_and_promotions)

DEFAULT_SEED = 42
DEFAULT_PRODUCTS = 50
DEFAULT_DAYS = 730                       # dos años de historia diaria
DEFAULT_START_DATE = "2024-01-01"
OUTPUT_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "synthetic_sales.csv")

COLUMNS = ["product_id", "date", "category", "rotation", "day_of_week", "month", "price",
           "units_available", "promotion", "discount_percentage", "previous_sales",
           "average_sales_7d", "average_sales_30d", "stockout", "units_sold"]


def build_catalog(rng, n_products):
    """Catálogo ficticio con productos de alta, media y baja rotación."""
    categories = list(CATEGORIES)
    rotations = rng.choice(["alta", "media", "baja"], size=n_products, p=[0.3, 0.4, 0.3])
    catalog = []
    for index in range(n_products):
        category = categories[index % len(categories)]
        name = f"{category} {index + 1:02d}"
        catalog.append(make_product_profile(rng, index + 1, name, category, rotations[index]))
    return catalog


def generate_dataset(seed=DEFAULT_SEED, n_products=DEFAULT_PRODUCTS, n_days=DEFAULT_DAYS,
                     start_date=DEFAULT_START_DATE):
    """Devuelve un DataFrame con el historial diario de ventas observadas."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range(start_date, periods=n_days, freq="D")
    frames = []

    for profile in build_catalog(rng, n_products):
        price, promotion, discount = simulate_prices_and_promotions(rng, profile, n_days)
        demand = simulate_demand(rng, profile, dates, price, discount)
        lead_time = int(rng.integers(2, 11))
        inventory = simulate_inventory(rng, demand, lead_time)

        frames.append(pd.DataFrame({
            "product_id": profile["product_id"],
            "date": dates,
            "category": profile["category"],
            "rotation": profile["rotation"],
            "day_of_week": dates.day_of_week,
            "month": dates.month,
            "price": price,
            "units_available": inventory["opening_stock"],
            "promotion": promotion,
            "discount_percentage": discount,
            "units_sold": inventory["sold"],
        }))

    df = pd.concat(frames, ignore_index=True)
    df = add_lag_features(df)
    # Se vendió todo lo disponible: la venta observada es una cota inferior de la demanda
    df["stockout"] = (df["units_sold"] >= df["units_available"]).astype(int)
    # Los primeros 30 días de cada producto no tienen promedio de 30 días
    df = df.dropna(subset=["average_sales_30d"]).reset_index(drop=True)
    df["date"] = df["date"].dt.strftime("%Y-%m-%d")
    for column in ["average_sales_7d", "average_sales_30d"]:
        df[column] = df[column].round(4)
    return df[COLUMNS]


def main():
    parser = argparse.ArgumentParser(description="Genera el dataset sintético de StockSense")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--output", default=OUTPUT_PATH)
    args = parser.parse_args()

    df = generate_dataset(seed=args.seed)
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    df.to_csv(args.output, index=False)
    print(f"Dataset generado: {len(df):,} registros -> {args.output}")


if __name__ == "__main__":
    main()
