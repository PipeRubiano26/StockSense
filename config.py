"""Configuración central de StockSense.

Los valores por defecto sirven para la ejecución local en Windows. En Kubernetes
se sobrescriben con variables de entorno (ver k8s/deployment.yaml).
"""
import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


def _env_flag(name, default):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "si", "sí")


class Config:
    SECRET_KEY = os.environ.get("STOCKSENSE_SECRET_KEY", "stocksense-dev-key")
    DATABASE_PATH = os.environ.get("STOCKSENSE_DB_PATH", os.path.join(BASE_DIR, "stocksense.db"))
    SQLALCHEMY_DATABASE_URI = "sqlite:///" + DATABASE_PATH
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # Espera hasta 15 s si otra réplica tiene la base bloqueada (SQLite compartido)
    SQLALCHEMY_ENGINE_OPTIONS = {"connect_args": {"timeout": 15}}

    # Modelo entrenado en el notebook (la app SOLO lo carga, nunca entrena)
    MODEL_PATH = os.path.join(BASE_DIR, "models", "demand_model.joblib")
    MODEL_METADATA_PATH = os.path.join(BASE_DIR, "models", "model_metadata.json")

    # Parámetros de negocio de las predicciones
    FORECAST_HORIZON_DAYS = 90      # máximo de días que se proyectan
    COVERAGE_DAYS = 14              # días de cobertura extra al recomendar reposición
    # Carga datos iniciales solo si la BD está vacía. En Kubernetes lo hace el initContainer.
    SEED_ON_STARTUP = _env_flag("STOCKSENSE_SEED_ON_STARTUP", True)

    # Endpoints para simular fallas en la demo de autorrecuperación (solo Kubernetes)
    ENABLE_CHAOS = _env_flag("STOCKSENSE_ENABLE_CHAOS", False)


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_ENGINE_OPTIONS = {}
    SEED_ON_STARTUP = False
    ENABLE_CHAOS = False
