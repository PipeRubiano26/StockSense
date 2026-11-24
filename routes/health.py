"""Endpoints de salud para Kubernetes (sondas liveness y readiness).

- /health/live   ¿El proceso responde? Si falla, Kubernetes REINICIA el contenedor.
- /health/ready  ¿Puede atender usuarios (base de datos y modelo)? Si falla, Kubernetes
                 deja de enviarle tráfico hasta que se recupere.

Los endpoints /health/chaos/* solo existen si STOCKSENSE_ENABLE_CHAOS=1 y sirven para
demostrar la autorrecuperación provocando fallas reales en una réplica.
"""
import os
import signal
import socket
import threading
import time

from flask import Blueprint, abort, current_app, jsonify, request
from sqlalchemy import text

from database import db

health_bp = Blueprint("health", __name__, url_prefix="/health")

POD_NAME = socket.gethostname()
STARTED_AT = time.time()
_state = {"hung": False}


@health_bp.before_app_request
def _reject_while_hung():
    """Mientras la réplica está 'colgada' (demo), ninguna página responde bien."""
    if _state["hung"] and not request.path.startswith("/health/") and not request.path.startswith("/static/"):
        return jsonify({"error": "Réplica bloqueada (falla simulada)", "pod": POD_NAME}), 503
    return None


def _base_info():
    return {"pod": POD_NAME, "uptime_seconds": round(time.time() - STARTED_AT, 1)}


@health_bp.get("/live")
def live():
    if _state["hung"]:
        return jsonify({**_base_info(), "status": "bloqueado"}), 503
    return jsonify({**_base_info(), "status": "ok"})


@health_bp.get("/ready")
def ready():
    checks = {}
    try:
        db.session.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:  # la base no responde o está bloqueada
        db.session.rollback()
        checks["database"] = f"error: {exc.__class__.__name__}"
    service = current_app.extensions["prediction_service"]
    checks["model"] = "ok" if service.available else "no disponible"

    healthy = all(value == "ok" for value in checks.values()) and not _state["hung"]
    body = {**_base_info(), "status": "ok" if healthy else "no listo", "checks": checks}
    return jsonify(body), (200 if healthy else 503)


def _require_chaos():
    if not current_app.config.get("ENABLE_CHAOS"):
        abort(404)


@health_bp.post("/chaos/hang")
def chaos_hang():
    """Simula que la aplicación se cuelga: la sonda liveness empieza a fallar."""
    _require_chaos()
    _state["hung"] = True
    return jsonify({**_base_info(), "status": "bloqueado",
                    "message": "La sonda liveness fallará; Kubernetes reiniciará este contenedor."})


@health_bp.post("/chaos/crash")
def chaos_crash():
    """Simula una caída: termina el proceso principal del contenedor."""
    _require_chaos()

    def _terminate():
        time.sleep(0.5)  # deja salir la respuesta antes de terminar
        # En el contenedor el PID 1 es Gunicorn (proceso principal): al terminarlo, el
        # contenedor se detiene y Kubernetes lo reinicia (restartPolicy: Always).
        os.kill(1, signal.SIGTERM)

    threading.Thread(target=_terminate, daemon=True).start()
    return jsonify({**_base_info(), "status": "cayendo",
                    "message": "El proceso termina; Kubernetes creará el contenedor de nuevo."})
