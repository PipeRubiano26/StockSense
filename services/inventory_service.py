"""
Lógica de negocio de inventario: productos, proveedores, ventas, movimientos
y órdenes de compra.

Regla central: el stock de un producto SOLO cambia junto con un registro en
InventoryMovement, en la misma transacción. Así el stock actual siempre es
igual a la suma de sus movimientos.
"""
from datetime import date, datetime, timedelta

from sqlalchemy import func

from database import db
from database.models import (PRODUCT_CATEGORIES, InventoryMovement, Product, PurchaseOrder,
                             Sale, Supplier)
from services.validators import FormValidator, ValidationError

MAX_QUANTITY = 1_000_000


# ----------------------------------------------------------------- productos
def _validate_product(data, product=None):
    form = FormValidator(data)
    values = {
        "name": form.text("name", "El nombre", max_length=120),
        "category": form.choice("category", "La categoría", PRODUCT_CATEGORIES),
        "description": form.text("description", "La descripción", required=False, max_length=300),
        "price": form.number("price", "El precio", min_value=0, max_value=100_000_000, exclusive_min=True),
        "minimum_stock": form.integer("minimum_stock", "El stock mínimo", min_value=0, max_value=MAX_QUANTITY),
        "current_stock": form.integer("current_stock", "El stock", min_value=0, max_value=MAX_QUANTITY),
        "supplier_id": form.integer("supplier_id", "El proveedor", min_value=1),
    }
    if values["supplier_id"] and db.session.get(Supplier, values["supplier_id"]) is None:
        form.errors["supplier_id"] = "El proveedor seleccionado no existe."
    if values["name"]:
        duplicate = Product.query.filter(func.lower(Product.name) == values["name"].lower())
        if product is not None:
            duplicate = duplicate.filter(Product.id != product.id)
        if duplicate.first():
            form.errors["name"] = "Ya existe un producto con ese nombre."
    form.raise_if_errors()
    return values


def _add_movement(product, movement_type, quantity, description, when=None):
    """Registra el movimiento y actualiza el stock en la misma transacción."""
    new_stock = product.current_stock + quantity
    if new_stock < 0:
        raise ValidationError({"quantity": f"Stock insuficiente: hay {product.current_stock} unidades disponibles."})
    product.current_stock = new_stock
    movement = InventoryMovement(product=product, movement_type=movement_type, quantity=quantity,
                                 description=description, movement_date=when or datetime.now())
    db.session.add(movement)
    return movement


def create_product(data):
    values = _validate_product(data)
    initial_stock = values.pop("current_stock")
    product = Product(**values, current_stock=0)
    db.session.add(product)
    if initial_stock > 0:
        _add_movement(product, "entrada", initial_stock, "Inventario inicial")
    db.session.commit()
    return product


def update_product(product, data):
    values = _validate_product(data, product)
    new_stock = values.pop("current_stock")
    for field, value in values.items():
        setattr(product, field, value)
    difference = new_stock - product.current_stock
    if difference != 0:
        # Un cambio manual de stock se registra como ajuste para no perder la trazabilidad
        _add_movement(product, "ajuste", difference, "Ajuste manual desde la edición del producto")
    db.session.commit()
    return product


def delete_product(product):
    db.session.delete(product)   # cascada: ventas, movimientos, órdenes y alertas
    db.session.commit()


def filter_products(search=None, category=None, stock_level=None):
    query = Product.query
    if search:
        pattern = f"%{search.strip()}%"
        query = query.filter(db.or_(Product.name.ilike(pattern), Product.category.ilike(pattern)))
    if category:
        query = query.filter(Product.category == category)
    if stock_level == "agotado":
        query = query.filter(Product.current_stock == 0)
    elif stock_level == "bajo":
        query = query.filter(Product.current_stock > 0, Product.current_stock <= Product.minimum_stock)
    elif stock_level == "normal":
        query = query.filter(Product.current_stock > Product.minimum_stock)
    return query.order_by(Product.name).all()


# --------------------------------------------------------------- proveedores
def _validate_supplier(data, supplier=None):
    form = FormValidator(data)
    values = {
        "name": form.text("name", "El nombre", max_length=120),
        "contact": form.text("contact", "El contacto", max_length=120),
        "email": form.email("email", "El correo"),
        "phone": form.text("phone", "El teléfono", max_length=30),
        "delivery_days": form.integer("delivery_days", "El tiempo de entrega", min_value=1, max_value=365),
    }
    if values["name"]:
        duplicate = Supplier.query.filter(func.lower(Supplier.name) == values["name"].lower())
        if supplier is not None:
            duplicate = duplicate.filter(Supplier.id != supplier.id)
        if duplicate.first():
            form.errors["name"] = "Ya existe un proveedor con ese nombre."
    form.raise_if_errors()
    return values


def create_supplier(data):
    supplier = Supplier(**_validate_supplier(data))
    db.session.add(supplier)
    db.session.commit()
    return supplier


def update_supplier(supplier, data):
    for field, value in _validate_supplier(data, supplier).items():
        setattr(supplier, field, value)
    db.session.commit()
    return supplier


def delete_supplier(supplier):
    if supplier.products:
        raise ValidationError({"general": "No se puede eliminar: el proveedor tiene productos asociados."})
    if supplier.purchase_orders:
        raise ValidationError({"general": "No se puede eliminar: el proveedor tiene órdenes de compra registradas."})
    db.session.delete(supplier)
    db.session.commit()


def associate_product(supplier, data):
    form = FormValidator(data)
    product_id = form.integer("product_id", "El producto", min_value=1)
    form.raise_if_errors()
    product = db.session.get(Product, product_id)
    if product is None:
        raise ValidationError({"product_id": "El producto no existe."})
    product.supplier = supplier
    db.session.commit()
    return product


# -------------------------------------------------------------------- ventas
def register_sale(data):
    """Registra una venta y descuenta el inventario. Rechaza ventas mayores al stock."""
    form = FormValidator(data)
    product_id = form.integer("product_id", "El producto", min_value=1)
    quantity = form.integer("quantity", "La cantidad", min_value=1, max_value=MAX_QUANTITY)
    promotion = form.boolean("promotion")
    discount = form.number("discount_percentage", "El descuento", required=False, min_value=0, max_value=90) or 0.0
    sale_day = form.date_value("sale_date", "La fecha", required=False, max_value=date.today())
    form.raise_if_errors()

    product = db.session.get(Product, product_id)
    if product is None:
        raise ValidationError({"product_id": "El producto no existe."})
    if promotion and discount <= 0:
        raise ValidationError({"discount_percentage": "Una venta en promoción debe tener un descuento mayor que 0."})
    if not promotion and discount > 0:
        raise ValidationError({"discount_percentage": "Solo las ventas en promoción pueden tener descuento."})
    if quantity > product.current_stock:
        raise ValidationError({"quantity": f"Stock insuficiente: hay {product.current_stock} unidades de "
                                           f"'{product.name}' y se intentó vender {quantity}."})

    now = datetime.now()
    sale_time = now if sale_day in (None, now.date()) else datetime.combine(sale_day, now.time())
    sale = Sale(product=product, quantity=quantity, sale_date=sale_time, promotion=promotion,
                discount_percentage=discount, unit_price=round(product.price * (1 - discount / 100), 2))
    db.session.add(sale)
    _add_movement(product, "salida", -quantity, "Salida por venta", when=sale_time)
    db.session.commit()
    return sale


def filter_sales(product_id=None, date_from=None, date_to=None):
    query = Sale.query
    if product_id:
        query = query.filter(Sale.product_id == product_id)
    if date_from:
        query = query.filter(Sale.sale_date >= datetime.combine(date_from, datetime.min.time()))
    if date_to:
        query = query.filter(Sale.sale_date < datetime.combine(date_to + timedelta(days=1), datetime.min.time()))
    return query.order_by(Sale.sale_date.desc(), Sale.id.desc())


# --------------------------------------------------------------- movimientos
def register_movement(product, data):
    """Entrada de mercancía o ajuste manual (positivo o negativo)."""
    form = FormValidator(data)
    movement_type = form.choice("movement_type", "El tipo de movimiento", ["entrada", "ajuste"])
    quantity = form.integer("quantity", "La cantidad", min_value=-MAX_QUANTITY, max_value=MAX_QUANTITY)
    description = form.text("description", "La descripción", max_length=200)
    form.raise_if_errors()
    if quantity == 0:
        raise ValidationError({"quantity": "La cantidad no puede ser 0."})
    if movement_type == "entrada" and quantity < 0:
        raise ValidationError({"quantity": "Una entrada debe tener cantidad positiva."})
    movement = _add_movement(product, movement_type, quantity, description)
    db.session.commit()
    return movement


# ---------------------------------------------------------- órdenes de compra
def create_purchase_order(product, data):
    form = FormValidator(data)
    quantity = form.integer("quantity", "La cantidad", min_value=1, max_value=MAX_QUANTITY)
    form.raise_if_errors()
    today = date.today()
    order = PurchaseOrder(product=product, supplier=product.supplier, quantity=quantity, order_date=today,
                          expected_delivery=today + timedelta(days=product.supplier.delivery_days),
                          status="pendiente")
    db.session.add(order)
    db.session.commit()
    return order


def receive_purchase_order(order):
    if order.status != "pendiente":
        raise ValidationError({"general": "Solo se pueden recibir órdenes pendientes."})
    order.status = "recibida"
    _add_movement(order.product, "entrada", order.quantity, f"Recepción de orden de compra #{order.id}")
    db.session.commit()
    return order


def cancel_purchase_order(order):
    if order.status != "pendiente":
        raise ValidationError({"general": "Solo se pueden cancelar órdenes pendientes."})
    order.status = "cancelada"
    db.session.commit()
    return order


def pending_orders(product_ids=None):
    query = PurchaseOrder.query.filter_by(status="pendiente")
    if product_ids is not None:
        query = query.filter(PurchaseOrder.product_id.in_(product_ids))
    return query.order_by(PurchaseOrder.expected_delivery).all()


# ------------------------------------------------- historial para el modelo
def daily_sales_history(products, end_date, days=60):
    """
    Ventas diarias por producto en los `days` días anteriores a `end_date`
    (sin incluirlo). Los días sin ventas valen 0. Solo cuenta desde que el
    producto existe, para no inventar días con cero ventas antes de su registro.
    """
    start_date = end_date - timedelta(days=days)
    product_ids = [product.id for product in products]
    rows = (db.session.query(Sale.product_id, func.date(Sale.sale_date), func.sum(Sale.quantity))
            .filter(Sale.product_id.in_(product_ids),
                    Sale.sale_date >= datetime.combine(start_date, datetime.min.time()),
                    Sale.sale_date < datetime.combine(end_date, datetime.min.time()))
            .group_by(Sale.product_id, func.date(Sale.sale_date)).all())
    totals = {(product_id, str(day)): int(quantity) for product_id, day, quantity in rows}

    histories = {}
    for product in products:
        first_day = max(start_date, product.created_at.date())
        n_days = (end_date - first_day).days
        histories[product.id] = [totals.get((product.id, (first_day + timedelta(days=i)).isoformat()), 0)
                                 for i in range(max(n_days, 0))]
    return histories


def sales_on_day(products, day):
    """Unidades ya vendidas en un día (se usa para descontarlas de la demanda de hoy)."""
    rows = (db.session.query(Sale.product_id, func.sum(Sale.quantity))
            .filter(Sale.product_id.in_([product.id for product in products]),
                    func.date(Sale.sale_date) == day.isoformat())
            .group_by(Sale.product_id).all())
    return {product_id: int(quantity) for product_id, quantity in rows}


# --------------------------------------------------------- estadísticas
def daily_sales_totals(days=90, product_id=None, include_today=True):
    """Unidades e ingresos por día (se calculan desde Sale, no se guardan)."""
    last_day = date.today() if include_today else date.today() - timedelta(days=1)
    start = last_day - timedelta(days=days - 1)
    query = (db.session.query(func.date(Sale.sale_date), func.sum(Sale.quantity),
                              func.sum(Sale.quantity * Sale.unit_price))
             .filter(Sale.sale_date >= datetime.combine(start, datetime.min.time()),
                     Sale.sale_date < datetime.combine(last_day + timedelta(days=1), datetime.min.time())))
    if product_id:
        query = query.filter(Sale.product_id == product_id)
    rows = {str(day): (int(units), float(revenue)) for day, units, revenue in
            query.group_by(func.date(Sale.sale_date)).all()}
    labels = [(start + timedelta(days=i)).isoformat() for i in range(days)]
    return {"labels": labels,
            "units": [rows.get(label, (0, 0))[0] for label in labels],
            "revenue": [round(rows.get(label, (0, 0))[1]) for label in labels]}


def top_selling_products(days=30, limit=5):
    since = datetime.combine(date.today() - timedelta(days=days), datetime.min.time())
    return (db.session.query(Product, func.sum(Sale.quantity).label("units"))
            .join(Sale).filter(Sale.sale_date >= since)
            .group_by(Product.id).order_by(func.sum(Sale.quantity).desc()).limit(limit).all())
