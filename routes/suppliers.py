"""Proveedores: registro, edición, tiempos de entrega y asociación de productos."""
from flask import Blueprint, flash, redirect, render_template, request, url_for

from database.models import Product, Supplier
from routes import get_or_404, refresh_product_alerts
from services import inventory_service
from services.validators import ValidationError

suppliers_bp = Blueprint("suppliers", __name__, url_prefix="/suppliers")


@suppliers_bp.get("/")
def list_suppliers():
    suppliers = Supplier.query.order_by(Supplier.delivery_days, Supplier.name).all()
    return render_template("suppliers/list.html", suppliers=suppliers)


@suppliers_bp.route("/new", methods=["GET", "POST"])
def create():
    errors = {}
    if request.method == "POST":
        try:
            supplier = inventory_service.create_supplier(request.form)
            flash(f"Proveedor '{supplier.name}' registrado.", "success")
            return redirect(url_for("suppliers.detail", supplier_id=supplier.id))
        except ValidationError as error:
            errors = error.errors
    return render_template("suppliers/form.html", supplier=None, values=request.form, errors=errors), \
        (400 if errors else 200)


@suppliers_bp.route("/<int:supplier_id>/edit", methods=["GET", "POST"])
def edit(supplier_id):
    supplier = get_or_404(Supplier, supplier_id)
    errors = {}
    values = request.form if request.method == "POST" else {
        "name": supplier.name, "contact": supplier.contact, "email": supplier.email,
        "phone": supplier.phone, "delivery_days": supplier.delivery_days}
    if request.method == "POST":
        try:
            inventory_service.update_supplier(supplier, request.form)
            # El tiempo de entrega cambia el riesgo de sus productos
            refresh_product_alerts(*supplier.products)
            flash("Proveedor actualizado.", "success")
            return redirect(url_for("suppliers.detail", supplier_id=supplier.id))
        except ValidationError as error:
            errors = error.errors
    return render_template("suppliers/form.html", supplier=supplier, values=values, errors=errors), \
        (400 if errors else 200)


@suppliers_bp.get("/<int:supplier_id>")
def detail(supplier_id):
    supplier = get_or_404(Supplier, supplier_id)
    other_products = Product.query.filter(Product.supplier_id != supplier.id).order_by(Product.name).all()
    orders = sorted(supplier.purchase_orders, key=lambda o: (o.order_date, o.id), reverse=True)[:15]
    return render_template("suppliers/detail.html", supplier=supplier, other_products=other_products,
                           orders=orders)


@suppliers_bp.post("/<int:supplier_id>/associate")
def associate(supplier_id):
    supplier = get_or_404(Supplier, supplier_id)
    try:
        product = inventory_service.associate_product(supplier, request.form)
        refresh_product_alerts(product)
        flash(f"'{product.name}' ahora se abastece con {supplier.name}.", "success")
    except ValidationError as error:
        for message in error.errors.values():
            flash(message, "danger")
    return redirect(url_for("suppliers.detail", supplier_id=supplier.id))


@suppliers_bp.post("/<int:supplier_id>/delete")
def delete(supplier_id):
    supplier = get_or_404(Supplier, supplier_id)
    try:
        inventory_service.delete_supplier(supplier)
        flash("Proveedor eliminado.", "success")
        return redirect(url_for("suppliers.list_suppliers"))
    except ValidationError as error:
        for message in error.errors.values():
            flash(message, "danger")
        return redirect(url_for("suppliers.detail", supplier_id=supplier.id))
