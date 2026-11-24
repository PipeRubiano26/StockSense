"""Pruebas de validación de entradas (campos obligatorios, tipos, rangos y formatos)."""
from datetime import date

import pytest

from services.validators import FormValidator, ValidationError


def test_required_and_optional_fields():
    form = FormValidator({"name": "   ", "note": ""})
    assert form.text("name", "El nombre") is None
    assert form.text("note", "La nota", required=False) is None
    assert form.errors == {"name": "El nombre es obligatorio."}


@pytest.mark.parametrize("value, expected", [("10", 10), (7, 7), ("0", 0)])
def test_integer_valid_values(value, expected):
    assert FormValidator({"n": value}).integer("n", "N", min_value=0) == expected


@pytest.mark.parametrize("value", ["abc", "1.5", 2.5, True, "1e3"])
def test_integer_rejects_non_integers(value):
    form = FormValidator({"n": value})
    assert form.integer("n", "N") is None and "entero" in form.errors["n"]


def test_number_ranges_and_negative_values():
    form = FormValidator({"price": "-1", "zero": "0", "big": "500", "comma": "12,5", "nan": "nan"})
    assert form.number("price", "El precio", min_value=0) is None
    assert form.number("zero", "Cero", min_value=0, exclusive_min=True) is None
    assert form.number("big", "Grande", max_value=100) is None
    assert form.number("comma", "Coma") == 12.5
    assert form.number("nan", "NaN") is None
    assert set(form.errors) == {"price", "zero", "big", "nan"}


def test_text_max_length_choice_and_email():
    form = FormValidator({"name": "x" * 121, "category": "Ropa", "email": "sin-arroba.com", "ok": "a@b.co"})
    form.text("name", "El nombre", max_length=120)
    form.choice("category", "La categoría", ["Snacks"])
    form.email("email", "El correo")
    assert form.email("ok", "Otro correo") == "a@b.co"
    assert set(form.errors) == {"name", "category", "email"}


def test_date_parsing_and_future_limit():
    form = FormValidator({"d1": "2026-01-15", "d2": "15/01/2026", "d3": "2999-01-01"})
    assert form.date_value("d1", "Fecha") == date(2026, 1, 15)
    assert form.date_value("d2", "Fecha") is None
    assert form.date_value("d3", "Fecha", max_value=date.today()) is None
    assert set(form.errors) == {"d2", "d3"}


def test_raise_if_errors_collects_all_messages():
    form = FormValidator({})
    form.text("a", "A")
    form.integer("b", "B")
    with pytest.raises(ValidationError) as error:
        form.raise_if_errors()
    assert set(error.value.errors) == {"a", "b"}


def test_supplier_form_validation(client):
    response = client.post("/suppliers/new", data={"name": "", "contact": "Ana", "email": "correo-invalido",
                                                   "phone": "123", "delivery_days": "0"})
    assert response.status_code == 400
    body = response.get_data(as_text=True)
    assert "El nombre es obligatorio" in body
    assert "El correo no tiene un formato válido" in body
    assert "El tiempo de entrega no puede ser menor que 1" in body


def test_api_rejects_malformed_payloads(client):
    response = client.post("/predictions/api/forecast", json={"product_id": "uno"})
    assert response.status_code == 400 and "product_id" in response.get_json()["fields"]
    response = client.post("/predictions/api/forecast", json={"product_id": 1, "horizon": 500})
    assert response.status_code == 400 and "horizon" in response.get_json()["fields"]
    response = client.post("/scenarios/api/run", json={"product_id": 1, "discount": -10, "supplier_delay": "x"})
    assert response.status_code == 400
    assert {"discount", "supplier_delay"} <= set(response.get_json()["fields"])
    response = client.post("/predictions/api/predict", data="no es json", content_type="text/plain")
    assert response.status_code == 400
