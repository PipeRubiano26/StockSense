"""
Simulador de comportamiento comercial (datos SINTÉTICOS).

Este módulo genera la demanda diaria de un producto a partir de reglas
comerciales explícitas: nivel de rotación, día de la semana, temporada,
tendencia, elasticidad al precio, promociones y ruido aleatorio controlado.

Lo usan dos procesos:
  * ml/generate_dataset.py -> dataset histórico para entrenar el modelo.
  * database/seed.py       -> historial inicial de ventas de la aplicación.

IMPORTANTE: los datos son ficticios y sirven para un experimento académico.
La demanda real de un negocio puede comportarse de forma muy distinta.
"""
import numpy as np
import pandas as pd

# Parámetros por categoría: rango de precio (COP), efecto fin de semana y
# aumento adicional de diciembre.
CATEGORIES = {
    "Bebidas": {"price_range": (2000, 9000), "weekend_boost": 0.35, "december_boost": 0.30},
    "Snacks": {"price_range": (1500, 7000), "weekend_boost": 0.30, "december_boost": 0.25},
    "Lácteos": {"price_range": (2500, 12000), "weekend_boost": 0.10, "december_boost": 0.10},
    "Abarrotes": {"price_range": (3000, 18000), "weekend_boost": 0.15, "december_boost": 0.20},
    "Aseo": {"price_range": (4000, 25000), "weekend_boost": 0.05, "december_boost": 0.05},
    "Cuidado personal": {"price_range": (5000, 30000), "weekend_boost": 0.05, "december_boost": 0.15},
}

# Unidades diarias promedio según el nivel de rotación
ROTATION_LEVELS = {"alta": (25, 60), "media": (8, 20), "baja": (1, 5)}

# Perfil base lunes(0) ... domingo(6). El fin de semana se ajusta por categoría.
WEEKDAY_PROFILE = np.array([0.92, 0.90, 0.95, 1.00, 1.10, 1.00, 1.00])

# Estacionalidad mensual (enero bajo por cuesta de enero, picos en mitad y fin de año)
MONTH_FACTORS = {1: 0.88, 2: 0.92, 3: 0.97, 4: 0.98, 5: 1.00, 6: 1.04,
                 7: 1.05, 8: 1.00, 9: 0.98, 10: 1.00, 11: 1.05, 12: 1.10}

# Cada punto porcentual de descuento aumenta la demanda en 2.5 %
# (un 20 % de descuento implica +50 % de demanda).
PROMO_UPLIFT = 2.5
DISCOUNT_OPTIONS = [10, 15, 20, 25, 30, 40]


def make_product_profile(rng, product_id, name, category, rotation, base_price=None):
    """Crea los parámetros ocultos que gobiernan la demanda de un producto."""
    category_cfg = CATEGORIES[category]
    low, high = ROTATION_LEVELS[rotation]
    if base_price is None:
        base_price = round(rng.uniform(*category_cfg["price_range"]) / 50) * 50
    return {
        "product_id": product_id,
        "name": name,
        "category": category,
        "rotation": rotation,
        "base_price": float(base_price),
        "base_demand": float(rng.uniform(low, high)),
        "elasticity": float(rng.uniform(0.8, 1.8)),
        "trend_per_year": float(rng.uniform(-0.10, 0.25)),
        "promo_start_prob": float(rng.uniform(1 / 70, 1 / 30)),
    }


def simulate_prices_and_promotions(rng, profile, n_days):
    """Precio de lista diario y calendario de promociones."""
    base_price = profile["base_price"]
    price = np.empty(n_days)
    promotion = np.zeros(n_days, dtype=int)
    discount = np.zeros(n_days, dtype=float)

    price_factor = 1.0
    promo_days_left = 0
    current_discount = 0
    for day in range(n_days):
        # Cambios de precio ocasionales (aprox. cada dos meses), acotados a +-15 %
        if rng.random() < 1 / 60:
            price_factor = float(np.clip(price_factor * rng.uniform(0.94, 1.08), 0.85, 1.15))
        price[day] = round(base_price * price_factor / 50) * 50

        if promo_days_left == 0 and rng.random() < profile["promo_start_prob"]:
            promo_days_left = int(rng.integers(3, 11))
            current_discount = int(rng.choice(DISCOUNT_OPTIONS))
        if promo_days_left > 0:
            promotion[day] = 1
            discount[day] = current_discount
            promo_days_left -= 1
    return price, promotion, discount


def expected_demand(profile, dates, price, discount, day_index):
    """Demanda esperada (sin ruido) para cada fecha. `day_index` mide la tendencia."""
    category_cfg = CATEGORIES[profile["category"]]
    dates = pd.DatetimeIndex(dates)
    day_of_week = dates.day_of_week.to_numpy()
    month = dates.month.to_numpy()

    weekday_factor = WEEKDAY_PROFILE[day_of_week] * np.where(
        day_of_week >= 5, 1 + category_cfg["weekend_boost"], 1.0)
    month_factor = np.array([MONTH_FACTORS[m] for m in month])
    month_factor = month_factor * np.where(month == 12, 1 + category_cfg["december_boost"], 1.0)
    trend_factor = 1 + profile["trend_per_year"] * (np.asarray(day_index) / 365)
    price_factor = (np.asarray(price) / profile["base_price"]) ** (-profile["elasticity"])
    promo_factor = 1 + PROMO_UPLIFT * np.asarray(discount) / 100

    return profile["base_demand"] * weekday_factor * month_factor * trend_factor * price_factor * promo_factor


def simulate_demand(rng, profile, dates, price, discount):
    """Demanda diaria real (latente) con ruido Gamma-Poisson controlado."""
    n_days = len(dates)
    mean = expected_demand(profile, dates, price, discount, np.arange(n_days))
    noise = rng.gamma(shape=12, scale=1 / 12, size=n_days)  # variación ~29 %
    return rng.poisson(mean * noise)


def simulate_inventory(rng, demand, lead_time, final_target=None, final_phase_days=0):
    """
    Simula el inventario con una política de punto de reorden.

    Las ventas observadas son min(demanda, stock disponible): cuando hay quiebre
    de stock la venta registrada es MENOR que la demanda real (venta censurada).
    Algunos pedidos llegan tarde para producir quiebres realistas.

    Si se indica `final_target`, al iniciar la fase final se hace una última
    recepción para terminar cerca de ese nivel de stock (lo usa el seed de la app).
    """
    n_days = len(demand)
    average = max(float(np.mean(demand)), 0.5)
    reorder_point = average * (lead_time + rng.uniform(3, 7))
    order_quantity = max(1, int(round(average * rng.uniform(14, 30))))

    stock = int(round(reorder_point + order_quantity))
    initial_stock = stock
    pending = []                      # (día_llegada, cantidad, día_pedido)
    receipts = []                     # (día_pedido, día_llegada, cantidad)
    opening_stock = np.zeros(n_days, dtype=int)
    sold = np.zeros(n_days, dtype=int)
    stop_day = n_days - final_phase_days if final_target is not None else n_days

    for day in range(n_days):
        arrived = [order for order in pending if order[0] == day]
        for arrival_day, quantity, order_day in arrived:
            stock += quantity
            receipts.append((order_day, arrival_day, quantity))
        pending = [order for order in pending if order[0] != day]

        if final_target is not None and day == stop_day:
            incoming = sum(order[1] for order in pending)
            needed = int(final_target + demand[day:].sum() - stock - incoming)
            if needed > 0:
                stock += needed
                receipts.append((max(day - lead_time, 0), day, needed))

        opening_stock[day] = stock
        sold[day] = min(int(demand[day]), stock)
        stock -= sold[day]

        on_order = sum(order[1] for order in pending)
        if day < stop_day and stock + on_order <= reorder_point:
            delay = int(rng.integers(2, 8)) if rng.random() < 0.15 else 0
            pending.append((day + lead_time + delay, order_quantity, day))

    return {
        "initial_stock": initial_stock,
        "opening_stock": opening_stock,
        "sold": sold,
        "final_stock": stock,
        "receipts": receipts,
    }
