"""
Fixtures de pruebas.

* `app`: base de datos SQLite en memoria con un proveedor y dos productos (rápida).
* `seeded_app`: base en memoria con los datos iniciales completos (12 meses de ventas),
  para las pruebas de integración Flask + SQLite + modelo.
Ambas usan el modelo real models/demand_model.joblib.
"""
from datetime import datetime, timedelta

import pytest

from app import create_app
from config import TestConfig
from database import db
from database.models import InventoryMovement, Product, Sale, Supplier
from database.seed import seed_database


@pytest.fixture
def app():
    app = create_app(TestConfig)
    with app.app_context():
        supplier = Supplier(name="Proveedor Prueba", contact="Ana", email="ana@prueba.example",
                            phone="300 000 0000", delivery_days=4)
        db.session.add(supplier)
        db.session.flush()
        for name, stock, minimum in [("Producto A", 50, 10), ("Producto B", 5, 8)]:
            product = Product(name=name, category="Snacks", price=3000, current_stock=0, minimum_stock=minimum,
                              supplier=supplier, created_at=datetime.now() - timedelta(days=60))
            db.session.add(product)
            product.current_stock = stock
            db.session.add(InventoryMovement(product=product, movement_type="entrada", quantity=stock,
                                             description="Inventario inicial"))
        db.session.commit()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture(scope="module")
def seeded_app():
    app = create_app(TestConfig)
    with app.app_context():
        seed_database()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def seeded_client(seeded_app):
    return seeded_app.test_client()


def product_by_name(name):
    return Product.query.filter_by(name=name).one()


def stock_matches_movements(product):
    total = db.session.query(db.func.sum(InventoryMovement.quantity)).filter_by(product_id=product.id).scalar()
    return (total or 0) == product.current_stock


def add_daily_sales(product, quantities, end_day=None):
    """Crea ventas diarias que terminan ayer (sirve para dar historial a un producto)."""
    end_day = end_day or (datetime.now() - timedelta(days=1))
    for offset, quantity in enumerate(reversed(quantities)):
        if quantity > 0:
            db.session.add(Sale(product=product, quantity=quantity, unit_price=product.price,
                                sale_date=end_day - timedelta(days=offset)))
    db.session.commit()
