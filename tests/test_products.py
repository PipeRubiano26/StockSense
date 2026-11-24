"""Pruebas del CRUD de productos e inventario."""
from database import db
from database.models import Alert, InventoryMovement, Product, Sale, Supplier
from services import inventory_service
from tests.conftest import product_by_name, stock_matches_movements


def valid_product(**overrides):
    data = {"name": "Galletas de prueba", "category": "Snacks", "description": "Paquete x6", "price": "4500",
            "current_stock": "80", "minimum_stock": "15", "supplier_id": "1"}
    data.update(overrides)
    return data


def test_register_product_creates_row_and_initial_movement(client, app):
    response = client.post("/products/new", data=valid_product())
    assert response.status_code == 302
    with app.app_context():
        product = product_by_name("Galletas de prueba")
        assert product.price == 4500 and product.current_stock == 80 and product.minimum_stock == 15
        movement = InventoryMovement.query.filter_by(product_id=product.id).one()
        assert movement.movement_type == "entrada" and movement.quantity == 80
        assert stock_matches_movements(product)


def test_register_product_rejects_missing_required_fields(client, app):
    response = client.post("/products/new", data=valid_product(name="", category="", price=""))
    assert response.status_code == 400
    body = response.get_data(as_text=True)
    assert "El nombre es obligatorio" in body and "El precio es obligatorio" in body
    with app.app_context():
        assert Product.query.count() == 2


def test_register_product_rejects_negative_values(client, app):
    response = client.post("/products/new", data=valid_product(price="-100", current_stock="-5", minimum_stock="-1"))
    assert response.status_code == 400
    body = response.get_data(as_text=True)
    assert "El precio debe ser mayor que 0" in body
    assert "El stock no puede ser menor que 0" in body
    assert "El stock mínimo no puede ser menor que 0" in body


def test_register_product_rejects_duplicate_name_and_unknown_category(client):
    response = client.post("/products/new", data=valid_product(name="producto a", category="Ropa"))
    assert response.status_code == 400
    body = response.get_data(as_text=True)
    assert "Ya existe un producto con ese nombre" in body and "La categoría no es una opción válida" in body


def test_edit_product_updates_fields_and_records_stock_adjustment(client, app):
    with app.app_context():
        product_id = product_by_name("Producto A").id
    response = client.post(f"/products/{product_id}/edit",
                           data=valid_product(name="Producto A editado", price="3200", current_stock="42"))
    assert response.status_code == 302
    with app.app_context():
        product = db.session.get(Product, product_id)
        assert product.name == "Producto A editado" and product.price == 3200 and product.current_stock == 42
        adjustment = InventoryMovement.query.filter_by(product_id=product_id, movement_type="ajuste").one()
        assert adjustment.quantity == -8
        assert stock_matches_movements(product)


def test_edit_nonexistent_product_returns_404(client):
    assert client.get("/products/999/edit").status_code == 404


def test_delete_product_removes_its_history(client, app):
    with app.app_context():
        product = product_by_name("Producto A")
        product_id = product.id
        inventory_service.register_sale({"product_id": product_id, "quantity": 3})
        db.session.add(Alert(product=product, alert_type="stock_bajo", message="prueba"))
        db.session.commit()
    response = client.post(f"/products/{product_id}/delete")
    assert response.status_code == 302
    with app.app_context():
        assert db.session.get(Product, product_id) is None
        assert Sale.query.filter_by(product_id=product_id).count() == 0
        assert InventoryMovement.query.filter_by(product_id=product_id).count() == 0
        assert Alert.query.filter_by(product_id=product_id).count() == 0
        assert Supplier.query.count() == 1   # el proveedor no se elimina


def test_search_and_stock_level_filter(client):
    body = client.get("/products/?q=producto b").get_data(as_text=True)
    assert "Producto B" in body and "Producto A" not in body
    body = client.get("/products/?stock_level=bajo").get_data(as_text=True)
    assert "Producto B" in body and "Producto A" not in body


def test_supplier_with_products_cannot_be_deleted(client, app):
    response = client.post("/suppliers/1/delete", follow_redirects=True)
    assert "No se puede eliminar" in response.get_data(as_text=True)
    with app.app_context():
        assert Supplier.query.count() == 1


def test_associate_product_to_new_supplier(client, app):
    client.post("/suppliers/new", data={"name": "Otro", "contact": "Luis", "email": "luis@otro.example",
                                        "phone": "1", "delivery_days": "9"})
    with app.app_context():
        supplier = Supplier.query.filter_by(name="Otro").one()
        product_id = product_by_name("Producto A").id
    client.post(f"/suppliers/{supplier.id}/associate", data={"product_id": product_id})
    with app.app_context():
        assert db.session.get(Product, product_id).supplier.delivery_days == 9
