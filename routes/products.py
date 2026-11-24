"""Inventario: productos, existencias, movimientos y órdenes de compra."""
from flask import Blueprint, flash, redirect, render_template, request, url_for

from database.models import PRODUCT_CATEGORIES, Product, PurchaseOrder, Supplier
from routes import get_or_404, refresh_product_alerts
from services import inventory_service
from services.validators import ValidationError

products_bp = Blueprint("products", __name__, url_prefix="/products")


def _flash_errors(error):
    for message in error.errors.values():
        flash(message, "danger")


@products_bp.get("/")
def list_products():
    filters = {"search": request.args.get("q", "").strip(),
               "category": request.args.get("category") or None,
               "stock_level": request.args.get("stock_level") or None}
    products = inventory_service.filter_products(**filters)
    return render_template("products/list.html", products=products, filters=filters,
                           categories=PRODUCT_CATEGORIES)


@products_bp.route("/new", methods=["GET", "POST"])
def create():
    errors = {}
    if request.method == "POST":
        try:
            product = inventory_service.create_product(request.form)
            refresh_product_alerts(product)
            flash(f"Producto '{product.name}' registrado.", "success")
            return redirect(url_for("products.detail", product_id=product.id))
        except ValidationError as error:
            errors = error.errors
    return render_template("products/form.html", product=None, values=request.form, errors=errors,
                           categories=PRODUCT_CATEGORIES, suppliers=Supplier.query.order_by(Supplier.name).all()), \
        (400 if errors else 200)


@products_bp.route("/<int:product_id>/edit", methods=["GET", "POST"])
def edit(product_id):
    product = get_or_404(Product, product_id)
    errors = {}
    values = request.form if request.method == "POST" else {
        "name": product.name, "category": product.category, "description": product.description or "",
        "price": product.price, "current_stock": product.current_stock,
        "minimum_stock": product.minimum_stock, "supplier_id": product.supplier_id}
    if request.method == "POST":
        try:
            inventory_service.update_product(product, request.form)
            refresh_product_alerts(product)
            flash("Producto actualizado.", "success")
            return redirect(url_for("products.detail", product_id=product.id))
        except ValidationError as error:
            errors = error.errors
    return render_template("products/form.html", product=product, values=values, errors=errors,
                           categories=PRODUCT_CATEGORIES, suppliers=Supplier.query.order_by(Supplier.name).all()), \
        (400 if errors else 200)


@products_bp.post("/<int:product_id>/delete")
def delete(product_id):
    product = get_or_404(Product, product_id)
    name = product.name
    inventory_service.delete_product(product)
    flash(f"Producto '{name}' eliminado junto con su historial.", "success")
    return redirect(url_for("products.list_products"))


@products_bp.get("/<int:product_id>")
def detail(product_id):
    product = get_or_404(Product, product_id)
    movements = sorted(product.movements, key=lambda m: (m.movement_date, m.id), reverse=True)[:25]
    orders = sorted(product.purchase_orders, key=lambda o: (o.order_date, o.id), reverse=True)[:10]
    sales_chart = inventory_service.daily_sales_totals(days=90, product_id=product.id)
    return render_template("products/detail.html", product=product, movements=movements, orders=orders,
                           sales_chart=sales_chart,
                           active_alerts=[a for a in product.alerts if a.status == "activa"])


@products_bp.post("/<int:product_id>/movements")
def add_movement(product_id):
    product = get_or_404(Product, product_id)
    try:
        inventory_service.register_movement(product, request.form)
        refresh_product_alerts(product)
        flash("Movimiento registrado y stock actualizado.", "success")
    except ValidationError as error:
        _flash_errors(error)
    return redirect(url_for("products.detail", product_id=product.id))


@products_bp.post("/<int:product_id>/orders")
def add_order(product_id):
    product = get_or_404(Product, product_id)
    try:
        order = inventory_service.create_purchase_order(product, request.form)
        refresh_product_alerts(product)
        flash(f"Orden #{order.id} creada: entrega esperada el {order.expected_delivery.isoformat()}.", "success")
    except ValidationError as error:
        _flash_errors(error)
    return redirect(request.form.get("next") or url_for("products.detail", product_id=product.id))


@products_bp.post("/orders/<int:order_id>/<action>")
def update_order(order_id, action):
    order = get_or_404(PurchaseOrder, order_id)
    try:
        if action == "receive":
            inventory_service.receive_purchase_order(order)
            flash(f"Orden #{order.id} recibida: +{order.quantity} unidades.", "success")
        elif action == "cancel":
            inventory_service.cancel_purchase_order(order)
            flash(f"Orden #{order.id} cancelada.", "warning")
        else:
            flash("Acción no válida.", "danger")
        refresh_product_alerts(order.product)
    except ValidationError as error:
        _flash_errors(error)
    return redirect(request.form.get("next") or url_for("products.detail", product_id=order.product_id))
