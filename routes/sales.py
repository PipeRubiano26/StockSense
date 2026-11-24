"""Ventas: registro (descuenta inventario) e historial con filtros."""
from datetime import date

from flask import Blueprint, flash, redirect, render_template, request, url_for

from database.models import Product
from routes import refresh_product_alerts
from services import inventory_service
from services.validators import FormValidator, ValidationError

sales_bp = Blueprint("sales", __name__, url_prefix="/sales")


@sales_bp.get("/")
def list_sales():
    form = FormValidator(request.args)
    product_id = form.integer("product_id", "El producto", required=False, min_value=1)
    date_from = form.date_value("date_from", "Desde", required=False)
    date_to = form.date_value("date_to", "Hasta", required=False)
    for message in form.errors.values():
        flash(message, "danger")
    query = inventory_service.filter_sales(product_id, date_from, date_to)
    page = query.paginate(page=request.args.get("page", 1, type=int), per_page=25, error_out=False)
    return render_template("sales/list.html", page=page, products=Product.query.order_by(Product.name).all(),
                           filters={"product_id": product_id, "date_from": date_from, "date_to": date_to})


@sales_bp.route("/new", methods=["GET", "POST"])
def create():
    errors = {}
    values = request.form if request.method == "POST" else {
        "product_id": request.args.get("product_id", ""), "sale_date": date.today().isoformat(), "quantity": 1}
    if request.method == "POST":
        try:
            sale = inventory_service.register_sale(request.form)
            refresh_product_alerts(sale.product)
            flash(f"Venta registrada: {sale.quantity} u. de '{sale.product.name}'. "
                  f"Stock restante: {sale.product.current_stock}.", "success")
            return redirect(url_for("sales.list_sales"))
        except ValidationError as error:
            errors = error.errors
    return render_template("sales/form.html", values=values, errors=errors,
                           products=Product.query.order_by(Product.name).all(),
                           today=date.today().isoformat()), (400 if errors else 200)
