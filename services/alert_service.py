"""
Generación de alertas de inventario.

Las condiciones se recalculan desde los datos actuales (stock, pedidos y
predicción del modelo). Cada producto tiene como máximo una alerta ACTIVA por
tipo: si la condición sigue, se actualiza el mensaje; si desaparece, la alerta
pasa a 'resuelta' (queda en el historial).
"""
from datetime import date

from database import db
from database.models import Alert, Product, PurchaseOrder


def _desired_alerts(product, analysis, delayed_orders):
    """Devuelve {tipo: mensaje} con las alertas que el producto debería tener ahora."""
    alerts = {}
    if product.current_stock <= product.minimum_stock:
        alerts["stock_bajo"] = (f"Stock actual de {product.current_stock} unidades, igual o inferior al mínimo "
                                f"de {product.minimum_stock}.")
    if analysis:
        days, lead = analysis["days_to_stockout"], analysis["lead_time_days"]
        if analysis["stockout_before_replenishment"]:
            alerts["quiebre_antes_reposicion"] = (
                f"Se estima que se agote en {days:g} días ({analysis['stockout_date']}), antes de que llegue un "
                f"pedido hecho hoy: el proveedor tarda {lead} días.")
        elif days is not None and days < lead + 7:
            alerts["agotamiento_proximo"] = (
                f"Se estima que se agote en {days:g} días ({analysis['stockout_date']}). "
                f"Tiempo de entrega del proveedor: {lead} días.")
        if analysis["needs_reorder"]:
            alerts["reposicion"] = (
                f"Stock ({analysis['current_stock']}) + pedidos pendientes ({analysis['pending_quantity']}) por "
                f"debajo del punto de reorden ({analysis['reorder_point']}). Se recomienda pedir "
                f"{analysis['recommended_quantity']} unidades.")
    if delayed_orders:
        details = "; ".join(f"orden #{order.id} de {order.quantity} u. esperada el "
                            f"{order.expected_delivery.isoformat()} ({order.days_delayed} días de retraso)"
                            for order in delayed_orders)
        alerts["retraso_proveedor"] = f"{product.supplier.name}: {details}."
    return alerts


def refresh_alerts(prediction_service, products=None):
    """Recalcula las alertas de los productos indicados (o de todos). Devuelve las analizadas."""
    products = list(products) if products is not None else Product.query.all()
    if not products:
        return {}
    product_ids = [product.id for product in products]

    analyses = prediction_service.analyze_products(products) if prediction_service.available else {}
    delayed = [order for order in PurchaseOrder.query.filter(PurchaseOrder.product_id.in_(product_ids),
                                                             PurchaseOrder.status == "pendiente",
                                                             PurchaseOrder.expected_delivery < date.today())]
    active = Alert.query.filter(Alert.product_id.in_(product_ids), Alert.status == "activa").all()
    active_by_key = {(alert.product_id, alert.alert_type): alert for alert in active}

    for product in products:
        product_delayed = [order for order in delayed if order.product_id == product.id]
        desired = _desired_alerts(product, analyses.get(product.id), product_delayed)
        for alert_type, message in desired.items():
            existing = active_by_key.pop((product.id, alert_type), None)
            if existing:
                existing.message = message
            else:
                db.session.add(Alert(product=product, alert_type=alert_type, message=message))
        if not prediction_service.available:
            # Sin modelo no se pueden evaluar las alertas que dependen de la predicción
            for key in [k for k in active_by_key if k[0] == product.id and
                        k[1] in ("agotamiento_proximo", "quiebre_antes_reposicion", "reposicion")]:
                active_by_key.pop(key)

    for alert in active_by_key.values():   # condiciones que ya no se cumplen
        alert.status = "resuelta"
    db.session.commit()
    return analyses


def resolve_alert(alert):
    alert.status = "resuelta"
    db.session.commit()


def active_alerts():
    return Alert.query.filter_by(status="activa").order_by(Alert.created_at.desc()).all()
