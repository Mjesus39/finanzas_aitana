
# helpers.py — versión unificada y funcional
from datetime import datetime, date, time, timedelta
from decimal import Decimal, ROUND_HALF_UP
from sqlalchemy import func
from extensions import db
from modelos import Producto, Venta, MovimientoCaja, Liquidacion, HistorialInventario


# ======================================================
# 📅 RANGOS DE FECHA
# ======================================================
def day_range(fecha: date):
    """Devuelve el rango de inicio y fin de un día."""
    start = datetime.combine(fecha, time.min)
    end = start + timedelta(days=1)
    return start, end


# ======================================================
# 💼 CAJA ANTERIOR
# ======================================================
def obtener_caja_anterior(fecha: date) -> float:
    """Obtiene la caja del día anterior desde la tabla Liquidacion."""
    dia_anterior = fecha - timedelta(days=1)
    liq_anterior = Liquidacion.query.filter_by(fecha=dia_anterior).first()
    return float(liq_anterior.caja) if liq_anterior else 0.0


# ======================================================
# 📦 INVENTARIO TOTAL (CON INTERÉS)
# ======================================================
def calcular_inventario_total() -> float:
    """
    Calcula el valor total del inventario actual con ganancia:
    unidades_restantes * valor_unitario * (1 + interes/100)
    Usa Decimal para precisión contable.
    """
    total_preciso = Decimal("0.00")

    productos = Producto.query.all()
    for p in productos:
        unidades = Decimal(str(p.unidades_restantes or 0))
        valor = Decimal(str(p.valor_unitario or 0))
        interes = Decimal(str(p.interes or 0))
        subtotal = unidades * valor * (Decimal("1") + interes / Decimal("100"))
        total_preciso += subtotal

    total_final = total_preciso.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return float(total_final)


# ======================================================
# 📈 ENTRADA DE INVENTARIO
# ======================================================
def calcular_entrada_inventario(fecha: date) -> float:
    """Calcula el valor total de entradas de inventario registradas en el día."""
    start, end = day_range(fecha)

    total = db.session.query(func.coalesce(func.sum(MovimientoCaja.monto), 0)) \
        .filter(MovimientoCaja.tipo == "entrada") \
        .filter(MovimientoCaja.fecha >= start, MovimientoCaja.fecha < end) \
        .scalar() or 0.0

    return float(total)


# ======================================================
# 💰 CAJA BASE DEL DÍA
# ======================================================
def caja_base_del_dia(fecha: date):
    """Devuelve la base de caja (ventas + entradas - salidas - gastos + caja anterior)."""
    start = datetime.combine(fecha, time.min)
    end = datetime.combine(fecha + timedelta(days=1), time.min)

    caja_anterior = obtener_caja_anterior(fecha)

    # 🟢 Total de ventas del día
    ventas = (
        db.session.query(func.coalesce(func.sum(Venta.ingreso), 0))
        .filter(Venta.fecha >= start, Venta.fecha < end)
        .scalar()
        or 0.0
    )

    # 💰 Entradas
    entradas = (
        db.session.query(func.coalesce(func.sum(MovimientoCaja.monto), 0))
        .filter(MovimientoCaja.tipo == "entrada")
        .filter(MovimientoCaja.fecha >= start, MovimientoCaja.fecha < end)
        .scalar()
        or 0.0
    )

    # 💸 Salidas + Gastos
    salidas = (
        db.session.query(func.coalesce(func.sum(MovimientoCaja.monto), 0))
        .filter(MovimientoCaja.tipo.in_(["salida", "gasto"]))
        .filter(MovimientoCaja.fecha >= start, MovimientoCaja.fecha < end)
        .scalar()
        or 0.0
    )

    # 🧮 Caja total
    return float(caja_anterior + ventas + entradas - salidas)
from datetime import datetime, date

def resetear_ventas_dia():
    """Reinicia las ventas diarias si cambió el día."""
    hoy = date.today()
    for producto in Producto.query.all():
        # Si la fecha del producto es de otro día, se resetea
        if producto.fecha != hoy:
            producto.vendidas_dia = 0
            producto.valor_vendido_dia = 0
            producto.fecha = hoy
    db.session.commit()


# ======================================================
# 🧮 FUNCIONES DE APOYO (PARA OTROS MÓDULOS)
# ======================================================
def _to_float(value):
    """Convierte un valor a float de forma segura (acepta coma o punto)."""
    if value is None or str(value).strip() == "":
        return 0.0
    return float(str(value).strip().replace(",", "."))


def _to_int(value):
    """Convierte un valor a entero de forma segura."""
    if value is None or str(value).strip() == "":
        return 0
    return int(float(str(value).strip().replace(",", ".")))
