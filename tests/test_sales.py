"""Pruebas de ventas, existencias y movimientos de inventario."""
from datetime import date, timedelta

import pytest

from database import db
from database.models import InventoryMovement, Product, PurchaseOrder, Sale
from services import inventory_service
from services.validators import ValidationError
from tests.conftest import product_by_name, stock_matches_movements


def test_sale_reduces_stock_and_creates_movement(client, app):
    with app.app_context():
        product_id = product_by_name("Producto A").id
    response = client.post("/sales/new", data={"product_id": product_id, "quantity": "12"})
    assert response.status_code == 302
    with app.app_context():
        product = db.session.get(Product, product_id)
        assert product.current_stock == 38
        sale = Sale.query.filter_by(product_id=product_id).one()
        assert sale.quantity == 12 and sale.unit_price == 3000
        movement = InventoryMovement.query.filter_by(product_id=product_id, movement_type="salida").one()
        assert movement.quantity == -12
        assert stock_matches_movements(product)


def test_sale_greater_than_stock_is_rejected(client, app):
    with app.app_context():
        product_id = product_by_name("Producto B").id   # stock 5
    response = client.post("/sales/new", data={"product_id": product_id, "quantity": "6"})
    assert response.status_code == 400
    assert "Stock insuficiente" in response.get_data(as_text=True)
    with app.app_context():
        assert db.session.get(Product, product_id).current_stock == 5
        assert Sale.query.count() == 0


def test_selling_exact_stock_leaves_zero(app):
    with app.app_context():
        product = product_by_name("Producto B")
        inventory_service.register_sale({"product_id": product.id, "quantity": 5})
        assert product.current_stock == 0 and product.stock_level == "agotado"


@pytest.mark.parametrize("quantity", ["0", "-3", "abc", "2.5", ""])
def test_sale_rejects_invalid_quantities(app, quantity):
    with app.app_context():
        product = product_by_name("Producto A")
        with pytest.raises(ValidationError) as error:
            inventory_service.register_sale({"product_id": product.id, "quantity": quantity})
        assert "quantity" in error.value.errors
        assert product.current_stock == 50


def test_promotion_rules_and_discounted_price(app):
    with app.app_context():
        product = product_by_name("Producto A")
        with pytest.raises(ValidationError):
            inventory_service.register_sale({"product_id": product.id, "quantity": 1, "promotion": "1"})
        with pytest.raises(ValidationError):
            inventory_service.register_sale({"product_id": product.id, "quantity": 1, "discount_percentage": 10})
        sale = inventory_service.register_sale({"product_id": product.id, "quantity": 2, "promotion": "1",
                                                "discount_percentage": "20"})
        assert sale.promotion and sale.unit_price == 2400


def test_sale_rejects_future_date_and_unknown_product(app):
    with app.app_context():
        product = product_by_name("Producto A")
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        with pytest.raises(ValidationError) as error:
            inventory_service.register_sale({"product_id": product.id, "quantity": 1, "sale_date": tomorrow})
        assert "sale_date" in error.value.errors
        with pytest.raises(ValidationError):
            inventory_service.register_sale({"product_id": 999, "quantity": 1})


def test_sales_history_filters(client, app):
    with app.app_context():
        a, b = product_by_name("Producto A"), product_by_name("Producto B")
        inventory_service.register_sale({"product_id": a.id, "quantity": 2})
        inventory_service.register_sale({"product_id": b.id, "quantity": 1})
        assert inventory_service.filter_sales(product_id=a.id).count() == 1
        assert inventory_service.filter_sales(date_from=date.today(), date_to=date.today()).count() == 2
        assert inventory_service.filter_sales(date_to=date.today() - timedelta(days=1)).count() == 0
        b_id = b.id
    body = client.get(f"/sales/?product_id={b_id}").get_data(as_text=True)
    assert "Producto B" in body and "1 venta(s)" in body


def test_negative_adjustment_cannot_leave_negative_stock(app):
    with app.app_context():
        product = product_by_name("Producto B")
        with pytest.raises(ValidationError):
            inventory_service.register_movement(product, {"movement_type": "ajuste", "quantity": -6,
                                                          "description": "merma"})
        inventory_service.register_movement(product, {"movement_type": "ajuste", "quantity": -2,
                                                      "description": "merma"})
        assert product.current_stock == 3 and stock_matches_movements(product)


def test_receiving_purchase_order_increases_stock(client, app):
    with app.app_context():
        product_id = product_by_name("Producto B").id
    client.post(f"/products/{product_id}/orders", data={"quantity": "40"})
    with app.app_context():
        order = PurchaseOrder.query.one()
        assert order.status == "pendiente"
        assert order.expected_delivery == date.today() + timedelta(days=4)
        order_id = order.id
    client.post(f"/products/orders/{order_id}/receive")
    with app.app_context():
        product = db.session.get(Product, product_id)
        assert product.current_stock == 45 and db.session.get(PurchaseOrder, order_id).status == "recibida"
        assert stock_matches_movements(product)
        with pytest.raises(ValidationError):   # no se puede recibir dos veces
            inventory_service.receive_purchase_order(db.session.get(PurchaseOrder, order_id))
