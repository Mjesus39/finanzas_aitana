# ======================================================
# tiempo.py — versión estable Render + Local (Chile 🇨🇱)
# ======================================================

from datetime import datetime, time, timedelta, date
from zoneinfo import ZoneInfo

# Zona horaria oficial de Chile continental
CHILE_TZ = ZoneInfo("America/Santiago")

# ======================================================
# 🕒 Hora actual
# ======================================================
def hora_actual():
    """
    Devuelve la hora actual en la zona horaria de Chile (correcta en Render).
    """
    return datetime.now(CHILE_TZ)

# ======================================================
# 📅 Fecha local
# ======================================================
def local_date():
    """Devuelve solo la fecha (YYYY-MM-DD) en hora chilena."""
    return hora_actual().date()

# ======================================================
# 📆 Rango de día
# ======================================================
def day_range(fecha: date):
    """Devuelve el rango de inicio y fin del día en hora de Chile."""
    start = datetime.combine(fecha, time.min, tzinfo=CHILE_TZ)
    end = start + timedelta(days=1)
    return start, end

# ======================================================
# 🕓 Conversión segura para mostrar
# ======================================================
def to_hora_chile(value):
    """Convierte datetimes a hora local chilena legible."""
    if not value:
        return ""

    try:
        if value.tzinfo is None:
            # Asumimos que viene en UTC si no tiene zona
            value = value.replace(tzinfo=ZoneInfo("UTC"))
        local_value = value.astimezone(CHILE_TZ)
        return local_value.strftime("%d/%m/%Y %H:%M:%S")
    except Exception:
        return str(value)
