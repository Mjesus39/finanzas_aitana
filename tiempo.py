# ======================================================
# tiempo.py — control horario centralizado (hora real Chile 🇨🇱)
# ======================================================

from datetime import datetime, time, timedelta, date
import pytz
from zoneinfo import ZoneInfo

# Zona horaria de Chile
CHILE_TZ = pytz.timezone("America/Santiago")

# ======================================================
# 🕒 Hora actual
# ======================================================
def hora_actual():
    """
    Devuelve la hora actual en la zona horaria de Chile,
    sin información de zona horaria (naive) para evitar
    que SQLAlchemy la convierta a UTC al guardar.
    """
    return datetime.now(CHILE_TZ).replace(tzinfo=None)

# ======================================================
# 📅 Día en hora local
# ======================================================
def local_date():
    """Devuelve solo la fecha (YYYY-MM-DD) en hora chilena."""
    return hora_actual().date()

# ======================================================
# 📆 Rango del día (inicio y fin)
# ======================================================
def day_range(fecha: date):
    """Devuelve el rango de inicio y fin del día, en hora de Chile."""
    start = datetime.combine(fecha, time.min)
    end = start + timedelta(days=1)
    return start, end

# ======================================================
# 🕓 Conversión segura para mostrar en pantallas
# ======================================================
def to_hora_chile(value):
    """Convierte fechas o datetimes a formato chileno legible (corrige desfase)."""
    if not value:
        return ""

    # Si es un objeto date (sin hora)
    if isinstance(value, date) and not hasattr(value, "hour"):
        return value.strftime("%d/%m/%Y")

    try:
        zona_chile = ZoneInfo("America/Santiago")

        # Si no tiene zona horaria, asumimos que ya está en hora local
        if value.tzinfo is None:
            local_value = value
        else:
            local_value = value.astimezone(zona_chile)

        return local_value.strftime("%d/%m/%Y %H:%M:%S")

    except Exception:
        return str(value)
