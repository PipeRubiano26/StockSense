"""Modelos de datos (tablas SQLite) de StockSense."""
from datetime import date, datetime

from sqlalchemy import CheckConstraint

from database import db

PRODUCT_CATEGORIES = ["Abarrotes", "Aseo", "Bebidas", "Cuidado personal", "Lácteos", "Snacks"]
MOVEMENT_TYPES = ["entrada", "salida", "ajuste"]
ORDER_STATUSES = ["pendiente", "recibida", "cancelada"]
ALERT_TYPES = {
    "stock_bajo": "Stock bajo",
    "agotamiento_proximo": "Próximo a agotarse",
    "quiebre_antes_reposicion": "Se agota antes de reponer",
    "reposicion": "Requiere reposición",
    "retraso_proveedor": "Retraso del proveedor",
}
ALERT_STATUSES = ["activa", "resuelta"]


class Supplier(db.Model):
    __tablename__ = "suppliers"
    __table_args__ = (CheckConstraint("delivery_days > 0", name="ck_supplier_delivery_days"),)

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, unique=True)
    contact = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(30), nullable=False)
    delivery_days = db.Column(db.Integer, nullable=False)

    products = db.relationship("Product", back_populates="supplier", order_by="Product.name")
    purchase_orders = db.relationship("PurchaseOrder", back_populates="supplier")


class Product(db.Model):
    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint("price > 0", name="ck_product_price"),
        CheckConstraint("current_stock >= 0", name="ck_product_stock"),
        CheckConstraint("minimum_stock >= 0", name="ck_product_minimum_stock"),
    )

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, unique=True)
    category = db.Column(db.String(60), nullable=False)
    description = db.Column(db.String(300), nullable=True)
    price = db.Column(db.Float, nullable=False)
    current_stock = db.Column(db.Integer, nullable=False, default=0)
    minimum_stock = db.Column(db.Integer, nullable=False, default=0)
    supplier_id = db.Column(db.Integer, db.ForeignKey("suppliers.id", ondelete="RESTRICT"), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)

    supplier = db.relationship("Supplier", back_populates="products")
    # Al eliminar un producto se elimina su historial asociado
    sales = db.relationship("Sale", back_populates="product", cascade="all, delete-orphan")
    movements = db.relationship("InventoryMovement", back_populates="product", cascade="all, delete-orphan")
    purchase_orders = db.relationship("PurchaseOrder", back_populates="product", cascade="all, delete-orphan")
    alerts = db.relationship("Alert", back_populates="product", cascade="all, delete-orphan")

    @property
    def stock_level(self):
        """Nivel de stock según el stock mínimo: agotado, bajo o normal."""
        if self.current_stock == 0:
            return "agotado"
        if self.current_stock <= self.minimum_stock:
            return "bajo"
        return "normal"


class Sale(db.Model):
    __tablename__ = "sales"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_sale_quantity"),
        CheckConstraint("unit_price >= 0", name="ck_sale_unit_price"),
        CheckConstraint("discount_percentage >= 0 AND discount_percentage <= 100", name="ck_sale_discount"),
    )

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    sale_date = db.Column(db.DateTime, nullable=False, default=datetime.now, index=True)
    quantity = db.Column(db.Integer, nullable=False)
    unit_price = db.Column(db.Float, nullable=False)  # precio final por unidad (con descuento)
    promotion = db.Column(db.Boolean, nullable=False, default=False)
    discount_percentage = db.Column(db.Float, nullable=False, default=0)

    product = db.relationship("Product", back_populates="sales")

    @property
    def total(self):
        return self.quantity * self.unit_price


class InventoryMovement(db.Model):
    """
    Cada cambio de stock queda registrado. La cantidad tiene signo:
    entrada > 0, salida < 0, ajuste puede ser positivo o negativo.
    Por eso la suma de movimientos de un producto es igual a su stock actual.
    """
    __tablename__ = "inventory_movements"
    __table_args__ = (
        CheckConstraint("movement_type IN ('entrada', 'salida', 'ajuste')", name="ck_movement_type"),
        CheckConstraint("quantity <> 0", name="ck_movement_quantity"),
        CheckConstraint("(movement_type <> 'entrada' OR quantity > 0) AND (movement_type <> 'salida' OR quantity < 0)",
                        name="ck_movement_sign"),
    )

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    movement_type = db.Column(db.String(20), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    movement_date = db.Column(db.DateTime, nullable=False, default=datetime.now)
    description = db.Column(db.String(200), nullable=True)

    product = db.relationship("Product", back_populates="movements")


class PurchaseOrder(db.Model):
    __tablename__ = "purchase_orders"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_order_quantity"),
        CheckConstraint("status IN ('pendiente', 'recibida', 'cancelada')", name="ck_order_status"),
        CheckConstraint("expected_delivery >= order_date", name="ck_order_dates"),
    )

    id = db.Column(db.Integer, primary_key=True)
    supplier_id = db.Column(db.Integer, db.ForeignKey("suppliers.id", ondelete="RESTRICT"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    quantity = db.Column(db.Integer, nullable=False)
    order_date = db.Column(db.Date, nullable=False, default=date.today)
    expected_delivery = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="pendiente")

    supplier = db.relationship("Supplier", back_populates="purchase_orders")
    product = db.relationship("Product", back_populates="purchase_orders")

    @property
    def is_delayed(self):
        """Un pedido pendiente cuya fecha de entrega ya pasó está retrasado (se calcula, no se guarda)."""
        return self.status == "pendiente" and self.expected_delivery < date.today()

    @property
    def days_delayed(self):
        return (date.today() - self.expected_delivery).days if self.is_delayed else 0


class Alert(db.Model):
    __tablename__ = "alerts"
    __table_args__ = (
        CheckConstraint("status IN ('activa', 'resuelta')", name="ck_alert_status"),
        CheckConstraint("alert_type IN ('stock_bajo', 'agotamiento_proximo', 'quiebre_antes_reposicion', "
                        "'reposicion', 'retraso_proveedor')", name="ck_alert_type"),
    )

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    alert_type = db.Column(db.String(40), nullable=False)
    message = db.Column(db.String(400), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
    status = db.Column(db.String(20), nullable=False, default="activa")

    product = db.relationship("Product", back_populates="alerts")

    @property
    def type_label(self):
        return ALERT_TYPES.get(self.alert_type, self.alert_type)
