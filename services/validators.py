"""
Validación de datos de entrada (formularios y API).

FormValidator lee cada campo, lo convierte al tipo esperado y acumula los
errores para mostrarlos todos a la vez en el formulario.
"""
import re
from datetime import date, datetime

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class ValidationError(Exception):
    """Error de validación con un diccionario {campo: mensaje}."""

    def __init__(self, errors):
        self.errors = errors if isinstance(errors, dict) else {"general": str(errors)}
        super().__init__("; ".join(f"{field}: {message}" for field, message in self.errors.items()))


class FormValidator:
    def __init__(self, data):
        self.data = data or {}
        self.errors = {}

    def _raw(self, field):
        value = self.data.get(field)
        if isinstance(value, str):
            value = value.strip()
        return None if value in (None, "") else value

    def _missing(self, field, required, label):
        if required:
            self.errors[field] = f"{label} es obligatorio."
        return None

    def text(self, field, label, required=True, max_length=120):
        value = self._raw(field)
        if value is None:
            return self._missing(field, required, label)
        value = str(value)
        if len(value) > max_length:
            self.errors[field] = f"{label} no puede superar {max_length} caracteres."
        return value

    def integer(self, field, label, required=True, min_value=None, max_value=None):
        value = self._raw(field)
        if value is None:
            return self._missing(field, required, label)
        try:
            if isinstance(value, bool) or (isinstance(value, float) and not value.is_integer()):
                raise ValueError
            number = int(str(value))
        except (TypeError, ValueError):
            self.errors[field] = f"{label} debe ser un número entero."
            return None
        return self._check_range(field, label, number, min_value, max_value)

    def number(self, field, label, required=True, min_value=None, max_value=None, exclusive_min=False):
        value = self._raw(field)
        if value is None:
            return self._missing(field, required, label)
        try:
            if isinstance(value, bool):
                raise ValueError
            number = float(str(value).replace(",", "."))
            if number != number or number in (float("inf"), float("-inf")):   # NaN o infinito
                raise ValueError
        except (TypeError, ValueError):
            self.errors[field] = f"{label} debe ser un número."
            return None
        if exclusive_min and min_value is not None and number <= min_value:
            self.errors[field] = f"{label} debe ser mayor que {min_value:g}."
            return None
        return self._check_range(field, label, number, min_value, max_value)

    def _check_range(self, field, label, number, min_value, max_value):
        if min_value is not None and number < min_value:
            self.errors[field] = f"{label} no puede ser menor que {min_value:g}."
            return None
        if max_value is not None and number > max_value:
            self.errors[field] = f"{label} no puede ser mayor que {max_value:g}."
            return None
        return number

    def boolean(self, field):
        value = self._raw(field)
        if isinstance(value, bool):
            return value
        return str(value).lower() in ("1", "true", "on", "si", "sí", "yes")

    def choice(self, field, label, options, required=True):
        value = self.text(field, label, required=required)
        if value is not None and value not in options:
            self.errors[field] = f"{label} no es una opción válida."
            return None
        return value

    def email(self, field, label, required=True):
        value = self.text(field, label, required=required)
        if value is not None and not EMAIL_PATTERN.match(value):
            self.errors[field] = f"{label} no tiene un formato válido."
            return None
        return value

    def date_value(self, field, label, required=True, max_value=None):
        value = self._raw(field)
        if value is None:
            return self._missing(field, required, label)
        if isinstance(value, datetime):
            parsed = value.date()
        elif isinstance(value, date):
            parsed = value
        else:
            try:
                parsed = datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
            except ValueError:
                self.errors[field] = f"{label} debe tener el formato AAAA-MM-DD."
                return None
        if max_value is not None and parsed > max_value:
            self.errors[field] = f"{label} no puede ser posterior a {max_value.isoformat()}."
            return None
        return parsed

    def raise_if_errors(self):
        if self.errors:
            raise ValidationError(self.errors)
