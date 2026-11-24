"""
Datos iniciales SINTÉTICOS de la aplicación (20 productos, 5 proveedores,
12 meses de ventas y movimientos de inventario).

Usa el mismo simulador comercial que el dataset de entrenamiento
(ml/simulation.py), por eso el historial es coherente con lo que aprendió el modelo.
Solo se ejecuta si la base de datos está vacía (no duplica datos al reiniciar).
"""
from datetime import date, datetime, time, timedelta
import math

import numpy as np
import pandas as pd

from database import db
from database.models import InventoryMovement, Product, PurchaseOrder, Sale, Supplier
from ml.simulation import (make_product_profile, simulate_demand, simulate_inventory,
                           simulate_prices_and_promotions)

SEED = 2026
HISTORY_DAYS = 365
FINAL_PHASE_DAYS = 25   # en los últimos días no se reabastece para llegar a niveles de stock variados

# Proveedores ficticios (correos con dominio reservado .example)
SUPPLIERS = [
    ("Distribuidora Andina S.A.S.", "Laura Gómez", "ventas@andina.example", "601 555 0101", 2),
    ("Lácteos del Valle Ltda.", "Carlos Ruiz", "pedidos@lacteosvalle.example", "602 555 0102", 3),
    ("Comercializadora El Dorado", "Marta Pineda", "contacto@eldorado.example", "601 555 0103", 5),
    ("Proveedora Higiene Total", "Andrés Salazar", "comercial@higienetotal.example", "604 555 0104", 7),
    ("Importadora Pacífico", "Diana Torres", "importaciones@pacifico.example", "602 555 0105", 10),
]

# nombre, categoría, proveedor (índice), rotación, precio base, días de cobertura al final
PRODUCTS = [
    ("Agua mineral 600 ml", "Bebidas", 0, "alta", 2000, 3),
    ("Gaseosa cola 1.5 L", "Bebidas", 0, "alta", 5500, 25),
    ("Jugo de naranja 1 L", "Bebidas", 1, "media", 6800, 9),
    ("Café molido 500 g", "Abarrotes", 2, "media", 16500, 40),
    ("Papas fritas 150 g", "Snacks", 0, "alta", 4200, 4),
    ("Galletas de avena 300 g", "Snacks", 2, "media", 3800, 30),
    ("Chocolatina 40 g", "Snacks", 2, "alta", 2500, 18),
    ("Leche entera 1 L", "Lácteos", 1, "alta", 4300, 2),
    ("Yogur natural 1 L", "Lácteos", 1, "media", 8900, 12),
    ("Queso campesino 500 g", "Lácteos", 1, "media", 11500, 6),
    ("Arroz blanco 1 kg", "Abarrotes", 2, "alta", 4600, 35),
    ("Aceite vegetal 1 L", "Abarrotes", 2, "media", 12800, 7),
    ("Pasta spaghetti 500 g", "Abarrotes", 2, "media", 3900, 50),
    ("Detergente en polvo 1 kg", "Aseo", 3, "media", 14500, 5),
    ("Jabón lavaloza 500 g", "Aseo", 3, "media", 6200, 45),
    ("Papel higiénico x4", "Aseo", 3, "alta", 9800, 20),
    ("Crema dental 100 ml", "Cuidado personal", 4, "media", 7900, 60),
    ("Shampoo 400 ml", "Cuidado personal", 4, "baja", 18900, 8),
    ("Desodorante roll-on", "Cuidado personal", 4, "baja", 13500, 70),
    ("Protector solar 120 ml", "Cuidado personal", 4, "baja", 29500, 90),
]

# Pedidos pendientes al momento de la carga: (producto, días desde el pedido, retraso)
# Un pedido con retraso > 0 ya debió llegar y sigue pendiente -> alerta de retraso.
PENDING_ORDERS = [
    ("Agua mineral 600 ml", 1, 0),
    ("Queso campesino 500 g", 1, 0),
    ("Detergente en polvo 1 kg", 10, 3),
    ("Shampoo 400 ml", 13, 2),
]


def _at(day, hour):
    return datetime.combine(day, time(hour=hour))


def seed_database(today=None):
    """Carga los datos iniciales si la base está vacía. Devuelve True si cargó datos."""
    if db.session.query(Product.id).first() is not None:
        return False

    today = today or date.today()
    rng = np.random.default_rng(SEED)
    start = today - timedelta(days=HISTORY_DAYS)
    dates = pd.date_range(start, periods=HISTORY_DAYS, freq="D")   # termina ayer

    suppliers = [Supplier(name=n, contact=c, email=e, phone=p, delivery_days=d) for n, c, e, p, d in SUPPLIERS]
    db.session.add_all(suppliers)
    db.session.flush()

    products_by_name = {}
    for index, (name, category, supplier_index, rotation, base_price, coverage_days) in enumerate(PRODUCTS):
        supplier = suppliers[supplier_index]
        profile = make_product_profile(rng, index + 1, name, category, rotation, base_price)
        price, promotion, discount = simulate_prices_and_promotions(rng, profile, HISTORY_DAYS)
        demand = simulate_demand(rng, profile, dates, price, discount)

        recent_average = max(float(demand[-30:].mean()), 0.3)
        final_target = int(round(recent_average * coverage_days))
        inventory = simulate_inventory(rng, demand, supplier.delivery_days,
                                       final_target=final_target, final_phase_days=FINAL_PHASE_DAYS)

        product = Product(
            name=name, category=category, price=float(price[-1]), supplier=supplier,
            description=f"Producto de {category.lower()} (rotación {rotation}). Datos sintéticos.",
            current_stock=int(inventory["final_stock"]),
            minimum_stock=max(3, math.ceil(recent_average * rng.uniform(4, 7))),
            created_at=_at(start, 7),
        )
        db.session.add(product)
        products_by_name[name] = product

        db.session.add(InventoryMovement(product=product, movement_type="entrada",
                                         quantity=inventory["initial_stock"], movement_date=_at(start, 7),
                                         description="Inventario inicial"))
        for order_day, arrival_day, quantity in inventory["receipts"]:
            order_date = dates[order_day].date()
            arrival_date = dates[arrival_day].date()
            db.session.add(PurchaseOrder(supplier=supplier, product=product, quantity=int(quantity),
                                         order_date=order_date, status="recibida",
                                         expected_delivery=order_date + timedelta(days=supplier.delivery_days)))
            db.session.add(InventoryMovement(product=product, movement_type="entrada", quantity=int(quantity),
                                             movement_date=_at(arrival_date, 8),
                                             description="Recepción de orden de compra"))

        for day, quantity in enumerate(inventory["sold"]):
            if quantity <= 0:
                continue
            sale_time = _at(dates[day].date(), int(rng.integers(9, 21)))
            unit_price = round(float(price[day]) * (1 - discount[day] / 100), 2)
            db.session.add(Sale(product=product, sale_date=sale_time, quantity=int(quantity),
                                unit_price=unit_price, promotion=bool(promotion[day]),
                                discount_percentage=float(discount[day])))
            db.session.add(InventoryMovement(product=product, movement_type="salida", quantity=-int(quantity),
                                             movement_date=sale_time, description="Salida por venta"))

    for name, days_ago, delay in PENDING_ORDERS:
        product = products_by_name[name]
        order_date = today - timedelta(days=days_ago)
        expected = order_date + timedelta(days=product.supplier.delivery_days)
        if delay:
            expected = today - timedelta(days=delay)
        quantity = max(10, product.minimum_stock * 3)
        db.session.add(PurchaseOrder(supplier=product.supplier, product=product, quantity=quantity,
                                     order_date=order_date, expected_delivery=expected, status="pendiente"))

    db.session.commit()
    return True


def reset_database():
    """Elimina y recrea todas las tablas (lo usa el comando `flask init-db --reset`)."""
    db.drop_all()
    db.create_all()


