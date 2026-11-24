"""Dashboard: indicadores calculados a partir de las tablas (no se almacenan)."""
from flask import Blueprint, render_template

from database.models import Product
from routes import get_prediction_service
from services import alert_service, inventory_service

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.get("/")
def index():
    service = get_prediction_service()
    products = Product.query.order_by(Product.name).all()
    # Una sola pasada del modelo: actualiza alertas y entrega la demanda estimada
    analyses = alert_service.refresh_alerts(service, products) if products else {}

    at_risk = sorted(
        [(product, analyses[product.id]) for product in products if product.id in analyses],
        key=lambda item: (item[1]["days_to_stockout"] if item[1]["days_to_stockout"] is not None else 9999))
    risk_counts = {level: 0 for level in ("crítico", "alto", "medio", "bajo")}
    for analysis in analyses.values():
        risk_counts[analysis["risk"]] += 1

    stats = {
        "total_products": len(products),
        "total_units": sum(product.current_stock for product in products),
        "inventory_value": sum(product.current_stock * product.price for product in products),
        "low_stock": sum(1 for product in products if product.current_stock <= product.minimum_stock),
        "active_alerts": len(alert_service.active_alerts()),
        "demand_7d": sum(analysis["demand_7d"] for analysis in analyses.values()) if analyses else None,
        "demand_today": sum(analysis["demand_today"] for analysis in analyses.values()) if analyses else None,
    }
    charts = {
        "sales": inventory_service.daily_sales_totals(days=90),
        "inventory": {
            "labels": [product.name for product in products],
            "stock": [product.current_stock for product in products],
            "minimum": [product.minimum_stock for product in products],
        },
        "risk": risk_counts,
    }
    top_products = inventory_service.top_selling_products(days=30, limit=5)
    return render_template("dashboard.html", stats=stats, charts=charts, at_risk=at_risk[:6],
                           top_products=top_products, model_available=service.available)
