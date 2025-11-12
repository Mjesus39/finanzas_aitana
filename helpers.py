# ======================================================
# helpers.py — versión final sincronizada 🇨🇱
# ======================================================

from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from sqlalchemy import func
from extensions import db
from modelos import Producto, Venta, MovimientoCaja, LiquidacionProducto, HistorialInventario
from tiempo import hora_actual, local_date, day_range

# ======================================================
# 💼 CAJA ANTERIOR — versión definitiva robusta
# ======================================================
def obtener_caja_anterior(fecha: date) -> float:
    """
    Devuelve la caja del día anterior o, si no existe,
    la última caja registrada (aunque sea del mismo día).
    Garantiza continuidad real en la caja.
    """
    # 1️⃣ Buscar liquidación exacta del día anterior
    dia_anterior = fecha - timedelta(days=1)
    liq_anterior = LiquidacionProducto.query.filter_by(fecha=dia_anterior).first()

    if liq_anterior:
        return float(liq_anterior.caja_dia)

    # 2️⃣ Si no hay del día anterior, buscar la más reciente antes o igual a hoy
    liq_previa = (
        LiquidacionProducto.query
        .filter(LiquidacionProducto.fecha <= fecha)
        .order_by(LiquidacionProducto.fecha.desc())
        .first()
    )

    # 3️⃣ Si existe, devolver su caja_dia (continuidad garantizada)
    return float(liq_previa.caja_dia) if liq_previa else 0.0


# ======================================================
# 📦 INVENTARIO TOTAL (CON INTERÉS)
# ======================================================
def calcular_inventario_total() -> float:
    """Calcula el valor total del inventario actual con ganancia."""
    total_preciso = Decimal("0.00")
    productos = Producto.query.all()

    for p in productos:
        unidades = Decimal(str(p.unidades_restantes or 0))
        valor = Decimal(str(p.valor_unitario or 0))
        interes = Decimal(str(p.interes or 0))
        subtotal = unidades * valor * (Decimal("1") + interes / Decimal("100"))
        total_preciso += subtotal

    return float(total_preciso.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


# ======================================================
# 📈 ENTRADAS DE EFECTIVO (MovimientoCaja)
# ======================================================
def calcular_entradas(fecha: date) -> float:
    """Suma todas las entradas de efectivo registradas en el día."""
    start, end = day_range(fecha)
    total = db.session.query(func.coalesce(func.sum(MovimientoCaja.monto), 0)) \
        .filter(MovimientoCaja.tipo == "entrada") \
        .filter(MovimientoCaja.fecha >= start, MovimientoCaja.fecha < end) \
        .scalar() or 0.0
    return float(total)


# ======================================================
# 💸 SALIDAS DE EFECTIVO (gastos, retiros, etc.)
# ======================================================
def calcular_salidas(fecha: date) -> float:
    """Suma todas las salidas de efectivo registradas en el día."""
    start, end = day_range(fecha)
    total = db.session.query(func.coalesce(func.sum(MovimientoCaja.monto), 0)) \
        .filter(MovimientoCaja.tipo.in_(["salida", "gasto"])) \
        .filter(MovimientoCaja.fecha >= start, MovimientoCaja.fecha < end) \
        .scalar() or 0.0
    return float(total)


# ======================================================
# 💰 CAJA BASE DEL DÍA
# ======================================================
def caja_base_del_dia(fecha: date) -> float:
    """
    Devuelve la caja base del día (caja anterior + ventas + entradas - salidas).
    Es usada para calcular la liquidación diaria.
    """
    start, end = day_range(fecha)
    caja_anterior = obtener_caja_anterior(fecha)

    # 🟢 Ventas del día
    ventas = (
        db.session.query(func.coalesce(func.sum(Venta.ingreso), 0))
        .filter(Venta.fecha >= start, Venta.fecha < end)
        .scalar() or 0.0
    )

    # 💰 Entradas
    entradas = (
        db.session.query(func.coalesce(func.sum(MovimientoCaja.monto), 0))
        .filter(MovimientoCaja.tipo == "entrada")
        .filter(MovimientoCaja.fecha >= start, MovimientoCaja.fecha < end)
        .scalar() or 0.0
    )

    # 💸 Salidas + Gastos
    salidas = (
        db.session.query(func.coalesce(func.sum(MovimientoCaja.monto), 0))
        .filter(MovimientoCaja.tipo.in_(["salida", "gasto"]))
        .filter(MovimientoCaja.fecha >= start, MovimientoCaja.fecha < end)
        .scalar() or 0.0
    )

    return float(caja_anterior + ventas + entradas - salidas)


# ======================================================
# 🔁 RESETEAR VENTAS DIARIAS (según hora local Chile)
# ======================================================
def resetear_ventas_dia():
    """Reinicia las ventas diarias si cambió el día (según hora local Chile)."""
    hoy = local_date()
    cambios = 0

    for producto in Producto.query.all():
        if getattr(producto, "fecha", None) != hoy:
            producto.vendidas_dia = 0
            producto.valor_vendido_dia = 0
            producto.fecha = hoy
            cambios += 1

    if cambios > 0:
        db.session.commit()
        print(f"🔄 Ventas diarias reiniciadas para {cambios} productos ({hoy})")


# ======================================================
# ⚙️ FUNCIONES AUXILIARES
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


# ======================================================
# 🎨 CLASES CSS PARA ESTADO DE PRODUCTO
# ======================================================
def estado_class(producto):
    """Devuelve una clase CSS según el stock restante."""
    if producto.unidades_restantes <= 0:
        return "table-danger"   # 🔴 Sin stock
    elif producto.unidades_restantes <= 5:
        return "table-warning"  # 🟡 Pocas unidades
    else:
        return "table-success"  # 🟢 Disponible
