"""Alertas de inventario."""
from flask import Blueprint, flash, redirect, render_template, url_for

from database.models import ALERT_TYPES, Alert
from routes import get_or_404, get_prediction_service
from services import alert_service, inventory_service

alerts_bp = Blueprint("alerts", __name__, url_prefix="/alerts")


@alerts_bp.get("/")
def index():
    # Se recalculan al abrir la página: la fecha de hoy y el stock cambian las condiciones
    analyses = alert_service.refresh_alerts(get_prediction_service())
    active = alert_service.active_alerts()
    resolved = Alert.query.filter_by(status="resuelta").order_by(Alert.created_at.desc()).limit(30).all()
    grouped = {alert_type: [a for a in active if a.alert_type == alert_type] for alert_type in ALERT_TYPES}
    return render_template("alerts/index.html", grouped=grouped, alert_types=ALERT_TYPES, resolved=resolved,
                           analyses=analyses, delayed_orders=[o for o in inventory_service.pending_orders()
                                                              if o.is_delayed])


@alerts_bp.post("/refresh")
def refresh():
    alert_service.refresh_alerts(get_prediction_service())
    flash("Alertas recalculadas con los datos actuales y el modelo.", "success")
    return redirect(url_for("alerts.index"))


@alerts_bp.post("/<int:alert_id>/resolve")
def resolve(alert_id):
    alert_service.resolve_alert(get_or_404(Alert, alert_id))
    flash("Alerta marcada como resuelta. Si la condición persiste, se generará de nuevo al recalcular.", "info")
    return redirect(url_for("alerts.index"))
